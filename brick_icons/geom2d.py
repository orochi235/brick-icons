"""Robust 2-D polygon booleans for fill fragments (shapely/GEOS isolated here).

Used by shade.fill_ops to (a) union smooth-group / coplanar facet polygons into
one region per surface and (b) clip each face to its visible fragment. All
coordinates are output-canvas px. Any GEOS failure degrades to an empty/original
geometry — a degenerate sliver must never kill a render.
"""
from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import Polygon

GRID = 1e-3            # set_precision snap grid, px


def _only_area(g):
    """Keep only polygonal content (make_valid can emit lines/points)."""
    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    if hasattr(g, "geoms"):
        polys = [x for x in g.geoms if x.geom_type in ("Polygon", "MultiPolygon")]
        return shapely.union_all(polys) if polys else Polygon()
    return Polygon()


def to_geom(poly, holes=None):
    """ndarray ring (+ optional hole rings) -> cleaned shapely polygon."""
    try:
        p = np.asarray(poly, float)
        if len(p) < 3:
            return Polygon()
        g = Polygon(p, [np.asarray(h, float) for h in (holes or []) if len(h) >= 3])
        g = shapely.set_precision(g, GRID)
        if not g.is_valid:
            g = shapely.make_valid(g)
        return _only_area(g)
    except Exception:
        return Polygon()


def union(a, b):
    try:
        return _only_area(shapely.union(a, b))
    except Exception:
        return a


def union_all(geoms):
    gs = [g for g in geoms if g is not None and not g.is_empty]
    if not gs:
        return Polygon()
    try:
        return _only_area(shapely.union_all(gs))
    except Exception:
        return gs[0]


def difference(a, b):
    try:
        return _only_area(shapely.difference(a, b))
    except Exception:
        return a


def area(g):
    return 0.0 if g is None else float(g.area)


def path_d(g):
    """Polygon/MultiPolygon -> one SVG path 'd' (one subpath per ring).
    Pair with fill-rule="evenodd" so interior rings render as holes."""
    if g is None or g.is_empty:
        return ""
    polys = list(getattr(g, "geoms", [g]))
    cmds = []
    for p in polys:
        if p.geom_type != "Polygon" or p.is_empty:
            continue
        for ring in [p.exterior, *p.interiors]:
            pts = list(ring.coords)[:-1]
            if len(pts) < 3:
                continue
            cmds.append("M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts) + " Z")
    return " ".join(cmds)
