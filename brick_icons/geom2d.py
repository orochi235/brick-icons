"""Robust 2-D polygon booleans for fill fragments (shapely/GEOS isolated here).

Used by shade.fill_ops to (a) union smooth-group / coplanar facet polygons into
one region per surface and (b) clip each face to its visible fragment. All
coordinates are output-canvas px. Any GEOS failure degrades to an empty/original
geometry — a degenerate sliver must never kill a render.
"""
from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import Polygon

GRID = 1e-3            # set_precision snap grid, px

# --- arc recovery ---------------------------------------------------------
# Face polygons sample their curves from known projected circles, so after
# the GEOS booleans boundary runs can snap back onto those ellipses and be
# emitted as true SVG arcs. Original sample vertices sit within the GRID
# snap of the exact ellipse; vertices GEOS creates at chord intersections
# (T-junctions between the 40- and 64-sample lattices of one circle) sit up
# to a chord-sag ~0.02 px off it. ARC_TOL admits both: snapping such a
# vertex onto the arc moves it ~1/40 of a stroke width — invisible — while
# genuine corners sit >=0.2 px off and stay polyline joints.
ARC_TOL = 0.05         # max vertex-to-ellipse distance, px
MAX_STEP = math.radians(15.0)   # max per-edge sweep: sampled steps are
                                # <=9 deg; a longer on-circle chord is a real
                                # straight cut whose ends merely touch
MIN_AXIS = 0.75        # px; flatter ellipses are visually straight


def arc_candidates(ellipses):
    """Prepare projected circles [(cx,cy,ux,uy,vx,vy)] for path_d recovery:
    point(t) = c + cos t*u + sin t*v. Drops degenerate (edge-on) ellipses."""
    cands = []
    for e in ellipses or []:
        c = np.array(e[:2], float)
        M = np.array([[e[2], e[4]], [e[3], e[5]]], float)   # columns u, v
        U_, S_, _ = np.linalg.svd(M)
        if S_[-1] < MIN_AXIS:
            continue
        cands.append({"c": c, "Minv": np.linalg.inv(M),
                      "det": float(M[0, 0] * M[1, 1] - M[0, 1] * M[1, 0]),
                      "rx": float(S_[0]), "ry": float(S_[1]),
                      "phi": math.degrees(math.atan2(U_[1, 0], U_[0, 0]))})
    return cands


def _vertex_angles(pts, cand, tol):
    """Ellipse param per vertex, NaN where the vertex is off the ellipse."""
    d = pts - cand["c"]
    m = d @ cand["Minv"].T
    r = np.hypot(m[:, 0], m[:, 1])
    # |r-1| is unit-circle space; ||p-c||/r converts it to px radially
    dist = np.abs(r - 1.0) * np.hypot(d[:, 0], d[:, 1]) / np.maximum(r, 1e-9)
    t = np.arctan2(m[:, 1], m[:, 0])
    t[dist > tol] = np.nan
    return t


def _assign_edges(pts, cands, tol):
    """Per ring edge i -> (cand_index, signed sweep) or None."""
    n = len(pts)
    assign = [None] * n
    for k, cand in enumerate(cands):
        t = _vertex_angles(pts, cand, tol)
        for i in range(n):
            if assign[i] is not None:
                continue
            ti, tj = t[i], t[(i + 1) % n]
            if np.isnan(ti) or np.isnan(tj):
                continue
            dt = (tj - ti + math.pi) % (2 * math.pi) - math.pi
            if 1e-9 < abs(dt) <= MAX_STEP:
                assign[i] = (k, dt)
    return assign


def _fmt(p):
    return f"{p[0]:.2f} {p[1]:.2f}"


def _arc_cmds(pts, idxs, dts, cand):
    """A-segments through ring vertices idxs (>=2 edges) on one candidate.
    Endpoints are exact ring vertices, so seams with neighboring faces and
    with plain L stretches stay watertight. Sweeps > 180 deg split at a
    mid-run vertex so every emitted arc keeps large-arc-flag 0."""
    total = sum(dts)
    sw = 1 if cand["det"] * (1 if total >= 0 else -1) > 0 else 0
    a = f'A {cand["rx"]:.2f} {cand["ry"]:.2f} {cand["phi"]:.2f} 0 {sw} '
    if abs(total) <= math.pi:
        return [a + _fmt(pts[idxs[-1]])]
    cum, split = 0.0, len(idxs) // 2
    for j, dt in enumerate(dts):
        cum += dt
        if abs(cum) >= abs(total) / 2:
            split = j + 1
            break
    split = min(max(split, 1), len(idxs) - 2)
    return [a + _fmt(pts[idxs[split]]), a + _fmt(pts[idxs[-1]])]


def _ring_d(pts, cands, tol):
    """One ring -> SVG subpath, snapping sampled runs back to true arcs."""
    n = len(pts)
    assign = _assign_edges(pts, cands, tol) if cands and n >= 3 else [None] * n

    def joined(a, b):     # consecutive edges continue the same directed arc
        return (a is not None and b is not None and a[0] == b[0]
                and (a[1] >= 0) == (b[1] >= 0))

    if assign[0] is not None and all(joined(assign[i - 1], assign[i])
                                     for i in range(n)):
        # whole ring is one closed curve: full ellipse as two half arcs
        idxs = list(range(n)) + [0]
        dts = [a[1] for a in assign]
        return ("M " + _fmt(pts[0]) + " "
                + " ".join(_arc_cmds(pts, idxs, dts, cands[assign[0][0]])) + " Z")

    start = 0
    while joined(assign[start - 1], assign[start]):
        start += 1                     # rotate so no run crosses the seam
    cmds = ["M " + _fmt(pts[start])]
    i = 0
    while i < n:
        e = (start + i) % n
        if assign[e] is None:
            cmds.append("L " + _fmt(pts[(e + 1) % n]))
            i += 1
            continue
        run = [e]
        while i + len(run) < n and joined(assign[run[-1]], assign[(run[-1] + 1) % n]):
            run.append((run[-1] + 1) % n)
        if len(run) < 2:               # lone matching edge: not worth an arc
            cmds.append("L " + _fmt(pts[(e + 1) % n]))
            i += 1
            continue
        idxs = run + [(run[-1] + 1) % n]
        cmds += _arc_cmds(pts, idxs, [assign[j][1] for j in run],
                          cands[assign[e][0]])
        i += len(run)
    return " ".join(cmds) + " Z"


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


def intersection(a, b):
    try:
        if not a.intersects(b):
            return Polygon()
        return _only_area(shapely.intersection(a, b))
    except Exception:
        return Polygon()


def area(g):
    return 0.0 if g is None else float(g.area)


def path_d(g, arcs=None, tol=ARC_TOL, min_area=0.0):
    """Polygon/MultiPolygon -> one SVG path 'd' (one subpath per ring).
    Pair with fill-rule="evenodd" so interior rings render as holes.
    `arcs` (from arc_candidates) enables arc recovery: boundary runs lying
    on a candidate ellipse are emitted as elliptical arcs, not polylines.
    `min_area` culls component polygons below it (px^2): the booleans shed
    sub-pixel crumbs along shared boundaries that pass the whole-fragment
    area gate by riding along with a large part."""
    if g is None or g.is_empty:
        return ""
    polys = list(getattr(g, "geoms", [g]))
    cmds = []
    for p in polys:
        if p.geom_type != "Polygon" or p.is_empty or p.area < min_area:
            continue
        for ring in [p.exterior, *p.interiors]:
            pts = np.asarray(ring.coords, float)[:-1]
            if len(pts) < 3:
                continue
            if arcs:
                cmds.append(_ring_d(pts, arcs, tol))
            else:
                cmds.append("M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts)
                            + " Z")
    return " ".join(cmds)
