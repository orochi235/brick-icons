from __future__ import annotations

import heapq
import math
from collections import defaultdict

import numpy as np
from PIL import Image, ImageDraw

from . import geom2d, hlr, primitives


def _project_px(P, right, up, fwd, s, cx, cy, half):
    a, b, z = hlr.project(P, right, up, fwd)
    return (a - cx) * s + half, (b - cy) * s + half, z


def _radius_pts(rec, thetas, level, radius=None):
    """World points on the rec's circle at `thetas` (radians), `level` along axis
    (0 = base ring, 1 = top ring). `radius` overrides the unit radius (in
    primitive units); default is the ring's outer radius (inner+1) or 1.0."""
    R = np.asarray(rec["R"], float); C = np.asarray(rec["t"], float)
    if radius is None:
        if rec["kind"] == "ring":
            radius = rec["inner"] + 1
        elif rec["kind"] == "con":
            radius = rec["inner"] + 1 - level      # N+1 at base -> N at top
        else:
            radius = 1.0
    U, A, V = R[:, 0], R[:, 1], R[:, 2]
    base = C + level * A
    return base + radius * (np.cos(thetas)[:, None] * U + np.sin(thetas)[:, None] * V)


def _merged_wall_rec(recs):
    """One synthetic cyli/con record covering a smooth chain of wall records
    (sections of the same infinite cylinder/cone). Returns None if the chain
    has no clean two free rims (degenerate or looped sharing)."""
    ends = {}
    for rec in recs:
        R = np.asarray(rec["R"], float); t = np.asarray(rec["t"], float)
        A = R[:, 1]; ru = float(np.linalg.norm(R[:, 0]))
        if rec["kind"] == "cyli":
            pairs = [(t, ru), (t + A, ru)]
        else:
            N = rec["inner"]
            pairs = [(t, (N + 1) * ru), (t + A, N * ru)]
        for C, r in pairs:
            key = primitives.rim_key(C, A, r)
            if key in ends:
                del ends[key]                    # interior joint
            else:
                ends[key] = (np.asarray(C, float), float(r))
    if len(ends) != 2:
        return None
    (C0, r0), (C1, r1) = ends.values()
    if r0 < r1:
        (C0, r0), (C1, r1) = (C1, r1), (C0, r0)  # base = wide end
    A = C1 - C0
    ah = float(np.linalg.norm(A))
    if ah < 1e-9:
        return None
    ahat = A / ah
    U0 = np.asarray(recs[0]["R"], float)[:, 0]
    u = U0 - float(U0 @ ahat) * ahat
    un = float(np.linalg.norm(u))
    if un < 1e-9:
        return None
    u = u / un
    v = np.cross(u, ahat)
    dr = r0 - r1
    if dr < 1e-9:
        R = np.column_stack([r0 * u, A, r0 * v])
        return {"kind": "cyli", "sector": 360.0, "inner": 0, "R": R, "t": C0}
    R = np.column_stack([dr * u, A, dr * v])
    return {"kind": "con", "sector": 360.0, "inner": r1 / dr, "R": R, "t": C0}


def merge_smooth_wall_recs(analytic):
    """Collapse chains of full-sector cyli/con records that continue each
    other smoothly through a shared rim — equal slope on opposite sides of
    the rim plane, the same predicate that suppresses the rim's STROKE in
    hlr — into one synthetic record per chain, so the wall shades as ONE
    face with ONE gradient. Left separate, each section fits its own
    gradient axis and the shared rim shows a tone step (4589's con3-on-con4
    body: identical stops over different axis extents). Non-wall records,
    partial sectors, creases, and ambiguously shared rims pass through
    unchanged. The synthetic con's `inner` may be non-integer."""
    walls = [i for i, r in enumerate(analytic)
             if r["kind"] in ("cyli", "con") and r["sector"] >= 360.0 - 1e-9]
    by_key = defaultdict(list)
    for i in walls:
        for key, side, slope in primitives.wall_rims(analytic[i]):
            by_key[key].append((i, side, slope))
    parent = {i: i for i in walls}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for ent in by_key.values():
        if len(ent) != 2:
            continue                             # free rim or 3-way sharing
        (i, si, mi), (j, sj, mj) = ent
        if i == j or si != -sj or mi != mj:
            continue                             # same side, or a crease
        if analytic[i]["kind"] != analytic[j]["kind"]:
            continue
        parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in walls:
        groups[find(i)].append(i)
    synth_at, drop = {}, set()
    for members in groups.values():
        if len(members) < 2:
            continue
        rec = _merged_wall_rec([analytic[i] for i in members])
        if rec is not None:
            synth_at[min(members)] = rec
            drop.update(members)
    if not synth_at:
        return list(analytic)
    return [synth_at.get(i, rec) for i, rec in enumerate(analytic)
            if i in synth_at or i not in drop]


def faces_from_analytic(analytic, right, up, fwd, s, cx, cy, half):
    faces = []
    for rec in merge_smooth_wall_recs(analytic):
        kind = rec["kind"]
        if kind == "edge":
            continue
        R = np.asarray(rec["R"], float)
        sect = math.radians(rec["sector"])
        if kind in ("disc", "ring"):
            th = np.linspace(0.0, sect, 64)
            hole_w = None
            if kind == "ring":
                # Annulus: full sector gets a REAL hole ring (the bore);
                # a partial sector is a simple valid polygon, so keep the
                # outer-forward / inner-back concatenation there.
                outer = _radius_pts(rec, th, 0.0, radius=rec["inner"] + 1)
                inner = _radius_pts(rec, th, 0.0, radius=rec["inner"])
                if sect >= 2 * math.pi - 1e-6:
                    w, hole_w = outer, inner
                else:
                    w = np.concatenate([outer, inner[::-1]], axis=0)
            else:
                w = _radius_pts(rec, th, 0.0)
            px, py, z = _project_px(w, right, up, fwd, s, cx, cy, half)
            n = R[:, 1]; n = n / np.linalg.norm(n)
            nv = np.array([n @ right, n @ up, n @ fwd])
            if nv[2] > 0:
                nv = -nv
            face = {"poly": np.stack([px, py], 1), "normal": nv,
                    "depth": float(np.mean(z)), "zs": z, "kind": kind,
                    "rec": rec}
            if hole_w is not None:
                hx, hy, _ = _project_px(hole_w, right, up, fwd, s, cx, cy, half)
                face["holes"] = [np.stack([hx, hy], 1)]
            faces.append(face)
        elif kind == "cyli":
            faces.extend(_cyl_wall_faces(rec, R, sect, right, up, fwd,
                                         s, cx, cy, half))
        elif kind == "con":
            faces.extend(_con_wall_faces(rec, R, sect, right, up, fwd,
                                         s, cx, cy, half))
    return faces


def _arc_sector_spans(lo, length, sect):
    """Intersect the arc starting at `lo` (radians) of `length` with the
    sector [0, sect] on the circle. Returns [(a, b)] spans (b > a), at most
    two: a wrapped arc can re-enter the sector past 0. A full sector needs no
    clamping — the raw interval is returned so a seamless single face is kept
    even when it crosses 0/2pi (angles are plain reals downstream)."""
    if sect >= 2 * math.pi - 1e-6:
        return [(lo, lo + length)]
    two = 2 * math.pi
    lo = lo % two
    pieces = [(lo, min(lo + length, two))]
    if lo + length > two:
        pieces.append((0.0, lo + length - two))
    spans = []
    for a, b in pieces:
        a, b = max(a, 0.0), min(b, sect)
        if b - a > 1e-3:
            spans.append((a, b))
    return spans


def _cyl_wall_faces(rec, R, sect, right, up, fwd, s, cx, cy, half):
    """Cylinder wall fills: the camera-facing outer half AND the far half's
    interior surface (visible when looking into an open tube — leaving it out
    produced 4019's white voids). Each visible span becomes one arc-region
    polygon with a linear-gradient spec; a partial sector can split a span in
    two where the arc wraps past 0."""
    U, A, V = R[:, 0], R[:, 1], R[:, 2]
    a = float(U @ fwd); b = float(V @ fwd)
    if a == 0.0 and b == 0.0:
        return []                                # axis points at camera: no wall
    phi = math.atan2(b, a)
    theta_face = phi + math.pi                   # most camera-facing angle
    halves = [(theta_face - math.pi / 2, False),         # outer near half
              (theta_face + math.pi / 2, True)]          # interior far half
    faces = []
    for start, interior in halves:
        for lo, hi in _arc_sector_spans(start, math.pi, sect):
            f = _wall_span_face(rec, U, V, lo, hi, interior,
                                right, up, fwd, s, cx, cy, half)
            if f is not None:
                faces.append(f)
    return faces


def _con_wall_faces(rec, R, sect, right, up, fwd, s, cx, cy, half):
    """Cone wall fills. Unlike a cylinder, the front-facing arc is NOT a half:
    with g = R^-1 @ fwd and (A, B, C) = (g0, g2, -g1), n(theta).fwd =
    hyp*cos(theta - phi0) - C, so the outer wall is visible on
    (phi0+d, phi0+2pi-d) where d = acos(C/hyp) — the generator angles — and
    the interior far wall on the complement. Axis-on view (hyp ~ 0, or
    |C| >= hyp): every generator faces the same way, one full-circle span."""
    Minv = np.linalg.inv(R)
    g = Minv @ np.asarray(fwd, float)
    A_, B_, C_ = float(g[0]), float(g[2]), float(-g[1])
    MT = Minv.T

    def normal_fn(th):
        return MT @ np.array([math.cos(th), 1.0, math.sin(th)])

    hyp = math.hypot(A_, B_)
    if hyp < 1e-12:
        spans = [(0.0, 2 * math.pi, float(g[1]) > 0)]
    elif abs(C_) >= hyp:
        spans = [(0.0, 2 * math.pi, C_ >= hyp)]
    else:
        phi0 = math.atan2(B_, A_)
        d = math.acos(max(-1.0, min(1.0, C_ / hyp)))
        spans = [(phi0 + d, phi0 + 2 * math.pi - d, False),
                 (phi0 - d, phi0 + d, True)]
    U, V = R[:, 0], R[:, 2]
    faces = []
    for start, end, interior in spans:
        if end - start < 1e-6:
            continue
        for lo, hi in _arc_sector_spans(start, end - start, sect):
            f = _wall_span_face(rec, U, V, lo, hi, interior, right, up, fwd,
                                s, cx, cy, half, normal_fn=normal_fn)
            if f is not None:
                faces.append(f)
    return faces


def _wall_span_face(rec, U, V, lo, hi, interior, right, up, fwd, s, cx, cy, half,
                    normal_fn=None):
    ths = np.linspace(lo, hi, 40)
    top = _radius_pts(rec, ths, 1.0)
    bot = _radius_pts(rec, ths, 0.0)
    tpx, tpy, tz = _project_px(top, right, up, fwd, s, cx, cy, half)
    bpx, bpy, bz = _project_px(bot, right, up, fwd, s, cx, cy, half)
    poly = np.concatenate([np.stack([tpx, tpy], 1),
                           np.stack([bpx, bpy], 1)[::-1]], axis=0)
    zs = np.concatenate([tz, bz])
    # gradient axis: mid-height points at the span's end angles
    mid = _radius_pts(rec, np.array([lo, hi]), 0.5)
    mpx, mpy, _ = _project_px(mid, right, up, fwd, s, cx, cy, half)
    p0 = (float(mpx[0]), float(mpy[0])); p1 = (float(mpx[1]), float(mpy[1]))
    axis = np.array([p1[0] - p0[0], p1[1] - p0[1]]); L2 = float(axis @ axis) or 1.0
    samples = []
    for th in np.linspace(lo, hi, 9):
        if normal_fn is None:
            n = math.cos(th) * U + math.sin(th) * V
        else:
            n = normal_fn(th)
        n = n / np.linalg.norm(n)
        if interior:
            n = -n                               # inward surface normal
        nv = np.array([n @ right, n @ up, n @ fwd])
        p = _radius_pts(rec, np.array([th]), 0.5)
        ppx, ppy, _ = _project_px(p, right, up, fwd, s, cx, cy, half)
        off = ((ppx[0] - p0[0]) * axis[0] + (ppy[0] - p0[1]) * axis[1]) / L2
        samples.append((float(np.clip(off, 0.0, 1.0)), nv))
    return {"poly": poly, "zs": zs, "depth": float(np.mean(zs)), "kind": rec["kind"],
            "rec": rec, "interior": interior,
            "span_deg": math.degrees(hi - lo),
            "grad_axis": (p0, p1), "grad_samples": samples}


def _hex(rgb):
    r, g, b = (max(0, min(255, round(c))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


class ShadingStyle:
    def tone(self, nv) -> str:
        raise NotImplementedError


class Flat3Style(ShadingStyle):
    """Flat faces: three tones by dominant orientation (top / left / right).
    Curved faces (cylinder walls) shade with a smooth Lambert ramp via `ramp`."""
    def __init__(self, part_color=(157, 157, 157)):
        self.part_color = tuple(part_color)
        self.top = _hex([c * 1.30 for c in part_color])
        self.left = _hex([c * 0.85 for c in part_color])
        self.right = _hex([c * 0.60 for c in part_color])
        # view-space light: upper-left, toward the viewer (matches left>right)
        L = np.array([-0.5, 0.6, -0.62]); self.light = L / np.linalg.norm(L)

    def tone(self, nv):
        if nv[1] > 0.5:
            return self.top
        return self.left if nv[0] < 0 else self.right

    def ramp(self, nv):
        """Continuous grey for a curved-surface normal (gradient stops)."""
        return self.ramp_b(max(0.0, float(np.dot(np.asarray(nv, float), self.light))))

    def ramp_b(self, b):
        """Grey for a raw Lambert brightness (n . light, already clamped)."""
        return _hex([c * (0.55 + 0.85 * float(b)) for c in self.part_color])


def _plane_depth_fn(f):
    """Screen-depth function (x, y) -> depth for a face.

    Projection is orthographic, so a PLANAR face's camera depth is an affine
    function of screen coords — recovered exactly from any 3 spread vertices
    and their per-vertex depths `zs`. Curved bands get their chord plane
    (callers refine with the face's own occluder when available); faces
    without aligned zs fall back to their constant mean depth."""
    poly, zs = f["poly"], f.get("zs")
    d0 = float(f["depth"])
    if zs is None or len(zs) != len(poly):
        return lambda x, y: d0
    p0 = poly[0]
    i1 = int(np.argmax(np.hypot(poly[:, 0] - p0[0], poly[:, 1] - p0[1])))
    v01 = poly[i1] - p0
    cr = v01[0] * (poly[:, 1] - p0[1]) - v01[1] * (poly[:, 0] - p0[0])
    i2 = int(np.argmax(np.abs(cr)))
    M = np.array([[p0[0], p0[1], 1.0],
                  [poly[i1, 0], poly[i1, 1], 1.0],
                  [poly[i2, 0], poly[i2, 1], 1.0]])
    if abs(np.linalg.det(M)) < 1e-6:
        return lambda x, y: d0
    a_, b_, c_ = np.linalg.solve(M, np.array([zs[0], zs[i1], zs[i2]], float))
    return lambda x, y: a_ * x + b_ * y + c_


def _overlap_witness(pa, pb, ha=(), hb=(), grid=48):
    """A screen point strictly inside the overlap of two face polygons, or
    None. Rasterizes both at low res over the bbox intersection and picks a
    most-interior overlap pixel (repeated erosion), so the witness stays away
    from shared edges where depths tie. `ha`/`hb` are optional hole rings
    (bores) punched out of the respective polygon before overlap."""
    ax0, ay0 = pa.min(axis=0); ax1, ay1 = pa.max(axis=0)
    bx0, by0 = pb.min(axis=0); bx1, by1 = pb.max(axis=0)
    x0, y0 = max(ax0, bx0), max(ay0, by0)
    x1, y1 = min(ax1, bx1), min(ay1, by1)
    if x1 - x0 < 0.5 or y1 - y0 < 0.5:
        return None
    sx = (grid - 1) / (x1 - x0); sy = (grid - 1) / (y1 - y0)

    def mask(p, holes):
        im = Image.new("1", (grid, grid), 0)
        draw = ImageDraw.Draw(im)
        draw.polygon([((q[0] - x0) * sx, (q[1] - y0) * sy) for q in p], fill=1)
        for h in holes:
            draw.polygon([((q[0] - x0) * sx, (q[1] - y0) * sy) for q in h], fill=0)
        return np.array(im, bool)

    m = mask(pa, ha) & mask(pb, hb)
    if not m.any():
        return None
    while True:                                  # erode to the interior
        er = m & np.pad(m, 1)[:-2, 1:-1] & np.pad(m, 1)[2:, 1:-1] \
               & np.pad(m, 1)[1:-1, :-2] & np.pad(m, 1)[1:-1, 2:]
        if not er.any():
            break
        m = er
    ys, xs = np.nonzero(m)
    j = len(xs) // 2
    return (x0 + xs[j] / sx, y0 + ys[j] / sy)


def _stall_release(remaining, succ, faces):
    """Pick the face to force-release at a topological stall: the deepest
    member of a SOURCE strongly-connected component of the remaining
    subgraph. At a stall every source component IS a cycle, and only its
    members may jump the queue — releasing the globally deepest remaining
    face instead can violate the direct constraints of faces merely blocked
    downstream (3960's far-rim dome facets were released ahead of the rim's
    interior far wall that way, got clipped behind it, and left a dark
    sawtooth band along the rim)."""
    rem = remaining if isinstance(remaining, set) else set(remaining)
    index, low, comp_id = {}, {}, {}
    onstk, stk, ncomp = set(), [], 0
    for root in rem:                             # iterative Tarjan
        if root in index:
            continue
        index[root] = low[root] = len(index)
        stk.append(root); onstk.add(root)
        work = [(root, iter(succ[root]))]
        while work:
            v, it = work[-1]
            child = None
            for w in it:
                if w not in rem:
                    continue
                if w not in index:
                    child = w
                    break
                if w in onstk:
                    low[v] = min(low[v], index[w])
            if child is not None:
                index[child] = low[child] = len(index)
                stk.append(child); onstk.add(child)
                work.append((child, iter(succ[child])))
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                while True:
                    w = stk.pop(); onstk.discard(w)
                    comp_id[w] = ncomp
                    if w == v:
                        break
                ncomp += 1
    comp_size = [0] * ncomp
    comp_in = [0] * ncomp
    for v in rem:
        comp_size[comp_id[v]] += 1
    for v in rem:
        for w in succ[v]:
            if w in rem and comp_id[w] != comp_id[v]:
                comp_in[comp_id[w]] += 1
    cand = [v for v in rem
            if comp_in[comp_id[v]] == 0 and comp_size[comp_id[v]] > 1]
    return max(cand or rem, key=lambda i: faces[i]["depth"])


def order_faces(faces, ray_origin=None, fwd=None, eps=1e-6, own_occ=None):
    """Witness-depth (Newell-style) paint ordering, replacing the mean-depth
    painter sort AND the occlusion cull: for every screen-overlapping pair,
    compare surface depths AT a point inside the overlap and require the
    farther face to paint first (topological sort). A fully hidden face
    simply paints early and is covered; a partially visible one shows exactly
    its uncovered part — no cull, so no over-cull.

    Depth at the witness: planar faces via their affine screen-depth plane;
    analytic faces via their OWN occluder along the witness ray (exact curved
    surface). Ties within eps add no constraint; cycles (rare, from
    interpenetrating LDraw subparts) break farthest-first. Stamps
    face['order'] (respected by fill_ops) and returns faces in paint order."""
    n = len(faces)
    dfs = [_plane_depth_fn(f) for f in faces]
    own_occ = own_occ or {}

    def depth_at(i, x, y):
        f = faces[i]
        occ = own_occ.get(id(f))
        if occ is not None and ray_origin is not None:
            O = ray_origin(np.array([x], float), np.array([y], float))
            # an interior far-half wall IS the far intersection; the near hit
            # is the front wall and would order it as if it were in front
            if f.get("interior") and hasattr(occ, "depth_far"):
                d = float(np.asarray(occ.depth_far(O, fwd), float)[0])
                if not np.isfinite(d):
                    # witness ray crosses the circle above/below the finite
                    # wall (e.g. over a stud's top disc): use the unclamped
                    # far hit as an ordering proxy so the interior wall still
                    # sorts behind the surfaces that cap it
                    d = float(np.asarray(occ.depth_far(O, fwd, clamp=False),
                                         float)[0])
            else:
                d = float(np.asarray(occ.depth(O, fwd), float)[0])
            if np.isfinite(d):
                return d
        return dfs[i](x, y)

    succ = defaultdict(set)
    indeg = [0] * n
    for i in range(n):
        for j in range(i + 1, n):
            w = _overlap_witness(faces[i]["poly"], faces[j]["poly"],
                                 ha=faces[i].get("holes") or (),
                                 hb=faces[j].get("holes") or ())
            if w is None:
                continue
            di, dj = depth_at(i, *w), depth_at(j, *w)
            if abs(di - dj) <= eps:
                continue                         # coplanar at witness: no edge
            a, b = (i, j) if di > dj else (j, i)  # farther paints first
            if b not in succ[a]:
                succ[a].add(b)
                indeg[b] += 1

    ready = [(-faces[i]["depth"], i) for i in range(n) if indeg[i] == 0]
    heapq.heapify(ready)
    out, done = [], [False] * n
    remaining = set(range(n))
    while len(out) < n:
        if not ready:                            # cycle: release a member
            k = _stall_release(remaining, succ, faces)
            heapq.heappush(ready, (-faces[k]["depth"], k))
            indeg[k] = 0
        _, i = heapq.heappop(ready)
        if done[i]:
            continue
        done[i] = True
        out.append(i)
        remaining.discard(i)
        for j in succ[i]:
            indeg[j] -= 1
            if indeg[j] == 0 and not done[j]:
                heapq.heappush(ready, (-faces[j]["depth"], j))
    for k, i in enumerate(out):
        faces[i]["order"] = k
    return [faces[i] for i in out]


MIN_FRAG_AREA = 0.2     # px^2: visible fragments smaller than this are noise


def _radial_focal_stops(samples, style, nbins=8):
    """Focal point + binned stops for a dome group's radial gradient.

    For a spherical cap, Lambert brightness is LINEAR in projected position,
    so a least-squares fit b ~ b0 + beta.(u,v) recovers the true bright-side
    direction and strength. The focal point goes up the fitted slope (scaled
    by how much of the group's brightness range the slope explains), which
    puts the FAR silhouette in the darkest stop. Without this, stops averaged
    per concentric band mix azimuths: the dome's edge-on fold facets came out
    too light and their faceted boundary spiked visibly against the dark rim
    wall (3960).

    Stops are parameterized exactly as SVG samples a focal radial gradient:
    t at a point q is |q-f| over the distance from f to the unit circle
    along the ray through q (per-sample quadratic); each stop's tone is the
    bin's mean brightness through style.ramp_b."""
    pts = np.array([p for p, _ in samples], float)
    nvs = [np.asarray(n, float) for _, n in samples]
    L = getattr(style, "light", None)
    if L is not None and len(pts) >= 3:
        b = np.array([max(0.0, float(n @ np.asarray(L, float))) for n in nvs])
        A = np.column_stack([np.ones(len(pts)), pts])
        # rcond clamps near-degenerate directions (e.g. samples lying along a
        # line) so the fitted slope stays in the well-determined subspace
        coef, *_ = np.linalg.lstsq(A, b, rcond=0.05)
        beta = coef[1:]
        rng = float(b.max() - b.min())
        bn = float(np.hypot(*beta))
        m = min(0.7, 1.2 * bn / (rng + 1e-9)) if rng > 1e-9 else 0.0
        f = beta / (bn or 1.0) * m
    else:
        b = np.zeros(len(pts))
        f = np.zeros(2)
    d = pts - f
    a = np.einsum("ij,ij->i", d, d)
    b2 = 2.0 * (d @ f)
    c = float(f @ f) - 1.0
    disc = np.maximum(b2 * b2 - 4 * a * c, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(a > 1e-12, (-b2 + np.sqrt(disc)) / (2 * a), np.inf)
        ts = np.clip(np.where(s > 1e-9, 1.0 / s, 0.0), 0.0, 1.0)
    ramp_b = getattr(style, "ramp_b", None)
    bins = defaultdict(list)
    for t, bv, n in zip(ts, b, nvs):
        bins[min(int(t * nbins), nbins - 1)].append((bv, n))
    stops = []
    for bi in sorted(bins):
        if ramp_b is not None:
            color = ramp_b(float(np.mean([bv for bv, _ in bins[bi]])))
        else:
            n = np.mean([n for _, n in bins[bi]], axis=0)
            color = style.ramp(n / (np.linalg.norm(n) or 1.0))
        stops.append(((bi + 0.5) / nbins, color))
    if stops:
        stops = [(0.0, stops[0][1])] + stops + [(1.0, stops[-1][1])]
    return stops, (float(f[0]), float(f[1]))


def fill_ops(faces, style):
    """Fill ops with exact visible-fragment clipping and per-surface merging.

    1) paint order: witness order when stamped, else far->near mean depth;
    2) CLIP nearest-first: each face's fragment = its polygon minus the union
       of everything nearer — the SVG contains zero hidden geometry;
    3) MERGE fragments sharing a facet-group id (smooth or coplanar groups
       share one gradient/tone by construction) via polygon union — one
       element per visually continuous surface. Union is robust to the
       T-junction tessellations and projected self-overlap that killed
       boundary tracing (see the 2026-07-05 spec).
    Ops emit farthest-first; fragments are disjoint, so order only decides
    which anti-alias stroke wins along shared boundaries.
    Flat faces: {'d','fill','depth'}; gradient faces: {'d','gradient','depth'}
    with gradient {'x1','y1','x2','y2','stops':[(offset,color),...]}."""
    if faces and all("order" in f for f in faces):
        ordered = sorted(faces, key=lambda f: f["order"])
    else:
        ordered = sorted(faces, key=lambda f: -f["depth"])

    frags = {}
    cover = None
    for idx in range(len(ordered) - 1, -1, -1):        # nearest first
        f = ordered[idx]
        g = geom2d.to_geom(f["poly"], f.get("holes"))
        if g.is_empty:
            continue
        frag = g if cover is None else geom2d.difference(g, cover)
        if geom2d.area(frag) >= MIN_FRAG_AREA:
            frags[idx] = frag
        cover = g if cover is None else geom2d.union(cover, g)

    members = defaultdict(list)                        # merge key -> indices
    for idx in sorted(frags):
        f = ordered[idx]
        key = f.get("group")
        members[("g", key) if key is not None else ("i", idx)].append(idx)

    ops, emitted = [], set()
    for idx in sorted(frags):                          # farthest-first
        if idx in emitted:
            continue
        f = ordered[idx]
        key = f.get("group")
        ks = members[("g", key) if key is not None else ("i", idx)]
        emitted.update(ks)
        geom = frags[ks[0]] if len(ks) == 1 else \
            geom2d.union_all([frags[j] for j in ks])
        d = geom2d.path_d(geom)
        if not d:
            continue
        if "grad_radial" in f:
            g = f["grad_radial"]
            stops, (fx, fy) = _radial_focal_stops(f["grad_samples"], style)
            ops.append({"d": d, "depth": f["depth"],
                        "gradient": {"type": "radial", "cx": g["cx"], "cy": g["cy"],
                                     "r": g["r"], "ratio": g["ratio"],
                                     "fx": fx, "fy": fy, "stops": stops}})
        elif "grad_axis" in f:
            p0, p1 = f["grad_axis"]
            stops = sorted(((off, style.ramp(nv)) for off, nv in f["grad_samples"]),
                           key=lambda s: s[0])
            ops.append({"d": d, "depth": f["depth"],
                        "gradient": {"x1": p0[0], "y1": p0[1], "x2": p1[0], "y2": p1[1],
                                     "stops": stops}})
        else:
            ops.append({"d": d, "fill": style.tone(f["normal"]),
                        "depth": f["depth"]})
    return ops


def apply_affine_faces(faces, f, ox, oy):
    """Remap face polygons (and any gradient axis) through the fit affine."""
    out = []
    for face in faces:
        p = face["poly"]
        q = np.stack([p[:, 0] * f + ox, p[:, 1] * f + oy], axis=1)
        nf = {**face, "poly": q}
        if face.get("holes"):
            nf["holes"] = [np.stack([h[:, 0] * f + ox, h[:, 1] * f + oy], axis=1)
                           for h in face["holes"]]
        if "grad_axis" in face:
            (a0, a1) = face["grad_axis"]
            nf["grad_axis"] = ((a0[0] * f + ox, a0[1] * f + oy),
                               (a1[0] * f + ox, a1[1] * f + oy))
        if "grad_radial" in face:
            g = face["grad_radial"]
            nf["grad_radial"] = {**g, "cx": g["cx"] * f + ox,
                                 "cy": g["cy"] * f + oy, "r": g["r"] * f}
        out.append(nf)
    return out


STYLES = {"flat3": Flat3Style}


def make_style(name, part_color=(157, 157, 157)):
    return STYLES[name](part_color=part_color)


def parse_hex_color(spec, default=(157, 157, 157)):
    """'0xRRGGBB' or '#RRGGBB' or 'RRGGBB' -> (r, g, b); default on failure."""
    if not spec:
        return default
    s = str(spec).lstrip("#").lower()
    if s.startswith("0x"):
        s = s[2:]
    try:
        v = int(s, 16)
        return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
    except ValueError:
        return default


def highlight_ops(analytic, right, up, fwd, s, cx, cy, half, strength=0.15):
    """Very diffuse speculars on up-facing disc tops: soft radial gradient blobs."""
    ops = []
    for rec in analytic:
        if rec["kind"] != "disc":
            continue
        R = np.asarray(rec["R"], float)
        n = R[:, 1] / np.linalg.norm(R[:, 1])
        if abs(n @ up) < 0.5:            # not clearly up/down facing
            continue
        th = np.linspace(0, 2 * math.pi, 24)
        w = _radius_pts(rec, th, 0.0)
        px, py, _ = _project_px(w, right, up, fwd, s, cx, cy, half)
        cxp, cyp = float(px.mean()), float(py.mean())
        rr = float(max(px.max() - px.min(), py.max() - py.min()) / 2.0)
        ops.append({"cx": cxp, "cy": cyp, "r": rr, "opacity": strength})
    return ops


def remap_highlights(his, f, ox, oy, strength):
    return [{"cx": h["cx"] * f + ox, "cy": h["cy"] * f + oy, "r": h["r"] * f,
             "opacity": strength} for h in his]


def _face_samples(f, inset=0.3, max_verts=8):
    """Sample pixels for HSR: the centroid plus up to `max_verts` polygon
    vertices pulled `inset` toward it, with matching self-depths.

    The inset is load-bearing twice over: raw vertices sit ON edges shared
    with adjacent walls (tie-depth => never occluded => hidden slivers would
    survive), and inset points stay strictly inside curved-wall polygons so
    the own-occluder ray still hits the surface. Self-depth per sample comes
    from the same affine combination of the per-vertex depths `zs` (exact for
    planar faces; a chord approximation for curved ones, refined by the own
    occluder in the caller). Faces without aligned `zs` fall back to the mean
    depth."""
    poly = f["poly"]
    c = poly.mean(axis=0)
    idx = np.unique(np.linspace(0, len(poly) - 1,
                                min(len(poly), max_verts)).round().astype(int))
    pts = np.vstack([c[None, :], poly[idx] * (1 - inset) + c * inset])
    zs = f.get("zs")
    if zs is not None and len(zs) == len(poly):
        zc = float(np.mean(zs))
        ds = np.concatenate([[zc], np.asarray(zs, float)[idx] * (1 - inset) + zc * inset])
    else:
        ds = np.full(len(pts), f["depth"], float)
    return pts, ds


def cull_occluded_faces(faces, occluders, ray_origin, fwd, eps,
                        kinds=("tri",), own_occ=None):
    """Winding-independent hidden-surface removal for fill faces.

    A face is culled only when EVERY sample (centroid + inset vertices, see
    `_face_samples`) has some other occluder nearer than the face's own
    surface by more than eps. Single-sample culling is wrong in both
    directions: a stud covering just the centroid must not cull a whole top
    face (3001's top is two big tris whose centroids land inside stud
    footprints), while a fully hidden underside sliver must still die.

    Self-depth per sample prefers the face's OWN occluder along that ray (a
    curved band's interpolated depth is a chord, nearer-biased mean would make
    a wall cull itself); rays that miss the own occluder keep the interpolated
    value. The own occluder is excluded from the 'nearer?' scan; the -eps
    margin keeps coplanar neighbours (studs/tops sitting ON the plane) from
    culling a face.

    `own_occ` maps id(face) -> its occluder (analytic faces only). Faces whose
    kind is not in `kinds` pass through untouched."""
    kept = []
    kinds = set(kinds)
    own_occ = own_occ or {}
    for f in faces:
        if f.get("kind") not in kinds:
            kept.append(f)
            continue
        pts, self_d = _face_samples(f)
        O = ray_origin(pts[:, 0], pts[:, 1])
        mine = own_occ.get(id(f))
        if mine is not None:
            d_own = np.asarray(mine.depth(O, fwd), float)
            self_d = np.where(np.isfinite(d_own), d_own, self_d)
        nearest = np.full(len(pts), np.inf)
        for occ in occluders:
            if occ is mine:
                continue                          # don't let a face occlude itself
            nearest = np.minimum(nearest, occ.depth(O, fwd))
        if not bool(np.all(nearest < self_d - eps)):
            kept.append(f)
    return kept


def faces_from_tris(tri, right, up, fwd, s, cx, cy, half, cond_edges=None):
    """Camera-facing triangle faces as px-space polygons with outward view-space
    normals. Winding is trusted (repaired upstream): a triangle whose outward
    normal points away from the camera (nv[2] >= 0) is a back-face and is
    CULLED — never flipped. Flipping was the old hack that leaked bright
    top-tone slivers from hollow parts' undersides.

    `cond_edges` (type-5 conditional lines; first two rows = the edge) marks
    smooth-surface facet seams: faces joined through them get one SHARED
    linear gradient so faceted curves (50950's slope, cone bodies) shade
    smoothly instead of banding into flat tones."""
    have_seams = cond_edges is not None and len(cond_edges) > 0
    faces = []
    for v in tri:                       # v: (3,3) world coords, outward-CCW
        n = np.cross(v[1] - v[0], v[2] - v[0])
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            continue
        n = n / ln
        nv = np.array([n @ right, n @ up, n @ fwd])
        back = nv[2] > -1e-6            # back-facing or edge-on
        if back and not have_seams:
            continue
        px, py, z = _project_px(v, right, up, fwd, s, cx, cy, half)
        poly = np.stack([px, py], axis=1)
        f = {"poly": poly, "normal": nv, "depth": float(np.mean(z)),
             "zs": z, "kind": "tri", "_verts": v}
        if back:
            # Provisional: kept only if a seam joins it to a front-facing
            # smooth group (see the filter below). A facet just past the
            # silhouette fold projects INSIDE the fold; culling it cut
            # notches out of the group's fill (3960's far rim sawtooth).
            f["backfill"] = True
        faces.append(f)
    _attach_smooth_gradients(faces, cond_edges if have_seams
                             else np.zeros((0, 2, 3)))
    front_groups = {f["group"] for f in faces if not f.get("backfill")}
    kept = []
    for f in faces:
        f.pop("_verts", None)
        if f.get("backfill") and not (f["group"] in front_groups
                                      and ("grad_axis" in f or "grad_radial" in f)):
            continue                    # hidden underside, not fold spillover
        kept.append(f)
    return kept


def _edge_key(a, b):
    ka, kb = tuple(np.round(a, 3)), tuple(np.round(b, 3))
    return (ka, kb) if ka <= kb else (kb, ka)


def _seam_edge_mask(A, B, cond_edges, tol=2e-3):
    """Boolean per edge (A[i]->B[i]): does it LIE ON some conditional-line
    segment? Exact endpoint matching fails in practice — part files subdivide
    facet edges (a tri edge is often HALF of the authored cond line) and mix
    coordinate precision — so match geometrically: both endpoints within tol
    of the cond segment."""
    E = len(A)
    mask = np.zeros(E, bool)
    for e in cond_edges:
        p = np.asarray(e[0], float); q = np.asarray(e[1], float)
        d = q - p
        L2 = float(d @ d)
        if L2 < 1e-12:
            continue
        todo = ~mask
        if not todo.any():
            break
        for P in (A, B):
            t = np.clip(((P - p) @ d) / L2, 0.0, 1.0)
            close = P - (p + t[:, None] * d)
            near = np.einsum("ij,ij->i", close, close) < tol * tol
            todo = todo & near
        mask |= todo
    return mask


def _attach_radial_gradient(faces, ks, front, nvs):
    """Shared radial-gradient spec for a dome-like group: unit-circle gradient
    space mapped to the group's bounding ellipse (center c0, semi-axes r and
    r*ratio). The extent covers ALL members (backfill facets included, so the
    gradient reaches the true fold); samples carry the FRONT members' normals
    at their normalized elliptic radii. All members share one dict, so
    trace's def-dedup keeps one def."""
    allv = np.vstack([faces[k]["poly"] for k in ks])
    c0 = (allv.min(axis=0) + allv.max(axis=0)) / 2.0
    w = float(allv[:, 0].max() - allv[:, 0].min()) or 1.0
    h = float(allv[:, 1].max() - allv[:, 1].min()) or 1.0
    ratio = h / w
    dx = allv[:, 0] - c0[0]
    dy = (allv[:, 1] - c0[1]) / ratio
    r = float(np.hypot(dx, dy).max()) or 1.0
    # samples carry each member's centroid in UNIT-ellipse coords (affine-
    # invariant under the uniform output fit) plus its normal; fill_ops picks
    # the focal point and stop tones from these with the style's light.
    samples = []
    for k, nv in zip(front, nvs):
        c = faces[k]["poly"].mean(axis=0)
        u = (c[0] - c0[0]) / r
        v = (c[1] - c0[1]) / (r * ratio)
        samples.append(((float(u), float(v)), nv))
    spec = {"cx": float(c0[0]), "cy": float(c0[1]), "r": r, "ratio": ratio}
    for k in ks:
        faces[k]["grad_radial"] = spec
        faces[k]["grad_samples"] = samples


def _attach_smooth_gradients(faces, cond_edges, min_spread=0.002):
    """Union faces across conditional-line seams; give each group one shared
    gradient (same axis + stops for every member — userSpaceOnUse gradients
    make the facets blend seamlessly without polygon union). Groups whose
    normals barely vary (min_spread on 1-cos) stay flat-toned."""
    parent = list(range(len(faces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_edge = defaultdict(list)
    edge_pts = []
    edge_ids = []
    for k, f in enumerate(faces):
        v = f["_verts"]
        for a, b in ((v[0], v[1]), (v[1], v[2]), (v[2], v[0])):
            ek = _edge_key(a, b)
            by_edge[ek].append(k)
            edge_pts.append((np.asarray(a, float), np.asarray(b, float)))
            edge_ids.append(ek)
    if edge_pts:
        A = np.stack([p[0] for p in edge_pts])
        B = np.stack([p[1] for p in edge_pts])
        on_seam = _seam_edge_mask(A, B, cond_edges)
        seam_keys = {edge_ids[i] for i in np.flatnonzero(on_seam)}
    else:
        seam_keys = set()
    for ek, ks in by_edge.items():
        for k in ks[1:]:
            # union across a seam always; across an ordinary shared edge only
            # when coplanar (quad halves meet at a diagonal, which is never a
            # conditional line) — coplanar union can't cross a real crease
            coplanar = float(faces[ks[0]]["normal"] @ faces[k]["normal"]) > 0.9999
            if ek not in seam_keys and not coplanar:
                continue
            ra, rb = find(ks[0]), find(k)
            if ra != rb:
                parent[rb] = ra

    groups = defaultdict(list)
    for k in range(len(faces)):
        faces[k]["group"] = find(k)     # merge key for fill_ops union
        groups[find(k)].append(k)
    for ks in groups.values():
        # gradients are derived from FRONT members only: backfill facets
        # (past the silhouette fold) extend the group's fill area, but their
        # away-facing normals would poison spread, dome detection, and stops
        front = [k for k in ks if not faces[k].get("backfill")]
        if len(front) < 2:
            continue
        nvs = [faces[k]["normal"] for k in front]
        cs = [faces[k]["poly"].mean(axis=0) for k in front]
        spread = max((1.0 - float(a @ b) for a in nvs for b in nvs), default=0.0)
        if spread < min_spread:
            continue                    # effectively flat: keep flat tones
        # LINEAR gradients only fit groups whose normals vary along ONE
        # direction (cylinder-like strips). A dome's normals spread in 2-D:
        # projecting them onto any single axis mixes different tones at the
        # same offset and stripes/bands (3960's dish). Detect via the normal
        # cloud's second singular value and use a RADIAL gradient instead.
        Nn = np.asarray(nvs, float)
        Nc = Nn - Nn.mean(axis=0)
        sn = np.linalg.svd(Nc, full_matrices=False, compute_uv=False)
        if len(sn) > 1 and sn[0] > 1e-9 and sn[1] / sn[0] > 0.35:
            _attach_radial_gradient(faces, ks, front, nvs)
            continue
        # gradient axis = principal direction of centroid spread in SCREEN
        # space (silhouette-to-silhouette, like analytic cylinder walls) —
        # picking the most-divergent NORMAL pair can yield a near-degenerate
        # or skewed screen axis on wide groups (cone bodies) and streak
        C = np.asarray(cs, float)
        Cc = C - C.mean(axis=0)
        _, _, Vt = np.linalg.svd(Cc, full_matrices=False)
        d0 = Vt[0]
        t = Cc @ d0
        p0 = tuple((C.mean(axis=0) + t.min() * d0).tolist())
        p1 = tuple((C.mean(axis=0) + t.max() * d0).tolist())
        axis = np.array([p1[0] - p0[0], p1[1] - p0[1]])
        L2 = float(axis @ axis) or 1.0
        samples = sorted(
            ((float(np.clip(((c[0] - p0[0]) * axis[0] + (c[1] - p0[1]) * axis[1])
                            / L2, 0.0, 1.0)), nv)
             for c, nv in zip(cs, nvs)), key=lambda t: t[0])
        ga = (p0, p1)
        for k in ks:
            faces[k]["grad_axis"] = ga
            faces[k]["grad_samples"] = samples
