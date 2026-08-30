"""OCCT-backed hidden-line removal. The only module that imports OCP."""
from __future__ import annotations
import math
from pathlib import Path

import numpy as np

try:
    import OCP  # noqa: F401
except ImportError as e:                      # pragma: no cover
    raise ImportError(
        "--engine occt needs the OCCT extra: pip install -e '.[occt]'"
    ) from e

from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Circ
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeCone
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace,
                                BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire,
                                BRepBuilderAPI_Sewing)
from OCP.TopoDS import TopoDS_Shape, TopoDS
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_CurveType
from OCP.GCPnts import GCPnts_QuasiUniformDeflection

from . import hlr

TOL = 1e-4


def frame(prim):
    """(origin, u_hat, a_hat, v_hat, radius, height, right_handed) or None if sheared."""
    U, A, V = prim.R[:, 0], prim.R[:, 1], prim.R[:, 2]
    ru, rv, h = np.linalg.norm(U), np.linalg.norm(V), np.linalg.norm(A)
    if min(ru, rv, h) < 1e-9:
        return None
    uh, vh, ah = U / ru, V / rv, A / h
    orth = (abs(uh @ ah) < 1e-6 and abs(vh @ ah) < 1e-6 and abs(uh @ vh) < 1e-6)
    uniform = abs(ru - rv) < 1e-6 * max(ru, rv)
    if not (orth and uniform):
        return None
    rh = float(np.cross(uh, vh) @ ah) > 0
    return prim.t, uh, ah, vh, ru, h, rh


def ax2(origin, zdir, xdir):
    return gp_Ax2(gp_Pnt(*map(float, origin)), gp_Dir(*map(float, zdir)),
                  gp_Dir(*map(float, xdir)))


def sector_rad(prim):
    return math.radians(min(prim.sector, 360.0))


def sector_face(origin, ah, uh, r_in, r_out, ang):
    """Planar disc/ring sector face bounded by two arcs and two radial lines."""
    a = ax2(origin, ah, uh)
    c_out = gp_Circ(a, r_out)
    eo = BRepBuilderAPI_MakeEdge(c_out, 0.0, ang).Edge()
    def pt(r, th):
        d = np.array(origin, float) + r * (math.cos(th) * np.array(uh, float)
                                           + math.sin(th) * np.cross(np.array(ah, float), np.array(uh, float)))
        return gp_Pnt(*map(float, d))
    w = BRepBuilderAPI_MakeWire(eo)
    if r_in > 1e-9:
        c_in = gp_Circ(a, r_in)
        ei = BRepBuilderAPI_MakeEdge(c_in, 0.0, ang).Edge()
        w.Add(BRepBuilderAPI_MakeEdge(pt(r_out, ang), pt(r_in, ang)).Edge())
        w.Add(ei)
        w.Add(BRepBuilderAPI_MakeEdge(pt(r_in, 0.0), pt(r_out, 0.0)).Edge())
    else:
        ctr = gp_Pnt(*map(float, origin))
        w.Add(BRepBuilderAPI_MakeEdge(pt(r_out, ang), ctr).Edge())
        w.Add(BRepBuilderAPI_MakeEdge(ctr, pt(r_out, 0.0)).Edge())
    return BRepBuilderAPI_MakeFace(w.Wire(), True).Face()


def annulus_face(origin, ah, uh, r_in, r_out, ang):
    """Planar disc/ring face; full ring, or a bounded sector."""
    if ang < 2 * math.pi - 1e-9:
        return sector_face(origin, ah, uh, r_in, r_out, ang)
    a = ax2(origin, ah, uh)
    outer = BRepBuilderAPI_MakeEdge(gp_Circ(a, r_out)).Edge()
    wo = BRepBuilderAPI_MakeWire(outer).Wire()
    mf = BRepBuilderAPI_MakeFace(wo, True)
    if r_in > 1e-9:
        inner = BRepBuilderAPI_MakeEdge(gp_Circ(a, r_in)).Edge()
        wi = BRepBuilderAPI_MakeWire(inner).Wire()
        mf.Add(wi.Reversed())
    return mf.Face()


def _cone_radii(r, n):
    """(r_base, r_top) for a conN primitive: N+1 tapering to N, scaled by r."""
    return (n + 1.0) * r, n * r


def cone_radii(prim):
    f = frame(prim)
    r = f[4] if f is not None else np.linalg.norm(prim.R[:, 0])
    return _cone_radii(r, float(prim.top))


def occt_faces(prim):
    """Exact OCCT faces for one recognized primitive, or [] if not representable."""
    k = prim.kind
    if k == "edge":
        return []                      # stroke-only, contributes no surface
    f = frame(prim)
    if f is None:
        return []
    o, uh, ah, vh, r, h, rh = f
    ang = sector_rad(prim)
    # The axis sets the EXTRUSION direction, so it must always be +ah --
    # negating it to fix a left-handed sector sweep builds the cone/cylinder
    # backwards off its base plane, which reads as a gap between subparts.
    # Handle the sweep by starting the x-direction at -ang instead.
    zdir = ah
    if not rh:
        uh = math.cos(-ang) * np.asarray(uh, float) + math.sin(-ang) * np.cross(ah, uh)
    try:
        if k == "cyli":
            return [BRepPrimAPI_MakeCylinder(ax2(o, zdir, uh), r, h, ang).Shape()]
        if k == "con":
            # conN: radius N+1 at the base tapering to N at the top, both in
            # primitive units, so the matrix scale r multiplies BOTH.
            r_base, r_top = _cone_radii(r, float(prim.top))
            return [BRepPrimAPI_MakeCone(ax2(o, zdir, uh),
                                         r_base, r_top, h, ang).Shape()]
        if k == "disc":
            return [annulus_face(o, zdir, uh, 0.0, r, ang)]
        if k == "ring":
            # ringN: inner radius N, outer N+1, both scaled by r.
            n = float(prim.inner)
            return [annulus_face(o, zdir, uh, n * r, (n + 1.0) * r, ang)]
    except Exception:
        return []
    return []


def tri_face(p):
    poly = BRepBuilderAPI_MakePolygon()
    for row in p:
        poly.Add(gp_Pnt(float(row[0]), float(row[1]), float(row[2])))
    poly.Close()
    if not poly.IsDone():
        return None
    try:
        mf = BRepBuilderAPI_MakeFace(poly.Wire(), True)
        return mf.Face() if mf.IsDone() else None
    except Exception:
        return None


def flatten_part(part: str, ldraw_dir) -> dict:
    roots = hlr.default_roots(Path(ldraw_dir))
    path = hlr._resolve_input(part, roots)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(path, np.eye(3), np.zeros(3), out, roots)
    return out


def build_shape(out: dict) -> TopoDS_Shape:
    sew = BRepBuilderAPI_Sewing(TOL)
    for prim in out["analytic"]:
        for f in occt_faces(prim):
            sew.Add(f)
    for p in out["tri"]:
        f = tri_face(np.asarray(p, float))
        if f is not None:
            sew.Add(f)
    sew.Perform()
    shape = sew.SewedShape()

    try:
        u = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
        u.Build()
        shape = u.Shape()
    except Exception:
        pass
    return shape


def count_faces(shape: TopoDS_Shape) -> int:
    ex, n = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE), 0
    while ex.More():
        n += 1
        ex.Next()
    return n


def projector_axes(right, up):
    """Settled empirically (task-6 fix round 1), not by re-deriving the
    algebra: Z = +cross(right, up), X = +right, with the resulting HLR
    edge Y negated in edges_to_ops. Three prior derivations -- the frame's
    own docstring (Z = -cross(right, up) = forward), the numeric box-corner
    check ((1,2,3) -> (2.8284271, 1.0249440) under both hlr.project and this
    formula), and a from-scratch review of both -- each verified the 2D
    screen-mapping identity image-Y = Z x X = -up and were each still wrong,
    because that identity holds for any of the 8 sign/negation combinations
    of (Z, X, screen-Y) and says nothing about which side of Z the HLR
    algorithm treats as the visible one. Z = forward (this frame's original
    choice) put the virtual eye on the FAR side of the part, so HLRBRep_Algo
    drew the hidden underside (anti-stud tubes visible, no studs on top) --
    confirmed by rendering part 3001 and comparing to the naive engine by
    eye, not by algebra.

    All 8 configurations were rendered for real (part 4070, the naive engine
    as ground truth) and scored by RMSE against the naive render, direct vs.
    mirrored both ways -- see task-6-report.md for the full table. Direct
    RMSE for this configuration is 37.95 against mirrors of 61-63 (a >20-point
    margin); every other configuration's direct RMSE lands in the 45-88
    range indistinguishable from its own mirrors. This one wins by a lot;
    nothing else is close.
    """
    return np.cross(right, up), np.asarray(right, float)


def hlr_edges(shape, right, up, fwd, cull=True):
    """Exact hidden-line removal, keyed 'sharp'/'smooth'/'outline' -> a
    TopoDS_Compound or None. With cull=False also '..._hidden' compounds."""
    z, x = projector_axes(right, up)
    a = ax2((0.0, 0.0, 0.0), z, x)
    algo = HLRBRep_Algo()
    algo.Add(shape)
    algo.Projector(HLRAlgo_Projector(a))
    algo.Update()
    algo.Hide()
    hs = HLRBRep_HLRToShape(algo)
    wanted = [("sharp", hs.VCompound), ("smooth", hs.Rg1LineVCompound),
              ("outline", hs.OutLineVCompound)]
    if not cull:
        wanted += [("sharp_hidden", hs.HCompound),
                   ("smooth_hidden", hs.Rg1LineHCompound),
                   ("outline_hidden", hs.OutLineHCompound)]
    got = {}
    for name, fn in wanted:
        try:
            shp = fn()
            got[name] = None if shp is None or shp.IsNull() else shp
        except Exception:
            got[name] = None
    return got


def _edge_ops(edge, kind):
    """Segment ops for one edge, reading its analytic curve type rather than
    discretizing -- HLR hands back real circles and ellipses to read off.

    OCCT's FirstParameter/LastParameter are radians; every downstream
    consumer of an 'arc' op (trace._arc_to_svg, process.draw_segments, and
    the naive engine's own arc emission in hlr.fit_ellipses) takes t0/t1 in
    DEGREES. Left unconverted, a full circle (0..2*pi radians) reads as a
    ~6-degree sliver -- the "broken partial arc" symptom (task-6 fix round
    2): stud rims came back as tiny chevrons, not because HLR sub-divided
    them, but because the sweep the SVG/raster path drew was 6 degrees wide
    instead of 360."""
    c = BRepAdaptor_Curve(edge)
    t0, t1 = c.FirstParameter(), c.LastParameter()
    t = c.GetType()
    if t == GeomAbs_CurveType.GeomAbs_Line:
        p, q = c.Value(t0), c.Value(t1)
        return [("line", p.X(), p.Y(), q.X(), q.Y(), kind)]
    if t == GeomAbs_CurveType.GeomAbs_Circle:
        g = c.Circle()
        r_maj = r_min = g.Radius()
    elif t == GeomAbs_CurveType.GeomAbs_Ellipse:
        g = c.Ellipse()
        r_maj, r_min = g.MajorRadius(), g.MinorRadius()
    else:
        d = GCPnts_QuasiUniformDeflection(c, 0.05)
        pts = [c.Value(d.Parameter(i + 1)) for i in range(d.NbPoints())]
        return [("line", a.X(), a.Y(), b.X(), b.Y(), kind)
                for a, b in zip(pts, pts[1:])]
    ctr = g.Location()
    ax = g.Position()
    u, v = ax.XDirection(), ax.YDirection()
    return [("arc", ctr.X(), ctr.Y(),
             u.X() * r_maj, u.Y() * r_maj, v.X() * r_min, v.Y() * r_min,
             math.degrees(t0), math.degrees(t1), kind)]


def _negate_y(ops):
    """The winning configuration (see projector_axes) needs HLR's raw Y
    negated to match hlr.project's screen convention -- settled by the same
    8-way empirical sweep, not re-derived."""
    out = []
    for op in ops:
        if op[0] == "line":
            _, x1, y1, x2, y2, k = op
            out.append(("line", x1, -y1, x2, -y2, k))
        else:
            _, cx, cy, ux, uy, vx, vy, t0, t1, k = op
            out.append(("arc", cx, -cy, ux, -uy, vx, -vy, t0, t1, k))
    return out


def edges_to_ops(compounds):
    """Segment ops for every edge in `compounds` (as returned by hlr_edges),
    keeping kind='sil' for anything from an 'outline*' compound."""
    ops = []
    for name, comp in compounds.items():
        if comp is None:
            continue
        kind = "sil" if name.startswith("outline") else "line"
        ex = TopExp_Explorer(comp, TopAbs_ShapeEnum.TopAbs_EDGE)
        while ex.More():
            ops += _edge_ops(TopoDS.Edge_s(ex.Current()), kind)
            ex.Next()
    return _negate_y(ops)


def visible_segments(out, right, up, fwd, render_px, cull=True):
    from .hlr import VisResult, _ops_bbox
    shape = build_shape(out)
    ops = edges_to_ops(hlr_edges(shape, right, up, fwd, cull=cull))
    if not ops:
        raise RuntimeError("OCCT engine produced no edges")
    bbox = _ops_bbox(ops)
    span = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) or 1.0
    s = (render_px - 20) / span
    return VisResult(ops, bbox, s, faces=(), analytic=())
