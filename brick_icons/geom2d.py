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
    point(t) = c + cos t*u + sin t*v. Drops degenerate (edge-on) ellipses.
    An optional 7th element overrides MAX_STEP (degrees) for that candidate:
    fitted hand-faceted rounds legitimately sweep ~45 deg per edge."""
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
                      "phi": math.degrees(math.atan2(U_[1, 0], U_[0, 0])),
                      "step": math.radians(e[6]) if len(e) > 6 else MAX_STEP})
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
            if 1e-9 < abs(dt) <= cand["step"]:
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


def region(ring):
    """Possibly SELF-INTERSECTING ring -> its full enclosed area (every lobe
    positive). to_geom is wrong for these: set_precision on an invalid
    polygon empties it; here make_valid resolves the crossings first."""
    try:
        p = np.asarray(ring, float)
        if len(p) < 3:
            return Polygon()
        g = shapely.make_valid(Polygon(p))
        return _only_area(shapely.set_precision(g, GRID))
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


def opened(g, r):
    """Morphological opening (erode then dilate by r), snapped back onto the
    precision grid. Buffer output is off-grid; mixing it into booleans with
    grid-snapped pipeline geometry raises topology errors (which the
    forgiving wrappers above would silently turn into wrong results)."""
    try:
        o = shapely.set_precision(g.buffer(-r).buffer(r), GRID)
        if not o.is_valid:
            o = shapely.make_valid(o)
        return _only_area(o)
    except Exception:
        return g


def intersection(a, b):
    try:
        if not a.intersects(b):
            return Polygon()
        return _only_area(shapely.intersection(a, b))
    except Exception:
        return Polygon()


def area(g):
    return 0.0 if g is None else float(g.area)


def arc_regions(segs):
    """Circular-segment polygons (arc + closing chord) of the drawn arc ops
    in a segment list. Face polygons follow the chords, but drawn arcs
    (fitted rounds) legitimately bulge past them by their sagitta — union
    these regions into the silhouette wherever it feeds strokes (clip,
    contour) so an arc is never flattened."""
    out = []
    for op in segs:
        if len(op) == 5 or op[0] == "line":
            continue
        _, cx, cy, ux, uy, vx, vy, t0, t1, _ = op
        ts = np.radians(np.linspace(t0, t1, max(8, int(abs(t1 - t0) / 5) + 2)))
        ring = np.stack([cx + np.cos(ts) * ux + np.sin(ts) * vx,
                         cy + np.cos(ts) * uy + np.sin(ts) * vy], 1)
        out.append(to_geom(ring))
    return out


def densify_on_arcs(pts, cands, max_step=6.0):
    """Subdivide ring edges whose endpoints lie on a candidate ellipse,
    inserting intermediate vertices ON the true ellipse (every <=max_step
    degrees). Faceted faces ring holes and studs with coarse inscribed
    polygons (LDraw 16-gons, 22.5 deg steps) whose chords sag ~0.5 px inside
    the true circle: booleans then cut neighboring fragments along the
    chords, the off-circle intersection vertices defeat arc recovery, and
    thin slivers (a counterbore crescent's tips) get eaten. Densified, every
    contested seam lies on the circle itself."""
    pts = np.asarray(pts, float)
    if not cands or len(pts) < 3:
        return pts
    assign = _assign_edges(pts, cands, ARC_TOL)
    if not any(a is not None for a in assign):
        return pts
    out = []
    n = len(pts)
    for i in range(n):
        out.append(pts[i])
        a = assign[i]
        if a is None:
            continue
        cand, dt = cands[a[0]], a[1]
        k = int(math.ceil(abs(math.degrees(dt)) / max_step))
        if k < 2:
            continue
        d = pts[i] - cand["c"]
        m = cand["Minv"] @ d
        t0 = math.atan2(m[1], m[0])
        M = np.linalg.inv(cand["Minv"])
        for j in range(1, k):
            t = t0 + dt * j / k
            out.append(cand["c"] + M @ np.array([math.cos(t), math.sin(t)]))
    return np.array(out)


def close_slivers(g, eps=0.1):
    """Morphological closing: dissolve hairline sliver holes and seam gaps
    (face-sampling mismatches along interior rims) without moving the real
    boundary (mitre joins restore convex corners exactly)."""
    if g is None or g.is_empty:
        return g
    try:
        return _only_area(g.buffer(eps, join_style="mitre")
                          .buffer(-eps, join_style="mitre"))
    except Exception:
        return g


def contour_d(g, arcs=None, min_ring_area=0.5):
    """Silhouette contour as an SVG path 'd': the cleaned outer boundary,
    for stroking under the per-edge strokes (mitered corner joins). Unlike
    the exact fill boundaries, hairline slivers and sub-pixel rings must NOT
    survive here — stroked at full width they render as tick marks."""
    g = close_slivers(g)
    if g is None or g.is_empty:
        return ""
    return path_d(g, arcs, min_area=min_ring_area, min_ring_area=min_ring_area)


def rings(g, min_area=0.0):
    """All boundary rings (exteriors and holes) of a polygonal geometry as
    (n,2) arrays, closing vertex dropped. Feeds raster contour drawing.
    `min_area` drops rings below it (sliver holes render as tick marks)."""
    out = []
    for p in getattr(g, "geoms", [g]):
        if p.geom_type != "Polygon" or p.is_empty or p.area < min_area:
            continue
        for ring in [p.exterior, *p.interiors]:
            pts = np.asarray(ring.coords, float)[:-1]
            if len(pts) >= 3 and (not min_area or Polygon(pts).area >= min_area
                                  or ring is p.exterior):
                out.append(pts)
    return out


def buffer_d(g, dist, mitre_limit=5.0):
    """Outward-buffer a silhouette polygon and return it as an SVG path 'd'
    (pure polylines, mitered corners). Used to clip the stroke layer: the
    boundary runs exactly along the outer edge of an outline stroke, so
    round end caps get cut flush instead of poking past silhouette corners.
    Pair with clip-rule="evenodd" so holes stay open."""
    if g is None or g.is_empty:
        return ""
    try:
        b = g.buffer(dist, join_style="mitre", mitre_limit=mitre_limit)
    except Exception:
        return ""
    return path_d(_only_area(b))


def path_d(g, arcs=None, tol=ARC_TOL, min_area=0.0, min_ring_area=0.0):
    """Polygon/MultiPolygon -> one SVG path 'd' (one subpath per ring).
    Pair with fill-rule="evenodd" so interior rings render as holes.
    `arcs` (from arc_candidates) enables arc recovery: boundary runs lying
    on a candidate ellipse are emitted as elliptical arcs, not polylines.
    `min_area` culls component polygons below it (px^2): the booleans shed
    sub-pixel crumbs along shared boundaries that pass the whole-fragment
    area gate by riding along with a large part. `min_ring_area` also drops
    interior rings (holes) below it — for stroked contours, where a
    sub-pixel hole renders as a full-width tick mark."""
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
            if (min_ring_area and ring is not p.exterior
                    and Polygon(ring).area < min_ring_area):
                continue
            if arcs:
                cmds.append(_ring_d(pts, arcs, tol))
            else:
                cmds.append("M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts)
                            + " Z")
    return " ".join(cmds)
