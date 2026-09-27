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
from shapely.geometry import MultiPoint, Polygon

from . import hlr, primitives, timing

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

    def placed(self):
        """The studs instancing draws -- clear and cut -- far to near, so a
        nearer stud paints over a farther one."""
        return sorted((v for v in self.verdicts if v.role in PLACED),
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


def _tri_cover(tris, hits, hull, right, up, fwd):
    """The projected outline (world A/B) of the planes the `hits` landed on:
    every triangle lying in one of those planes and reaching the stud's
    hull."""
    T = np.asarray(tris, float)
    n, d, keys = _plane_keys(T)
    q = _ab(T.reshape(-1, 3), right, up, fwd).reshape(-1, 3, 2)
    h2 = _ab(hits, right, up, fwd)
    planes = set()
    for H, (x, y) in zip(hits, h2):
        for i in np.nonzero(np.abs(n @ H - d) < PLANE_TOL)[0]:
            if keys[i] is not None and _in_tri2(q[i], x, y):
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
           right, up):
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
            regions.append(_tri_cover(occ.tris, hits, hull, right, up, fwd))
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
                             prim_of, hull, right, up)
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
