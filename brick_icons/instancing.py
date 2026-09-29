"""Stud instancing: draw each declared stud once, and place it wherever it
shows.

A stud is what the part DECLARED as one -- geometry under a `p/stud*.dat`
reference that `hlr.is_stud` accepts, tagged by `hlr.flatten` -- and under an
orthographic view every stud of one file, basis and color is the same drawing
moved. So before the engine runs each stud is tested against everything that
is not itself (`classify`): nothing in front of it, it is `clear`; everything,
`hidden`; only planes, `cut` by their outline; anything curved, or anything
the outline cannot account for, `fallback`, and the engine draws it as it
always did. Every stud that is not a fallback stays in the engine's input as
an occluder and stops contributing edges and faces (`withhold`). `Instancer`
draws each distinct stud once, alone, through the same engine at the part's
scale, and both writers place that one drawing.

Spec: docs/superpowers/specs/2026-09-27-stud-instancing-design.md
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiPoint, Polygon

from . import geom2d, hlr, primitives, process, shade, sweep, timing, trace

#: Angles sampled round each circle of a stud when classifying it.
SAMPLES = 24
#: Heights sampled on a stud's wall: both rims and half way up.
WALL_LEVELS = (0.0, 0.5, 1.0)
#: How far (projected LDU) a sample may sit on the wrong side of a cut
#: stud's cover outline and still agree with it: a sample ON the outline is
#: hit or missed by float noise.
AGREE_LDU = 0.05
#: Depth tolerance as a fraction of the part's depth range -- the naive
#: engine's own (hlr._visible_segments_analytic): a stud's base rim lies ON
#: the plate it stands on.
DEPTH_EPS = 1e-3
#: How far (LDU) a hit may sit off a triangle's plane and still lie on it.
PLANE_TOL = 1e-3
ROLES = ("clear", "cut", "hidden", "fallback")
PLACED = ("clear", "cut")


@dataclass(frozen=True, eq=False)
class StudRef:
    """One stud reference as flatten placed it (hlr.flatten's stud_refs)."""
    id: int
    path: Path
    R: np.ndarray
    t: np.ndarray
    color: int
    body: int
    invert: bool

    @property
    def key(self):
        """What makes two studs the same drawing moved: the file, the basis
        (rounded, so authoring noise does not split a baseplate's studs), the
        color and body (decoration), and the winding (back-face culling)."""
        return (Path(self.path).name.lower(),
                tuple(float(x) for x in np.round(self.R, 4).ravel()),
                int(self.color), int(self.body), bool(self.invert))


@dataclass(eq=False)
class Verdict:
    """One stud's classification. `hull` is everything it covers and `cover`
    (cut only) the planes in front of it, both world A/B; (a, b, depth) is
    its reference origin projected."""
    ref: StudRef
    role: str
    hull: object = None
    cover: object = None
    a: float = 0.0
    b: float = 0.0
    depth: float = 0.0

    def shown(self):
        """What of the stud the drawing shows, world A/B."""
        if self.hull is None:
            return None
        if self.role == "cut":
            from . import geom2d
            return geom2d.difference(self.hull, self.cover)
        return self.hull


@dataclass(eq=False)
class Plan:
    """Every stud's verdict for one render, and the view it was made in."""
    verdicts: list
    basis: tuple
    printed: bool = False

    def counts(self):
        c = {r: 0 for r in ROLES}
        for v in self.verdicts:
            c[v.role] += 1
        return c

    def placed(self, roles=PLACED):
        """The studs instancing draws -- clear and cut, or `roles` -- far to
        near, so a nearer stud paints over a farther one."""
        return sorted((v for v in self.verdicts if v.role in roles),
                      key=lambda v: -v.depth)


def refs_of(out):
    return [StudRef(id=i, path=Path(r["path"]), R=np.asarray(r["R"], float),
                    t=np.asarray(r["t"], float), color=int(r["color"]),
                    body=int(r["body"]), invert=bool(r["invert"]))
            for i, r in sorted(out.get("stud_refs", {}).items())]


def members(out):
    """({stud id: [prims]}, {stud id: [tris]}) of what flatten tagged."""
    prims, tris = {}, {}
    for p in out.get("analytic", ()):
        if p.stud is not None:
            prims.setdefault(p.stud, []).append(p)
    for v, m in zip(out.get("tri", ()), out.get("tri_meta", ())):
        if m.get("stud") is not None:
            tris.setdefault(m["stud"], []).append(np.asarray(v, float))
    return prims, tris


def stud_points(prims, tris, n=SAMPLES):
    """World points on a stud's declared geometry: each primitive's circles
    over its own sector (a wall's rims and middle, a ring's bore, a disc's
    half-radius ring and center, a partial sector's center) and each
    triangle's corners and centroid."""
    pts = []
    for p in prims:
        th = np.radians(np.linspace(0.0, p.sector, n))
        for lv in (WALL_LEVELS if p.kind in ("cyli", "con") else (0.0,)):
            pts.append(p.ring_pts(th, lv))
        if p.kind == "ring":
            pts.append(p.ring_pts(th, 0.0, radius=float(p.inner)))
        if p.kind == "disc":
            pts.append(p.ring_pts(th, 0.0, radius=0.5))
            pts.append(p.t[None, :])
        elif not p.is_full:
            pts.append(p.t[None, :])
    for v in tris:
        v = np.asarray(v, float)
        pts.append(v)
        pts.append(v.mean(axis=0)[None, :])
    return np.vstack(pts) if pts else np.zeros((0, 3))


def _depth_range(out, fwd):
    pts = ([np.asarray(out["tri"], float).reshape(-1, 3)]
           if out.get("tri") else [])
    pts += [p.fit_pts() for p in out.get("analytic", ())]
    if not pts:
        return 1.0
    z = np.vstack(pts) @ np.asarray(fwd, float)
    return float(z.max() - z.min()) or 1.0


def _ab(P, right, up, fwd):
    a, b, _ = hlr.project(np.asarray(P, float), right, up, fwd)
    return np.stack([a, b], 1)


def prim_region(prim, right, up, fwd, n=64):
    """A flat primitive's projected outline, world A/B: a disc, or a ring
    with its bore."""
    th = np.radians(np.linspace(0.0, prim.sector, n))
    outer = prim.ring_pts(th, 0.0)
    inner = (prim.ring_pts(th, 0.0, radius=float(prim.inner))
             if prim.kind == "ring" else None)
    holes = []
    if prim.is_full:
        shell = outer
        if inner is not None:
            holes = [inner]
    elif inner is not None:
        shell = np.vstack([outer, inner[::-1]])
    else:
        shell = np.vstack([outer, prim.t[None, :]])
    return Polygon(_ab(shell, right, up, fwd),
                   [_ab(h, right, up, fwd) for h in holes]).buffer(0)


def _plane_keys(T):
    """(unit normals, offsets, keys) per triangle, one sign per plane
    whichever way a triangle winds; a degenerate one's key is None."""
    e0, e1 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    n = np.cross(e0, e1)
    ln = np.linalg.norm(n, axis=1)
    ok = ln > 1e-12
    n[ok] /= ln[ok, None]
    lead = np.take_along_axis(
        n, np.argmax(np.abs(n) > 1e-6, axis=1)[:, None], 1)[:, 0]
    n *= np.where(lead < 0, -1.0, 1.0)[:, None]
    d = np.einsum("ij,ij->i", n, T[:, 0])
    keys = [(tuple(float(x) for x in np.round(n[i], 4)), round(float(d[i]), 2))
            if ok[i] else None for i in range(len(T))]
    return n, d, keys


def _in_tri2(q, x, y, slack=1e-6):
    (x0, y0), (x1, y1), (x2, y2) = q
    den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(den) < 1e-12:
        return False
    l0 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / den
    l1 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / den
    return l0 >= -slack and l1 >= -slack and 1.0 - l0 - l1 >= -slack


def smooth_tris(tris, cond):
    """Boolean per triangle: is it a facet of a surface the part declared
    curved -- does a type-5 line lie on one of its edges?"""
    T = np.asarray(tris, float).reshape(-1, 3, 3)
    if not len(T) or not len(cond):
        return np.zeros(len(T), bool)
    A = T.reshape(-1, 3)
    B = T[:, [1, 2, 0]].reshape(-1, 3)
    return shade._seam_edge_mask(A, B, cond).reshape(-1, 3).any(axis=1)


def _tri_cover(tris, hits, hull, right, up, fwd, smooth=None):
    """The projected outline (world A/B) of the planes the `hits` landed on:
    every triangle lying in one of those planes and reaching the stud's
    hull. None when a hit landed on a triangle `smooth` marks (smooth_tris):
    a facet's outline is the tessellation's, not the surface's."""
    T = np.asarray(tris, float)
    n, d, keys = _plane_keys(T)
    q = _ab(T.reshape(-1, 3), right, up, fwd).reshape(-1, 3, 2)
    h2 = _ab(hits, right, up, fwd)
    planes = set()
    for H, (x, y) in zip(hits, h2):
        for i in np.nonzero(np.abs(n @ H - d) < PLANE_TOL)[0]:
            if keys[i] is not None and _in_tri2(q[i], x, y):
                if smooth is not None and smooth[i]:
                    return None
                planes.add(keys[i])
    if not planes:
        return Polygon()
    x0, y0, x1, y1 = hull.bounds
    lo, hi = q.min(axis=1), q.max(axis=1)
    near = ((hi[:, 0] >= x0) & (lo[:, 0] <= x1)
            & (hi[:, 1] >= y0) & (lo[:, 1] <= y1))
    polys = [Polygon(q[i]) for i in np.nonzero(near)[0] if keys[i] in planes]
    polys = [g for g in polys if g.area > 0]
    return shapely.union_all(polys) if polys else Polygon()


def _judge(hidden, which, depth, O, fwd, a, b, index, prim_of, hull,
           right, up, smooth_of=None):
    if not hidden.any():
        return "clear", None
    if hidden.all():
        return "hidden", None
    regions = []
    for i in sorted({int(w) for w in which[hidden]}):
        occ = index.occluders[i]
        if isinstance(occ, primitives.DiscOccluder) and id(occ) in prim_of:
            regions.append(prim_region(prim_of[id(occ)], right, up, fwd))
        elif isinstance(occ, primitives.TriangleOccluder):
            m = hidden & (which == i)
            hits = O[m] + depth[m][:, None] * fwd[None, :]
            cover = _tri_cover(occ.tris, hits, hull, right, up, fwd,
                               smooth_of(occ) if smooth_of else None)
            if cover is None:
                return "fallback", None
            regions.append(cover)
        else:
            return "fallback", None     # curved, or nothing here can outline it
    cover = shapely.union_all(regions)
    pts = shapely.points(a, b)
    grown, shrunk = cover.buffer(AGREE_LDU), cover.buffer(-AGREE_LDU)
    if ((hidden & ~shapely.covers(grown, pts)).any()
            or (~hidden & shapely.covers(shrunk, pts)).any()):
        return "fallback", None         # the outline does not explain the hits
    return "cut", cover


def classify(out, right, up, fwd):
    """A Verdict per stud flatten recorded, from sampling its geometry
    against every occluder that is not its own. Reads `out` as flatten left
    it (stud tags intact) and changes nothing."""
    refs = refs_of(out)
    if not refs:
        return []
    fwd = np.asarray(fwd, float)
    prims, tris = members(out)
    occluders, prim_of = [], {}
    for p in out.get("analytic", ()):
        occ = p.occluder()
        if occ is not None:
            occluders.append(occ)
            prim_of[id(occ)] = p
    ground = [np.asarray(v, float)
              for v, m in zip(out.get("tri", ()), out.get("tri_meta", ()))
              if m.get("stud") is None]
    if ground:
        occluders.append(primitives.TriangleOccluder(np.array(ground)))
    own_tris = {}
    for sid, ts in tris.items():
        own_tris[sid] = primitives.TriangleOccluder(np.array(ts))
        occluders.append(own_tris[sid])
    index = primitives.OccluderIndex(occluders, fwd)
    eps = DEPTH_EPS * _depth_range(out, fwd)
    smooth = {}

    def smooth_of(occ):
        if id(occ) not in smooth:
            smooth[id(occ)] = smooth_tris(occ.tris, out.get("5") or [])
        return smooth[id(occ)]

    verdicts = []
    for ref in refs:
        a0, b0, z0 = hlr.project(ref.t[None, :], right, up, fwd)
        at = dict(a=float(a0[0]), b=float(b0[0]), depth=float(z0[0]))
        ps, ts = prims.get(ref.id, []), tris.get(ref.id, [])
        P = stud_points(ps, ts)
        if not len(P):
            verdicts.append(Verdict(ref, "fallback", **at))
            continue
        a, b, z = hlr.project(P, right, up, fwd)
        hull = MultiPoint(np.stack([a, b], 1)).convex_hull
        own = [p.occluder() for p in ps if p.occluder() is not None]
        if ref.id in own_tris:
            own.append(own_tris[ref.id])
        O = P - z[:, None] * fwd[None, :]
        depth, which = index.nearest_hit(O, skip=own)
        hidden = z > depth + eps
        role, cover = _judge(hidden, which, depth, O, fwd, a, b, index,
                             prim_of, hull, right, up, smooth_of)
        verdicts.append(Verdict(ref, role, hull=hull, cover=cover, **at))
    return verdicts


#: Slack, in the stud's local units, of the envelope `Envelopes` tests.
ENVELOPE_TOL = 0.02


class Envelopes:
    """The space each withheld stud occupies: a cylinder about the stud's
    own local Y axis, as wide and as tall as its declared geometry. The sewn
    shape occt draws from carries no stud tag, so occt asks here whether a
    face or crease lies wholly inside one."""

    def __init__(self, items):
        self._env, lo, hi = [], [], []
        for ref, P in items:
            P = np.asarray(P, float)
            if not len(P):
                continue
            Minv = np.linalg.inv(ref.R)
            L = (P - ref.t) @ Minv.T
            self._env.append((Minv, ref.t,
                              float(np.hypot(L[:, 0], L[:, 2]).max()),
                              float(L[:, 1].min()), float(L[:, 1].max())))
            # the samples are inscribed in the true circles: pad the box
            pad = 0.05 * float((P.max(0) - P.min(0)).max()) + ENVELOPE_TOL
            lo.append(P.min(0) - pad)
            hi.append(P.max(0) + pad)
        self._lo = np.array(lo, float).reshape(-1, 3)
        self._hi = np.array(hi, float).reshape(-1, 3)

    def __len__(self):
        return len(self._env)

    def holds(self, P):
        P = np.atleast_2d(np.asarray(P, float))
        if not len(P) or not self._env:
            return False
        pmin, pmax = P.min(0), P.max(0)
        for i in np.nonzero(np.all(self._lo <= pmin, 1)
                            & np.all(self._hi >= pmax, 1))[0]:
            Minv, t, r, y0, y1 = self._env[i]
            L = (P - t) @ Minv.T
            if (np.hypot(L[:, 0], L[:, 2]).max() <= r + ENVELOPE_TOL
                    and L[:, 1].min() >= y0 - ENVELOPE_TOL
                    and L[:, 1].max() <= y1 + ENVELOPE_TOL):
                return True
        return False


def withhold(out, right, up, fwd):
    """Classify every stud and take each one instancing will place (every
    role but fallback) out of the drawing: its primitives and triangles are
    marked `withheld` -- still occluders, never drawn -- and its type-2 and
    type-5 lines leave out["2"] and out["5"]. Runs on `out` as flatten left
    it, before sweep.substitute and arcfit rewrite those lists. Records the
    four role counts for the census."""
    verdicts = classify(out, right, up, fwd)
    gone = {v.ref.id for v in verdicts if v.role != "fallback"}
    if gone:
        for p in out.get("analytic", ()):
            if p.stud in gone:
                p.withheld = True
        for m in out.get("tri_meta", ()):
            if m.get("stud") in gone:
                m["withheld"] = True
        for typ in ("2", "5"):
            lines = out.get(typ, [])
            tags = out.get(typ + "_stud") or [None] * len(lines)
            out[typ] = [e for e, s in zip(lines, tags) if s not in gone]
            out[typ + "_stud"] = [s for s in tags if s not in gone]
        prims, tris = members(out)
        out["stud_held"] = Envelopes(
            [(v.ref, stud_points(prims.get(v.ref.id, []),
                                 tris.get(v.ref.id, [])))
             for v in verdicts if v.ref.id in gone])
    plan = Plan(verdicts, (right, up, fwd), printed=bool(out.get("printed")))
    for role, n in plan.counts().items():
        timing.count(f"studs_{role}", n)
    return plan


def limb_points(prim, fwd):
    """World (base, top) of each limb generator of a cylinder or cone
    primitive seen along `fwd` -- the lines Cylinder/Cone.drawn_with_depth
    draw as its silhouette. [] for other kinds, or a cone with no limb."""
    fwd = np.asarray(fwd, float)
    g = np.linalg.inv(prim.R) @ fwd
    if prim.kind == "cyli":
        th0 = math.atan2(-float(g[0]), float(g[2]))
        thetas, rb, rt = (th0, th0 + math.pi), 1.0, 1.0
    elif prim.kind == "con":
        a_, b_, c_ = float(g[0]), float(g[2]), float(-g[1])
        hyp = math.hypot(a_, b_)
        if hyp < 1e-12 or abs(c_) > hyp:
            return []
        phi0 = math.atan2(b_, a_)
        d = math.acos(max(-1.0, min(1.0, c_ / hyp)))
        thetas, rb, rt = (phi0 + d, phi0 - d), prim.top + 1.0, float(prim.top)
    else:
        return []
    out = []
    for th in thetas:
        if not prim.is_full and math.degrees(th) % 360.0 > prim.sector + 1e-6:
            continue
        base = prim.ring_pts(np.array([th]), 0.0, radius=rb)[0]
        top = prim.ring_pts(np.array([th]), 1.0, radius=rt)[0]
        out.append((base, top))
    return out


def shown_ops(plan, proj):
    """The union of what every placed stud shows, in op space (`proj`'s fit
    of world A/B; None leaves A/B as it is)."""
    g = shapely.union_all([s for s in (v.shown() for v in plan.placed())
                           if s is not None and not s.is_empty])
    if proj is None:
        return g
    return shapely.transform(g, lambda P: (P - (proj.cx, proj.cy)) * proj.s
                             + proj.half)


def grow_bbox(bbox, plan, proj):
    """`bbox` (op space) grown over what every placed stud shows: a withheld
    stud draws no op, and a naive bbox is its ops'."""
    if proj is None:
        return bbox
    g = shown_ops(plan, proj)
    if g.is_empty:
        return bbox
    x0, y0, x1, y1 = bbox
    a0, b0, a1, b1 = g.bounds
    return (float(min(x0, a0)), float(min(y0, b0)),
            float(max(x1, a1)), float(max(y1, b1)))


def canvas_geom(g, k, kx, ky):
    """A world-A/B geometry in canvas px."""
    return affinity.affine_transform(g, [k, 0.0, 0.0, k, kx, ky])


def origin_fit(res, k):
    """The (f, ox, oy) under which canvas_affine(res, ...) is (k, 0, 0): a
    lone stud's own drawing, its reference origin on canvas (0, 0)."""
    p = res.proj
    if p is None:
        return (k, 0.0, 0.0)
    f = k / p.s
    return (f, -(p.half - p.cx * p.s) * f, -(p.half - p.cy * p.s) * f)


def translate_op(op, dx, dy):
    if op[0] == "line":
        _, x1, y1, x2, y2, kind = op
        return ("line", x1 + dx, y1 + dy, x2 + dx, y2 + dy, kind)
    _, cx, cy, ux, uy, vx, vy, t0, t1, kind = op
    return ("arc", cx + dx, cy + dy, ux, uy, vx, vy, t0, t1, kind)


def _line_ops(piece, kind):
    out = []
    for g in getattr(piece, "geoms", [piece]):
        if g.geom_type != "LineString" or g.is_empty:
            continue
        c = list(g.coords)
        out += [("line", x1, y1, x2, y2, kind)
                for (x1, y1), (x2, y2) in zip(c, c[1:])]
    return out


def clip_ops(ops, region, n=24):
    """Stroke ops cut to `region`, as line ops: what a PNG draws of a cut
    stud. An arc comes back as the chords of its sampled polyline, the way
    process.draw_segments samples one anyway."""
    shapely.prepare(region)
    out = []
    for op in ops:
        out += _line_ops(LineString(process.op_points(op, n))
                         .intersection(region), op[-1])
    return out


def cut_ops(ops, hide, n=24, keep=None):
    """Stroke ops less where they cross `hide`: the part's strokes a PNG
    draws around studs (hide_region). An op that misses `hide`, or that
    `keep` claims (a stud's own stroke), comes back as it was; one that
    crosses it, as line ops."""
    if hide is None or hide.is_empty:
        return list(ops)
    shapely.prepare(hide)
    out = []
    for op in ops:
        if len(op) == 5:                               # legacy line tuple
            op = ("line",) + tuple(op)
        if keep is not None and keep(op):
            out.append(op)
            continue
        line = LineString(process.op_points(op, n))
        if not shapely.intersects(line, hide):
            out.append(op)
            continue
        out += _line_ops(line.difference(hide), op[-1])
    return out


def _span(out, right, up, fwd):
    """The larger projected extent (LDU) of a flattened drawing."""
    pts = ([np.asarray(out["tri"], float).reshape(-1, 3)]
           if out["tri"] else [])
    pts += [np.asarray(e, float) for e in out["2"]]
    pts += [p.fit_pts() for p in out["analytic"]]
    if not pts:
        return 1.0
    a, b, _ = hlr.project(np.vstack(pts), right, up, fwd)
    return float(max(a.max() - a.min(), b.max() - b.min())) or 1.0


class Instancer:
    """Draws each distinct stud of a plan once and places it.

    `res` is the part's VisResult with `studs` set. A definition is the stud
    alone, run through `engine` -- the part's own pipeline, at the part's
    render scale -- cached by StudRef.key; its strokes and fills are fitted
    with origin_fit so the stud's reference origin is canvas (0, 0) at `k`
    px per LDU. Both writers place those same ops: `svg_parts` as `<use>`,
    `png_ops` translated and cut to shape."""

    def __init__(self, res, engine, ldraw_dir):
        self.res = res
        self.plan = res.studs
        self.engine = engine
        self.ldraw_dir = ldraw_dir
        self.roots = hlr.default_roots(ldraw_dir)
        self._lone, self._strokes = {}, {}

    def lone(self, ref):
        got = self._lone.get(ref.key)
        if got is not None:
            return got
        right, up, fwd = self.plan.basis
        out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": [],
               "printed": self.plan.printed}
        hlr.flatten(ref.path, ref.R, np.zeros(3), out, self.roots, depth=1,
                    inherited_invert=ref.invert, color=ref.color,
                    body=ref.body)
        for key in ("2_stud", "5_stud", "stud_refs", "studs"):
            out.pop(key, None)
        sweep.substitute(out)
        # the part's render px per LDU, so every pixel-sized tolerance in the
        # engine and its tail means what it meant for the part
        render_px = max(64, int(round(self.res.s * _span(out, right, up, fwd)))
                        + 20)
        with timing.phase("studs"):
            got = hlr.draw_flattened(out, right, up, fwd, render_px,
                                     cull=True, engine=self.engine)
        self._lone[ref.key] = got
        return got

    def strokes(self, ref, k):
        key = (ref.key, round(float(k), 9))
        if key not in self._strokes:
            lone = self.lone(ref)
            self._strokes[key] = hlr.affine_segments(lone.segs,
                                                     *origin_fit(lone, k))
        return self._strokes[key]

    def fills(self, ref, k, style, stud_px, crumb, weld_corners,
              deco_shade=True):
        if style is None:
            return []
        lone = self.lone(ref)
        if not lone.faces:
            return []
        fit = origin_fit(lone, k)
        with timing.phase("studs"):
            return shade.fill_ops(
                shade.apply_affine_faces(lone.faces, *fit), style, clip=True,
                ellipses=hlr.fit_ellipses(lone.ellipses, *fit),
                proj=lone.proj, fit=fit, refits=lone.refits, loops=lone.loops,
                strokes=self.strokes(ref, k), line_px=stud_px, sil_px=stud_px,
                weld_corners=weld_corners, ldraw_dir=self.ldraw_dir,
                crumb=crumb, sil_walls=False, deco_shade=deco_shade)

    def clip(self, v, k, kx, ky, pad):
        """A cut stud's clip, canvas px: its footprint grown by `pad` (its
        strokes' reach), less the planes in front of it."""
        return geom2d.difference(canvas_geom(v.hull, k, kx, ky).buffer(pad),
                                 canvas_geom(v.cover, k, kx, ky))

    def svg_parts(self, fit, stud_px, style=None, crumb=None,
                  weld_corners=False, deco_shade=True):
        """Elements for trace.segments_to_svg(between=...): one `<defs>`
        with each distinct stud's fill group (`sd<n>f`), stroke group
        (`sd<n>s`) and every cut stud's clip, then `<g class="studs">` of
        `<use>` pairs far to near -- fills then strokes, so a nearer stud
        covers a farther one's lines as the engine would. [] when nothing is
        placed."""
        placed = self.plan.placed()
        if not placed:
            return []
        k, kx, ky = hlr.canvas_affine(self.res, *fit)
        crumb = shade.RESIDUE_CRUMB if crumb is None else crumb
        defs, uses, ids, has_fill, clips = [], ['<g class="studs">'], {}, {}, 0
        for v in placed:
            if v.ref.key not in ids:
                n = ids[v.ref.key] = len(ids)
                fills = self.fills(v.ref, k, style, stud_px, crumb,
                                   weld_corners, deco_shade)
                has_fill[n] = bool(fills)
                if fills:
                    gdefs, body = trace.fill_elements(fills,
                                                      gid_prefix=f"sd{n}g")
                    defs += gdefs
                    defs.append(f'<g id="sd{n}f">' + "".join(body) + "</g>")
                defs.append(f'<g id="sd{n}s" stroke="black" fill="none" '
                            f'stroke-linecap="round">'
                            + "".join(trace.stroke_elements(
                                self.strokes(v.ref, k), stud_px, stud_px))
                            + "</g>")
            n = ids[v.ref.key]
            x, y = v.a * k + kx, v.b * k + ky
            pair = "".join(f'<use href="#sd{n}{layer}" x="{x:.2f}" y="{y:.2f}"/>'
                           for layer in (("f", "s") if has_fill[n] else ("s",)))
            if v.role == "cut":
                d = geom2d.path_d(self.clip(v, k, kx, ky, stud_px))
                if not d:
                    continue
                defs.append(f'<clipPath id="sc{clips}"><path d="{d}" '
                            f'clip-rule="evenodd"/></clipPath>')
                uses.append(f'<g clip-path="url(#sc{clips})">{pair}</g>')
                clips += 1
            else:
                uses.append(pair)
        return ["<defs>" + "".join(defs) + "</defs>"] + uses + ["</g>"]

    def png_ops(self, fit, stud_px):
        """The same strokes for a PNG under `fit`: translated to every placed
        stud, a cut one cut to its clip."""
        placed = self.plan.placed()
        if not placed:
            return []
        k, kx, ky = hlr.canvas_affine(self.res, *fit)
        ops = []
        for v in placed:
            moved = [translate_op(op, v.a * k + kx, v.b * k + ky)
                     for op in self.strokes(v.ref, k)]
            ops += (clip_ops(moved, self.clip(v, k, kx, ky, stud_px))
                    if v.role == "cut" else moved)
        return ops

    def hide_region(self, fit, stroke_px):
        """hide_region over this plan's placed studs."""
        return hide_region(self.res, self.plan, fit, stroke_px)


def stroke_ink(ops, px, n=24):
    """What stroke ops `px` wide cover, same space as the ops."""
    lines = [LineString(process.op_points(op if len(op) != 5
                                          else ("line",) + tuple(op), n))
             for op in ops]
    return shapely.union_all([ln.buffer(0.5 * px) for ln in lines]) \
        if lines else Polygon()


def within(region, tol, n=5):
    """A predicate: does a stroke op lie wholly inside `region` grown by
    `tol`?"""
    grown = region.buffer(tol)
    shapely.prepare(grown)

    def inside(op):
        xy = np.asarray(process.op_points(
            op if len(op) != 5 else ("line",) + tuple(op), n), float)
        return bool(shapely.contains_xy(grown, xy[:, 0], xy[:, 1]).all())
    return inside


def unplaced_hide(res, plan, fit, segs, stroke_px, stud_px):
    """(hide, spare) for a render whose studs the engine drew (res.unplaced):
    hide_region over the clear studs, and the predicate that spares the ops
    lying wholly inside one -- a clear stud has nothing in front of it, so
    those are its own drawing, whether the stud tier knows them or not (a
    round part's studs truncated at its wall, 3941). Everything else stops at
    the stud's edge instead of capping onto its top. (None, None) when no
    stud is clear."""
    k, kx, ky = hlr.canvas_affine(res, *fit)
    feet = [canvas_geom(v.hull, k, kx, ky)
            for v in plan.placed(("clear",)) if v.hull is not None]
    if not feet:
        return None, None
    spare = within(geom2d.union_all(feet), 0.5 * stroke_px)
    drawn = stroke_ink([op for op in segs if spare(op)], stud_px)
    return (hide_region(res, plan, fit, stroke_px, roles=("clear",),
                        drawn=drawn), spare)


def hide_region(res, plan, fit, stroke_px, roles=PLACED, drawn=None):
    """Where neither the part's strokes nor its silhouette contour draw:
    what the studs of `roles` show, canvas px under `fit` of `res`. A clear
    stud has nothing in front of it, so a part stroke inside it can only be
    a round cap overhanging from an edge behind it, or the contour of a face
    it stands in front of. A cut one hides what it shows less half of
    `stroke_px`, the widest part stroke, so the occluder's own edge along
    the cut keeps both halves of its width. With instancing off the engine
    draws every stud, and only the clear ones hide (unplaced_hide); `drawn`
    is what the studs' own strokes ink (stroke_ink). Where a clear
    stud's outline is not drawn by them -- the engine gave it to a part
    edge or the contour running along it (3941's rim studs) -- the stud
    gives way half of `stroke_px` inside it, so that stroke keeps its width.
    None when no stud of `roles` shows."""
    k, kx, ky = hlr.canvas_affine(res, *fit)
    parts = []
    for v in plan.placed(roles):
        g = canvas_geom(v.shown(), k, kx, ky)
        if v.role == "cut":
            g = g.buffer(-0.5 * stroke_px)
        elif drawn is not None and not g.is_empty:
            bare = shapely.difference(g.boundary, drawn)  # geom2d.difference keeps areas only
            if not bare.is_empty:
                g = geom2d.difference(g, bare.buffer(0.5 * stroke_px))
        if not g.is_empty:
            parts.append(g)
    return geom2d.union_all(parts) if parts else None
