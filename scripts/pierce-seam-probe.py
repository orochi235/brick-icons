#!/usr/bin/env python3
"""Every seam `occt._pierce_seams` keeps, and how far it is from the plane's
own material.

    .venv/bin/python scripts/pierce-seam-probe.py 35480 67811 3626bpsk

The pass keeps a curved-curved seam that lies in the PLANE of some planar
face. A plane is unbounded and a face is not, so a seam can match a plane
whose material is nowhere near it -- which is the shape of the 67811 and
3626bpsk regressions. `gap` is the distance from the seam to the nearest face
on the plane it matched: 0 means the seam runs along that face's own boundary,
which is what a bore through a plate looks like.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import config, hlr, occt  # noqa: E402
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface  # noqa: E402
from OCP.BRepExtrema import BRepExtrema_DistShapeShape  # noqa: E402
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType  # noqa: E402
from OCP.TopAbs import TopAbs_ShapeEnum  # noqa: E402
from OCP.TopExp import TopExp  # noqa: E402
from OCP.TopoDS import TopoDS  # noqa: E402
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape  # noqa: E402


def geometry(part: str, ldraw_dir: Path) -> dict:
    roots = hlr.default_roots(ldraw_dir)
    path = hlr._resolve_input(part, roots)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    out["printed"] = hlr._is_printed(path)
    hlr.flatten(path, np.eye(3), np.zeros(3), out, roots)
    if out["tri"]:
        fixed = hlr.repair.repaired_tris(np.array(out["tri"]), out["tri_meta"],
                                         hlr.MESH_CACHE_DIR)
        out["tri"] = list(fixed)
        out["tri_colors"] = [m["color"] for m in out["tri_meta"]]
    out["fit_arcs"], out["2"] = hlr.arcfit.fit_edge_arcs(out["2"], out["5"])
    return out


def plane_of(face):
    ax = BRepAdaptor_Surface(face).Plane().Axis()
    d, p = ax.Direction(), ax.Location()
    n = np.array([d.X(), d.Y(), d.Z()], float)
    off = float(n @ np.array([p.X(), p.Y(), p.Z()], float))
    if off < 0 or (off == 0 and n[0] < 0):
        n, off = -n, -off
    return n, off


def report(part: str, ldraw_dir: Path) -> None:
    out = geometry(part, ldraw_dir)
    shape = occt.build_shape(out)
    planes = occt._planar_planes(shape)
    faces = list(occt._faces_of_type(shape, GeomAbs_SurfaceType.GeomAbs_Plane))
    by_plane: dict[tuple, list] = {}
    for f in faces:
        try:
            n, off = plane_of(f)
        except Exception:
            continue
        by_plane.setdefault(occt_key(n, off), []).append(f)

    amap = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_ShapeEnum.TopAbs_EDGE,
                                   TopAbs_ShapeEnum.TopAbs_FACE, amap)
    print(f"== {part}: {len(faces)} planar faces, {len(planes)} planes")
    kept = 0
    for i in range(1, amap.Extent() + 1):
        fl = amap.FindFromIndex(i)
        if fl.Size() != 2:
            continue
        fa, fb = fl.First(), fl.Last()
        if fa.IsSame(fb):
            continue
        try:
            kinds = [BRepAdaptor_Surface(TopoDS.Face_s(f)).GetType()
                     for f in (fa, fb)]
        except Exception:
            continue
        if any(k == GeomAbs_SurfaceType.GeomAbs_Plane for k in kinds):
            continue
        edge = TopoDS.Edge_s(amap.FindKey(i))
        try:
            c = BRepAdaptor_Curve(edge)
            if c.GetType() == GeomAbs_CurveType.GeomAbs_Line:
                continue
            t0, t1 = c.FirstParameter(), c.LastParameter()
            pts = np.array([[(v := c.Value(t0 + (t1 - t0) * k / 4.0)).X(),
                             v.Y(), v.Z()] for k in range(5)], float)
        except Exception:
            continue
        for n, off in planes:
            if np.abs(pts @ n - off).max() > occt.PIERCE_TOL:
                continue
            kept += 1
            mates = by_plane.get(occt_key(n, off), [])
            gap = min((dist(edge, f) for f in mates), default=float("inf"))
            ctr = pts.mean(0)
            print(f"  seam {kept:3d}  n=({n[0]:5.2f},{n[1]:5.2f},{n[2]:5.2f})"
                  f" off={off:8.3f}  ctr=({ctr[0]:7.2f},{ctr[1]:7.2f},"
                  f"{ctr[2]:7.2f})  faces_on_plane={len(mates):3d}"
                  f"  gap={gap:8.3f}")
            break
    print(f"  {kept} seams kept")


def occt_key(n, off):
    return (round(n[0], 5), round(n[1], 5), round(n[2], 5), round(off, 4))


def dist(a, b) -> float:
    d = BRepExtrema_DistShapeShape(a, b)
    d.Perform()
    return float(d.Value()) if d.IsDone() else float("inf")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    args = ap.parse_args()
    ldraw = config.load_config().ldraw_dir
    for p in args.parts:
        report(p, ldraw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
