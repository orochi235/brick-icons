from __future__ import annotations

import heapq
import math
from collections import defaultdict

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


def fill_ops(faces, style, clip=True, ellipses=None, proj=None, fit=None):
    """Fill ops with exact visible-fragment clipping and per-surface merging.

    clip=False keeps every face whole (no occlusion subtraction) for
    translucent rendering; paint order is still farthest-first so nearer
    faces blend over deeper ones.
    `ellipses` are projected circles (canvas space) for arc recovery: fill
    boundary runs sampled from them are emitted as true SVG arcs.

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
    arcs = geom2d.arc_candidates(ellipses)
    if faces and all("order" in f for f in faces):
        ordered = sorted(faces, key=lambda f: f["order"])
    else:
        ordered = sorted(faces, key=lambda f: -f["depth"])

    frags, geoms = {}, {}
    cover = None
    for idx in range(len(ordered) - 1, -1, -1):        # nearest first
        f = ordered[idx]
        g = geom2d.to_geom(f["poly"], f.get("holes"))
        if g.is_empty:
            continue
        geoms[idx] = g
        frag = g if (cover is None or not clip) else geom2d.difference(g, cover)
        if geom2d.area(frag) >= MIN_FRAG_AREA:
            frags[idx] = frag
        if clip:
            cover = g if cover is None else geom2d.union(cover, g)

    if clip:
        _refine_order_clips(ordered, geoms, frags, proj, fit)

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
    return ops


def silhouette_geom(faces):
    """Union of every face polygon: the part's exact projected silhouette
    (canvas px). Feeds the stroke-layer clip (see geom2d.buffer_d)."""
    return geom2d.union_all([geom2d.to_geom(f["poly"], f.get("holes"))
                             for f in faces])


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
