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
from OCP.TopoDS import TopoDS_Shape
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain

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


def visible_segments(out, right, up, fwd, render_px, cull=True):
    raise NotImplementedError("OCCT engine lands in Task 6")
