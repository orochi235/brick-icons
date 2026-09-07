"""Condline-guided arc fitting for hand-faceted rounds.

Modern LDraw parts often bake small rounds directly into the part file as a
few raw quads (54200's rounded top corners, rounded-corner plates, ...)
instead of referencing curve primitives, so analytic substitution never sees
them. The author's smoothness intent survives, though: the facet seams are
type-5 conditional lines. A junction vertex shared by exactly two drawn
(type-2) edges that is also an endpoint of a condline edge marks a smooth
profile chain; fitting a circle through the chain recovers the intended round
(facet vertices are authored ON the true curve). Genuinely faceted geometry
(gear teeth, stud junctions) meets at plain hard edges and is never touched.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

_Q = 4                  # endpoint quantization, decimals (world units)
TURN_MIN = 0.5          # deg; below: collinear continuation, not a curve
TURN_MAX = 60.0         # deg; above: a real corner even if condline-adjacent
FIT_RTOL = 5e-3         # circle-fit residual as a fraction of chain extent
PLANE_RTOL = 2e-3       # planarity residual as a fraction of chain extent
MIN_STEP = 10.0         # deg; finer per-edge sweeps are primitive-grade
                        # tessellation, not a hand-faceted round — leave alone
ANCHOR_ANG = 15.0       # deg; a neighbor within this of the provisional end
                        # tangent anchors the fit (tangent-chord angle test)
ANCHOR_RTOL = 0.15      # both-end tangency estimates must agree to this * r
_ANCHOR_PLANE = 0.09    # ~5 deg; anchor directions must lie in-plane
MIN_FREE_EDGES = 3      # unanchored chains need this many edges (so the
                        # residual gate has teeth) ...
SYM_RATIO = 3.0         # ... unless a 2-edge chain's sweeps are within this
                        # ratio. A fabricated fit (two chords of DIFFERENT
                        # true arcs meeting smoothly at a condline) comes out
                        # lopsided -- but so does a real round authored on a
                        # slanted plane, which projects to an ELLIPSE and so
                        # is unequal in sweep however evenly it was faceted
                        # (54200's inner corner, 1.57). Measured over the
                        # specimen list: the rounds run to 2.66, and the first
                        # fabricated fit is 32062's axle end at 4.16, which
                        # balloons its bevels into blobs.


def arc_point(arc, t_deg):
    """World point of a fitted arc at parameter t (degrees)."""
    t = math.radians(float(t_deg))
    return arc["C"] + math.cos(t) * arc["U"] + math.sin(t) * arc["V"]


def _key(p):
    return tuple(np.round(np.asarray(p, float), _Q))


def _turn_deg(edges, i, j, vk):
    """Turn angle at junction vk between edges i and j, both oriented to
    flow THROUGH the junction (0 = collinear continuation)."""
    ei, ej = edges[i], edges[j]
    di = ei[1] - ei[0]
    if _key(ei[1]) != vk:
        di = -di                        # orient di into vk
    dj = ej[1] - ej[0]
    if _key(ej[0]) != vk:
        dj = -dj                        # orient dj out of vk
    ni, nj = np.linalg.norm(di), np.linalg.norm(dj)
    if ni < 1e-12 or nj < 1e-12:
        return None
    c = float(np.dot(di, dj) / (ni * nj))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _fit_circle(P, tang=((), ())):
    """Fit a circle to ordered coplanar points P (m,3). Returns
    (C, U, V, t_deg_list, n_anchors) or None; point(t) = C + cos t*U +
    sin t*V with t_deg monotonically increasing from 0.

    The circle always passes exactly through BOTH chain terminals (center on
    their perpendicular bisector) so joins stay watertight. `tang` supplies
    candidate continuation directions (world space, outgoing) at the first
    and last vertex: a direction that is in-plane and aligned with the
    provisional end tangent anchors the fit — tangency then picks the center
    and interior vertices only validate it, so the arc meets the adjoining
    line without overshooting it. n_anchors reports how many ends anchored.
    """
    P = np.asarray(P, float)
    c0 = P.mean(axis=0)
    D = P - c0
    extent = float(np.linalg.norm(D, axis=1).max()) or 1.0
    _, S, Vt = np.linalg.svd(D, full_matrices=False)
    n = Vt[-1]
    if len(P) > 3 and float(np.abs(D @ n).max()) > PLANE_RTOL * extent:
        return None                     # not coplanar
    e1, e2 = Vt[0], Vt[1]
    xy = np.stack([D @ e1, D @ e2], axis=1)
    # Kasa fit: |p|^2 = 2 p.c + (r^2 - |c|^2), linear in (cx, cy, k)
    A = np.column_stack([2 * xy, np.ones(len(xy))])
    b = (xy ** 2).sum(axis=1)
    try:
        (kx, ky, k), *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    if k + kx * kx + ky * ky <= 0:
        return None
    # center lives on the terminals' perpendicular bisector: c(s) = M + s*nb
    a2, b2 = xy[0], xy[-1]
    ab = b2 - a2
    lab = float(np.linalg.norm(ab))
    if lab < 1e-12:
        return None
    nb = np.array([-ab[1], ab[0]]) / lab
    M = (a2 + b2) / 2.0
    s0 = float((np.array([kx, ky]) - M) @ nb)        # Kasa, projected
    r0 = float(np.hypot(*(a2 - (M + s0 * nb))))

    def end_tangent(p2, s):             # unit end tangent, pointing outward
        rad = p2 - (M + s * nb)
        tg = np.array([-rad[1], rad[0]])
        tg /= np.linalg.norm(tg) or 1.0
        other = b2 if p2 is a2 else a2
        return tg if tg @ (p2 - other) > 0 else -tg

    anchors = []
    for p2, dirs in ((a2, tang[0]), (b2, tang[1])):
        best = None
        for d3 in dirs:
            d3 = np.asarray(d3, float)
            ld = float(np.linalg.norm(d3))
            if ld < 1e-12 or abs(float(d3 @ n)) / ld > _ANCHOR_PLANE:
                continue                # out of the circle's plane
            d2 = np.array([float(d3 @ e1), float(d3 @ e2)]) / ld
            cosang = float(d2 @ end_tangent(p2, s0))
            if cosang < math.cos(math.radians(ANCHOR_ANG)):
                continue                # not a tangent continuation
            den = float(nb @ d2)
            if abs(den) < 1e-9:
                continue
            s_t = float(((p2 - M) @ d2) / den)       # tangency: (p-c).d = 0
            if best is None or cosang > best[1]:
                best = (s_t, cosang)
        if best is not None:
            anchors.append(best[0])
    if len(anchors) == 2 and abs(anchors[0] - anchors[1]) > ANCHOR_RTOL * r0:
        return None                     # ends disagree: not one true round

    def circle(s):
        c2 = M + s * nb
        r = float(np.hypot(*(a2 - c2)))
        return c2, r, float(np.abs(np.hypot(*(xy - c2).T) - r).max())

    c2, r, resid = circle(float(np.mean(anchors)) if anchors else s0)
    if resid > FIT_RTOL * extent:
        # A neighbouring CHORD lies half its own sweep off its circle's
        # tangent, so on 16-gon tessellation (11.25 deg against ANCHOR_ANG's
        # 15) it reads as a tangent continuation of whatever chain it touches.
        # When the tangency it implies throws the chain's OWN vertices off the
        # circle, it was a crease: 3941's stud truncation meets the stud
        # circle at one, and anchoring to it drove r from 6.8 to 4.7. Keep the
        # unanchored fit, and report no anchors so the lopsided-chain gate
        # below still has teeth.
        if not anchors:
            return None                 # smooth but not circular
        c2, r, resid = circle(s0)
        if resid > FIT_RTOL * extent:
            return None
        anchors = []
    C = c0 + c2[0] * e1 + c2[1] * e2
    rel = P - C
    u_hat = rel[0] / np.linalg.norm(rel[0])
    v_hat = np.cross(n, u_hat)
    t = np.degrees(np.arctan2(rel @ v_hat, rel @ u_hat))
    if len(t) > 1 and t[1] < 0:         # sweep toward the second vertex
        v_hat, t = -v_hat, -t
    t = np.where(t < -1e-9, t + 360.0, t)
    if np.any(np.diff(t) <= 0) or t[-1] >= 360.0 - 1e-9:
        return None                     # folded or full-loop chain
    return C, u_hat * r, v_hat * r, t, len(anchors)


def fit_edge_arcs(edges, condlines):
    """Replace smooth chains of type-2 edges with fitted 3-D circle arcs.

    edges: list of (2,3) world-space drawn lines; condlines: list of (4,3)
    type-5 rows (first two points are the edge). Returns (arcs, kept_edges)
    where arcs are dicts {C, U, V, t0, t1, step} — point(t) = C + cos t*U +
    sin t*V, t in degrees, step the largest per-edge sweep — and kept_edges
    are the input edges not consumed by any arc.
    """
    edges = list(edges)
    if not edges or not condlines:
        return [], edges
    cond_ends = set()
    for q in condlines:
        cond_ends.add(_key(q[0]))
        cond_ends.add(_key(q[1]))
    inc, orig = defaultdict(list), {}
    for i, e in enumerate(edges):
        for p in (e[0], e[1]):
            k = _key(p)
            inc[k].append(i)
            orig.setdefault(k, np.asarray(p, float))

    def smooth(vk):
        if vk not in cond_ends or len(inc[vk]) != 2:
            return False
        turn = _turn_deg(edges, *inc[vk], vk)
        return turn is not None and TURN_MIN <= turn <= TURN_MAX

    smooth_v = {vk for vk, es in inc.items() if len(es) == 2 and smooth(vk)}

    def pts(verts):
        return np.array([orig[k] for k in verts], float)

    def far_end(i, vk):
        p, q = _key(edges[i][0]), _key(edges[i][1])
        return q if p == vk else p

    # Seed on each smooth junction (two chords -> exact circle), then grow
    # outward one edge at a time, accepting only while the refit circle still
    # holds every vertex. Growth stops exactly where a tangent straight run
    # (or any off-circle continuation) begins, so those edges survive intact.
    consumed, arcs = set(), []
    for vk in sorted(smooth_v):
        i, j = inc[vk]
        if i in consumed or j in consumed:
            continue
        chain = [i, j]
        verts = [far_end(i, vk), vk, far_end(j, vk)]
        fit = _fit_circle(pts(verts))
        if fit is None:
            continue
        grew = True
        while grew:
            grew = False
            for end in (0, -1):
                vt = verts[end]
                if vt not in smooth_v:
                    continue
                a, b = inc[vt]
                nxt = b if a in chain else a
                if nxt in consumed or nxt in chain:
                    continue
                cand = ([far_end(nxt, vt)] + verts if end == 0
                        else verts + [far_end(nxt, vt)])
                refit = _fit_circle(pts(cand))
                if refit is None:
                    continue
                verts, fit = cand, refit
                chain = [nxt] + chain if end == 0 else chain + [nxt]
                grew = True
        # anchor candidates: outgoing directions of non-chain neighbors at
        # each terminal (the straight runs the arc must join seamlessly)
        tang = tuple([orig[far_end(i2, vt)] - orig[vt]
                      for i2 in inc[vt] if i2 not in chain and i2 not in consumed]
                     for vt in (verts[0], verts[-1]))
        fit = _fit_circle(pts(verts), tang)
        if fit is None:
            continue
        C, U, V, t, n_anchors = fit
        steps = np.diff(t)
        if (n_anchors == 0 and len(chain) < MIN_FREE_EDGES
                and float(steps.max() / steps.min()) > SYM_RATIO):
            continue                    # bare lopsided chain: fabricated
        if float(np.diff(t).min()) < MIN_STEP:
            continue
        # P/tv: the chain vertices and their arc params. Occlusion tests run
        # along this chord path — it lies ON the faceted mesh, so the arc
        # inherits exactly the chords' visibility and its slight outward
        # bulge can never escape the silhouette as a phantom curve.
        arcs.append({"C": C, "U": U, "V": V,
                     "t0": float(t[0]), "t1": float(t[-1]),
                     "step": float(np.diff(t).max()),
                     "P": pts(verts), "tv": t})
        consumed.update(chain)
    kept = [e for i, e in enumerate(edges) if i not in consumed]
    return arcs, kept


# --- silhouette arc recovery (screen space, contour only) ---------------
# The limb of a tessellated surface is not an authored edge, so nothing in
# the library declares it round and fit_edge_arcs above cannot see it: what
# reaches the drawing is a run of chords. These constants decide when such a
# run is one ellipse drawn as a polygon rather than a polygon.
SIL_TURN_MIN = 3.0      # deg; below: a straight continuation, not a curve
SIL_TURN_MAX = 24.0     # deg; the library's own round step is 22.5 (a
                        # 16-gon). Every real polygon profile in the corpus
                        # is coarser -- a 12-sided prism turns 30, an
                        # octagon 45 -- and at those steps a polygon and a
                        # faceted round are the same points on the same
                        # circle, so nothing downstream could tell them
                        # apart. The cap is the whole defense.
SIL_MIN_PTS = 6         # a conic has five degrees of freedom, so a
                        # five-point fit is exact and its residual proves
                        # nothing. Six is the first testable run.
SIL_TOL_PX = 0.25      # max vertex-to-ellipse distance, output px at a
                        # 256 icon -- the wide-pass contour gate's tolerance
SIL_SPAN_MAX = 180.0    # deg; a longer sweep is a closed rim, and those
                        # arrive as real arcs already


def _conic(P):
    """Least-squares conic through P (n,2) as (C, U, V) with point(t) =
    C + cos t*U + sin t*V, or None when the fit is not an ellipse."""
    c0 = P.mean(axis=0)
    s = float(np.abs(P - c0).max()) or 1.0
    Q = (P - c0) / s
    x, y = Q[:, 0], Q[:, 1]
    A = np.column_stack([x * x, x * y, y * y, x, y, np.ones_like(x)])
    try:
        a, b, c, d, e, f = np.linalg.svd(A)[2][-1]
    except np.linalg.LinAlgError:
        return None
    if b * b - 4 * a * c >= 0:              # parabola or hyperbola
        return None
    try:
        cx, cy = np.linalg.solve([[2 * a, b], [b, 2 * c]], [-d, -e])
    except np.linalg.LinAlgError:
        return None
    fc = a * cx * cx + b * cx * cy + c * cy * cy + d * cx + e * cy + f
    w, V = np.linalg.eigh([[a, b / 2.0], [b / 2.0, c]])
    if np.any(-fc / w <= 0):
        return None
    r = np.sqrt(-fc / w)
    return (np.array([cx, cy]) * s + c0, V[:, 0] * r[0] * s, V[:, 1] * r[1] * s)


def _params(P, C, U, V):
    """Ellipse parameter (degrees) per point, unwrapped to run monotonically,
    and the max distance from a point to the ellipse."""
    M = np.column_stack([U, V])
    try:
        m = np.linalg.solve(M, (P - C).T).T
    except np.linalg.LinAlgError:
        return None, None
    n = np.linalg.norm(m, axis=1)
    if np.any(n < 1e-12):
        return None, None
    dev = np.linalg.norm((M @ (m / n[:, None] - m).T).T, axis=1)
    t = np.degrees(np.arctan2(m[:, 1], m[:, 0]))
    t = t[0] + np.cumsum(np.concatenate([[0.0], (np.diff(t) + 180) % 360 - 180]))
    return t, float(dev.max())


def _sil_chains(sil, tol):
    """Silhouette line ops chained end to end into point runs, each with the
    ops it consumed."""
    ends = [(np.array(o[1:3], float), np.array(o[3:5], float)) for o in sil]
    lens = [float(np.linalg.norm(b - a)) for a, b in ends]
    used, out = set(), []
    for i in range(len(sil)):
        if i in used or lens[i] < tol:
            continue
        used.add(i)
        P, own = [ends[i][0], ends[i][1]], [i]
        grew = True
        while grew:
            grew = False
            for j in range(len(sil)):
                if j in used or lens[j] < tol:
                    continue
                for a, b in (ends[j], ends[j][::-1]):
                    if np.linalg.norm(P[-1] - a) <= tol:
                        P.append(b); own.append(j)
                    elif np.linalg.norm(P[0] - b) <= tol:
                        P.insert(0, a); own.insert(0, j)
                    else:
                        continue
                    used.add(j); grew = True
                    break
                if grew:
                    break
        out.append((np.array(P), own))
    return out


def _smooth_spans(P):
    """Index ranges of P that turn steadily one way — candidate arc runs.
    Splits at a corner, at a straight joint, and where the turn changes
    sign, so a straight side or a real crease can never be swept in."""
    d = np.diff(P, axis=0)
    ang = np.degrees(np.arctan2(d[:, 1], d[:, 0]))
    turn = (np.diff(ang) + 180) % 360 - 180
    cuts = [0]
    for i, t in enumerate(turn):
        if not (SIL_TURN_MIN <= abs(t) <= SIL_TURN_MAX) \
                or (i and np.sign(t) != np.sign(turn[i - 1])):
            cuts.append(i + 1)
    cuts.append(len(P) - 1)
    return [(a, b) for a, b in zip(cuts, cuts[1:]) if b + 1 - a >= SIL_MIN_PTS]


def fit_silhouette_arcs(segs):
    """Draw a silhouette that is one ellipse as an arc, not as its chords.

    Returns (segs, ellipses). The ellipses are arc-recovery candidates in
    hlr's `ellipses` format with a per-candidate step and snap tolerance, so
    geom2d.densify_on_arcs pulls the fill boundary onto the same curve the
    stroke now follows — strokes and fills have to move together or the
    divergence opens paint slivers along the run.

    Only silhouette ops are eligible, and only where the fit is
    over-determined and tight (see the constants above). A run this rule
    accepts and a genuine polygon of the same step are the same points; the
    turn cap, not the fit, is what separates them.
    """
    if not segs:
        return segs, []
    sil = [o for o in segs if o[0] == "line" and o[-1] == "sil"]
    if len(sil) < SIL_MIN_PTS - 1:
        return segs, []
    pts = np.array([p for o in sil for p in ((o[1], o[2]), (o[3], o[4]))],
                   float)
    dim = float(max(pts.max(axis=0) - pts.min(axis=0))) or 1.0
    join_tol = 0.004 * dim                       # ~1 output px at a 256 icon
    fit_tol = SIL_TOL_PX / 256.0 * dim

    # Endpoints of everything that is NOT this silhouette: a real polygon's
    # corners are authored edges, and the crease lands on the outline right
    # at the corner. A faceted round's limb vertices are bare -- the facet
    # boundaries there are conditional lines, drawn only where they ARE the
    # limb. That is the one difference between the two that the library
    # declares rather than leaves to be inferred from the sampling.
    creases = np.array([q for o in segs if o[0] == "line" and o[-1] != "sil"
                        for q in ((o[1], o[2]), (o[3], o[4]))], float)

    def bare(p):
        return not len(creases) or bool(
            np.linalg.norm(creases - p, axis=1).min() > join_tol)

    drop, arcs, ells = set(), [], []
    for P, own in _sil_chains(sil, join_tol):
        for a, b in _smooth_spans(P):
            if not all(bare(q) for q in P[a + 1:b]):
                continue                     # a crease meets the run: corners
            got = _conic(P[a:b + 1])
            if got is None:
                continue
            C, U, V = got
            t, dev = _params(P[a:b + 1], C, U, V)
            if t is None or dev > fit_tol or abs(t[-1] - t[0]) > SIL_SPAN_MAX:
                continue
            t0, t1 = (t[0], t[-1]) if t[-1] > t[0] else (t[-1], t[0])
            arcs.append(("arc", C[0], C[1], U[0], U[1], V[0], V[1],
                         float(t0), float(t1), "sil"))
            # the run's own coarsest sweep, so densify_on_arcs subdivides the
            # fill edges it just took over rather than treating them as
            # already fine enough
            step = float(np.abs(np.diff(t)).max())
            ells.append((C[0], C[1], U[0], U[1], V[0], V[1], step,
                         float(max(dev, fit_tol))))
            drop.update(own[a:b])
    if not arcs:
        return segs, []
    keep, seen = [], 0
    for op in segs:
        if op[0] == "line" and op[-1] == "sil":
            if seen in drop:
                seen += 1
                continue
            seen += 1
        keep.append(op)
    return keep + arcs, ells
