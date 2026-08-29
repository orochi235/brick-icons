"""THROWAWAY spike probe -- see docs/superpowers/specs/2026-08-29-occt-spike.md.

Builds an OCCT solid from the repo's own primitive recognizer, sews it, runs
exact HLR, and reports timings + curve types. Not wired into brick_icons/.
Run with the scratch venv that has cadquery-ocp, with this repo on PYTHONPATH.
"""
from __future__ import annotations
import math, os, sys, time
from pathlib import Path

import numpy as np

from OCP.gp import gp_Pnt, gp_Dir, gp_Ax1, gp_Ax2, gp_Ax3, gp_Circ, gp_Trsf, gp_Vec
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeCone
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace,
                                BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire,
                                BRepBuilderAPI_Sewing)
from OCP.BRep import BRep_Tool
from OCP.TopoDS import TopoDS, TopoDS_Shape
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_CurveType

from brick_icons import hlr, primitives

TOL = 1e-4
stats = {"uniform": 0, "sheared": 0, "kinds": {}}


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
        stats["sheared"] += 1
        return None
    stats["uniform"] += 1
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


def occt_faces(prim):
    """Exact OCCT faces for one recognized primitive, or [] if not representable."""
    k = prim.kind
    stats["kinds"][k] = stats["kinds"].get(k, 0) + 1
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
            n = float(prim.top)
            return [BRepPrimAPI_MakeCone(ax2(o, zdir, uh),
                                         (n + 1.0) * r, n * r, h, ang).Shape()]
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


def count(shape, kind):
    ex, n = TopExp_Explorer(shape, kind), 0
    while ex.More():
        n += 1
        ex.Next()
    return n


def build(part, ldraw_dir, tol=None):
    roots = hlr.default_roots(ldraw_dir)
    path = hlr._resolve_input(part, roots)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    t0 = time.time()
    hlr.flatten(path, np.eye(3), np.zeros(3), out, roots)
    t_flat = time.time() - t0

    t0 = time.time()
    sew = BRepBuilderAPI_Sewing(TOL if tol is None else tol)
    n_prim = n_tri = 0
    for prim in out["analytic"]:
        for f in occt_faces(prim):
            sew.Add(f)
            n_prim += 1
    for p in out["tri"]:
        f = tri_face(np.asarray(p, float))
        if f is not None:
            sew.Add(f)
            n_tri += 1
    sew.Perform()
    shape = sew.SewedShape()
    t_sew = time.time() - t0

    t0 = time.time()
    try:
        u = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
        u.Build()
        shape = u.Shape()
    except Exception as e:
        print(f"    unify failed: {e}")
    t_unify = time.time() - t0

    return shape, dict(flatten=t_flat, sew=t_sew, unify=t_unify,
                       prim_faces=n_prim, tri_faces=n_tri,
                       raw_tris=len(out["tri"]), analytic=len(out["analytic"]))


def view_basis_of(lat, long):
    return hlr.view_basis(lat, long)


def run_hlr(shape, lat=30.0, long=45.0, yaw_deg=0.0, pitch_deg=0.0,
            pitchx_deg=0.0):
    right0, up0, fwd0 = view_basis_of(lat, long)
    for axis, deg in (("Y", yaw_deg), ("right", pitch_deg), ("X", pitchx_deg)):
        if not deg:
            continue
        v = {"Y": (0.0, 1.0, 0.0), "X": (1.0, 0.0, 0.0),
             "right": tuple(map(float, right0))}[axis]
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        tr = gp_Trsf()
        tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*v)), math.radians(deg))
        shape = BRepBuilderAPI_Transform(shape, tr, True).Shape()
    right, up, fwd = hlr.view_basis(lat, long)
    # OCCT sets image Y = Z x X, so pick Z = right x up to land Y on `up`
    # exactly; feeding view_basis's fwd directly pitches the result 90 deg.
    zdir = np.cross(right, up)
    a = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*map(float, zdir)), gp_Dir(*map(float, -right)))
    algo = HLRBRep_Algo()
    algo.Add(shape)
    algo.Projector(HLRAlgo_Projector(a))
    t0 = time.time()
    algo.Update()
    algo.Hide()
    t_hlr = time.time() - t0
    hs = HLRBRep_HLRToShape(algo)
    res = {}
    for name, fn in (("sharp", hs.VCompound), ("smooth", hs.Rg1LineVCompound),
                     ("outline", hs.OutLineVCompound)):
        try:
            res[name] = fn()
        except Exception:
            res[name] = None
    return res, t_hlr


def curve_census(comp):
    names = {GeomAbs_CurveType.GeomAbs_Line: "line",
             GeomAbs_CurveType.GeomAbs_Circle: "circle",
             GeomAbs_CurveType.GeomAbs_Ellipse: "ellipse",
             GeomAbs_CurveType.GeomAbs_BSplineCurve: "bspline",
             GeomAbs_CurveType.GeomAbs_BezierCurve: "bezier"}
    c = {}
    if comp is None:
        return c
    ex = TopExp_Explorer(comp, TopAbs_ShapeEnum.TopAbs_EDGE)
    while ex.More():
        try:
            t = BRepAdaptor_Curve(TopoDS.Edge_s(ex.Current())).GetType()
            k = names.get(t, str(t))
        except Exception:
            k = "?"
        c[k] = c.get(k, 0) + 1
        ex.Next()
    return c


OUTDIR = "/private/tmp/claude-501/-Users-mike-src-brick-icons/af861015-c686-40de-b2de-660e57db7c9a/scratchpad/occt-out"


def main(argv):
    Path(OUTDIR).mkdir(parents=True, exist_ok=True)
    ldraw_dir = Path("vendor/ldraw")
    parts = argv or ["3001"]
    for i, part in enumerate(parts, 1):
        print(f"[{i}/{len(parts)}] {part}", flush=True)
        try:
            shape, m = build(part, ldraw_dir)
        except Exception as e:
            print(f"    BUILD FAILED: {type(e).__name__}: {e}", flush=True)
            continue
        nf = count(shape, TopAbs_ShapeEnum.TopAbs_FACE)
        nsh = count(shape, TopAbs_ShapeEnum.TopAbs_SHELL)
        nsol = count(shape, TopAbs_ShapeEnum.TopAbs_SOLID)
        valid = BRepCheck_Analyzer(shape).IsValid()
        print(f"    analytic={m['analytic']} tris={m['raw_tris']} -> "
              f"prim_faces={m['prim_faces']} tri_faces={m['tri_faces']}", flush=True)
        print(f"    sewed: faces={nf} shells={nsh} solids={nsol} valid={valid}  "
              f"flatten={m['flatten']:.2f}s sew={m['sew']:.2f}s unify={m['unify']:.2f}s",
              flush=True)
        try:
            res, t_hlr = run_hlr(shape,
                lat=float(os.environ.get('LAT', '30')),
                long=float(os.environ.get('LONG', '45')),
                pitch_deg=float(os.environ.get('PITCH', '0')),
                pitchx_deg=float(os.environ.get('PITCHX', '0')))
            for name in ("sharp", "smooth", "outline"):
                print(f"    hlr/{name}: {curve_census(res[name])}", flush=True)
            print(f"    HLR {t_hlr:.2f}s", flush=True)
            write_svg(res, f"{OUTDIR}/{part}.occt{os.environ.get('TAG','')}.svg")
        except Exception as e:
            print(f"    HLR FAILED: {type(e).__name__}: {e}", flush=True)
    print(f"  frames: uniform={stats['uniform']} sheared={stats['sheared']}  "
          f"kinds={stats['kinds']}", flush=True)



# --- SVG dump (appended: spike step 2 visual check) ---------------------
def _edges_2d(comp, deflection=0.05):
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    out = []
    if comp is None:
        return out
    ex = TopExp_Explorer(comp, TopAbs_ShapeEnum.TopAbs_EDGE)
    while ex.More():
        try:
            ad = BRepAdaptor_Curve(TopoDS.Edge_s(ex.Current()))
            d = GCPnts_QuasiUniformDeflection(ad, deflection)
            pts = [ad.Value(d.Parameter(i)) for i in range(1, d.NbPoints() + 1)]
            out.append([(p.X(), p.Y()) for p in pts])
        except Exception:
            pass
        ex.Next()
    return out


def write_svg(res, path, px=512, margin=12):
    layers = [("sharp", "#111", 2.0), ("outline", "#111", 2.0),
              ("smooth", "#c00", 1.2)]
    polys = {n: _edges_2d(res.get(n)) for n, _, _ in layers}
    allpts = [p for v in polys.values() for poly in v for p in poly]
    if not allpts:
        print(f"    (no edges to draw for {path})")
        return
    xs = [p[0] for p in allpts]; ys = [p[1] for p in allpts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    s = (px - 2 * margin) / max(x1 - x0, y1 - y0, 1e-9)
    def T(p):
        return ((p[0] - x0) * s + margin, (p[1] - y0) * s + margin)
    body = []
    for name, col, w in layers:
        for poly in polys[name]:
            d = " ".join(("M" if i == 0 else "L") + "%.2f,%.2f" % T(p)
                         for i, p in enumerate(poly))
            body.append(f'<path d="{d}" fill="none" stroke="{col}" '
                        f'stroke-width="{w}" stroke-linecap="round"/>')
    Path(path).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{px}" height="{px}" '
        f'viewBox="0 0 {px} {px}"><rect width="{px}" height="{px}" fill="white"/>'
        + "".join(body) + "</svg>")
    print(f"    wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
