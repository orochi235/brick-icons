"""OCCT-backed hidden-line removal. The only module that imports OCP."""
from __future__ import annotations
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

try:
    import OCP  # noqa: F401
except ImportError as e:                      # pragma: no cover
    raise ImportError(
        "--engine occt needs the OCCT extra: pip install -e '.[occt]'"
    ) from e

from OCP.gp import gp_Pnt, gp_Dir, gp_Vec, gp_Ax2, gp_Circ, gp_Elips
from OCP.BRepPrimAPI import (BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeCone,
                             BRepPrimAPI_MakePrism)
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace,
                                BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire,
                                BRepBuilderAPI_Sewing)
from OCP.TopoDS import TopoDS_Shape, TopoDS_Compound, TopoDS
from OCP.TopAbs import TopAbs_ShapeEnum, TopAbs_Orientation
from OCP.TopExp import TopExp_Explorer, TopExp
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.GeomAbs import GeomAbs_Shape
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.GeomLProp import GeomLProp_SLProps
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopLoc import TopLoc_Location
from OCP.BRepTools import BRepTools, BRepTools_WireExplorer

from . import hlr, primitives

TOL = 1e-4
ORTHO_TOL = 1e-4     # see frame(); measured noise floors are 1.2e-6 and 8.9e-6
ROUND_TOL = 1e-4


def frame(prim):
    """(origin, u_hat, a_hat, v_hat, radius_u, radius_v, height, right_handed),
    or None if sheared.

    ru != rv is an ellipse, not shear -- 50950's wall measures 68.3 x 84.9 at
    an orthogonality residual of exactly 0. Callers decide what to do with it;
    `is_round` is the test.
    """
    U, A, V = prim.R[:, 0], prim.R[:, 1], prim.R[:, 2]
    ru, rv, h = np.linalg.norm(U), np.linalg.norm(V), np.linalg.norm(A)
    if min(ru, rv, h) < 1e-9:
        return None
    uh, vh, ah = U / ru, V / rv, A / h
    # At 1e-6 this rejected 32 of 3942bp01's cones on residuals of 1.2e-6 --
    # float noise off accumulated subpart transforms, not shear. They then
    # built no face, so its wall was cracks and every band drew as a hoop.
    if not (abs(uh @ ah) < ORTHO_TOL and abs(vh @ ah) < ORTHO_TOL
            and abs(uh @ vh) < ORTHO_TOL):
        return None
    rh = float(np.cross(uh, vh) @ ah) > 0
    return prim.t, uh, ah, vh, ru, rv, h, rh


def is_round(ru, rv):
    return abs(ru - rv) < ROUND_TOL * max(ru, rv)


def ellipse_axes(o, uh, vh, ru, rv):
    """(gp_Ax2, major, minor, phase) for o + ru*cos(t)*uh + rv*sin(t)*vh.

    gp_Elips measures its parameter from the MAJOR axis and OCCT refuses a
    minor radius larger than the major, so when rv wins the frame turns a
    quarter turn and the LDraw sector angle rides along in `phase`. Taking the
    ellipse's own normal as the Z direction also makes the sweep run u -> v
    whatever the primitive's handedness, so no start-angle correction is
    needed here.
    """
    w = np.cross(np.asarray(uh, float), np.asarray(vh, float))
    if ru >= rv:
        return ax2(o, w, uh), ru, rv, 0.0
    return ax2(o, w, vh), rv, ru, -math.pi / 2


def ellipse_edge(o, uh, vh, ru, rv, ang):
    a, maj, minr, ph = ellipse_axes(o, uh, vh, ru, rv)
    el = gp_Elips(a, float(maj), float(minr))
    if ang >= 2 * math.pi - 1e-9:
        return BRepBuilderAPI_MakeEdge(el).Edge()
    return BRepBuilderAPI_MakeEdge(el, float(ph), float(ph + ang)).Edge()


def elliptic_wall(o, uh, ah, vh, ru, rv, h, ang):
    """The lateral surface of an elliptical cylinder, which no BRepPrimAPI
    maker builds -- extrude the ellipse instead."""
    v = gp_Vec(*(float(x) for x in np.asarray(ah, float) * h))
    prism = BRepPrimAPI_MakePrism(ellipse_edge(o, uh, vh, ru, rv, ang), v)
    return TopoDS.Face_s(prism.Shape())


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
        # Reversed() is typed TopoDS_Shape, which MakeFace.Add refuses; without
        # the downcast every full ring raised and occt_faces swallowed it.
        mf.Add(TopoDS.Wire_s(wi.Reversed()))
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
    o, uh, ah, vh, ru, rv, h, rh = f
    ang = sector_rad(prim)
    if not is_round(ru, rv):
        # Only cyli has a measured elliptical instance (50950). The rest would
        # be guesswork, and occt_faces returning [] is the honest answer.
        if k != "cyli":
            return []
        try:
            return [elliptic_wall(o, uh, ah, vh, ru, rv, h, ang)]
        except Exception:
            return []
    r = ru
    # The axis sets the EXTRUSION direction, so it must always be +ah --
    # negating it to fix a left-handed sector sweep builds the cone/cylinder
    # backwards off its base plane, which reads as a gap between subparts.
    # Handle the sweep by starting the x-direction at -ang instead.
    zdir = ah
    if not rh:
        uh = math.cos(-ang) * np.asarray(uh, float) + math.sin(-ang) * np.cross(ah, uh)
    try:
        # .Face() is the LATERAL surface; .Shape() would be a capped solid, and
        # LDraw's cyli/con are open tubes and skirts -- the caps are material
        # the part never had, and they occlude whatever sits inside the tube.
        if k == "cyli":
            return [BRepPrimAPI_MakeCylinder(ax2(o, zdir, uh), r, h, ang).Face()]
        if k == "con":
            # conN: radius N+1 at the base tapering to N at the top, both in
            # primitive units, so the matrix scale r multiplies BOTH.
            r_base, r_top = _cone_radii(r, float(prim.top))
            return [BRepPrimAPI_MakeCone(ax2(o, zdir, uh),
                                         r_base, r_top, h, ang).Face()]
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
    if out["tri"]:
        from . import repair
        fixed = repair.repaired_tris(np.array(out["tri"]), out["tri_meta"],
                                     hlr.MESH_CACHE_DIR)
        out["tri"] = list(fixed)
    return out


def _edges_of(comp):
    ex = TopExp_Explorer(comp, TopAbs_ShapeEnum.TopAbs_EDGE)
    while ex.More():
        yield TopoDS.Edge_s(ex.Current())
        ex.Next()


def _compound(edges):
    b = BRep_Builder()
    comp = TopoDS_Compound()
    b.MakeCompound(comp)
    for e in edges:
        b.Add(comp, e)
    return comp


def _line_edge(a, c):
    if np.linalg.norm(np.asarray(a, float) - np.asarray(c, float)) < 1e-7:
        return None
    try:
        return BRepBuilderAPI_MakeEdge(gp_Pnt(*map(float, a)),
                                       gp_Pnt(*map(float, c))).Edge()
    except Exception:
        return None


def _curve_key(edge):
    """Identity of an edge's underlying curve, for dropping a duplicate.

    A stud rim is authored as an `edge` primitive AND arrives again as the
    junction between its cylinder and the disc above it. Fed to HLR twice, the
    two copies are hidden-line-removed independently and disagree where the
    circle grazes its own cylinder, so one draws a rear arc the other hides --
    doubled ink plus a stray sliver at every stud base.
    """
    c = BRepAdaptor_Curve(edge)
    t = c.GetType()
    if t == GeomAbs_CurveType.GeomAbs_Circle:
        g = c.Circle()
        o, ax = g.Location(), g.Axis().Direction()
        d = (ax.X(), ax.Y(), ax.Z())
        if d < (0.0, 0.0, 0.0):                # axis sign is not identity
            d = tuple(-v for v in d)
        return ("circle", round(g.Radius(), 3), tuple(round(v, 3) for v in
                (o.X(), o.Y(), o.Z())), tuple(round(v, 3) for v in d))
    a, b = c.Value(c.FirstParameter()), c.Value(c.LastParameter())
    ka = tuple(round(v, 3) for v in (a.X(), a.Y(), a.Z()))
    kb = tuple(round(v, 3) for v in (b.X(), b.Y(), b.Z()))
    return ("line",) + (ka, kb) if ka <= kb else ("line",) + (kb, ka)


def dedupe_edges(edges):
    """Edges with one entry per distinct curve, first occurrence winning."""
    seen, out = set(), []
    for e in edges:
        try:
            k = _curve_key(e)
        except Exception:
            out.append(e)
            continue
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def authored_edges(out: dict, right, up):
    """(hard, conditional) compounds of the edges LDraw actually states.

    LDraw states its edges rather than implying them, so these are the only
    candidates to draw: type-2 lines and the `edge` primitives that carry a
    rim circle are unconditional, and type-5 conditional lines are drawn only
    where their two control points fall on the same side in screen space.
    Everything else in a mesh interior is tessellation.

    The conditional half is what a tessellated curved surface has instead of a
    silhouette: HLR's outline compound reports the true silhouette of an
    analytic surface, but a dish that arrives as triangles has none, and its
    profile is a facet boundary that only a condline distinguishes from the
    tessellation beside it.
    """
    hard, cond = [], []
    for e in out.get("2", ()):
        seg = np.asarray(e, float)
        ed = _line_edge(seg[0], seg[1])
        if ed is not None:
            hard.append(ed)
    for prim in out["analytic"]:
        if prim.kind != "edge":
            continue
        f = frame(prim)
        if f is None:
            continue
        o, uh, ah, vh, ru, rv, _h, _rh = f
        ang = sector_rad(prim)
        try:
            if not is_round(ru, rv):
                hard.append(ellipse_edge(o, uh, vh, ru, rv, ang))
                continue
            circ = gp_Circ(ax2(o, ah, uh), float(ru))
            hard.append(BRepBuilderAPI_MakeEdge(circ).Edge()
                        if ang >= 2 * math.pi - 1e-9
                        else BRepBuilderAPI_MakeEdge(circ, 0.0, ang).Edge())
        except Exception:
            pass
    for q in out.get("5", ()):
        pts = np.asarray(q, float)
        sx, sy, _ = hlr.project(pts, right, up, np.zeros(3))
        p1, p2 = np.array([sx[0], sy[0]]), np.array([sx[1], sy[1]])
        if not hlr.same_side(p1, p2, np.array([sx[2], sy[2]]),
                             np.array([sx[3], sy[3]])):
            continue
        ed = _line_edge(pts[0], pts[1])
        if ed is not None:
            cond.append(ed)
    return _compound(hard), _compound(cond)


CURVED = (GeomAbs_SurfaceType.GeomAbs_Cylinder, GeomAbs_SurfaceType.GeomAbs_Cone,
          GeomAbs_SurfaceType.GeomAbs_Sphere, GeomAbs_SurfaceType.GeomAbs_Torus)


TANGENT_DEG = 30.0     # measured gap is 12 to 60; see analytic_creases


def _face_normal(face, edge):
    try:
        c = BRepAdaptor_Curve(edge)
        pt = c.Value((c.FirstParameter() + c.LastParameter()) / 2.0)
        surf = BRep_Tool.Surface_s(TopoDS.Face_s(face))
        proj = GeomAPI_ProjectPointOnSurf(pt, surf)
        if proj.NbPoints() < 1:
            return None
        u, v = proj.LowerDistanceParameters()
        props = GeomLProp_SLProps(surf, u, v, 1, 1e-6)
        if not props.IsNormalDefined():
            return None
        n = props.Normal()
        return np.array([n.X(), n.Y(), n.Z()])
    except Exception:
        return None


def analytic_creases(shape: TopoDS_Shape, out: dict) -> TopoDS_Shape:
    """Junctions of exact curved surfaces that are not tangent -- a dish's
    outer rim, a cone's base. LDraw authors neither as an edge.

    A dihedral test is safe HERE and nowhere else, because the population is
    junctions between exact surfaces rather than facets of a tessellation.
    Measured over 4740, 3942bp01, 4589 and 3941, every band seam of a smooth
    wall lands at 0-12 degrees and every real edge at 60-90, with nothing in
    between; TANGENT_DEG sits in that empty gap. Re-measure with
    scripts/measure-crease-angles.py before moving it. Applying the same test
    to triangles instead would draw the whole tessellation, which is the
    explosion this engine exists to avoid -- and they cannot reach here, since
    both their faces are planes.

    A one-face edge is NOT a crease. It is a sewing crack, and 3942bp01's 120
    of them drew as 120 hoops. Accepting them was motivated only by a printed
    dish whose decoration triangles never stitched to the band below, which is
    the decal problem rather than this one.
    """
    amap = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_ShapeEnum.TopAbs_EDGE,
                                   TopAbs_ShapeEnum.TopAbs_FACE, amap)
    cos_tol = math.cos(math.radians(TANGENT_DEG))
    keep = []
    for i in range(1, amap.Extent() + 1):
        faces = list(amap.FindFromIndex(i))
        if len(faces) != 2:
            continue          # a crack has no junction; see the docstring
        if faces[0].IsSame(faces[1]):
            continue          # a closed surface's parametric seam, not a crease
        try:
            kinds = [BRepAdaptor_Surface(TopoDS.Face_s(f)).GetType()
                     for f in faces]
        except Exception:
            continue
        if not any(k in CURVED for k in kinds):
            continue
        edge = TopoDS.Edge_s(amap.FindKey(i))
        a, b = _face_normal(faces[0], edge), _face_normal(faces[1], edge)
        if a is None or b is None:
            continue
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na < 1e-9 or nb < 1e-9:
            continue
        if abs(float(a @ b)) / (na * nb) > cos_tol:
            continue          # the wall carries on through: not where it ends
        keep.append(edge)
    return _compound(keep)


def build_shape(out: dict) -> TopoDS_Shape:
    """The sewn faces. They exist to occlude; their boundaries are not drawn
    -- see authored_edges."""
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


MATCH_TOL = 1e-3       # 2D LDU; a fragment lies exactly on its own curve


def _screen_axes(right, up):
    """The projector's 2D frame. Pinned empirically, like projector_axes: for
    4740 the 3D centre (0,-4,0) lands at (0, 3.464) and HLR reports that
    ellipse at (0, 3.460). Do not re-derive."""
    z, x = projector_axes(right, up)
    return np.asarray(x, float), np.cross(z, x)


def op_projection(right, up, fwd):
    """The render camera in OP space -- the (A, -B) coordinates every op and
    face polygon of this engine is written in.

    The identity pixel fit is not a placeholder: cli.apply_affine_faces maps
    op space to the canvas afterwards, exactly as it does for the ops.
    """
    return primitives.Projection(np.asarray(right, float),
                                 np.asarray(up, float),
                                 np.asarray(fwd, float),
                                 s=1.0, cx=0.0, cy=0.0, half=0.0)


def _proj2(P, ax, ay):
    P = np.atleast_2d(np.asarray(P, float))
    return np.stack([P @ ax, P @ ay], axis=-1)


def _seg_locus(a, b, kind, ax, ay, ell=None):
    """`ell` is the projected conic a matched fragment should be RE-READ
    against while still being MATCHED as this chord -- see locus_arc."""
    p, q = _proj2([a, b], ax, ay)
    return ("seg", p, q, kind, ell)


def _ell_locus(o, u, v, ru, rv, kind, ax, ay):
    """The 2D locus of o + ru*cos(t)*u + rv*sin(t)*v. An ellipse projects to an
    ellipse, so the pair of projected semi-axes is the whole conic."""
    c = _proj2([o], ax, ay)[0]
    A = _proj2([np.asarray(o, float) + ru * np.asarray(u, float)], ax, ay)[0] - c
    B = _proj2([np.asarray(o, float) + rv * np.asarray(v, float)], ax, ay)[0] - c
    M = np.stack([A, B], axis=1)
    if abs(np.linalg.det(M)) < 1e-12:
        return None                      # edge-on: the circle projects to a line
    return ("ell", c, np.linalg.inv(M), kind)


def _on_locus(pts, locus) -> bool:
    if locus[0] == "seg":
        a, b = locus[1], locus[2]
        d = b - a
        n = np.linalg.norm(d)
        if n < 1e-12:
            return False
        w = pts - a
        cross = np.abs(w[:, 0] * d[1] - w[:, 1] * d[0]) / n
        t = (w @ d) / (n * n)
        return bool(np.all(cross < MATCH_TOL)
                    and np.all(t > -1e-3) and np.all(t < 1 + 1e-3))
    c, Minv = locus[1], locus[2]
    cs = (pts - c) @ Minv.T
    return bool(np.all(np.abs(np.linalg.norm(cs, axis=1) - 1.0) < MATCH_TOL))


def _merge_collinear(loci, tol=MATCH_TOL):
    """Collinear seg loci that abut, joined end to end.

    ShapeUpgrade_UnifySameDomain merges collinear edges across subparts, so one
    HLR fragment can span several authored segments and lie inside none of
    them -- 32062 authors its axial ridge in five pieces (three axlehol8
    sections plus the two notch spans) and gets back one edge running the whole
    axle, which the containment test in _on_locus then rejected. Merging first
    keeps that test, so nothing undeclared is still nothing drawn.
    """
    keep, groups = [], defaultdict(list)
    for l in loci:
        if l[0] != "seg" or (len(l) > 4 and l[4] is not None):
            keep.append(l)               # ell loci, and chords of a fitted arc
            continue
        p, q = l[1], l[2]
        d = q - p
        n = float(np.hypot(d[0], d[1]))
        if n < 1e-12:
            keep.append(l)
            continue
        u = d / n
        if u[0] < -1e-12 or (abs(u[0]) <= 1e-12 and u[1] < 0):
            u = -u                       # one direction per line, not two
        groups[(l[3], round(float(u[0]), 6), round(float(u[1]), 6))].append(
            (float(p @ u), float(q @ u), float(p[0] * -u[1] + p[1] * u[0]), l))
    for (kind, ux, uy), items in groups.items():
        u = np.array([ux, uy])
        nrm = np.array([-uy, ux])
        for _off, run in _by_offset(items):
            spans = sorted((min(a, b), max(a, b)) for a, b, _o, _l in run)
            lo, hi = spans[0]
            for s0, s1 in spans[1:]:
                if s0 <= hi + tol:
                    hi = max(hi, s1)
                    continue
                keep.append(("seg", lo * u + _off * nrm, hi * u + _off * nrm,
                             kind, None))
                lo, hi = s0, s1
            keep.append(("seg", lo * u + _off * nrm, hi * u + _off * nrm,
                         kind, None))
    return keep


def _by_offset(items, tol=1e-9):
    """(offset, rows) clusters of items sharing a perpendicular offset.

    Float-noise scale, NOT MATCH_TOL: truly collinear authored segments agree
    exactly, and the merged locus is rebuilt at the cluster's mean offset, so a
    loose tolerance here would shift the line by as much as the match tolerance
    and drop fragments that lay on the original. The loose tolerance belongs to
    the SPAN join, where abutting ends really do disagree.
    """
    out = []
    for it in sorted(items, key=lambda r: r[2]):
        if out and it[2] - out[-1][1][-1][2] <= tol:
            out[-1][1].append(it)
        else:
            out.append((it[2], [it]))
    return [(np.mean([r[2] for r in rows]), rows) for _o, rows in out]


def authored_loci(shape, out, right, up):
    """2D loci every drawable edge must lie on: type-2 lines (including the
    chains arcfit claimed), `edge` primitives, analytic creases, and condlines
    that read as a silhouette."""
    ax, ay = _screen_axes(right, up)
    loci = []
    for e in out.get("2", ()):
        seg = np.asarray(e, float)
        if np.linalg.norm(seg[0] - seg[1]) > 1e-7:
            loci.append(_seg_locus(seg[0], seg[1], "line", ax, ay))
    # arcfit MOVES a fitted chain out of out["2"], so its edges reach here only
    # through fit_arcs. Without this every axle-hole and gear-hub rim went
    # undrawn. Matched as the authored chords -- the shape's own fragments ARE
    # those chords and miss the fitted arc by the sagitta -- but re-read
    # against the arc, so occt stylizes the chain the way naive does instead
    # of drawing two chords meeting at a point.
    for a in out.get("fit_arcs", ()):
        P = np.asarray(a["P"], float)
        U, V = np.asarray(a["U"], float), np.asarray(a["V"], float)
        ru, rv = float(np.linalg.norm(U)), float(np.linalg.norm(V))
        ell = (_ell_locus(a["C"], U / ru, V / rv, ru, rv, "line", ax, ay)
               if min(ru, rv) > 1e-9 else None)
        for p, q in zip(P[:-1], P[1:]):
            if np.linalg.norm(p - q) > 1e-7:
                loci.append(_seg_locus(p, q, "line", ax, ay, ell))
    for prim in out["analytic"]:
        if prim.kind != "edge":
            continue
        f = frame(prim)
        if f is None:
            continue
        o, uh, ah, vh, ru, rv, _h, _rh = f
        loc = _ell_locus(o, uh, vh, float(ru), float(rv), "line", ax, ay)
        if loc is not None:
            loci.append(loc)
    for e in _edges_of(analytic_creases(shape, out)):
        try:
            a = BRepAdaptor_Curve(e)
            if a.GetType() != GeomAbs_CurveType.GeomAbs_Circle:
                continue
            g = a.Circle()
            pos = g.Position()
            o = np.array([g.Location().X(), g.Location().Y(), g.Location().Z()])
            u = np.array([pos.XDirection().X(), pos.XDirection().Y(),
                          pos.XDirection().Z()])
            v = np.array([pos.YDirection().X(), pos.YDirection().Y(),
                          pos.YDirection().Z()])
        except Exception:
            continue
        loc = _ell_locus(o, u, v, g.Radius(), g.Radius(), "line", ax, ay)
        if loc is not None:
            loci.append(loc)
    for q in out.get("5", ()):
        pts = np.asarray(q, float)
        sx, sy, _ = hlr.project(pts, right, up, np.zeros(3))
        if not hlr.same_side(np.array([sx[0], sy[0]]), np.array([sx[1], sy[1]]),
                             np.array([sx[2], sy[2]]), np.array([sx[3], sy[3]])):
            continue
        if np.linalg.norm(pts[0] - pts[1]) > 1e-7:
            loci.append(_seg_locus(pts[0], pts[1], "sil", ax, ay))
    return _merge_collinear([l for l in loci if l is not None])


def _fragment_points(edge):
    c = BRepAdaptor_Curve(edge)
    t0, t1 = c.FirstParameter(), c.LastParameter()
    ts = np.linspace(t0, t1, 5)
    out = []
    for t in ts:
        p = c.Value(float(t))
        out.append((p.X(), p.Y()))
    return np.array(out, float)


def select_authored(comp, loci):
    """(edge, kind) for every fragment lying on an authored locus.

    HLR splits an edge into visible pieces but does not reshape its curve, so a
    fragment of an authored edge still lies exactly on that edge's projection.
    Selecting from the SHAPE's own fragments is what keeps occlusion right:
    added as a separate edge-shape, a stud's base circle is coincident with its
    own cylinder and HLR breaks the tie visible, keeping a full 360-degree
    fragment where the same edge inside the shape splits into 45/45/135/135/180.
    """
    got = []
    if comp is None:
        return got
    for e in _edges_of(comp):
        try:
            pts = _fragment_points(e)
        except Exception:
            continue
        for locus in loci:
            if _on_locus(pts, locus):
                got.append((e, locus))
                break
    return got


def locus_arc(edge, locus, kind):
    """The fragment re-read as an arc of its locus ellipse, or None.

    HLR returns a projected ELLIPSE as a BSpline approximation -- only a
    projected circle comes back as a conic -- so 50950's elliptical wall drew
    as 31 straight segments and the miter where the last one met the outline
    barbed past the corner. The locus is the exact projected conic the
    fragment was matched against, so its parameters are all that is missing.
    """
    if locus[0] == "seg":
        locus = locus[4] if len(locus) > 4 else None
        if locus is None:
            return None                   # a plain authored line stays a line
    elif locus[0] != "ell":
        return None
    else:
        c = BRepAdaptor_Curve(edge)
        if c.GetType() in (GeomAbs_CurveType.GeomAbs_Line,
                           GeomAbs_CurveType.GeomAbs_Circle,
                           GeomAbs_CurveType.GeomAbs_Ellipse):
            return None                   # already exact; leave it alone
    ctr, Minv = locus[1], locus[2]
    try:
        pts = _fragment_points(edge)
        M = np.linalg.inv(Minv)           # columns are the projected semi-axes
    except Exception:
        return None
    cs = (pts - ctr) @ Minv.T
    th = np.unwrap(np.arctan2(cs[:, 1], cs[:, 0]))
    return ("arc", ctr[0], ctr[1], M[0, 0], M[1, 0], M[0, 1], M[1, 1],
            math.degrees(th[0]), math.degrees(th[-1]), kind)


def hlr_edges(shape, right, up, cull=True, edges=None, cond=None):
    """Exact hidden-line removal, keyed 'sharp'/'cond'/'outline' -> a
    TopoDS_Compound or None. With cull=False also '..._hidden' compounds.

    `edges` and `cond` are the authored-edge compounds from authored_edges.
    Given them, they are projected alongside `shape` and 'sharp'/'cond' carry
    only their visible parts, so the faces serve purely as occluders. Without
    them 'sharp' is every edge HLR calls a crease, which on a triangulated
    part is the whole tessellation -- 4740p03 at 13359 lines against naive's
    2.
    """
    z, x = projector_axes(right, up)
    a = ax2((0.0, 0.0, 0.0), z, x)
    algo = HLRBRep_Algo()
    algo.Add(shape)
    for extra in (edges, cond):
        if extra is not None:
            algo.Add(extra)
    algo.Projector(HLRAlgo_Projector(a))
    algo.Update()
    algo.Hide()
    hs = HLRBRep_HLRToShape(algo)
    wanted = [("sharp", (lambda: hs.VCompound(edges)) if edges is not None
                        else hs.VCompound),
              ("outline", hs.OutLineVCompound)]
    if cond is not None:
        wanted.append(("cond", lambda: hs.VCompound(cond)))
    if not cull:
        wanted += [("sharp_hidden", (lambda: hs.HCompound(edges))
                    if edges is not None else hs.HCompound),
                   ("outline_hidden", hs.OutLineHCompound)]
        if cond is not None:
            wanted.append(("cond_hidden", lambda: hs.HCompound(cond)))
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
    the naive engine's own arc emission in hlr.dedupe_segments) takes t0/t1 in
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


BOUNDARY_STEP_DEG = 9.0    # naive samples a wall span at 40 points; matched


def _edge_points(edge, step_deg=BOUNDARY_STEP_DEG):
    """World points along one edge, ON its own curve.

    A line contributes its endpoints. A circle or ellipse is sampled, because
    fill_ops takes a polygon -- but every sample sits exactly on the conic, so
    geom2d.arc_candidates reads the run back as the arc it came from.
    """
    c = BRepAdaptor_Curve(edge)
    t0, t1 = c.FirstParameter(), c.LastParameter()
    if c.GetType() == GeomAbs_CurveType.GeomAbs_Line:
        ts = [t0, t1]
    else:
        span = abs(math.degrees(t1 - t0))
        ts = np.linspace(t0, t1, max(2, int(math.ceil(span / step_deg)) + 1))
    P = np.array([[p.X(), p.Y(), p.Z()]
                  for p in (c.Value(float(t)) for t in ts)], float)
    if edge.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
        P = P[::-1]
    return P


def _wire_points(wire, step_deg=BOUNDARY_STEP_DEG):
    """A wire as one closed loop of world points, in wire order."""
    loop = []
    ex = BRepTools_WireExplorer(wire)
    while ex.More():
        P = _edge_points(ex.Current(), step_deg)
        ex.Next()
        if loop and np.linalg.norm(P[0] - loop[-1]) < TOL:
            P = P[1:]
        loop.extend(P)
    if len(loop) > 1 and np.linalg.norm(loop[0] - loop[-1]) < TOL:
        loop = loop[:-1]
    return np.array(loop, float)


def _limb_params(a, b, c, fwd):
    """Parameters where a curved surface turns edge-on to the camera.

    Every curved surface in this library has a normal of the form
    n(u) = cos u * a + sin u * b + c (c is zero for a cylinder, the axial term
    for a cone), so n(u).fwd = 0 is A cos u + B sin u + C = 0 -- at most two
    roots, and none when the surface never turns edge-on at all.
    """
    A, B, C = float(a @ fwd), float(b @ fwd), float(c @ fwd)
    R = math.hypot(A, B)
    if R < 1e-12:
        return []
    ratio = -C / R
    if abs(ratio) > 1.0:
        return []
    phi = math.atan2(A, B)              # A cos u + B sin u == R sin(u + phi)
    u = math.asin(max(-1.0, min(1.0, ratio)))
    return sorted({(u - phi) % (2 * math.pi),
                   (math.pi - u - phi) % (2 * math.pi)})


def _plane_face(face, proj, step_deg=BOUNDARY_STEP_DEG):
    """One planar face as a fill_ops face dict."""
    pl = BRepAdaptor_Surface(face).Plane()
    d = pl.Axis().Direction()
    n = np.array([d.X(), d.Y(), d.Z()], float)
    if face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
        n = -n
    outer = BRepTools.OuterWire_s(face)
    W = _wire_points(outer, step_deg)
    px, py, z = proj.to_px(W)
    holes = []
    ex = TopExp_Explorer(face, TopAbs_ShapeEnum.TopAbs_WIRE)
    while ex.More():
        w = TopoDS.Wire_s(ex.Current())
        ex.Next()
        if w.IsSame(outer):
            continue
        hx, hy, _ = proj.to_px(_wire_points(w, step_deg))
        holes.append(np.stack([hx, hy], 1))
    f = {"poly": np.stack([px, py], 1),
         "normal": np.array([n @ proj.right, n @ proj.up, n @ proj.fwd]),
         "depth": float(np.mean(z)), "zs": z, "kind": "occt-plane",
         # carrier plane key: fill_ops unions same-plane fragments that abut
         # without a shared edge, which is what UnifySameDomain declined to do
         "plane": (round(float(n[0]), 4), round(float(n[1]), 4),
                   round(float(n[2]), 4), round(float(n @ W[0]), 2)),
         "color": 16}
    if holes:
        f["holes"] = holes
    return f


def _faces_of_type(shape, want):
    ex = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face_s(ex.Current())
        ex.Next()
        if BRepAdaptor_Surface(face).GetType() == want:
            yield face


CURVED_SURFACES = (GeomAbs_SurfaceType.GeomAbs_Cylinder,
                   GeomAbs_SurfaceType.GeomAbs_Cone,
                   # 50950's elliptical wall: elliptic_wall extrudes an
                   # ellipse, and no BRepPrimAPI maker builds one, so it
                   # reaches HLR as an extrusion rather than a cylinder.
                   GeomAbs_SurfaceType.GeomAbs_SurfaceOfExtrusion)


def _curved_frame(face):
    """(point(u, v), normal(u), a, b, c) for any face kind in CURVED_SURFACES.

    `point` and `normal` are callables in the surface's own parameters;
    (a, b, c) are the normal's cos/sin/constant vectors for _limb_params.
    """
    s = BRepAdaptor_Surface(face)
    kind = s.GetType()
    flip = -1.0 if face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED else 1.0
    if kind == GeomAbs_SurfaceType.GeomAbs_SurfaceOfExtrusion:
        el = s.BasisCurve().Ellipse()
        pos = el.Position()
        o = np.array([pos.Location().X(), pos.Location().Y(), pos.Location().Z()])
        X = np.array([pos.XDirection().X(), pos.XDirection().Y(), pos.XDirection().Z()])
        Y = np.array([pos.YDirection().X(), pos.YDirection().Y(), pos.YDirection().Z()])
        d = s.Direction()
        D = np.array([d.X(), d.Y(), d.Z()], float)
        maj, minr = el.MajorRadius(), el.MinorRadius()

        def point(u, v):
            u = np.atleast_1d(np.asarray(u, float))
            return (o + maj * np.cos(u)[:, None] * X + minr * np.sin(u)[:, None] * Y
                    + np.asarray(v, float).reshape(-1, 1) * D)

        # n(u) = C'(u) x D with C'(u) = -maj sin u X + minr cos u Y, so the
        # normal keeps the cos/sin form _limb_params solves.
        a = flip * minr * np.cross(Y, D)
        b = flip * -maj * np.cross(X, D)
        c = np.zeros(3)

        def normal(u):
            return math.cos(u) * a + math.sin(u) * b + c

        return point, normal, a, b, c

    g = s.Cylinder() if kind == GeomAbs_SurfaceType.GeomAbs_Cylinder else s.Cone()
    pos = g.Position()
    o = np.array([pos.Location().X(), pos.Location().Y(), pos.Location().Z()])
    X = np.array([pos.XDirection().X(), pos.XDirection().Y(), pos.XDirection().Z()])
    Y = np.array([pos.YDirection().X(), pos.YDirection().Y(), pos.YDirection().Z()])
    Z = np.array([pos.Direction().X(), pos.Direction().Y(), pos.Direction().Z()])

    if kind == GeomAbs_SurfaceType.GeomAbs_Cylinder:
        r = g.Radius()

        def point(u, v):
            u = np.atleast_1d(np.asarray(u, float))
            return (o + r * (np.cos(u)[:, None] * X + np.sin(u)[:, None] * Y)
                    + np.asarray(v, float).reshape(-1, 1) * Z)

        a, b, c = flip * X, flip * Y, np.zeros(3)
    else:
        r0, semi = g.RefRadius(), g.SemiAngle()

        def point(u, v):
            u = np.atleast_1d(np.asarray(u, float))
            v = np.asarray(v, float).reshape(-1, 1)
            rad = r0 + v * math.sin(semi)
            return (o + rad * (np.cos(u)[:, None] * X + np.sin(u)[:, None] * Y)
                    + v * math.cos(semi) * Z)

        a = flip * math.cos(semi) * X
        b = flip * math.cos(semi) * Y
        c = flip * -math.sin(semi) * Z

    def normal(u):
        return math.cos(u) * a + math.sin(u) * b + c

    return point, normal, a, b, c


def _span_face(point, normal, ua, ub, v0, v1, proj, step_deg=BOUNDARY_STEP_DEG):
    """One limb-to-limb span of a curved face, as a fill_ops face dict.

    Boundary order is top arc, limb generator, bottom arc, limb generator --
    the arcs sampled on the true circle, the generators straight because they
    are straight. Same field set as primitives._wall_span_face, which is what
    shade's gradient machinery reads.
    """
    n = max(2, int(math.ceil(abs(math.degrees(ub - ua)) / step_deg)) + 1)
    us = np.linspace(ua, ub, n)
    top = point(us, v1)
    bot = point(us, v0)
    tpx, tpy, tz = proj.to_px(top)
    bpx, bpy, bz = proj.to_px(bot)
    poly = np.concatenate([np.stack([tpx, tpy], 1),
                           np.stack([bpx, bpy], 1)[::-1]], axis=0)
    zs = np.concatenate([tz, bz])

    mid = point(np.array([ua, ub]), (v0 + v1) / 2.0)
    mpx, mpy, _ = proj.to_px(mid)
    p0 = (float(mpx[0]), float(mpy[0]))
    p1 = (float(mpx[1]), float(mpy[1]))
    axis = np.array([p1[0] - p0[0], p1[1] - p0[1]])
    L2 = float(axis @ axis) or 1.0
    samples = []
    for th in np.linspace(ua, ub, 9):
        nw = normal(th)
        nw = nw / np.linalg.norm(nw)
        nv = np.array([nw @ proj.right, nw @ proj.up, nw @ proj.fwd])
        p = point(np.array([th]), (v0 + v1) / 2.0)
        ppx, ppy, _ = proj.to_px(p)
        off = ((ppx[0] - p0[0]) * axis[0] + (ppy[0] - p0[1]) * axis[1]) / L2
        samples.append((float(np.clip(off, 0.0, 1.0)), nv))

    mid_n = normal((ua + ub) / 2.0)
    mid_n = mid_n / np.linalg.norm(mid_n)
    # A span covering the whole turn never turned edge-on, so it has no near
    # and far half to choose between; it is marked interior because that is
    # the branch whose probe falls back to the UNCLAMPED surface hit. The
    # other branch falls back to an affine plane through a curved sheet, and
    # on 4740 that mis-sorts the dish into a dark crescent over its own top.
    full_turn = abs(ub - ua) > 2 * math.pi - 1e-6
    return {"poly": poly, "zs": zs, "depth": float(np.mean(zs)),
            "kind": "occt-wall", "color": 16,
            # the far half of a wall: order_faces takes its depth from the
            # occluder's FAR hit, which is what `interior` selects
            "interior": True if full_turn else bool(mid_n @ proj.fwd > 0),
            "span_deg": abs(math.degrees(ub - ua)),
            "grad_axis": (p0, p1), "grad_samples": samples}


def _unwrap(u, u0):
    """`u` lifted into [u0, u0 + 2*pi) -- UV bounds are not always [0, 2*pi)."""
    return u0 + (u - u0) % (2 * math.pi)


def _face_occluder(face):
    """The exact surface behind a curved face, as one of the occluder classes
    the naive engine already probes along a witness ray.

    They take a LOCAL frame whose columns are (U, axis, V) with unit radius
    and height 0..1, so the frame is built to carry the face's own radius and
    height. A plane gets None: its depth is affine and _plane_depth_fn
    recovers it exactly.
    """
    s = BRepAdaptor_Surface(face)
    kind = s.GetType()
    if kind == GeomAbs_SurfaceType.GeomAbs_SurfaceOfExtrusion:
        el = s.BasisCurve().Ellipse()
        pos = el.Position()
        o = np.array([pos.Location().X(), pos.Location().Y(), pos.Location().Z()])
        X = np.array([pos.XDirection().X(), pos.XDirection().Y(), pos.XDirection().Z()])
        Y = np.array([pos.YDirection().X(), pos.YDirection().Y(), pos.YDirection().Z()])
        d = s.Direction()
        D = np.array([d.X(), d.Y(), d.Z()], float)
        maj, minr = el.MajorRadius(), el.MinorRadius()
        u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
        # CylinderOccluder measures its sector from LOCAL angle 0, and R^-1
        # already carries the ellipse to a unit circle -- so the re-basing
        # rotation is applied to that circle, where it is a rotation, rather
        # than to the ellipse, where it would not be.
        A = math.cos(u0) * maj * X + math.sin(u0) * minr * Y
        C = -math.sin(u0) * maj * X + math.cos(u0) * minr * Y
        R = np.column_stack([A, (v1 - v0) * D, C])
        return primitives.CylinderOccluder(R, o + v0 * D,
                                           math.degrees(u1 - u0))
    if kind not in (GeomAbs_SurfaceType.GeomAbs_Cylinder,
                    GeomAbs_SurfaceType.GeomAbs_Cone):
        return None
    g = s.Cylinder() if kind == GeomAbs_SurfaceType.GeomAbs_Cylinder else s.Cone()
    pos = g.Position()
    o = np.array([pos.Location().X(), pos.Location().Y(), pos.Location().Z()])
    X = np.array([pos.XDirection().X(), pos.XDirection().Y(), pos.XDirection().Z()])
    Y = np.array([pos.YDirection().X(), pos.YDirection().Y(), pos.YDirection().Z()])
    Z = np.array([pos.Direction().X(), pos.Direction().Y(), pos.Direction().Z()])
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    # the occluders measure their sector from local angle 0
    Xs = math.cos(u0) * X + math.sin(u0) * Y
    Ys = -math.sin(u0) * X + math.cos(u0) * Y
    sector = math.degrees(u1 - u0)
    h = v1 - v0

    if kind == GeomAbs_SurfaceType.GeomAbs_Cylinder:
        r = g.Radius()
        R = np.column_stack([r * Xs, h * Z, r * Ys])
        return primitives.CylinderOccluder(R, o + v0 * Z, sector)

    semi = g.SemiAngle()
    rb = g.RefRadius() + v0 * math.sin(semi)
    rt = g.RefRadius() + v1 * math.sin(semi)
    if abs(rb - rt) < 1e-9:
        return None                      # degenerate cone: no exact taper
    # ConeOccluder is radius (top+1) at y=0 tapering to top at y=1
    scale = rb - rt
    top = rt / scale
    R = np.column_stack([scale * Xs, h * math.cos(semi) * Z, scale * Ys])
    return primitives.ConeOccluder(R, o + v0 * Z, sector, top)


def _shape_faces(shape):
    ex = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face_s(ex.Current())
        ex.Next()
        yield face


def _span_edges(u0, u1, limbs):
    """The u values a curved face is cut at, in order.

    A CLOSED face has no boundary at u0, so it is cut at its limbs only:
    cutting the seam as well splits the near half in two, and each piece then
    runs its own 0..1 gradient ramp with a tone break where they meet.
    """
    if u1 - u0 > 2 * math.pi - 1e-9 and limbs:
        cut = sorted(_unwrap(u, u0) for u in limbs)
        return cut + [cut[0] + 2 * math.pi]
    return sorted({u0, u1} | {u for u in (_unwrap(v, u0) for v in limbs)
                              if u0 + 1e-9 < u < u1 - 1e-9})


def _faces_for(face, proj, cull_back=True, step_deg=BOUNDARY_STEP_DEG):
    """Every fill face one OCCT face contributes: one for a plane, one per
    limb-cut span for a cylinder or cone."""
    kind = BRepAdaptor_Surface(face).GetType()
    if kind == GeomAbs_SurfaceType.GeomAbs_Plane:
        f = _plane_face(face, proj, step_deg)
        if cull_back and f["normal"][2] > -1e-6:
            return []
        return [f] if len(f["poly"]) >= 3 else []
    if kind not in CURVED_SURFACES:
        return []
    point, normal, a, b, c = _curved_frame(face)
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    edges = _span_edges(u0, u1, _limb_params(a, b, c, proj.fwd))
    out = []
    for ua, ub in zip(edges, edges[1:]):
        if ub - ua < 1e-9:
            continue
        f = _span_face(point, normal, ua, ub, v0, v1, proj, step_deg)
        if len(f["poly"]) >= 3:
            out.append(f)
    return out


def plane_faces(shape, proj, cull_back=True):
    """Every planar face of `shape`, camera-facing ones only by default.

    Culling matches faces_from_tris: winding is trusted (repair.repaired_tris
    fixed it upstream) and a face pointing away is never visible on a closed
    part. It is a cost decision, not a correctness one -- order_faces is
    O(faces^2) in witness tests and 3649 sews 846 of them.
    """
    return [f for face in _shape_faces(shape)
            for f in _faces_for(face, proj, cull_back=cull_back)
            if f["kind"] == "occt-plane"]


def curved_faces(shape, proj, step_deg=BOUNDARY_STEP_DEG):
    """Cylinder and cone faces, cut at their limbs into spans."""
    return [f for face in _shape_faces(shape)
            for f in _faces_for(face, proj, step_deg=step_deg)
            if f["kind"] == "occt-wall"]


def _boundary_conics(shape, proj):
    """Every circular or elliptical edge of `shape` as a projected conic in op
    space, for geom2d.arc_candidates.

    The drawn arc ops are already candidates, but they cover only the edges
    HLR reports as VISIBLE. A rim that is hidden still bounds a fill, and its
    boundary -- sampled at BOUNDARY_STEP_DEG on the true curve -- then re-emits
    as a fan of chords instead of one arc.
    """
    out, seen = [], set()
    ex = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_EDGE)
    while ex.More():
        edge = TopoDS.Edge_s(ex.Current())
        ex.Next()
        c = BRepAdaptor_Curve(edge)
        t = c.GetType()
        if t == GeomAbs_CurveType.GeomAbs_Circle:
            g = c.Circle()
            ru = rv = g.Radius()
        elif t == GeomAbs_CurveType.GeomAbs_Ellipse:
            g = c.Ellipse()
            ru, rv = g.MajorRadius(), g.MinorRadius()
        else:
            continue
        pos = g.Position()
        o = np.array([pos.Location().X(), pos.Location().Y(), pos.Location().Z()])
        X = np.array([pos.XDirection().X(), pos.XDirection().Y(), pos.XDirection().Z()])
        Y = np.array([pos.YDirection().X(), pos.YDirection().Y(), pos.YDirection().Z()])
        cx, cy, _ = proj.to_px(o[None, :])
        ux, uy, _ = proj.to_px((o + ru * X)[None, :])
        vx, vy, _ = proj.to_px((o + rv * Y)[None, :])
        cand = (float(cx[0]), float(cy[0]),
                float(ux[0] - cx[0]), float(uy[0] - cy[0]),
                float(vx[0] - cx[0]), float(vy[0] - cy[0]))
        key = tuple(round(v, 4) for v in cand)
        if key not in seen:
            seen.add(key)
            out.append(cand)
    return out


def ordered_faces(shape, proj):
    """Every fill face of `shape`, in paint order, each curved one depth-probed
    against its own exact surface."""
    from . import shade
    faces, own_occ = [], {}
    for face in _shape_faces(shape):
        occ = _face_occluder(face)
        for f in _faces_for(face, proj):
            faces.append(f)
            if occ is not None:
                own_occ[id(f)] = occ
    if not faces:
        return []
    zs = np.concatenate([f["zs"] for f in faces])
    zrange = float(zs.max() - zs.min()) or 1.0
    return shade.order_faces(faces, proj, 1e-3 * zrange, own_occ=own_occ)


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
    keeping kind='sil' for anything from an 'outline*' or 'cond*' compound.

    A 'smooth*' compound, if one is passed, is NOT drawn: those edges are
    interior to one surface, and where such an edge does read as an outline
    the projector already emits it in the outline compound.
    """
    ops = []
    for name, comp in compounds.items():
        if comp is None or name.startswith("smooth"):
            continue
        kind = "sil" if name.startswith(("outline", "cond")) else "line"
        ex = TopExp_Explorer(comp, TopAbs_ShapeEnum.TopAbs_EDGE)
        while ex.More():
            ops += _edge_ops(TopoDS.Edge_s(ex.Current()), kind)
            ex.Next()
    return _negate_y(ops)


def face_polys(shape, right, up, deflection):
    """Every face of `shape` as a projected polygon in op space (Y already
    negated, like the segment ops).

    Built for the silhouette contour, which needs only their union -- but the
    per-face split is what the fills slice will attribute colour and depth to,
    so it stays per-face rather than pre-unioned.
    """
    ax, ay = _screen_axes(right, up)
    BRepMesh_IncrementalMesh(shape, float(deflection), False, 0.5, True)
    polys = []
    ex = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face_s(ex.Current())
        ex.Next()
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            continue
        trsf = loc.Transformation()
        nodes = []
        for i in range(1, tri.NbNodes() + 1):
            pnt = tri.Node(i).Transformed(trsf)
            nodes.append((pnt.X(), pnt.Y(), pnt.Z()))
        P = _proj2(np.array(nodes, float), ax, ay)
        P[:, 1] *= -1.0                       # op space; see _negate_y
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            polys.append(P[[a - 1, b - 1, c - 1]])
    return polys


def _union_bbox(bbox, polys):
    """`bbox` grown to hold every projected polygon."""
    if not len(polys):
        return bbox
    P = np.vstack([np.asarray(p, float) for p in polys])
    return (min(bbox[0], P[:, 0].min()), min(bbox[1], P[:, 1].min()),
            max(bbox[2], P[:, 0].max()), max(bbox[3], P[:, 1].max()))


def visible_segments(out, right, up, render_px, cull=True, fwd=None):
    from .hlr import VisResult, _ops_bbox
    if fwd is None:
        z, _ = projector_axes(right, up)
        fwd = -z / np.linalg.norm(z)
    shape = build_shape(out)
    comps = hlr_edges(shape, right, up, cull=cull)
    loci = authored_loci(shape, out, right, up)
    picked = select_authored(comps.get("sharp"), loci)
    if not cull:
        picked += select_authored(comps.get("sharp_hidden"), loci)
    ops = []
    for edge, locus in picked:
        kind = locus[3]
        arc = locus_arc(edge, locus, kind)
        ops += [arc] if arc is not None else _edge_ops(edge, kind)
    for name in ("outline", "outline_hidden"):
        comp = comps.get(name)
        if comp is None:
            continue
        for edge in _edges_of(comp):
            ops += _edge_ops(edge, "sil")
    ops = _negate_y(ops)
    if not ops:
        raise RuntimeError("OCCT engine produced no edges")
    bbox = _ops_bbox(ops)
    span = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) or 1.0
    # Sub-pixel, or the contour under an exact arc stroke reads as a polygon
    # and its chords poke out from behind it.
    polys = face_polys(shape, right, up, span / render_px * 0.25)
    # The faces are drawn too -- they are the silhouette contour, which is this
    # engine's stand-in for fills. Framing on the edges alone cropped 4740 at
    # `front` to the 14 LDU its edges span, throwing away 26 LDU of dish that
    # only the contour draws.
    bbox = _union_bbox(bbox, polys)
    span = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) or 1.0
    s = (render_px - 20) / span
    # The drawn arcs ARE the contour's arc candidates -- an arc op's fields
    # 1..6 are already the (cx, cy, ux, uy, vx, vy) arc_candidates takes.
    # Without them contour_d traces the raw tessellation and 3005's silhouette
    # came out as 147 path commands against naive's 21.
    ells, seen = [], set()
    for op in ops:
        if op[0] != "arc":
            continue
        k = tuple(round(v, 4) for v in op[1:7])
        if k not in seen:
            seen.add(k)
            ells.append(tuple(op[1:7]))
    proj = op_projection(right, up, fwd)
    faces = ordered_faces(shape, proj)
    for cand in _boundary_conics(shape, proj):
        k = tuple(round(v, 4) for v in cand)
        if k not in seen:
            seen.add(k)
            ells.append(cand)
    return VisResult(ops, bbox, s, faces=faces, analytic=(),
                     ellipses=tuple(ells), proj=proj, sil_polys=polys)
