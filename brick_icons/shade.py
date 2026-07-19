from __future__ import annotations

import heapq
import math
from collections import Counter, defaultdict

import numpy as np
from PIL import Image, ImageDraw

from . import geom2d, primitives


def faces_from_analytic(analytic, proj):
    """Fill faces for analytic primitives, with smooth wall chains merged to
    single faces (see primitives.merge_smooth_walls)."""
    return [f for prim in primitives.merge_smooth_walls(analytic)
            for f in prim.faces(proj)]


def _hex(rgb):
    r, g, b = (max(0, min(255, round(c))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


class ShadingStyle:
    def tone(self, nv) -> str:
        raise NotImplementedError


class Flat3Style(ShadingStyle):
    """Flat faces: three tones by dominant orientation (top / lit side /
    shadow side). Curved faces (cylinder walls) shade with a smooth Lambert
    ramp via `ramp`. `light` is a VIEW-space unit vector (see light_vector);
    the default is upper-left, toward the viewer. The flat side tones are
    stylized constants — the light picks WHICH side is the lit one and
    drives the curved ramps; it does not re-derive the palette."""
    def __init__(self, part_color=(157, 157, 157), light=None):
        self.part_color = tuple(part_color)
        self.top = _hex([c * 1.30 for c in part_color])
        bright = _hex([c * 0.85 for c in part_color])
        dark = _hex([c * 0.60 for c in part_color])
        if light is None:
            light = np.array([-0.5, 0.6, -0.62])
        L = np.asarray(light, float); self.light = L / np.linalg.norm(L)
        lit_left = self.light[0] <= 0
        self.left = bright if lit_left else dark
        self.right = dark if lit_left else bright

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


def order_faces(faces, proj=None, eps=1e-6, own_occ=None):
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
        if occ is not None and proj is not None:
            O = proj.ray_origin(np.array([x], float), np.array([y], float))
            # an interior far-half wall IS the far intersection; the near hit
            # is the front wall and would order it as if it were in front
            if f.get("interior") and hasattr(occ, "depth_far"):
                d = float(np.asarray(occ.depth_far(O, proj.fwd), float)[0])
                if not np.isfinite(d):
                    # witness ray crosses the circle above/below the finite
                    # wall (e.g. over a stud's top disc): use the unclamped
                    # far hit as an ordering proxy so the interior wall still
                    # sorts behind the surfaces that cap it
                    d = float(np.asarray(occ.depth_far(O, proj.fwd,
                                                       clamp=False),
                                         float)[0])
            else:
                d = float(np.asarray(occ.depth(O, proj.fwd), float)[0])
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


def _face_depth_probe(face, proj, fit):
    """pts(N,2) canvas px -> surface camera depth per point, or None.

    Flat faces (they carry a view normal) fit an exact plane through their
    projected vertices; wall faces query their primitive's analytic occluder
    through the render Projection (undoing the canvas fit affine first)."""
    poly, zs = np.asarray(face["poly"], float), np.asarray(face.get("zs", ()), float)
    if "normal" in face and len(zs) == len(poly) and len(poly) >= 3:
        A = np.column_stack([poly[:, 0], poly[:, 1], np.ones(len(poly))])
        try:
            coef, *_ = np.linalg.lstsq(A, zs, rcond=None)
        except np.linalg.LinAlgError:
            return None
        resid = np.abs(A @ coef - zs)
        if resid.max() > 1e-3 * (abs(zs).max() + 1.0):
            return None                       # not actually planar: bail out
        return lambda pts: pts @ coef[:2] + coef[2]
    prim = face.get("prim")
    occ = prim.occluder() if prim is not None else None
    if occ is None or proj is None or fit is None:
        return None
    f, ox, oy = fit

    def probe(pts):
        xs = (pts[:, 0] - ox) / f
        ys = (pts[:, 1] - oy) / f
        return occ.depth(proj.ray_origin(xs, ys), proj.fwd)
    return probe


def _refine_order_clips(ordered, geoms, frags, proj, fit, step=1.2):
    """Fix clips the scalar paint order got wrong.

    A face that passes THROUGH other geometry (3673's pin barrel runs through
    its collar) admits no correct total order: with a single scalar it
    subtracts regions where it is actually behind. For each region a face
    lost, grid-sample true surface depths: where EVERY covering face is
    absent (its surface misses the ray — a wall span polygon overhangs its
    own silhouette) or verifiably behind, hand the cells back to the front
    face and cut them out of the impostors. The cell boundary is blocky, but
    faces genuinely in front keep their exact fragments and paint later, so
    they overpaint the ragged edge; order-consistent clips are untouched."""
    if not geoms:
        return
    depths = [f["depth"] for f in ordered]
    eps = 0.02 * ((max(depths) - min(depths)) or 1.0)
    probes = {}

    def probe(idx):
        if idx not in probes:
            probes[idx] = _face_depth_probe(ordered[idx], proj, fit)
        return probes[idx]

    import shapely as _sh
    from shapely.geometry import box
    for idx in sorted(geoms):
        g = geoms[idx]
        lost = geom2d.difference(g, frags[idx]) if idx in frags else g
        if geom2d.area(lost) < 4 * MIN_FRAG_AREA or probe(idx) is None:
            continue
        x0, y0, x1, y1 = lost.bounds
        gx = np.arange(x0 + step / 2, x1, step)
        gy = np.arange(y0 + step / 2, y1, step)
        if not len(gx) or not len(gy):
            continue
        XX, YY = np.meshgrid(gx, gy)
        pts = np.stack([XX.ravel(), YY.ravel()], 1)
        pts = pts[_sh.contains_xy(lost, pts[:, 0], pts[:, 1])]
        if not len(pts):
            continue
        di = probe(idx)(pts)
        exposed = np.isfinite(di)                     # no coverer in front yet
        coverers = []
        # scan ALL other faces: true depth is the authority here, and an
        # impostor's real occluder sits at a LOWER paint order by definition
        for j in sorted(geoms):
            if j == idx or not exposed.any():
                continue
            inter = geom2d.intersection(lost, geoms[j])
            if geom2d.area(inter) < MIN_FRAG_AREA:
                continue
            sel = _sh.contains_xy(inter, pts[:, 0], pts[:, 1])
            pj = probe(j)
            if pj is None:                            # can't verify: trust order
                exposed &= ~sel
                continue
            if not sel.any():
                continue
            dj = np.full(len(pts), np.inf)
            dj[sel] = pj(pts[sel])
            in_front = sel & np.isfinite(dj) & (dj <= di + eps)
            exposed &= ~in_front
            coverers.append((j, sel))
        if not exposed.any():
            continue
        cells = [box(p[0] - step / 2, p[1] - step / 2,
                     p[0] + step / 2, p[1] + step / 2)
                 for p in pts[exposed]]
        # buffer past the cell lattice so no impostor frame survives along
        # the region boundary; bleed into a true front face is harmless —
        # it paints later and overpaints the overshoot exactly
        take = geom2d.intersection(
            geom2d.union_all(cells).buffer(step * 0.75), lost)
        if geom2d.area(take) < 4 * MIN_FRAG_AREA:
            continue
        frags[idx] = geom2d.union(frags[idx], take) if idx in frags else take
        for j, _ in coverers:                          # impostors lose the cells
            if j in frags:
                cut = geom2d.difference(frags[j], take)
                if geom2d.area(cut) >= MIN_FRAG_AREA:
                    frags[j] = cut
                elif geom2d.area(geom2d.intersection(frags[j], take)) > 0:
                    del frags[j]


def _ell_pts(op, t0, t1, step=1.0):
    """Sample an arc op's ellipse over [t0, t1] degrees (canvas space)."""
    n = max(3, int(abs(t1 - t0) / step) + 1)
    ts = np.radians(np.linspace(t0, t1, n))
    return np.stack([op[1] + np.cos(ts) * op[3] + np.sin(ts) * op[5],
                     op[2] + np.cos(ts) * op[4] + np.sin(ts) * op[6]], axis=1)


def refit_fill_boundaries(geoms, refits):
    """Move fill seams onto refit separators (hlr._snap_rim_crossings pass 2).

    The stroke for a counterbore's wall/annulus separator is redrawn as a
    bore-aspect arc; the region between the old (true projected) curve and
    the new one must swap sides so the tone boundary lands under the stroke.
    geoms: {key: shapely geom} fill fragments, same space as the refit ops."""
    from shapely import Point
    out = dict(geoms)
    for old, new, bore in refits:
        # transfer zone: area between the two curves (bore hole excluded)
        old_pts = _ell_pts(old, old[7], old[8])
        new_pts = _ell_pts(new, new[7], new[8])
        if (np.linalg.norm(old_pts[0] - new_pts[0])
                > np.linalg.norm(old_pts[0] - new_pts[-1])):
            new_pts = new_pts[::-1]
        zone = geom2d.region(np.vstack([old_pts, new_pts[::-1]]))
        zone = geom2d.difference(zone, geom2d.to_geom(_ell_pts(bore, 0, 360)))
        if geom2d.area(zone) <= 0:
            continue
        disk_new = geom2d.to_geom(_ell_pts(new, 0, 360))
        # owners: fragments just inside/outside the new arc at its apex
        cN = np.array(new[1:3])
        apex = _ell_pts(new, (new[7] + new[8]) / 2.0, (new[7] + new[8]) / 2.0)[0]
        p_in, p_out = (Point(*(cN + s * (apex - cN))) for s in (0.97, 1.03))
        ann = next((k for k, g in out.items() if g.contains(p_in)), None)
        wal = next((k for k, g in out.items() if g.contains(p_out)), None)
        if ann is None or wal is None or ann == wal:
            continue
        # the swap booleans leave pinhole rings where the zone boundary
        # re-traces the same curves at a different sampling phase; close
        # them at a radius-scaled eps or they bloat the SVG (tick marks)
        r_new = (math.hypot(new[3], new[4]) + math.hypot(new[5], new[6])) / 2.0
        eps = min(0.1, 0.002 * r_new)
        out[ann] = geom2d.close_slivers(
            geom2d.union(geom2d.difference(out[ann], zone),
                         geom2d.intersection(zone, disk_new)), eps)
        out[wal] = geom2d.close_slivers(
            geom2d.union(geom2d.difference(out[wal], zone),
                         geom2d.difference(zone, disk_new)), eps)
    return out


# Residue thresholds are in OUTPUT px (canvas units, the space faces are in
# when fill_ops is called): what junk is visible at label scale is set by
# the output stroke widths (2 px edges, 0.8 px fill self-stroke), not by the
# projection resolution — scaling these by the proj->canvas fit made the
# gates resolution-dependent (render_px 2048 kept junk that 900 culled).
# ERODE ~0.3x edge stroke: anything locally thinner is unreadable.
# MIN_AREA keeps morphological-opening shavings at corners (~r^2) from
# counting as residue and churning every boundary.
RESIDUE_ERODE = 0.6
RESIDUE_MIN_AREA = 0.8
# CRUMB: at emission, per-PIECE erosion radius — booleans along
# near-coincident boundaries shed hairline crumbs every pass, and arc
# snapping can inflate a crumb into a visible dash. Fills are SELF-STROKED
# 0.8 px to close AA seams, so a hairline piece paints at stroke width no
# matter how thin — the radius is half that. A wide-bodied thin-tipped
# piece (counterbore crescent) survives whole: a per-piece TEST, not a trim.
RESIDUE_CRUMB = 0.4
# SPUR: max VISIBLE area (outside the drawn ink) of an escaped-seam spur
# that donation may hand across the seam (see _donate_escaped_spurs).
# Nub-class artifacts are a few px^2; bigger sub-stroke-thin regions are
# long legitimate strips (3673's barrel lens, silhouette bands) where a
# tone swap would be a visible regression.
SPUR_MAX_AREA = 8.0
# a seam exactly at the ink edge still shows: the fill's 0.8px self-stroke
# overhangs 0.4 past its boundary, plus ~a raster pixel of AA. Coverage
# demands the seam sit this far INSIDE the drawn stroke.
SPUR_COVER_MARGIN = 0.5


def _merge_members(ordered, frags):
    """Merge keying for emitted fill elements: facet-group id, else identity.
    FLAT tri faces additionally union by carrier plane — subpart tilings abut
    with no shared edge (T-junctions), so edge-adjacency grouping leaves one
    wall split into same-tone fills whose antialiased joints read as faint
    seams at label sizes (3700's side face). Gradient groups are excluded:
    their fills differ even when members share a plane.
    Returns (members: root -> [frag idx], roots: frag idx -> root)."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    keys = {}
    for idx in sorted(frags):
        f = ordered[idx]
        g = f.get("group")
        keys[idx] = ("g", g) if g is not None else ("i", idx)
        find(keys[idx])
        if (f.get("plane") is not None and "grad_axis" not in f
                and "grad_radial" not in f):
            ra, rb = find(("p", f["plane"])), find(keys[idx])
            if ra != rb:
                parent[rb] = ra
    members, roots = defaultdict(list), {}
    for idx in sorted(frags):
        roots[idx] = find(keys[idx])
        members[roots[idx]].append(idx)
    return members, roots


def _contour_region(geoms, arcs):
    """The region the drawn silhouette contour encloses: union of every
    face polygon, sliver-closed and with boundary runs snapped onto the
    arc candidates — the geometry contour_d strokes. Where arc recovery
    pulls the drawn outline inside the raw silhouette (a faceted corner
    against a fitted arc), the difference matters: fills exist out to the
    raw boundary but the outline stroke covers only the snapped curve."""
    U = geom2d.close_slivers(geom2d.union_all(list(geoms.values())))
    if U is None or U.is_empty:
        return U
    polys = []
    for poly in getattr(U, "geoms", [U]):
        if poly.geom_type != "Polygon" or poly.is_empty:
            continue
        sh = np.asarray(poly.exterior.coords, float)[:-1]
        hs = [np.asarray(r.coords, float)[:-1] for r in poly.interiors]
        polys.append(geom2d.to_geom(
            geom2d.densify_on_arcs(sh, arcs),
            [geom2d.densify_on_arcs(h, arcs) for h in hs]))
    return geom2d.union_all(polys) if polys else U


def _trim_safe(p, ks, frags, geoms, sil, ink=None):
    """May the dead (locally sub-stroke) part `p` of a visible surface be
    trimmed away? Trimming hands the area to whatever the re-clip finds
    beneath, or to the background — only sound when that replacement paints
    like the surroundings. Two sound cases:
    - silhouette overhang: nothing else covers `p` and it lies mostly
      OUTSIDE `sil`, the region the drawn contour encloses (sliver-closed,
      arc-snapped silhouette) — dropping it reads as background past the
      drawn outline. A strip INSIDE the contour must stay: dropping it
      punches a white pinhole between the fills and the outline stroke
      (3941's base-rim sliver);
    - absorbed by a visible neighbor: `p` is covered by deeper faces and
      the claimant (nearest-behind, who the re-clip hands the area to)
      already paints adjacent to `p`, so its fill continues seamlessly.
    Anything else keeps the owner's fill — correct tone, authored
    boundaries under the strokes. Without this, 3941's top-face pinch fell
    to HIDDEN interior faces whose grid-edged fills nubbed past the stroke
    cover, and a band strip with no claimant at all dropped to a white
    pinhole."""
    import shapely as _sh
    others = [i for i in geoms if i not in ks and geoms[i].intersects(p)]
    cover = geom2d.union_all([geoms[i] for i in others]) if others else None
    ca = geom2d.area(geom2d.intersection(p, cover)) if cover is not None \
        else 0.0
    if ca <= 0.05 * p.area:
        if sil is None:
            return True
        inside = geom2d.area(geom2d.intersection(p, sil))
        return inside < 0.5 * p.area
    if ca < 0.95 * p.area:
        return False               # mixed: part of it would drop to white
    x0, y0, x1, y1 = p.bounds
    XX, YY = np.meshgrid(np.arange(x0 + 0.5, x1, 1.0),
                         np.arange(y0 + 0.5, y1, 1.0))
    pts = np.stack([XX.ravel(), YY.ravel()], 1) if XX.size else \
        np.zeros((0, 2))
    if len(pts):
        pts = pts[_sh.contains_xy(p, pts[:, 0], pts[:, 1])]
    if not len(pts):
        rp = p.representative_point()
        pts = np.array([[rp.x, rp.y]])
    votes = ok = 0
    claimants = Counter()
    for x, y in pts[:32]:
        cs = [i for i in others if _sh.contains_xy(geoms[i], x, y)]
        if not cs:
            continue
        votes += 1
        c = max(cs)                # nearest-behind: the re-clip's claimant
        fc = frags.get(c)
        if fc is not None and fc.distance(_sh.Point(x, y)) < 1.5:
            ok += 1
            claimants[c] += 1
    if not (votes > 0 and ok * 2 >= votes):
        return False
    if ink is None:
        return True
    show = geom2d.difference(p, ink)
    if geom2d.area(show) <= 0.05:
        return True                # drops under drawn ink: invisible
    # the piece SHOWS, so the claimant must also RETAIN it: handed to a
    # claimant on whose fragment it is again a locally sub-stroke flap
    # (edge contact past the claimant's own boundary, not authored overlap
    # above its surface), the next residue round trims it from the claimant
    # with nothing beneath — two locally sound handoffs jointly baring
    # background inside the part (30137's stud-graze strip: top face ->
    # log-column wall -> white needle under the back-edge arc).
    fc = frags.get(claimants.most_common(1)[0][0])
    if fc is None:
        return False
    fused = geom2d.opened(geom2d.union(fc, p), RESIDUE_ERODE)
    return geom2d.area(geom2d.difference(show, fused)) <= 0.05


def _residue_trims(ordered, frags, garea, geoms=None, sil=None,
                   ink=None):
    """Per-face residue regions: parts of each MERGED surface's visible area
    that vanish under morphological opening (locally thinner than ~2x
    RESIDUE_ERODE) and are big enough to matter. These are authored-overlap
    leftovers (a ring spanning slot mouths, plate tris overhanging a drawn
    rim), not drawable detail — LDraw parts overlap surfaces freely and rely
    on z-fighting being invisible. Tested on the merged element so a thin
    tile FUSED into a big wall polygon never counts as residue. With `geoms`
    (all faces' pre-clip polygons) and `sil` (the drawn-contour region:
    sliver-closed, arc-snapped silhouette), each candidate part must also
    pass _trim_safe — genuine visible pinches of a surface stay with it."""
    r = RESIDUE_ERODE
    min_a = RESIDUE_MIN_AREA
    members, _ = _merge_members(ordered, frags)
    trims = {}
    for ks in members.values():
        G = frags[ks[0]] if len(ks) == 1 else \
            geom2d.union_all([frags[j] for j in ks])
        live = geom2d.opened(G, r)
        if live.is_empty:
            # the whole surface is sub-stroke. If the surface is MOSTLY
            # VISIBLE it is thin by nature (a narrow silhouette band) —
            # deleting it would punch a hole in the drawing, keep it. If it
            # is the sub-stroke remnant of a mostly-hidden surface (3941's
            # top ring surviving as crescents over the slot mouths), it is
            # all residue.
            full = sum(garea.get(j, 0.0) for j in ks)
            if full <= 0.0 or geom2d.area(G) / full >= 0.5:
                continue
            du = G
        else:
            dead = geom2d.difference(G, live)
            parts = [p for p in getattr(dead, "geoms", [dead])
                     if p.geom_type == "Polygon" and p.area >= min_a]
            if geoms is not None:
                ks_set = set(ks)
                parts = [p for p in parts
                         if _trim_safe(p, ks_set, frags, geoms, sil, ink)]
            if not parts:
                continue
            du = geom2d.union_all(parts)
        for j in ks:
            t = geom2d.intersection(frags[j], du)
            if not t.is_empty and t.area > 0.0:
                trims[j] = t
    return trims


def _loop_cut_merged(merged, loops):
    """Confine mostly-inside elements to their stylized fold-arc loop.

    An element whose visible area lies >= half inside a closed loop (3941's
    far bore wall / wall bands seen through the axle opening) is clipped to
    it: its authored boundary projects past the drawn stylized arcs (facet
    scallops, junction wedges, parallax fringes) and the fill's self-stroke
    paints that spill beyond the black stroke. Each cut piece is ABSORBED by
    the touching mostly-outside element (the surrounding top face): dropping
    it instead leaves unpainted pinholes wherever the spill reached past the
    stroke's cover. Mostly-outside elements (a front stud overlapping the
    loop's occluded section) are never clipped."""
    L = geom2d.union_all([geom2d.region(p) for p in loops])
    interior = set()
    for r, g in merged.items():
        a = geom2d.area(g)
        if a > 0.0 and geom2d.area(geom2d.intersection(g, L)) / a >= 0.5:
            interior.add(r)
    # iterate in merged's insertion order, not set order: the keys are
    # string-bearing tuples whose set order varies with the process hash
    # seed, and absorption below unions pieces into receivers — a
    # seed-dependent order jitters ring start vertices in the output
    for r in [k for k in merged if k in interior]:
        spill = geom2d.difference(merged[r], L)
        if spill.is_empty:
            continue
        merged[r] = geom2d.intersection(merged[r], L)
        for piece in getattr(spill, "geoms", [spill]):
            if piece.geom_type != "Polygon" or piece.area <= 0.0:
                continue
            probe = piece.buffer(0.2)
            best, contact = None, 0.0
            for r2, g2 in merged.items():
                if r2 in interior:
                    continue
                c = geom2d.area(geom2d.intersection(probe, g2))
                if c > contact:
                    best, contact = r2, c
            if best is not None:
                merged[best] = geom2d.union(merged[best], piece)


def _stroke_band(strokes, sil, line_px, sil_px):
    """The region the drawn strokes cover (canvas space): every emitted
    line/arc op buffered to its width, plus the silhouette contour at
    sil width. Mirrors trace.segments_to_svg: ops shorter than 0.6x their
    stroke are skipped there (bare cap dots) and so provide no cover."""
    from shapely.geometry import LineString
    parts = []
    for op in strokes:
        if len(op) == 5:                               # legacy line tuple
            op = ("line",) + tuple(op)
        sw = sil_px if op[-1] == "sil" else line_px
        if op[0] == "line":
            _, x1, y1, x2, y2, _k = op
            if math.hypot(x2 - x1, y2 - y1) < 0.6 * sw:
                continue
            parts.append(LineString([(x1, y1), (x2, y2)]).buffer(sw / 2.0))
        else:
            r = (math.hypot(op[3], op[4]) + math.hypot(op[5], op[6])) / 2.0
            if r * math.radians(abs(op[8] - op[7])) < 0.6 * sw:
                continue
            parts.append(
                LineString(_ell_pts(op, op[7], op[8])).buffer(sw / 2.0))
    if sil is not None and not sil.is_empty:
        parts.append(sil.boundary.buffer(sil_px / 2.0))
    if not parts:
        return None, None
    import shapely as _sh
    ink = geom2d.union_all(parts)
    # coverage = ink eroded by the self-stroke overhang: a seam must sit
    # deep enough under the stroke that the fill's own 0.8px stroke stays
    # covered. Erode the UNION (junction overlaps keep their interior),
    # snapped back onto the precision grid (see geom2d.opened).
    safe = _sh.set_precision(ink.buffer(-SPUR_COVER_MARGIN), geom2d.GRID)
    return safe, ink


def _donate_escaped_spurs(merged, order, strokes, sil, line_px, sil_px):
    """Reassign fill spurs whose seam escapes the drawn strokes.

    Every seam between emitted elements is meant to lie under a drawn
    stroke or on the silhouette — the stylized drawing has no other tone
    boundaries. Clipping against TRUE geometry still leaves violations:
    parallax pockets between a surface's authored edge and the fitted
    drawn arc, and _refine_order_clips cell takes, both hand a
    later-painting element slivers past the stroke band, where its 0.8px
    self-stroke escapes the 2px cover and paints a nub on the earlier
    surface (3941's top-face nubs at the stud/rim tangency pinches).

    For each element, sub-stroke-thin protrusions of its area outside the
    stroke band (morphological opening; the spur may connect to the body
    THROUGH the uncovered gap, so piece connectivity cannot find it) whose
    border runs along the element's own boundary away from the silhouette
    are donated to the max-contact neighbor across that seam — but only
    when that neighbor paints EARLIER: the artifact is strictly the later
    painter's self-stroke on the earlier fill, and the reverse donation
    would repaint the pocket with the wrong surface's tone. Donation
    moves the seam under the stroke band; the area cap keeps legitimate
    thin strips (a barrel lens, a rim band) with their true surface."""
    import shapely as _sh
    band, ink = _stroke_band(strokes, sil, line_px, sil_px)
    if band is None:
        return
    sil_b = sil.boundary.buffer(0.5) \
        if sil is not None and not sil.is_empty else None

    def near(g, bounds, pad=0.5):
        # window a big geometry down to the work area; snap the cut back
        # onto the precision grid (off-grid booleans: see geom2d.opened)
        x0, y0, x1, y1 = bounds
        c = _sh.clip_by_rect(g, x0 - pad, y0 - pad, x1 + pad, y1 + pad)
        return _sh.set_precision(c, geom2d.GRID)

    # a donation can surface the NEXT seam: the pocket handed from the wall
    # to the top face now abuts a still-earlier junction sliver uncovered —
    # iterate to a fixpoint (donations flow strictly later->earlier, so the
    # area-weighted paint order decreases and this terminates; the cap is a
    # backstop). Only elements a donation touched need re-examination.
    dirty = set(merged)
    for _ in range(4):
        moved = False
        bnds = {r: g.bounds for r, g in merged.items()}
        for r in sorted(merged, key=order.get):        # earliest first
            if r not in dirty:
                continue
            dirty.discard(r)
            W = merged[r]
            outside = geom2d.difference(W, near(band, W.bounds, 1.0))
            if outside.is_empty:
                continue
            core = geom2d.opened(outside, 0.5 * line_px)
            thin = geom2d.difference(outside, core)
            pieces = [p for p in getattr(thin, "geoms", [thin])
                      if p.geom_type == "Polygon" and p.area > 0.05]
            if not pieces:
                continue
            Wb = W.boundary.buffer(0.02)
            for p in pieces:
                inkp = near(ink, p.bounds)
                if geom2d.area(geom2d.difference(p, inkp)) > SPUR_MAX_AREA:
                    continue                           # visibly large: real
                # a fringe that meets its own element's core in the OPEN is
                # continuous visible surface — donating it swaps tone along
                # a live edge (3941's notch-corner ticks). A true stranded
                # spur reaches its core only under the ink (or not at all).
                touch = geom2d.intersection(p.buffer(0.05),
                                            near(core, p.bounds))
                if not touch.is_empty \
                        and not geom2d.difference(touch, inkp).is_empty:
                    continue
                esc = p.boundary.intersection(near(Wb, p.bounds))
                if sil_b is not None and not esc.is_empty:
                    esc = esc.difference(near(sil_b, p.bounds, 1.0))
                if esc.is_empty or esc.length < 0.5:
                    continue
                probe = esc.buffer(0.3)
                # a HAIRLINE spur must go to a receiver that actually abuts
                # it: the contact probe tolerates a 0.3 gap, and a donated
                # sub-crumb piece separated from its receiver's fill is
                # crumb-culled at emission — an unpainted hole where the
                # spur used to paint. Wide-enough pieces survive on their
                # own, so any near receiver is safe.
                pb = p.buffer(0.05)
                need_touch = p.buffer(-RESIDUE_CRUMB).is_empty
                qx0, qy0, qx1, qy1 = probe.bounds
                best, contact = None, 0.0
                for r2, g2 in merged.items():
                    if r2 == r:
                        continue
                    bx0, by0, bx1, by1 = bnds[r2]
                    if bx1 < qx0 or bx0 > qx1 or by1 < qy0 or by0 > qy1:
                        continue
                    if need_touch and not pb.intersects(g2):
                        continue
                    c = geom2d.area(geom2d.intersection(probe, g2))
                    if c > contact:
                        best, contact = r2, c
                if best is None:
                    continue
                if order[best] >= order[r]:
                    # stranded-piece fallback: normally only the LATER
                    # painter donates (the artifact is its self-stroke on
                    # the earlier fill; the reverse donation repaints
                    # wrong). But a piece with no open link to its own
                    # core whose UNCOVERED seam runs along this single
                    # later-painting receiver is a stranded island
                    # (3941's ring-floor chips against the axle boss):
                    # taking the receiver's tone closes the only open
                    # seam, and no third surface can be misrepresented.
                    # Under-ink escapes stay put — donating them would be
                    # invisible churn.
                    esc_open = esc.difference(inkp)
                    if esc_open.is_empty or esc_open.length < 0.5:
                        continue
                    stray = esc_open.difference(
                        near(merged[best], p.bounds).buffer(0.1))
                    if stray.length > 0.05 * esc_open.length:
                        continue
                merged[r] = geom2d.difference(merged[r], p)
                merged[best] = geom2d.union(merged[best], p)
                bnds[best] = merged[best].bounds
                dirty.update((r, best))
                moved = True
        if not moved:
            break


def _ink_lens_pockets(base, vis, strokes, sil, line_px, sil_px):
    """Uncovered pockets trapped between converging drawn strokes, to be
    painted out as ink. Where stylized strokes cross or graze at a shallow
    angle they leave a thin lens neither covers; whatever tone shows in it
    (a wall taper, a white pinhole) reads as a chip in a solid-ink junction
    at label scale (3941's boss/stud pinches, frayed corners). A pocket is
    inked only when it could never read as surface: sub-stroke-thin under
    morphological opening, small, and bordered almost entirely by drawn
    ink. Exception: a pocket NO fill paints (`vis` = union of emitted fill
    geometry) is enclosed background — a white slit inside the part (the
    drawn fold arc bowing past the authored facet chord, 30137's log
    tops). Every border it has is already a visible seam, so it is inked
    regardless of the ink fraction. Wide or large openings are legitimate
    visible surface (a barrel lens, a rim band) and stay."""
    import shapely as _sh
    band, ink = _stroke_band(strokes, sil, line_px, sil_px)
    if ink is None or ink.is_empty or base is None or base.is_empty:
        return []                  # no drawn ink (e.g. zero-width strokes):
                                   # nothing for a pocket to hide inside
    open_r = geom2d.difference(base, ink)
    out = []
    for p in getattr(open_r, "geoms", [open_r]):
        if p.geom_type != "Polygon" or not 0.02 < p.area <= SPUR_MAX_AREA:
            continue
        if not geom2d.opened(p, 0.5 * line_px).is_empty:
            continue
        x0, y0, x1, y1 = p.bounds
        inkp = _sh.clip_by_rect(ink, x0 - 1, y0 - 1, x1 + 1, y1 + 1)
        exposed = p.boundary.difference(inkp.buffer(0.1))
        if exposed.length > 0.1 * p.boundary.length:
            continue
        out.append(p)
    whites = []
    if vis is not None and not vis.is_empty:
        # enclosed unpainted slits: interior HOLES of everything painted
        # (fills + ink) — white needles where the authored surface stops
        # short of the drawn curve (30137's log-top folds, and the shards
        # where the rounded back edge grazes a stud: there the pocket lies
        # outside every face polygon AND the enclosing stroke is partially
        # clipped, so only the union's holes see it). Returned separately:
        # the caller ABSORBS them into the max-contact fill, extending the
        # surface to the stroke — black ink here would read as scratches.
        # A hole thinner than the stroke can never read as an intentional
        # opening. No SPUR_MAX_AREA cap: white has no tone to
        # misrepresent (the 8x backstop fences off pathological failures).
        from shapely.geometry import box as _box
        outU = geom2d.union_all(out) if out else None
        U = geom2d.union(vis, ink)
        bx0, by0, bx1, by1 = U.bounds
        comp = geom2d.difference(_box(bx0 - 2, by0 - 2, bx1 + 2, by1 + 2), U)
        # enclosed voids = complement components that never reach the
        # outside. The opening (0.15) severs the sub-pixel leak channels
        # where a stroke band and a fill boundary converge without quite
        # touching — through which a white wedge would drain into the open
        # region and evade detection (30137's stud grazes). Slit-width
        # voids survive the opening.
        core = comp.buffer(-0.15).buffer(0.15)
        for p in getattr(core, "geoms", [core]):
            if p.geom_type != "Polygon" or p.is_empty:
                continue
            px0, py0, px1, py1 = p.bounds
            if (px0 <= bx0 - 1 or py0 <= by0 - 1
                    or px1 >= bx1 + 1 or py1 >= by1 + 1):
                continue                     # the outside, not a void
            void = geom2d.intersection(p.buffer(0.2), comp)
            if not 0.02 < geom2d.area(void) <= 8 * SPUR_MAX_AREA:
                continue
            if not geom2d.opened(void, 0.5 * line_px).is_empty:
                continue
            if outU is not None and void.within(outU.buffer(0.05)):
                continue
            whites.append(void)
    return out, whites


def _weld_junction_notches(strokes, base, line_px, sil_px, broad=False):
    """Thin uncovered notches at a multi-stroke T-graze junction, welded
    solid as ink. Where a drawn stroke terminates on the INTERIOR of
    another stroke's band (a cap graze: 30137's rear-scallop arcs and
    separator stubs dying on the stud cap rims), the converging bands trap
    a tapering sliver of surface that reads as a light chip in what should
    be one solid join (the beaked-Y junction). The sliver leaks into the
    open face region, so the enclosed-lens gates (_ink_lens_pockets)
    never see it. Weld = morphological closing of the stroke bands at
    half the stroke width, minus the bands: exactly the region pinched
    between ink closer than one stroke width — a gap that thin can never
    read as an intentional opening. Only thin pieces within reach of a
    T-graze junction are inked, and only inside `base` (the drawn part
    region): welding is a junction treatment, not a general gap-filler,
    and the silhouette's outer profile is not ours to reshape.
    Shared-vertex (V) joins do not count as junctions — every ordinary
    face corner is one, and the wedge between its bands is surface.
    Two gates keep this from restyling every corner in the library
    (vetoed 2026-07-18 — stud-cylinder limb/rim corners especially):
    the dying stroke must be a STUB (shorter than 3x its stroke width —
    30137's 6.7 deg bridge between the scallop V and the rim; a limb
    line or seam dying on a rim is long and keeps its corner), and the
    notch must touch >= 3 distinct stroke bands (the arc + stub + rim
    pile-up; a two-band tangency sliver is an ordinary corner wedge).
    `broad=True` (opt-in --weld-corners) drops both gates and welds
    every T-graze notch, the pre-veto census-P look."""
    import shapely as _sh
    from shapely import STRtree
    from shapely.geometry import LineString, Point
    bands, ends, stub, lines, sws = [], [], [], [], []
    for op in strokes:
        if len(op) == 5:                               # legacy line tuple
            op = ("line",) + tuple(op)
        sw = sil_px if op[-1] == "sil" else line_px
        if op[0] == "line":
            pts = np.array([[op[1], op[2]], [op[3], op[4]]])
            length = math.hypot(pts[1, 0] - pts[0, 0], pts[1, 1] - pts[0, 1])
            if length < 0.6 * sw:
                continue
            eps = [pts[0], pts[-1]]
        else:
            r = (math.hypot(op[3], op[4]) + math.hypot(op[5], op[6])) / 2.0
            length = r * math.radians(abs(op[8] - op[7]))
            if length < 0.6 * sw:
                continue
            pts = _ell_pts(op, op[7], op[8])
            eps = [] if abs(op[8] - op[7]) >= 359.0 else [pts[0], pts[-1]]
        ln = LineString(pts)
        bands.append(ln.buffer(sw / 2.0))
        lines.append(ln)
        sws.append(sw)
        ends.append(eps)
        stub.append(length < 3.0 * sw)
    if len(bands) < 2 or base is None or base.is_empty:
        return []

    tree = STRtree(bands)
    joins = []
    for i, eps in enumerate(ends):
        if not stub[i] and not broad:
            continue                # only a dying STUB makes a junction
        for e in eps:
            pt = Point(e)
            for j in tree.query(pt, predicate="within"):
                if j == i:
                    continue
                # shared vertex: V join (an ordinary face corner). The
                # tolerance is half the landed-on stroke's width — corner
                # endpoints land inside each other's bands but chord
                # stylization scatters them past any absolute epsilon
                # (60474's bite corner: flank end 0.79 px from the rim
                # chord's end)
                if any(np.linalg.norm(np.asarray(e2) - e) < 0.5 * sws[j]
                       for e2 in ends[j]):
                    continue
                # collinear twin: the stub lies (almost) entirely INSIDE
                # the landed-on band — duplicate/split authoring of the
                # same edge (60474's bite flank is drawn as two short
                # pieces over a full-length twin), not a stroke arriving
                # from outside. A genuine graze (30137) only pokes its
                # tip in, so most of its length stays outside the band.
                if lines[i].difference(bands[j]).length \
                        < 0.25 * lines[i].length:
                    continue
                joins.append(pt)
                break
    if not joins:
        return []
    ink = geom2d.union_all(bands)
    rc = 0.5 * line_px
    closed = _sh.set_precision(ink.buffer(rc).buffer(-rc), geom2d.GRID)
    gaps = geom2d.intersection(geom2d.difference(closed, ink), base)
    reach = 3.0 * line_px
    out = []
    for p in getattr(gaps, "geoms", [gaps]):
        if p.geom_type != "Polygon" or not 0.02 < p.area <= SPUR_MAX_AREA:
            continue
        if not geom2d.opened(p, 0.5 * line_px).is_empty:
            continue
        if not any(pt.distance(p) <= reach for pt in joins):
            continue
        pb = p.buffer(0.05)
        if broad or len(tree.query(pb, predicate="intersects")) >= 3:
            out.append(p)
    return out


def fill_ops(faces, style, clip=True, ellipses=None, proj=None, fit=None,
             refits=None, loops=None, strokes=None, line_px=2.0,
             sil_px=2.0, drop=None, weld_corners=False):
    """Fill ops with exact visible-fragment clipping and per-surface merging.

    clip=False keeps every face whole (no occlusion subtraction) for
    translucent rendering; paint order is still farthest-first so nearer
    faces blend over deeper ones.
    `ellipses` are projected circles (canvas space) for arc recovery: fill
    boundary runs sampled from them are emitted as true SVG arcs.

    1) paint order: witness order when stamped, else far->near mean depth;
    2) CLIP nearest-first: each face's fragment = its polygon minus the union
       of everything nearer — the SVG contains zero hidden geometry;
    3) RESIDUE: locally sub-stroke parts of a merged surface's visible area
       (thinner than ~RESIDUE_ERODE, morphological opening test) are authored
       overlap/near-coincidence leftovers, not drawable detail — light ticks
       down recess walls, scallops past drawn rims (3941's axle cross). The
       offending faces are trimmed by those regions and the clip re-runs, so
       DEEPER surfaces absorb the area (or it drops at the silhouette);
    4) MERGE fragments sharing a facet-group id (smooth or coplanar groups
       share one gradient/tone by construction) via polygon union — one
       element per visually continuous surface. Union is robust to the
       T-junction tessellations and projected self-overlap that killed
       boundary tracing (see the 2026-07-05 spec).
    Ops emit farthest-first; fragments are disjoint, so order only decides
    which anti-alias stroke wins along shared boundaries.
    Flat faces: {'d','fill','depth'}; gradient faces: {'d','gradient','depth'}
    with gradient {'x1','y1','x2','y2','stops':[(offset,color),...]}."""
    arcs = geom2d.arc_candidates(ellipses)
    if faces and all("order" in f for f in faces):
        ordered = sorted(faces, key=lambda f: f["order"])
    else:
        ordered = sorted(faces, key=lambda f: -f["depth"])

    g_cache = {}

    def clip_pass(trims=None):
        frags, geoms, garea = {}, {}, {}
        cover = None
        for idx in range(len(ordered) - 1, -1, -1):    # nearest first
            f = ordered[idx]
            # coarse facet rings (16-gon hole/stud surrounds) snap onto their
            # true circles BEFORE the booleans, so clips against neighboring
            # analytic faces cut along the circle instead of chords —
            # off-circle chord intersections defeat arc recovery and eat thin
            # slivers (counterbore crescent tips)
            if idx not in g_cache:
                g_cache[idx] = geom2d.to_geom(
                    geom2d.densify_on_arcs(f["poly"], arcs),
                    [geom2d.densify_on_arcs(h, arcs)
                     for h in (f.get("holes") or [])])
            g = g_cache[idx]
            if trims is not None and idx in trims:
                g = geom2d.difference(g, trims[idx])
            if g.is_empty:
                continue
            geoms[idx] = g
            garea[idx] = geom2d.area(g)
            frag = g if (cover is None or not clip) else geom2d.difference(g, cover)
            if geom2d.area(frag) >= MIN_FRAG_AREA:
                frags[idx] = frag
            if clip:
                cover = g if cover is None else geom2d.union(cover, g)
        if clip:
            _refine_order_clips(ordered, geoms, frags, proj, fit)
        return frags, garea, geoms

    frags, garea, geoms = clip_pass()
    if clip:
        # iterate: absorbing residue hands the area to deeper faces, whose
        # own thin leftovers only show up on the next pass (3941: ring ->
        # plate tris -> walls, one authored layer per round). The cap trades
        # completeness for speed — each round re-runs the boolean clip —
        # and the emission crumb cull mops up the sub-stroke tail that
        # further rounds would chase.
        trims = {}
        # drawn-op ink only (no contour term: the contour of already-
        # trimmed geometry would count as phantom cover exactly over a
        # laundered strip) — decides whether a candidate trim SHOWS
        _, ops_ink = _stroke_band(strokes, None, line_px, sil_px) \
            if strokes else (None, None)
        for _ in range(3):
            sil = _contour_region(geoms, arcs) if geoms else None
            new = _residue_trims(ordered, frags, garea, geoms=geoms,
                                 sil=sil, ink=ops_ink)
            # a re-clip (full boolean pass) only pays off when some residue
            # is SUBSTANTIVE — wide enough to survive the emission crumb
            # cull. Hairline-only rounds (most parts) stop here: emission
            # drops those pieces and the sub-AA slits left behind are
            # invisible, at a third of the render cost.
            if not any(not p.buffer(-RESIDUE_CRUMB).is_empty
                       for t in new.values()
                       for p in getattr(t, "geoms", [t])
                       if p.geom_type == "Polygon"):
                break
            for j, t in new.items():
                trims[j] = t if j not in trims else geom2d.union(trims[j], t)
            frags, garea, geoms = clip_pass(trims)

    if refits:
        f, ox, oy = fit if fit is not None else (1.0, 0.0, 0.0)
        mapped = [tuple(op[:1] + (op[1] * f + ox, op[2] * f + oy)
                        + tuple(v * f for v in op[3:7]) + op[7:]
                        for op in r) for r in refits]
        frags = refit_fill_boundaries(frags, mapped)

    members, roots = _merge_members(ordered, frags)

    merged = {}
    for idx in sorted(frags):
        r = roots[idx]
        if r not in merged:
            ks = members[r]
            merged[r] = frags[ks[0]] if len(ks) == 1 else \
                geom2d.union_all([frags[j] for j in ks])
    if clip and loops is not None and len(loops):
        f_, ox_, oy_ = fit if fit is not None else (1.0, 0.0, 0.0)
        _loop_cut_merged(merged, [np.stack([p[:, 0] * f_ + ox_,
                                            p[:, 1] * f_ + oy_], axis=1)
                                  for p in loops])
    pockets = []
    if clip and strokes and merged:
        order = {r: min(ks) for r, ks in members.items() if r in merged}
        silR = _contour_region(geoms, arcs) if geoms else None
        _donate_escaped_spurs(merged, order, strokes, silR, line_px, sil_px)
        vis = geom2d.union_all(list(merged.values()))
        base = silR if silR is not None and not silR.is_empty else vis
        # include drawn-arc bulge regions: a stylized arc bows past the
        # authored facet chords, and the slit between them belongs to no
        # face polygon at all (30137's log tops) — the contour/clip
        # already grow by these same regions
        arcr = geom2d.arc_regions(strokes)
        if arcr:
            base = geom2d.union_all([base] + arcr)
        # pass the arc-grown region as the band's silhouette too: the raw
        # contour region still carries the chord-vs-arc notch that the
        # DRAWN contour absorbs, and its boundary would count as phantom
        # ink exactly over the white slit
        pockets, whites = _ink_lens_pockets(base, vis, strokes, base,
                                            line_px, sil_px)
        # T-graze junctions (stroke dying on another stroke's band) weld
        # solid: their notch leaks into the open face region, so the
        # enclosed-pocket gates above never see it
        pockets += _weld_junction_notches(strokes, base, line_px, sil_px,
                                          broad=weld_corners)
        # every point of `base` (the arc-grown drawn-silhouette region) is
        # part surface: background may show only OUTSIDE the drawn contour.
        # Thin unpainted needles inside it — residue the trim rounds
        # laundered to background (30137's stud-graze strip: top face ->
        # column wall -> gone, each handoff locally sound), and arc-bulge
        # slits whose leak channel is too wide for the enclosed-hole
        # detection above — are absorbed like the enclosed whites. Wide or
        # large pieces are left alone: those are deliberate drops
        # (silhouette overhangs) or a bug better seen than papered over.
        _, inkR = _stroke_band(strokes, base, line_px, sil_px)
        bare = geom2d.difference(
            base, vis if inkR is None else geom2d.union(vis, inkR))
        for p in getattr(bare, "geoms", [bare]):
            if (p.geom_type != "Polygon"
                    or not 0.02 < p.area <= 8 * SPUR_MAX_AREA):
                continue
            if not geom2d.opened(p, 0.5 * line_px).is_empty:
                continue
            whites.append(p)
        for p in whites:
            probe = p.buffer(0.2)
            best, contact = None, 0.0
            for r2, g2 in merged.items():
                cnt = geom2d.area(geom2d.intersection(probe, g2))
                if cnt > contact:
                    best, contact = r2, cnt
            if best is not None:
                merged[best] = geom2d.union(merged[best], p)

    ops, emitted = [], set()
    for idx in sorted(frags):                          # farthest-first
        if idx in emitted:
            continue
        f = ordered[idx]
        ks = members[roots[idx]]
        emitted.update(ks)
        geom = merged[roots[idx]]
        if drop is not None:
            # silhouette spur trim: fills follow the trimmed outline so no
            # unstroked tone pokes past it (see silhouette_spur_trim)
            geom = geom2d.difference(geom, drop)
            if geom.is_empty:
                continue
        if clip:
            # crumb cull (see RESIDUE_CRUMB): per-piece, so thin TIPS of a
            # wide-bodied piece are untouched
            from shapely.geometry import Polygon as _Poly
            er = RESIDUE_CRUMB
            pieces = []
            for p in getattr(geom, "geoms", [geom]):
                if p.geom_type != "Polygon" or p.buffer(-er).is_empty:
                    continue
                # hole counterpart of the crumb cull: a hole thinner than
                # the 0.8px self-stroke can never render as a hole, but its
                # ring's self-stroke paints a hairline of this fill's tone
                # across the ink (3941's axle-cross bowties) — dissolve it
                holes = [h for h in p.interiors
                         if not _Poly(h).buffer(-er).is_empty]
                if len(holes) != len(p.interiors):
                    p = _Poly(p.exterior, holes)
                pieces.append(p)
            if not pieces:
                continue
            geom = pieces[0] if len(pieces) == 1 else geom2d.union_all(pieces)
        d = geom2d.path_d(geom, arcs, min_area=MIN_FRAG_AREA)
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
    # junction-lens pockets paint LAST (over every surface fill, under the
    # strokes): solid ink where converging strokes trap a sliver of tone
    for g in pockets:
        d = geom2d.path_d(g, arcs)
        if d:
            ops.append({"d": d, "fill": "#000000", "depth": 0.0})
    return ops


def silhouette_geom(faces):
    """Union of every face polygon: the part's exact projected silhouette
    (canvas px). Feeds the stroke-layer clip (see geom2d.buffer_d)."""
    return geom2d.union_all([geom2d.to_geom(f["poly"], f.get("holes"))
                             for f in faces])


def silhouette_spur_trim(faces, ellipses, sil_px, strokes=None):
    """Outline bulges over a drawn rim, shallower than the outline stroke:
    a plate's far corner peeking over the stud in front of it (3020's back
    corner). Stroked at sil width the whole bump is ink, rendering as a
    witch-hat spike with notches on the neighboring rim arc. A silhouette
    piece beyond a carrier ellipse that (a) rises less than ~the stroke
    width above the rim, (b) rides the rim for a good share of its
    perimeter, and (c) borders the background (so trimming reads as
    background, not a punched hole) can never read as shape. Trimmed from
    the silhouette AND the fills (fill_ops drop=), the outline follows the
    rim's smooth arc instead. Taller overhangs and rim-free corners are
    real outline and stay. With `strokes` (drawn segment ops), a piece a
    LINE stroke passes THROUGH (both endpoints beyond it) is vetoed: the
    stroke would keep poking past the trimmed outline as a barb over a
    white notch (32062's flange edge grazing the lobe arc); strokes that
    END inside the bump (3020's corner) are absorbed and trim fine.
    Returns the trim region, or None."""
    import shapely as _sh
    from shapely.geometry import LineString as _LS, Point as _Pt
    from shapely.geometry import MultiLineString as _MLS
    from shapely.geometry import Polygon as _Poly
    sil = silhouette_geom(faces)
    if sil is None or sil.is_empty or not ellipses:
        return None
    lines, drawn = [], []
    for op in strokes or []:
        if len(op) == 5:
            op = ("line",) + tuple(op)
        if op[0] == "line":
            lines.append((float(op[1]), float(op[2]),
                          float(op[3]), float(op[4])))
            drawn.append(_LS([op[1:3], op[3:5]]))
        elif op[0] == "arc":
            pts_a = _ell_pts(op, op[7], op[8])
            if len(pts_a) >= 2:
                drawn.append(_LS(pts_a))
    dmls = _MLS(drawn) if drawn else None
    bnd = sil.boundary
    ts = np.linspace(0.0, 2.0 * np.pi, 181)
    out = []
    for e in ellipses:
        c = np.array(e[:2], float)
        M = np.array([[e[2], e[4]], [e[3], e[5]]], float)
        try:
            Minv = np.linalg.inv(M)
        except np.linalg.LinAlgError:
            continue
        ex, ey = abs(e[2]) + abs(e[4]), abs(e[3]) + abs(e[5])
        x0, y0 = c[0] - ex - 3 * sil_px, c[1] - ey - 3 * sil_px
        x1, y1 = c[0] + ex + 3 * sil_px, c[1] + ey + 3 * sil_px
        w = _sh.clip_by_rect(sil, x0, y0, x1, y1)
        if w.is_empty:
            continue
        disk = _Poly(np.stack([c[0] + np.cos(ts) * e[2] + np.sin(ts) * e[4],
                               c[1] + np.cos(ts) * e[3] + np.sin(ts) * e[5]],
                              axis=1))
        outer = geom2d.difference(w, disk)
        for p in getattr(outer, "geoms", [outer]):
            if p.geom_type != "Polygon" or not 0.05 < p.area <= SPUR_MAX_AREA:
                continue
            px0, py0, px1, py1 = p.bounds
            if (px0 <= x0 + 1e-6 or py0 <= y0 + 1e-6
                    or px1 >= x1 - 1e-6 or py1 >= y1 - 1e-6):
                continue                     # window-frame cut, not a bump
            pts = np.asarray(p.exterior.coords, float)
            m = (pts - c) @ Minv.T
            r = np.hypot(m[:, 0], m[:, 1])
            rise = (r - 1.0) * np.hypot(*(pts - c).T) / np.maximum(r, 1e-9)
            if not 0.55 * sil_px < float(rise.max()) <= 1.1 * sil_px:
                continue                     # too tall: real shape. Too flat:
                                             # already hidden inside the rim
                                             # stroke band — trimming only
                                             # moves the contour and bares
                                             # stroke stubs (32062's corners)
            pb = p.buffer(0.25)
            base = disk.boundary.intersection(pb).length
            if base < max(0.5, 0.2 * p.exterior.length):
                continue                     # incidental graze, not rim-based
            open_edge = max(p.exterior.length - base, 0.5)
            if bnd.intersection(pb).length < 0.3 * open_edge:
                continue                     # interior sliver: trim = pinhole
            grown = p.buffer(0.3)
            if any(_LS([(lx0, ly0), (lx1, ly1)]).intersection(grown).length
                   > 0.3
                   and not grown.contains(_Pt(lx0, ly0))
                   and not grown.contains(_Pt(lx1, ly1))
                   for lx0, ly0, lx1, ly1 in lines):
                continue                     # through-going stroke: barb
            if dmls is not None:
                # the carrier must be DRAWN along the piece's base: the
                # trimmed outline inherits that stroke's ink, hiding the
                # clipped stubs of strokes that terminate inside the piece.
                # A base the drawn arc only partly covers (32062's lobe arc
                # ending mid-sliver) leaves them poking past a bare outline.
                base_line = disk.boundary.intersection(pb)
                gx0, gy0, gx1, gy1 = pb.bounds
                near = _sh.clip_by_rect(dmls, gx0 - 2, gy0 - 2,
                                        gx1 + 2, gy1 + 2)
                bare = base_line.difference(near.buffer(0.6))
                if bare.length > max(0.3, 0.1 * base_line.length):
                    continue                 # bare base: stubs become barbs
            out.append(p)
    return geom2d.union_all(out) if out else None


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


def light_vector(spec):
    """'LAT,LONG' (degrees, VIEW space) -> unit light direction.

    LAT is elevation above the view horizon; LONG is azimuth around the view
    axis, 0 = from the viewer, positive = from the viewer's LEFT. The default
    style light (upper-left, toward the viewer) is roughly '37,39'."""
    lat_s, long_s = str(spec).split(",")
    el, az = math.radians(float(lat_s)), math.radians(float(long_s))
    return np.array([-math.sin(az) * math.cos(el),
                     math.sin(el),
                     -math.cos(az) * math.cos(el)])


def make_style(name, part_color=(157, 157, 157), light=None):
    lv = light_vector(light) if isinstance(light, str) else light
    return STYLES[name](part_color=part_color, light=lv)


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


def cull_occluded_faces(faces, occluders, proj, eps,
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
        O = proj.ray_origin(pts[:, 0], pts[:, 1])
        mine = own_occ.get(id(f))
        if mine is not None:
            d_own = np.asarray(mine.depth(O, proj.fwd), float)
            self_d = np.where(np.isfinite(d_own), d_own, self_d)
        nearest = np.full(len(pts), np.inf)
        for occ in occluders:
            if occ is mine:
                continue                          # don't let a face occlude itself
            nearest = np.minimum(nearest, occ.depth(O, proj.fwd))
        if not bool(np.all(nearest < self_d - eps)):
            kept.append(f)
    return kept


def faces_from_tris(tri, proj, cond_edges=None):
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
        nv = np.array([n @ proj.right, n @ proj.up, n @ proj.fwd])
        back = nv[2] > -1e-6            # back-facing or edge-on
        if back and not have_seams:
            continue
        px, py, z = proj.to_px(v)
        poly = np.stack([px, py], axis=1)
        # carrier plane key (world normal + offset): fill_ops unions flat
        # same-plane fragments that abut without shared edges (T-junction
        # subpart tilings the edge-adjacency grouping below can't connect)
        plane = (round(float(n[0]), 4), round(float(n[1]), 4),
                 round(float(n[2]), 4), round(float(n @ v[0]), 2))
        f = {"poly": poly, "normal": nv, "depth": float(np.mean(z)),
             "zs": z, "kind": "tri", "plane": plane, "_verts": v}
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
        # "_verts" stays: absorb_wall_facets needs world coordinates to
        # match facets against analytic wall surfaces
        if f.get("backfill") and not (f["group"] in front_groups
                                      and ("grad_axis" in f or "grad_radial" in f)):
            continue                    # hidden underside, not fold spillover
        kept.append(f)
    return kept


def absorb_wall_facets(tri_faces, an_faces, tol=2e-3, abut_px=3.0):
    """Authored facet faces lying ON an analytic wall's surface inherit the
    abutting wall face's gradient and merge into its fill element.

    LDraw files sometimes author short stretches of a primitive-tiled wall
    as raw quads (60474's outer wall resumes as quads for ~6 deg beside
    each bite). Grouped alone their normals barely spread, so they render
    as a FLAT facet tone butted against the analytic band's gradient — a
    visible square patch. Geometry match: every vertex of the facet group
    within `tol` of the wall surface in the prim's local frame (unit
    radius at the vertex's height, height in 0..1) with an outward-radial
    world normal (interior facets seen through openings must not steal an
    exterior band's paint). The group takes the px-nearest exterior wall
    face's paint; past the gradient window's end the userSpaceOnUse
    gradient clamps to its end stop, which is exactly the shared-boundary
    tone, so the join stays continuous."""
    from shapely.geometry import Polygon

    walls = [f for f in an_faces
             if f.get("grad_axis") is not None and f.get("prim") is not None
             and not f.get("interior")]
    if not walls or not tri_faces:
        return

    def poly(f):
        p = Polygon(f["poly"])
        return p if p.is_valid else p.buffer(0)

    def on_wall(prim, v, n_world):
        local = (np.linalg.inv(prim.R) @ (np.asarray(v, float) - prim.t).T).T
        lvl = local[:, 1]
        if lvl.min() < -0.02 or lvl.max() > 1.02:
            return False
        r_exp = prim.radius_at(lvl) if hasattr(prim, "radius_at") else 1.0
        if np.max(np.abs(np.hypot(local[:, 0], local[:, 2]) - r_exp)) > tol:
            return False
        # tessellation facets span <= 22.5 deg (16-gon); a wider facet is a
        # flat FEATURE face whose corners merely lie on the circle (30136's
        # end face is clipped to the log profile: a chord plane, and its
        # normal equals the radial direction at the chord's mid-angle, so
        # the outward test below cannot reject it)
        aa = np.arctan2(local[:, 2], local[:, 0])
        rel = (aa - aa[0] + math.pi) % (2 * math.pi) - math.pi
        if rel.max() - rel.min() > math.radians(25.0):
            return False
        # outward facing: the facet's world normal agrees with the radial
        # direction at its centroid (in the prim's local frame)
        c = local.mean(axis=0)
        nl = prim.R.T @ np.asarray(n_world, float)
        rdir = np.array([c[0], 0.0, c[2]])
        rn = np.linalg.norm(rdir) * np.linalg.norm(nl)
        return rn > 1e-12 and float(nl @ rdir) / rn > 0.7

    by_group = defaultdict(list)
    for tf in tri_faces:
        if "grad_axis" in tf or "grad_radial" in tf or "_verts" not in tf:
            continue                    # already smooth-shaded, or no coords
        by_group[tf.get("group", id(tf))].append(tf)
    prims = {id(f["prim"]): f["prim"] for f in walls}
    for members in by_group.values():
        cands = None
        for tf in members:
            v = tf["_verts"]
            n = np.cross(v[1] - v[0], v[2] - v[0])
            ln = np.linalg.norm(n)
            if ln < 1e-9:
                cands = set()
                break
            mine = {pid for pid, prim in prims.items()
                    if on_wall(prim, v, n / ln)}
            cands = mine if cands is None else cands & mine
            if not cands:
                break
        if not cands:
            continue                    # some member is off-surface: keep flat
        wall_cands = [f for f in walls if id(f["prim"]) in cands]
        gp = poly(members[0])
        for tf in members[1:]:
            gp = gp.union(poly(tf))
        best, bd = None, abut_px
        for wf in wall_cands:
            d = gp.distance(poly(wf))
            if d < bd:
                best, bd = wf, d
        if best is None:
            continue                    # on-surface but not abutting a band
        best.setdefault("group", ("wallgrad", id(best)))
        for tf in members:
            tf["group"] = best["group"]
            tf["grad_axis"] = best["grad_axis"]
            tf["grad_samples"] = best["grad_samples"]


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
        # gradient axis = screen direction along which the NORMALS change
        # (first left singular vector of the centroid<->normal cross-
        # covariance): iso-tone lines on a curved strip are its straight
        # rulings, so the axis must follow the curve. The footprint's long
        # axis only coincides with it on narrow strips — a wide, short curve
        # would shade ACROSS the rulings. Degenerate correlation falls back
        # to the footprint axis.
        C = np.asarray(cs, float)
        Cc = C - C.mean(axis=0)
        X = Nn - Nn.mean(axis=0)
        Uc, sc, _ = np.linalg.svd(Cc.T @ X, full_matrices=False)
        if sc[0] > 1e-9:
            d0 = Uc[:, 0]
        else:
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
