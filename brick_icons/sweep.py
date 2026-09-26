"""Hand-authored ring-quad tubes become chains of exact cone frustums.

A bent tube -- 3127a's crane hook -- is authored as rings of vertices at
successive stations along a spine, joined by quads. No primitive names it, so
it reached the engines as 136 planes whose normals wrap the sphere, and no
ramp could shade it. Its quads keep the rings exactly: consecutive quads share
a ring's vertices, so recovering the rings is a lookup on the authored
geometry, never an inference over a tessellation (the two of those that were
tried and failed are recorded on `shade._band_misfit_radials`).

The sweep is discretized where the author discretized it: one right cone
frustum per station pair, between the fitted circles of its two rings. The
engines already build, occlude, silhouette and ramp a cone, and a joint
between two exact surfaces draws no crease under `occt.TANGENT_DEG`. Each
piece is exact; the chain is not: its outline kinks and its tone steps at
every joint (scripts/measure-sweep-fit.py).

Where a run of pairs lies on one circular bend at one radius -- every bend
of a rail or a handlebar, and LDraw's own torus primitives, which reach here
as ring quads -- occt builds the torus section instead (`_bend`, carried on
the frustum as `bend`), so the tube is one smooth exact surface and its
outline is a curve. Tapered chains (3127a's hook) stay frustums. `BENDS`
disarms the torus; `SUBSTITUTE` disarms the pass.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from . import primitives

#: Disarm to leave every ring-quad tube as its authored facets.
SUBSTITUTE = True
#: Fewest vertices a ring may have: a 6-gon is the coarsest LDraw round.
MIN_RING = 6
#: How far a ring's vertices may stray from their fitted circle, as a
#: fraction of the radius. Authored rings are exact to file precision; the
#: slack is for a ring transformed through a scaled reference.
ROUND_TOL = 0.02
#: A ring's plane may tilt this far off the chord to the next ring; a hook's
#: rings sit a few degrees off, a corner or a kink much more.
TILT_DEG = 30.0
#: How fast the radius may change along the spine, as a ratio of the
#: distance between rings: a tube tapers gently (3127a's hook 0.07), while
#: a dome or dish authored as concentric rings is the same ring-quad
#: structure with its radius collapsing to nothing at the pole (3960's rings
#: step in radius with no height at all). One band past this and the whole
#: chain is left as the facet dome the shading already knows.
MAX_TAPER = 0.5
#: Keep the authored conditional lines that run ROUND a ring (the ones along
#: the tube always go: the frustums silhouette themselves).
KEEP_RING_CONDLINES = True
#: Rebuild a bent station pair as the torus section its rings lie on,
#: rather than a frustum across its chord. Disarm to draw every pair as a
#: frustum. Only occt builds the torus; the frustum stays on the primitive
#: for everything else that reads it.
BENDS = True
#: How far the second ring may sit off the arc the first ring's center and
#: plane define, as a fraction of the bend radius. Authored rings on a
#: circular bend land on it to file precision.
BEND_TOL = 0.01
#: A pair bent less than this is straight: its frustum is already exact.
MIN_BEND_DEG = 0.5
#: The bend radius must clear the tube radius by this factor, or the inside
#: of the bend folds through itself (75652's tightest is 1.08).
MIN_BEND_RATIO = 1.02
#: Vertex keys are world coordinates rounded to this many decimals: shared
#: vertices come through one matrix and agree exactly, so this only guards
#: against the last bit.
KEY_DECIMALS = 4


def _key(p):
    return tuple(np.round(np.asarray(p, float), KEY_DECIMALS).tolist())


class _Parity:
    """Union-find with an orientation bit: two directed edges are the same
    undirected edge either way round, and a quad's opposite sides run the
    same way."""

    def __init__(self):
        self.parent, self.flip = {}, {}

    def find(self, x):
        self.parent.setdefault(x, x)
        self.flip.setdefault(x, False)
        path = []
        while self.parent[x] != x:
            path.append(x)
            x = self.parent[x]
        acc = False
        for y in reversed(path):
            acc ^= self.flip[y]
            self.flip[y] = acc
            self.parent[y] = x
        return x

    def union(self, a, b, flipped):
        """Declare a and b the same class, with b's orientation equal to a's
        (flipped=False) or opposite. Returns False on a contradiction."""
        ra, rb = self.find(a), self.find(b)
        fa, fb = self.flip[a], self.flip[b]
        if ra == rb:
            return (fa ^ fb) == flipped
        self.parent[rb] = ra
        self.flip[rb] = fa ^ fb ^ flipped
        return True


def _quads(out):
    """[(first tri index, 4 vertex keys, 4 points, meta)] off the flattener's
    tagged triangle pairs."""
    tris, metas = out["tri"], out["tri_meta"]
    quads, i = [], 0
    while i < len(tris) - 1:
        q = metas[i].get("quad")
        if q is not None and metas[i + 1].get("quad") == q:
            a, b, c = (np.asarray(p, float) for p in tris[i])
            d = np.asarray(tris[i + 1][2], float)
            pts = [a, b, c, d]
            quads.append((i, [_key(p) for p in pts], pts, metas[i]))
            i += 2
        else:
            i += 1
    return quads


def _fit_ring(points):
    """(center, radius, normal) of a ring, or None if it is not one circle."""
    P = np.asarray(points, float)
    if len(P) < MIN_RING:
        return None
    c = P.mean(axis=0)
    _, s, vt = np.linalg.svd(P - c, full_matrices=False)
    n = vt[2]
    if s[0] <= 1e-9 or s[2] / s[0] > ROUND_TOL:
        return None                     # not planar
    r = np.linalg.norm(P - c, axis=1)
    if r.mean() <= 1e-9 or r.std() / r.mean() > ROUND_TOL:
        return None                     # not a circle about its mean
    # spread round the whole turn, not bunched on one side
    u = vt[0]
    v = np.cross(n, u)
    ang = np.sort(np.arctan2((P - c) @ v, (P - c) @ u))
    gaps = np.diff(np.concatenate([ang, [ang[0] + 2 * np.pi]]))
    if gaps.max() > 2.5 * (2 * np.pi / len(P)):
        return None
    return c, float(r.mean()), n


def _frustum(c0, r0, n0, c1, r1, n1, color, body):
    """One exact wall between two rings: a cylinder when the radii agree,
    else a cone with its base at the wider ring.

    The rings are not perpendicular to the chord between their centers -- on
    a bend each sits on the bisector of its two chords -- so a right frustum
    ending on the chord's own end planes meets its neighbor tilted, and the
    two never sew: the hook drew a free circle at every joint. The wall is
    therefore built LONGER than the chord and cut back to the two ring
    planes (`cut`, applied by `occt.occt_faces`), so consecutive walls share
    the section in the ring plane. That holds exactly only when both have
    one radius: two cones of different taper cut by one plane give
    different ellipses (3127a's differ by 2.9% of r, too far to sew at TOL).
    """
    c0, c1 = np.asarray(c0, float), np.asarray(c1, float)
    n0, n1 = np.asarray(n0, float), np.asarray(n1, float)
    if r1 > r0:
        c0, r0, n0, c1, r1, n1 = c1, r1, n1, c0, r0, n0
    axis = c1 - c0
    h = float(np.linalg.norm(axis))
    if h <= 1e-9:
        return None
    a = axis / h
    # planes face INTO the wall's own span
    if float(n0 @ a) < 0:
        n0 = -n0
    if float(n1 @ a) > 0:
        n1 = -n1
    cut = ((c0, n0), (c1, n1))
    # extend past both rings by the wider radius, with the taper carried on
    ext = max(r0, r1)
    slope = (r1 - r0) / h
    r0e, r1e = r0 - slope * ext, r1 + slope * ext
    if r1e <= 1e-6:                       # the cone's apex is inside the extension
        ext1 = max(0.0, (r1 - 1e-3) / -slope) if slope < 0 else ext
        r1e = r1 + slope * ext1
    else:
        ext1 = ext
    c0, c1, r0, r1 = c0 - a * ext, c1 + a * ext1, r0e, r1e
    axis = c1 - c0
    h = float(np.linalg.norm(axis))
    ref = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(a, ref)
    u /= np.linalg.norm(u)
    v = np.cross(a, u)
    if r0 - r1 < 1e-3 * r0:
        R = np.column_stack([u * r0, axis, v * r0])
        prim = primitives.Cylinder(R=R, t=np.asarray(c0, float))
    else:
        s = r0 - r1
        R = np.column_stack([u * s, axis, v * s])
        prim = primitives.Cone(R=R, t=np.asarray(c0, float), top=r1 / s)
    prim.color = color
    prim.body = body
    prim.sweep = True
    prim.cut = cut
    return prim


def _bend(c0, r0, n0, c1, r1, n1):
    """The torus section two rings lie on, or None when they do not share one.

    A ring's plane is square to the spine, so its normal is the spine's
    direction at that station. A circular arc from c0 leaving along n0 is
    fixed by c1 alone; the pair is one torus section when that arc also
    arrives along n1 and both rings have one radius. Returns (center, axis,
    start direction, bend radius, tube radius, angle): the torus sweeps
    from `center + bend radius * start` about `axis`, counterclockwise.
    """
    c0, c1 = np.asarray(c0, float), np.asarray(c1, float)
    d = c1 - c0
    L = float(np.linalg.norm(d))
    if L <= 1e-9 or abs(r1 - r0) > 1e-3 * max(r0, r1):
        return None
    n0 = np.asarray(n0, float) * (1.0 if float(np.asarray(n0) @ d) > 0 else -1.0)
    n1 = np.asarray(n1, float) * (1.0 if float(np.asarray(n1) @ d) > 0 else -1.0)
    theta = math.acos(float(np.clip(n0 @ n1, -1.0, 1.0)))
    if math.degrees(theta) < MIN_BEND_DEG:
        return None
    m = n1 - (n1 @ n0) * n0                      # toward the inside of the bend
    m /= np.linalg.norm(m)
    Rb = L / (2.0 * math.sin(theta / 2.0))
    O = c0 + Rb * m
    # the arc from c0 along n0 through the bend angle must land on c1 with
    # tangent n1; anything else is a biarc or a twist, and stays a frustum
    end = O + Rb * (math.cos(theta) * -m + math.sin(theta) * n0)
    if np.linalg.norm(end - c1) > BEND_TOL * Rb:
        return None
    r = 0.5 * (r0 + r1)
    if Rb < MIN_BEND_RATIO * r:
        return None
    start = -m
    axis = np.cross(start, n0)
    axis /= np.linalg.norm(axis)
    return O, axis, start, Rb, r, theta


def _same_torus(a, b):
    Oa, ka, _sa, Ra, ra, _ta = a
    Ob, kb, _sb, Rb, rb, _tb = b
    return (np.linalg.norm(Oa - Ob) <= BEND_TOL * Ra and float(ka @ kb) > 0.9998
            and abs(Ra - Rb) <= BEND_TOL * Ra and abs(ra - rb) <= 1e-3 * ra)


def _merge_bends(chain):
    """Give each run of pairs on one torus a single section, on the first
    pair of the run; the rest carry `()`, meaning covered. Each pair's own
    fit differs from its neighbor's in the last authored digit (2583's bend
    radius reads 9.999 and 10.001), which is past OCCT's sewing tolerance, so
    per-pair sections would never sew into one tube."""
    i = 0
    while i < len(chain):
        b = chain[i].bend
        j = i + 1
        while b and j < len(chain) and chain[j].bend and _same_torus(b, chain[j].bend):
            j += 1
        if b and j - i > 1:
            run = [p.bend for p in chain[i:j]]
            O = np.mean([x[0] for x in run], axis=0)
            k = np.mean([x[1] for x in run], axis=0)
            k /= np.linalg.norm(k)
            Rb = float(np.mean([x[3] for x in run]))
            r = float(np.mean([x[4] for x in run]))
            first, last = run[0], run[-1]
            p0 = first[0] + first[3] * first[2]
            q = last[0] + last[3] * (math.cos(last[5]) * last[2]
                                     + math.sin(last[5]) * np.cross(last[1], last[2]))
            start = p0 - O
            start -= (start @ k) * k
            start /= np.linalg.norm(start)
            e = q - O
            e -= (e @ k) * k
            angle = math.atan2(float(np.cross(start, e) @ k), float(start @ e)) % (2 * math.pi)
            chain[i].bend = (O, k, start, Rb, r, angle)
            for p in chain[i + 1:j]:
                p.bend = ()
        i = j


def _declared_smooth(edges, out):
    """Does the part declare every one of these edges a smooth seam (a type-5
    line lies on it)? A hexagonal nut is rings of quads too, and its vertices
    sit on a circle; what tells it from a tube is that nobody drew a
    conditional line along its corners."""
    from . import shade
    if not edges:
        return False
    A = np.array([a for a, _ in edges], float)
    B = np.array([b for _, b in edges], float)
    return bool(shade._seam_edge_mask(A, B, out.get("5") or []).all())


def tubes(out):
    """Every ring-quad tube in `out`: [(rings, quad indices)], each ring a
    (center, radius, normal, vertex-key set), in spine order. A chain counts
    only when its bands' edges along the spine are all declared smooth."""
    quads = _quads(out)
    if not quads:
        return [], quads
    uf = _Parity()
    by_quad = {}
    for qi, (_, keys, _pts, _meta) in enumerate(quads):
        a, b, c, d = keys
        # a->b runs with d->c; b->c runs with a->d
        ok = uf.union((a, b), (d, c), False) and uf.union((b, c), (a, d), False)
        # the same undirected edge, seen from either end
        for p, q in ((a, b), (b, c), (c, d), (d, a)):
            ok = uf.union((p, q), (q, p), True) and ok
        by_quad[qi] = ok
    classes = defaultdict(set)          # root -> {(start, end)}
    bad = set()
    for qi, (_, keys, _pts, _meta) in enumerate(quads):
        a, b, c, d = keys
        for p, q in ((a, b), (b, c), (c, d), (d, a)):
            root = uf.find((p, q))
            if not by_quad[qi]:
                bad.add(root)
            classes[root].add((q, p) if uf.flip[(p, q)] else (p, q))
    # a class is a BAND when its edges pair one ring's vertices with the
    # next's, each vertex once
    bands = {}
    for root, edges in classes.items():
        if root in bad:
            continue
        starts = {p for p, _ in edges}
        ends = {q for _, q in edges}
        if len(starts) != len(edges) or len(ends) != len(edges) or starts & ends:
            continue
        bands[root] = (frozenset(starts), frozenset(ends))
    # chain bands whose end ring is another's start ring; the families that
    # close on themselves are the chords running round the tube
    by_start = {s: root for root, (s, _e) in bands.items()}
    by_end = {e: root for root, (_s, e) in bands.items()}
    seen, chains = set(), []
    for root, (s, e) in bands.items():
        if root in seen or s in by_end:
            continue                    # not the head of a chain
        chain, cur = [], root
        while cur is not None and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            cur = by_start.get(bands[cur][1])
        chains.append(chain)
    pts_of = {}
    for _, keys, pts, _meta in quads:
        for k, p in zip(keys, pts):
            pts_of[k] = p
    quad_of_edge = defaultdict(set)
    for qi, (_, keys, _pts, _meta) in enumerate(quads):
        a, b, c, d = keys
        for p, q in ((a, b), (b, c), (c, d), (d, a)):
            quad_of_edge[frozenset((p, q))].add(qi)
    found = []
    for chain in chains:
        ring_sets = [bands[chain[0]][0]] + [bands[r][1] for r in chain]
        rings = []
        for vs in ring_sets:
            fit = _fit_ring([pts_of[k] for k in vs])
            if fit is None:
                break
            rings.append((*fit, vs))
        if len(rings) != len(ring_sets):
            continue
        ok = True
        for (c0, r0, n0, _v0), (c1, r1, _n1, _v1) in zip(rings, rings[1:]):
            axis = c1 - c0
            h = np.linalg.norm(axis)
            if h <= 1e-9 or abs(float(n0 @ axis)) / h < np.cos(np.radians(TILT_DEG)) \
                    or abs(r1 - r0) > MAX_TAPER * h:
                ok = False
                break
        if not ok:
            continue
        if not _declared_smooth([(pts_of[p], pts_of[q]) for root in chain
                                 for p, q in classes[root]], out):
            continue
        qis = set()
        for root in chain:
            for p, q in classes[root]:
                qis |= quad_of_edge[frozenset((p, q))]
        found.append((rings, sorted(qis)))
    return found, quads


def substitute(out) -> int:
    """Replace every ring-quad tube in `out` with cone frustums. Returns how
    many tubes were replaced."""
    if not SUBSTITUTE or not out.get("tri") or "analytic" not in out:
        return 0
    found, quads = tubes(out)
    if not found:
        return 0
    drop_tris = set()
    on_ring = {}
    for rings, qis in found:
        for qi in qis:
            first, _keys, _pts, meta = quads[qi]
            drop_tris.update((first, first + 1))
        for i, (_c, _r, _n, vs) in enumerate(rings):
            for k in vs:
                on_ring[k] = (id(rings), i)
        meta = quads[qis[0]][3]
        chain = []
        for (c0, r0, n0, _v0), (c1, r1, n1, _v1) in zip(rings, rings[1:]):
            prim = _frustum(c0, r0, n0, c1, r1, n1, meta["color"],
                            meta.get("body", 16))
            if prim is not None:
                prim.bend = _bend(c0, r0, n0, c1, r1, n1) if BENDS else None
                out["analytic"].append(prim)
                chain.append(prim)
        _merge_bends(chain)
    out["tri"] = [t for i, t in enumerate(out["tri"]) if i not in drop_tris]
    out["tri_meta"] = [m for i, m in enumerate(out["tri_meta"]) if i not in drop_tris]
    # The authored conditional lines ALONG the tube marked its facet
    # silhouettes; the frustums silhouette themselves, and keeping the lines
    # would draw the facet limb beside the exact one. The ones round a ring
    # stay: they suppress the joint between two exact surfaces.
    kept = []
    for seg in out.get("5", ()):
        a, b = on_ring.get(_key(seg[0])), on_ring.get(_key(seg[1]))
        if a is not None and b is not None and a[0] == b[0] and (
                a[1] != b[1] or not KEEP_RING_CONDLINES):
            continue
        kept.append(seg)
    out["5"] = kept
    out["sweeps"] = len(found)
    return len(found)
