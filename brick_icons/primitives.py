"""Analytic substitution for LDraw curved primitives.

LDraw curved geometry is faceted (a cylinder = 48 flat quads). This module
recognizes the named curved primitives and represents them as exact analytic
shapes so the HLR renderer can emit true arcs/ellipses and occlude against a
continuous (gridless) depth field instead of a rasterized z-buffer.

Conventions (see docs/superpowers/specs/2026-06-28-primitive-substitution-design.md):
- A primitive's world transform maps local point p -> R @ p + t.
  So center C = t, basis U = R[:,0], V = R[:,2], axis A = R[:,1].
- Canonical circle: p(theta) = (cos t, 0, sin t), radius 1, theta from +X -> +Z.
  A fractional primitive `n-d*` spans sector_deg = 360*n/d, start theta = 0.
- ringN: annulus inner radius N, outer N+1, in the local XZ plane at y=0.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

_FRAC = re.compile(r"^(\d+)-(\d+)(edge|cyli|cylo|disc|ring|con)(\d*)$")

# Reference aliases applied during flatten, BEFORE resolution/substitution:
# icon-scale stand-ins for primitives whose extra detail cannot survive label
# size. (stud10 used to be aliased to the plain stud, but the lateral
# truncation it models is the plate boundary clipping the stud — a real,
# visible feature on round 2x2 parts — so it now recurses normally.)
ALIAS_REFS = {}


@dataclass(frozen=True, eq=False)
class Projection:
    """Camera + pixel-fit context for one render.

    Bundles the view basis and the pixel fit so geometry code takes one
    argument instead of seven. to_AB mirrors hlr.project (A, B image-down,
    Z = camera depth); to_px applies the pixel fit; ray_origin inverts it
    back to world ray origins for the occlusion oracle.
    """
    right: np.ndarray
    up: np.ndarray
    fwd: np.ndarray
    s: float
    cx: float
    cy: float
    half: float

    def to_AB(self, P):
        P = np.asarray(P, float)
        return P @ self.right, -(P @ self.up), P @ self.fwd

    def to_px(self, P):
        a, b, z = self.to_AB(P)
        return ((a - self.cx) * self.s + self.half,
                (b - self.cy) * self.s + self.half, z)

    def ray_origin(self, xs, ys):
        a = (np.asarray(xs, float) - self.half) / self.s + self.cx
        b = (np.asarray(ys, float) - self.half) / self.s + self.cy
        return a[:, None] * self.right - b[:, None] * self.up

    def circle(self, R, t, radius):
        """Project the world circle at (R, t, radius) into pixel space."""
        return project_circle(R, t, radius, self.to_AB,
                              self.s, self.cx, self.cy, self.half)


def parse_primitive(name: str):
    """basename -> (kind, sector_deg, inner_radius) or None.

    None means "not a substitutable curved primitive" -> the caller should fall
    back to faceted polygon recursion. kind in {'edge','cyli','disc','ring',
    'con'}; 'cylo' is aliased to 'cyli'. For 'con' the third element is the
    TOP radius N: geometry is radius N+1 at local y=0 tapering to N at y=1.

    'ndis' deliberately stays faceted: its tris join adjacent smooth/coplanar
    facet groups (seam/coplanar union) and inherit the group's gradient, so
    the seam is invisible; an analytic ndis face gets a flat tone that
    mismatches the group ramp (3960 grew a visible square around its stud).
    fill_ops' polygon union merges the faceted tris into one region anyway.
    """
    base = name.replace("\\", "/").split("/")[-1].lower()
    if base.endswith(".dat"):
        base = base[:-4]
    m = _FRAC.match(base)
    if not m:
        return None
    num, den, fam, suffix = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
    if den == 0:
        return None
    sector = 360.0 * num / den
    kind = "cyli" if fam == "cylo" else fam
    if kind == "con":
        if not suffix:
            return None            # 'conN' always carries its top radius
        return ("con", sector, int(suffix))
    inner = int(suffix) if (kind == "ring" and suffix) else 0
    if kind == "ring" and inner == 0:
        return None
    return (kind, sector, inner)


class Ellipse:
    """2-D ellipse in pixel space: point(theta) = center + cos t*u + sin t*v."""

    def __init__(self, center, u, v, depth_coeffs=(0.0, 0.0, 0.0)):
        self.center = np.asarray(center, float)
        self.u = np.asarray(u, float)
        self.v = np.asarray(v, float)
        # (Zc, Zu, Zv): camera depth at angle t is Zc + cos t*Zu + sin t*Zv.
        self.depth_coeffs = depth_coeffs

    def depth(self, theta):
        zc, zu, zv = self.depth_coeffs
        return zc + math.cos(theta) * zu + math.sin(theta) * zv

    def point(self, theta):
        return self.center + math.cos(theta) * self.u + math.sin(theta) * self.v

    def points(self, thetas):
        thetas = np.asarray(thetas, float)[:, None]
        return self.center + np.cos(thetas) * self.u + np.sin(thetas) * self.v

    def svg_axes(self):
        """Return (rx, ry, phi_deg): the semi-axes and x-rotation of the ellipse.

        The unit circle maps through M = [u v] to this ellipse, so the singular
        values of M are the semi-axes and the first left-singular vector gives
        the major-axis direction.
        """
        M = np.column_stack([self.u, self.v])
        U_, S_, _ = np.linalg.svd(M)
        rx, ry = float(S_[0]), float(S_[1])
        phi = math.degrees(math.atan2(U_[1, 0], U_[0, 0]))
        return rx, ry, phi


def project_circle(R, t, radius, to_AB, s, cx, cy, half):
    """Project the world circle C + radius*(cos t*U + sin t*V) into pixel space.

    `to_AB(Pw) -> (A, B, Z)` is the camera projector (Z = depth); (s, cx, cy,
    half) the pixel fit (half = render_px/2). Returns an Ellipse whose
    `depth_coeffs` attribute carries the camera depth of the circle point at
    angle t as Zc + cos t*Zu + sin t*Zv.
    """
    R = np.asarray(R, float)
    return project_circle_uv(np.asarray(t, float), R[:, 0] * radius,
                             R[:, 2] * radius, to_AB, s, cx, cy, half)


def project_circle_uv(C, U, V, to_AB, s, cx, cy, half):
    """project_circle for a circle given directly by center C and in-plane
    radius vectors U, V (world space): point(t) = C + cos t*U + sin t*V."""
    C = np.asarray(C, float)
    pts = np.stack([C, C + U, C + V])
    A, B, Z = to_AB(pts)
    px = (A - cx) * s + half
    py = (B - cy) * s + half
    center = np.array([px[0], py[0]])
    u = np.array([px[1] - px[0], py[1] - py[0]])
    v = np.array([px[2] - px[0], py[2] - py[0]])
    depth_coeffs = (float(Z[0]), float(Z[1] - Z[0]), float(Z[2] - Z[0]))
    return Ellipse(center, u, v, depth_coeffs)


def _angle_in_sector(local_x, local_z, sector):
    """Boolean mask: do local (x,z) coords fall within [0, sector] degrees?"""
    if sector >= 360.0 - 1e-9:
        return np.ones(np.shape(local_x), bool)
    ang = np.degrees(np.arctan2(local_z, local_x)) % 360.0
    return ang <= sector + 1e-6


class CylinderOccluder:
    """Finite cylinder wall (unit radius, height 0..1 in the local frame)
    under transform R, t; optional angular sector.

    Works in the primitive's LOCAL frame (Minv = R^-1, like ConeOccluder) so
    elliptical scale and shear are exact — 30136's log walls are elliptical
    cylinders, and a circular mean-radius proxy leaked hidden edges through.
    The ray parameter lambda is invariant under the linear map, so returned
    depths are world units along F, same as the other occluders.

    `depth(O, F)` returns the nearest ray hit parameter lambda (depth along F)
    for each ray origin in O, inf on miss.
    """

    def __init__(self, R, t, sector):
        self.R = np.asarray(R, float)
        self.t = np.asarray(t, float)
        self.Minv = np.linalg.inv(self.R)
        self.sector = sector

    def _hits(self, O, F, clamp=True):
        """Both wall intersections per ray as (lam_near, lam_far); invalid
        hits (out of height / sector / miss) are +inf / -inf respectively.
        clamp=False skips the height/sector bounds — an ordering proxy for
        rays that cross the circle where the finite wall doesn't exist."""
        O = np.atleast_2d(O).astype(float)
        o = (O - self.t) @ self.Minv.T
        f = self.Minv @ np.asarray(F, float)
        a = f[0] * f[0] + f[2] * f[2]
        near = np.full(len(o), np.inf)
        far = np.full(len(o), -np.inf)
        if a < 1e-12:                                 # ray parallel to axis
            return near, far
        b = 2.0 * (o[:, 0] * f[0] + o[:, 2] * f[2])
        c = o[:, 0] * o[:, 0] + o[:, 2] * o[:, 2] - 1.0
        disc = b * b - 4 * a * c
        ok = disc >= 0
        sq = np.sqrt(np.where(ok, disc, 0.0))
        for lam in ((-b - sq) / (2 * a), (-b + sq) / (2 * a)):
            if clamp:
                P_ = o + lam[:, None] * f
                y = P_[:, 1]
                valid = (ok & (y >= -1e-6) & (y <= 1.0 + 1e-6)
                         & _angle_in_sector(P_[:, 0], P_[:, 2], self.sector))
            else:
                valid = ok
            near = np.minimum(near, np.where(valid, lam, np.inf))
            far = np.maximum(far, np.where(valid, lam, -np.inf))
        return near, far

    def depth(self, O, F):
        return self._hits(O, F)[0]

    def depth_far(self, O, F, clamp=True):
        return self._hits(O, F, clamp=clamp)[1]


class ConeOccluder:
    """Truncated cone: local radius (top+1) at y=0 tapering to `top` at y=1,
    under transform R, t; optional angular sector.

    Works in the primitive's LOCAL frame (Minv = R^-1) so scale and shear are
    exact; the ray parameter lambda is invariant under the linear map, so the
    returned depths are world units along F, same as the other occluders.
    """

    def __init__(self, R, t, sector, top):
        self.R = np.asarray(R, float)
        self.t = np.asarray(t, float)
        self.Minv = np.linalg.inv(self.R)
        self.sector = sector
        self.top = float(top)

    def _hits(self, O, F, clamp=True):
        O = np.atleast_2d(O).astype(float)
        o = (O - self.t) @ self.Minv.T
        f = self.Minv @ np.asarray(F, float)
        rb = self.top + 1.0                     # base radius, local units
        k = rb - o[:, 1]                        # section radius at the origin's y
        a = f[0] * f[0] + f[2] * f[2] - f[1] * f[1]
        b = 2.0 * (o[:, 0] * f[0] + o[:, 2] * f[2] + k * f[1])
        c = o[:, 0] * o[:, 0] + o[:, 2] * o[:, 2] - k * k
        near = np.full(len(o), np.inf)
        far = np.full(len(o), -np.inf)
        if abs(a) < 1e-12:                      # ray parallel to a generator
            with np.errstate(divide="ignore", invalid="ignore"):
                lam = np.where(np.abs(b) > 1e-12, -c / b, np.inf)
            roots, ok = [lam], np.abs(b) > 1e-12
        else:
            disc = b * b - 4 * a * c
            ok = disc >= 0
            sq = np.sqrt(np.where(ok, disc, 0.0))
            roots = [(-b - sq) / (2 * a), (-b + sq) / (2 * a)]
        for lam in roots:
            P_ = o + lam[:, None] * f
            y = P_[:, 1]
            if clamp:
                valid = (ok & np.isfinite(lam) & (y >= -1e-6) & (y <= 1 + 1e-6)
                         & _angle_in_sector(P_[:, 0], P_[:, 2], self.sector))
            else:
                valid = ok & np.isfinite(lam) & (rb - y >= 0)   # not the mirror nappe
            near = np.minimum(near, np.where(valid, lam, np.inf))
            far = np.maximum(far, np.where(valid, lam, -np.inf))
        return near, far

    def depth(self, O, F):
        return self._hits(O, F)[0]

    def depth_far(self, O, F, clamp=True):
        return self._hits(O, F, clamp=clamp)[1]


class DiscOccluder:
    """Planar disc / annulus spanned by the local X/Z columns (U, V).

    The radial and sector tests run in unit param coords (solved through the
    U/V Gram matrix), so an elliptically scaled disc is exact — the previous
    mean-radius circle proxy misjudged elliptical rims. inner/outer are unit
    multiples (a ring's bore and rim)."""

    def __init__(self, R, t, sector, inner, outer):
        self.C = np.asarray(t, float)
        R = np.asarray(R, float)
        self.U, self.V = R[:, 0], R[:, 2]
        n = np.cross(self.U, self.V)
        self.n = n / (np.linalg.norm(n) or 1.0)
        self.inner = float(inner)
        self.outer = float(outer)
        self.sector = sector
        G = np.array([[self.U @ self.U, self.U @ self.V],
                      [self.U @ self.V, self.V @ self.V]])
        self.Ginv = (np.linalg.inv(G)
                     if abs(np.linalg.det(G)) > 1e-18 else None)

    def depth(self, O, F):
        O = np.atleast_2d(O).astype(float)
        F = np.asarray(F, float)
        denom = float(F @ self.n)
        out = np.full(O.shape[0], np.inf)
        if abs(denom) < 1e-12 or self.Ginv is None:   # parallel / degenerate
            return out
        lam = ((self.C - O) @ self.n) / denom
        rel = O + lam[:, None] * F - self.C
        lx, lz = self.Ginv @ np.stack([rel @ self.U, rel @ self.V])
        rad = np.hypot(lx, lz)
        valid = ((rad >= self.inner - 1e-6) & (rad <= self.outer + 1e-6)
                 & _angle_in_sector(lx, lz, self.sector))
        return np.where(valid, lam, out)


class TriangleOccluder:
    """Flat triangles (world coords, shape (M,3,3)) as a gridless depth source.

    `depth(O, F)` returns, per ray, the nearest triangle-plane hit parameter
    lambda inside the triangle, inf on miss.
    """

    def __init__(self, tris):
        self.tris = np.asarray(tris, float) if len(tris) else np.zeros((0, 3, 3))

    def depth(self, O, F):
        O = np.atleast_2d(O).astype(float)
        F = np.asarray(F, float)
        out = np.full(O.shape[0], np.inf)
        for tri in self.tris:
            v0, v1, v2 = tri
            e0, e1 = v1 - v0, v2 - v0
            n = np.cross(e0, e1)
            denom = float(F @ n)
            if abs(denom) < 1e-12:
                continue
            lam = ((v0 - O) @ n) / denom
            Ph = O + lam[:, None] * F
            e2 = Ph - v0
            d00 = float(e0 @ e0); d01 = float(e0 @ e1); d11 = float(e1 @ e1)
            d20 = e2 @ e0; d21 = e2 @ e1
            denomb = d00 * d11 - d01 * d01
            if abs(denomb) < 1e-18:
                continue
            v = (d11 * d20 - d01 * d21) / denomb
            w = (d00 * d21 - d01 * d20) / denomb
            u = 1.0 - v - w
            inside = (u >= -1e-6) & (v >= -1e-6) & (w >= -1e-6)
            out = np.minimum(out, np.where(inside, lam, np.inf))
        return out


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


@dataclass(eq=False, kw_only=True)
class Primitive:
    """One substituted analytic primitive under world transform p -> R @ p + t.

    Identity semantics (eq=False): faces reference their source primitive and
    hlr keys ordering maps by instance, so two geometrically equal primitives
    must stay distinct. kind is the stable string used in face dicts and SVG
    op tags.
    """
    R: np.ndarray
    t: np.ndarray
    sector: float = 360.0

    kind = None          # class attribute, overridden per subclass

    def __post_init__(self):
        self.R = np.asarray(self.R, float)
        self.t = np.asarray(self.t, float)

    @property
    def is_full(self):
        return self.sector >= 360.0 - 1e-9

    def occluder(self):
        """Cached analytic occlusion surface; None for stroke-only kinds.
        Cached so every consumer (global occluder list, silhouette self-
        exclusion, witness ordering) sees the SAME instance."""
        try:
            return self._occ
        except AttributeError:
            self._occ = self._make_occluder()
            return self._occ

    def _make_occluder(self):
        return None

    def radius_at(self, level):
        """Unit-circle radius (in primitive units) at `level` along the axis."""
        return 1.0

    def ring_pts(self, thetas, level, radius=None):
        """World points on the primitive's circle at `thetas` (radians),
        `level` along the axis (0 = base ring, 1 = top ring). `radius`
        overrides the default radius_at(level)."""
        if radius is None:
            radius = self.radius_at(level)
        U, A, V = self.R[:, 0], self.R[:, 1], self.R[:, 2]
        base = self.t + level * A
        return base + radius * (np.cos(thetas)[:, None] * U
                                + np.sin(thetas)[:, None] * V)

    def fit_pts(self, n=16):
        """World sample points on the primary circle(s), for the pixel fit."""
        ang = np.linspace(0.0, math.radians(self.sector), n)
        return self.ring_pts(ang, 0.0)

    def _rim_circles(self):
        """([(center, radius, side)], slope) for wall kinds; ([], 0.0)
        otherwise. side is +-1 along +A; slope is d(radius)/d(height)."""
        return [], 0.0

    def wall_rims(self):
        """[(key, side, slope)] for a WALL's rim circles (Cylinder/Cone).

        `side` is which side of the circle plane the wall lies on (+-1 along
        the key's canonical axis); `slope` is d(radius)/d(height) in that
        canonical direction, rounded. A rim arc is suppressed wherever a
        wall with EQUAL slope lies on the OPPOSITE side (stacked
        cone/cylinder sections, e.g. 4589's con3-on-con4 joint) — coverage
        is per angular bin (hlr.smooth_rim_skips), so a sectored sharer
        suppresses only its own stretch and the rim survives across the
        gaps (60474's bite-interrupted lower wall, 3941's base-lip
        cutouts). Same-side sharing and unequal slopes (creases) keep the
        arc."""
        rims, rate = self._rim_circles()
        if not rims:
            return []
        A = self.R[:, 1]
        ahat = A / (np.linalg.norm(A) or 1.0)
        out = []
        for C, radius, side in rims:
            key = rim_key(C, A, radius)
            aligned = float(np.dot(ahat, key[1])) > 0
            out.append((key,
                        side if aligned else -side,
                        round(rate if aligned else -rate, 3)))
        return out

    def flat_rims(self):
        """[(key, side)] for a FLAT surface's edge circles (Disc/Ring).

        `side` is radial: +1 if the surface lies INSIDE the circle (the
        circle is its outer edge), -1 if outside (inner edge). A circle
        where full-sector flat surfaces lie on BOTH radial sides is an
        interior seam of one continuous annulus (LDraw tiles wide flats
        from concentric ring primitives, e.g. 4073's plate top), not an
        edge — drawing it leaves a phantom 'collar' ring."""
        return []

    def _rim_emit_spans(self, skip_rims):
        """Per rim circle (in _rim_circles order: base, then top when
        present): local-angle (deg0, deg1) spans of the rim arc that remain
        real edges. skip_rims maps (rim_key, side) -> True (the whole rim is
        a smooth joint) or a rim_span_bins mask (a sectored wall continues
        on the other side over those angles only — 60474's bite-interrupted
        lower wall). A plain set of (key, side) pairs reads as all-True."""
        whole = [(0.0, self.sector)]
        if not skip_rims:
            return whole, whole
        rims = self.wall_rims()
        out = []
        for i in (0, 1):
            if i >= len(rims) or (rims[i][0], rims[i][1]) not in skip_rims:
                out.append(whole)
                continue
            v = (skip_rims[(rims[i][0], rims[i][1])]
                 if isinstance(skip_rims, dict) else True)
            out.append([] if v is True
                       else rim_uncovered_spans(self, rims[i][0], v))
        return out

    def drawn_with_depth(self, proj, skip_rims=None):
        """Return [(op, depth_fn)] pre-occlusion drawn-op candidates.

        depth_fn maps an op's sample params to camera depth: degrees for arc
        ops, t in [0,1] for line ops. `skip_rims` is a set of (rim_key, side)
        pairs (see wall_rims) whose base/top arcs must not be emitted: rims
        where a full-sector wall continues smoothly on the other side of the
        circle plane (stacked section joints)."""
        raise NotImplementedError

    def faces(self, proj):
        """Fill faces (dicts) for the shading pipeline; [] for stroke-only
        kinds. Face dicts carry pixel-space "poly", per-vertex "zs", mean
        "depth", the source "prim", and either a view-space "normal" (flat
        faces) or a linear-gradient spec (wall faces)."""
        return []

    def _flat_face(self, w, hole_w, proj):
        px, py, z = proj.to_px(w)
        n = self.R[:, 1]
        n = n / np.linalg.norm(n)
        nv = np.array([n @ proj.right, n @ proj.up, n @ proj.fwd])
        if nv[2] > 0:
            nv = -nv
        face = {"poly": np.stack([px, py], 1), "normal": nv,
                "depth": float(np.mean(z)), "zs": z, "kind": self.kind,
                "prim": self}
        if hole_w is not None:
            hx, hy, _ = proj.to_px(hole_w)
            face["holes"] = [np.stack([hx, hy], 1)]
        return face

    def _wall_span_face(self, lo, hi, interior, proj, normal_fn=None):
        U, V = self.R[:, 0], self.R[:, 2]
        ths = np.linspace(lo, hi, 40)
        top = self.ring_pts(ths, 1.0)
        bot = self.ring_pts(ths, 0.0)
        tpx, tpy, tz = proj.to_px(top)
        bpx, bpy, bz = proj.to_px(bot)
        poly = np.concatenate([np.stack([tpx, tpy], 1),
                               np.stack([bpx, bpy], 1)[::-1]], axis=0)
        zs = np.concatenate([tz, bz])
        # gradient axis: mid-height points at the span's end angles
        mid = self.ring_pts(np.array([lo, hi]), 0.5)
        mpx, mpy, _ = proj.to_px(mid)
        p0 = (float(mpx[0]), float(mpy[0])); p1 = (float(mpx[1]), float(mpy[1]))
        axis = np.array([p1[0] - p0[0], p1[1] - p0[1]])
        L2 = float(axis @ axis) or 1.0
        samples = []
        for th in np.linspace(lo, hi, 9):
            if normal_fn is None:
                n = math.cos(th) * U + math.sin(th) * V
            else:
                n = normal_fn(th)
            n = n / np.linalg.norm(n)
            if interior:
                n = -n                               # inward surface normal
            nv = np.array([n @ proj.right, n @ proj.up, n @ proj.fwd])
            p = self.ring_pts(np.array([th]), 0.5)
            ppx, ppy, _ = proj.to_px(p)
            off = ((ppx[0] - p0[0]) * axis[0] + (ppy[0] - p0[1]) * axis[1]) / L2
            samples.append((float(np.clip(off, 0.0, 1.0)), nv))
        return {"poly": poly, "zs": zs, "depth": float(np.mean(zs)),
                "kind": self.kind, "prim": self, "interior": interior,
                "span_deg": math.degrees(hi - lo),
                "grad_axis": (p0, p1), "grad_samples": samples}


@dataclass(eq=False, kw_only=True)
class Edge(Primitive):
    """Drawn circle arc; no surface."""
    kind = "edge"

    def drawn_with_depth(self, proj, skip_rims=None):
        ell = proj.circle(self.R, self.t, 1.0)
        return [(_arc_op(ell, 0.0, self.sector, "edge"), _arc_depth_fn(ell))]


@dataclass(eq=False, kw_only=True)
class Disc(Primitive):
    """Filled circle in the local XZ plane."""
    kind = "disc"

    def _make_occluder(self):
        return DiscOccluder(self.R, self.t, self.sector, 0.0, 1.0)

    def flat_rims(self):
        ru = float(np.linalg.norm(self.R[:, 0]))
        return [(rim_key(self.t, self.R[:, 1], ru), +1)]

    def drawn_with_depth(self, proj, skip_rims=None):
        if skip_rims and ("flat", *self.flat_rims()[0]) in skip_rims:
            return []
        ell = proj.circle(self.R, self.t, 1.0)
        return [(_arc_op(ell, 0.0, self.sector, "edge"), _arc_depth_fn(ell))]

    def faces(self, proj):
        sect = math.radians(self.sector)
        th = np.linspace(0.0, sect, 64)
        w = self.ring_pts(th, 0.0)
        if sect < 2 * math.pi - 1e-6:
            # partial sector: close the pie through the center — the implicit
            # arc-end chord otherwise fills a phantom triangle over the
            # uncovered quarter (double-painting stud10's coplanar fan tris)
            w = np.concatenate([w, self.t[None, :]], axis=0)
        return [self._flat_face(w, None, proj)]


@dataclass(eq=False, kw_only=True)
class Ring(Primitive):
    """Annulus: inner radius `inner`, outer `inner + 1`."""
    kind = "ring"
    inner: int = 1

    def _make_occluder(self):
        return DiscOccluder(self.R, self.t, self.sector,
                            self.inner, self.inner + 1)

    def radius_at(self, level):
        return self.inner + 1

    def flat_rims(self):
        ru = float(np.linalg.norm(self.R[:, 0]))
        A = self.R[:, 1]
        return [(rim_key(self.t, A, ru * (self.inner + 1)), +1),
                (rim_key(self.t, A, ru * self.inner), -1)]

    def drawn_with_depth(self, proj, skip_rims=None):
        skip = skip_rims or set()
        ops = []
        for radius, rim in zip((self.inner + 1, self.inner), self.flat_rims()):
            if ("flat", *rim) in skip:
                continue
            ell = proj.circle(self.R, self.t, radius)
            ops.append((_arc_op(ell, 0.0, self.sector, "edge"),
                        _arc_depth_fn(ell)))
        return ops

    def faces(self, proj):
        sect = math.radians(self.sector)
        th = np.linspace(0.0, sect, 64)
        # Annulus: full sector gets a REAL hole ring (the bore); a partial
        # sector is a simple valid polygon, so keep the outer-forward /
        # inner-back concatenation there.
        outer = self.ring_pts(th, 0.0, radius=self.inner + 1)
        inner = self.ring_pts(th, 0.0, radius=self.inner)
        if sect >= 2 * math.pi - 1e-6:
            return [self._flat_face(outer, inner, proj)]
        w = np.concatenate([outer, inner[::-1]], axis=0)
        return [self._flat_face(w, None, proj)]


@dataclass(eq=False, kw_only=True)
class Cylinder(Primitive):
    """Wall of a finite cylinder: radius 1, axis from t to t + A."""
    kind = "cyli"

    def _make_occluder(self):
        return CylinderOccluder(self.R, self.t, self.sector)

    def _rim_circles(self):
        A = self.R[:, 1]
        ru = float(np.linalg.norm(self.R[:, 0]))
        return [(self.t, ru, +1), (self.t + A, ru, -1)], 0.0

    def _end_circles(self):
        """Both end circles of the wall (for merge chain-end pairing)."""
        A = self.R[:, 1]
        ru = float(np.linalg.norm(self.R[:, 0]))
        return [(self.t, ru), (self.t + A, ru)]

    def fit_pts(self, n=16):
        ang = np.linspace(0.0, math.radians(self.sector), n)
        return np.vstack([self.ring_pts(ang, 0.0),      # base + top rings
                          self.ring_pts(ang, 1.0)])

    def drawn_with_depth(self, proj, skip_rims=None):
        base_spans, top_spans = self._rim_emit_spans(skip_rims)
        A = self.R[:, 1]
        fwd = np.asarray(proj.fwd, float)
        # silhouette generators: the local wall normal at param t is
        # (cos t, 0, sin t) and normals map through R^-T, so n.fwd = 0
        # reduces via g = R^-1 @ fwd to g0 cos t + g2 sin t = 0. For an
        # elliptical wall (30136's logs) the RADIAL direction is not the
        # normal, so the old radial test put the limb at the wrong angle.
        g = np.linalg.inv(self.R) @ fwd
        theta = math.atan2(-float(g[0]), float(g[2]))
        base = proj.circle(self.R, self.t, 1.0)
        top = proj.circle(self.R, self.t + A, 1.0)
        pairs = []
        for th in (theta, theta + math.pi):
            deg = math.degrees(th) % 360.0
            if self.is_full or deg <= self.sector + 1e-6:
                pb, pt = base.point(th), top.point(th)
                op = ("line", float(pb[0]), float(pb[1]),
                      float(pt[0]), float(pt[1]), "sil")
                pairs.append((op, _line_depth_fn(base.depth(th), top.depth(th))))
        for d0, d1 in base_spans:
            pairs.append((_arc_op(base, d0, d1, "edge"),
                          _arc_depth_fn(base)))
        for d0, d1 in top_spans:
            pairs.append((_arc_op(top, d0, d1, "edge"),
                          _arc_depth_fn(top)))
        return pairs

    def faces(self, proj):
        """Cylinder wall fills: the camera-facing outer half AND the far
        half's interior surface (visible when looking into an open tube —
        leaving it out produced 4019's white voids). Each visible span
        becomes one arc-region polygon with a linear-gradient spec; a partial
        sector can split a span in two where the arc wraps past 0.

        Like the cone, everything runs off the local frame: with
        g = R^-1 @ fwd, n(theta).fwd = hyp*cos(theta - phi0), so the outer
        wall faces the camera on (phi0 + pi/2, phi0 + 3pi/2) — the halves
        split exactly at the silhouette generators even under elliptical
        scale, and normal_fn supplies the true (R^-T) surface normals."""
        Minv = np.linalg.inv(self.R)
        g = Minv @ np.asarray(proj.fwd, float)
        MT = Minv.T

        def normal_fn(th):
            return MT @ np.array([math.cos(th), 0.0, math.sin(th)])

        if math.hypot(float(g[0]), float(g[2])) < 1e-12:
            return []                            # axis points at camera: no wall
        phi0 = math.atan2(float(g[2]), float(g[0]))
        sect = math.radians(self.sector)
        halves = [(phi0 + math.pi / 2, False),           # outer near half
                  (phi0 - math.pi / 2, True)]            # interior far half
        faces = []
        for start, interior in halves:
            for lo, hi in _arc_sector_spans(start, math.pi, sect):
                f = self._wall_span_face(lo, hi, interior, proj,
                                         normal_fn=normal_fn)
                if f is not None:
                    faces.append(f)
        return faces


@dataclass(eq=False, kw_only=True)
class Cone(Primitive):
    """Truncated-cone wall: local radius top+1 at y=0 tapering to `top` at
    y=1. `top` is a float: merged smooth stacks produce non-integer values."""
    kind = "con"
    top: float = 0.0

    def _make_occluder(self):
        return ConeOccluder(self.R, self.t, self.sector, self.top)

    def radius_at(self, level):
        return self.top + 1 - level                      # top+1 at base -> top

    def _rim_circles(self):
        A = self.R[:, 1]
        ru = float(np.linalg.norm(self.R[:, 0]))
        ah = float(np.linalg.norm(A)) or 1.0
        rate = -ru / ah                                  # radius shrinks toward +A
        rims = [(self.t, (self.top + 1) * ru, +1)]
        if self.top > 0:
            rims.append((self.t + A, self.top * ru, -1))
        return rims, rate

    def _end_circles(self):
        """Both end circles INCLUDING the radius-0 apex (top == 0).

        Distinct from _rim_circles, which omits the apex: an apex has no
        rim arc to draw or suppress, but it IS a chain terminus — the
        merge's end-pairing needs it so an apex-terminated stack still
        resolves to exactly two free ends. Collapsing this into
        _rim_circles breaks con*-on-con0 merges."""
        A = self.R[:, 1]
        ru = float(np.linalg.norm(self.R[:, 0]))
        return [(self.t, (self.top + 1) * ru), (self.t + A, self.top * ru)]

    def fit_pts(self, n=16):
        ang = np.linspace(0.0, math.radians(self.sector), n)
        return np.vstack([self.ring_pts(ang, 0.0),      # base + top rings
                          self.ring_pts(ang, 1.0)])

    def drawn_with_depth(self, proj, skip_rims=None):
        base_spans, top_spans = self._rim_emit_spans(skip_rims)
        N = float(self.top)
        A3 = self.R[:, 1]
        fwd = np.asarray(proj.fwd, float)
        base = proj.circle(self.R, self.t, N + 1.0)
        topc = proj.circle(self.R, self.t + A3, N) if N > 0 else None
        if topc is None:                        # apex: project the point itself
            pxa, pya, zz = proj.to_px((self.t + A3)[None, :])
            apex_xy = (pxa[0], pya[0])
            apex_z = float(zz[0])
        pairs = []
        # silhouette generators: local cone normal is constant along a
        # generator, m(th) = (cos th, 1, sin th); world n.fwd = 0 reduces via
        # g = R^-1 @ fwd to g0 cos th + g2 sin th = -g1 (0, 1, or 2 solutions).
        g = np.linalg.inv(self.R) @ fwd
        A_, B_, C_ = float(g[0]), float(g[2]), float(-g[1])
        hyp = math.hypot(A_, B_)
        if hyp > 1e-12 and abs(C_) <= hyp:
            phi0 = math.atan2(B_, A_)
            dth = math.acos(max(-1.0, min(1.0, C_ / hyp)))
            for th in (phi0 + dth, phi0 - dth):
                deg = math.degrees(th) % 360.0
                if self.is_full or deg <= self.sector + 1e-6:
                    pb = base.point(th)
                    if topc is not None:
                        pt_, zt = topc.point(th), topc.depth(th)
                    else:
                        pt_, zt = apex_xy, apex_z
                    op = ("line", float(pb[0]), float(pb[1]),
                          float(pt_[0]), float(pt_[1]), "sil")
                    pairs.append((op, _line_depth_fn(base.depth(th), zt)))
        for d0, d1 in base_spans:
            pairs.append((_arc_op(base, d0, d1, "edge"),
                          _arc_depth_fn(base)))
        if topc is not None:
            for d0, d1 in top_spans:
                pairs.append((_arc_op(topc, d0, d1, "edge"),
                              _arc_depth_fn(topc)))
        return pairs

    def faces(self, proj):
        """Cone wall fills. Unlike a cylinder, the front-facing arc is NOT a
        half: with g = R^-1 @ fwd and (A, B, C) = (g0, g2, -g1), n(theta).fwd
        = hyp*cos(theta - phi0) - C, so the outer wall is visible on
        (phi0+d, phi0+2pi-d) where d = acos(C/hyp) — the generator angles —
        and the interior far wall on the complement. Axis-on view (hyp ~ 0,
        or |C| >= hyp): every generator faces the same way, one full-circle
        span."""
        Minv = np.linalg.inv(self.R)
        g = Minv @ np.asarray(proj.fwd, float)
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
        sect = math.radians(self.sector)
        faces = []
        for start, end, interior in spans:
            if end - start < 1e-6:
                continue
            for lo, hi in _arc_sector_spans(start, end - start, sect):
                f = self._wall_span_face(lo, hi, interior, proj,
                                         normal_fn=normal_fn)
                if f is not None:
                    faces.append(f)
        return faces


_KIND_CLASSES = {"edge": Edge, "cyli": Cylinder, "disc": Disc}


def from_ref(name, R, t):
    """Construct the Primitive for an LDraw subfile reference, or None to
    fall back to faceted recursion (see parse_primitive for what is and is
    not substitutable, and why ndis stays faceted)."""
    spec = parse_primitive(name)
    if spec is None:
        return None
    kind, sector, inner = spec
    if kind == "ring":
        return Ring(R=R, t=t, sector=sector, inner=inner)
    if kind == "con":
        return Cone(R=R, t=t, sector=sector, top=float(inner))
    return _KIND_CLASSES[kind](R=R, t=t, sector=sector)


def _arc_op(ell, t0_deg, t1_deg, kind):
    """Parametric arc op: ('arc', cx, cy, ux, uy, vx, vy, t0_deg, t1_deg, kind).
    The point at param t (degrees) is center + cos t*u + sin t*v — the SAME
    parameterization the depth_fn uses, so visibility sampling stays consistent.
    SVG (rx, ry, phi) is derived only at write time via Ellipse.svg_axes()."""
    return ("arc", float(ell.center[0]), float(ell.center[1]),
            float(ell.u[0]), float(ell.u[1]), float(ell.v[0]), float(ell.v[1]),
            float(t0_deg), float(t1_deg), kind)


def arc_ellipse(op):
    """Reconstruct the parametric Ellipse from an arc op (carries depth-free geometry)."""
    _, cx, cy, ux, uy, vx, vy, _, _, _ = op
    return Ellipse((cx, cy), (ux, uy), (vx, vy))


def _arc_depth_fn(ell):
    zc, zu, zv = ell.depth_coeffs

    def depth(deg):
        t = np.radians(np.asarray(deg, float))
        return zc + np.cos(t) * zu + np.sin(t) * zv
    return depth


def _line_depth_fn(z0, z1):
    def depth(ts):
        ts = np.asarray(ts, float)
        return z0 + (z1 - z0) * ts
    return depth


def rim_key(C, A, radius):
    """Canonical key for a rim circle (center, axis line, radius), rounded so
    coincident rims from different primitives compare equal."""
    C = np.round(np.asarray(C, float), 3)
    n = np.asarray(A, float)
    ln = np.linalg.norm(n)
    n = n / (ln or 1.0)
    for c in n:                          # canonical axis sign
        if abs(c) > 1e-9:
            if c < 0:
                n = -n
            break
    return (tuple(C), tuple(np.round(n, 3)), round(float(radius), 3))


_RIM_BINS = 720          # 0.5-degree angular bins for rim-seam coverage


def _rim_key_frame(key):
    """Canonical in-plane (u0, v0) frame for a rim key's axis, so every
    primitive sharing the circle bins its angles consistently."""
    n = np.asarray(key[1], float)
    e = np.zeros(3)
    e[int(np.argmin(np.abs(n)))] = 1.0
    u0 = np.cross(n, e)
    u0 /= np.linalg.norm(u0)
    v0 = np.cross(n, u0)
    return u0, v0


def _rim_bin_idx(prim, key):
    """(local angles, bin index per angle) sampling the primitive's sector
    densely (>= 2 samples per bin at a full sector) — direction and
    handedness of the local frame fall out of the sampling."""
    th = np.linspace(0.0, math.radians(min(prim.sector, 360.0)),
                     2 * _RIM_BINS)
    u0, v0 = _rim_key_frame(key)
    d = np.cos(th)[:, None] * prim.R[:, 0] + np.sin(th)[:, None] * prim.R[:, 2]
    ang = np.arctan2(d @ v0, d @ u0)
    idx = np.floor((ang % (2 * math.pi)) / (2 * math.pi)
                   * _RIM_BINS).astype(int) % _RIM_BINS
    return th, idx


def rim_span_bins(prim, key):
    """Boolean mask over _RIM_BINS angular bins: which angles of the rim
    circle `key` the primitive's sector covers, in the key's canonical
    in-plane frame (so rotated instances of a sectored primitive land in
    consistent bins)."""
    _, idx = _rim_bin_idx(prim, key)
    mask = np.zeros(_RIM_BINS, bool)
    mask[idx] = True
    return mask


def rim_facet_span_bins(key, side, slope, tris, rel_tol=2e-3, touch_tol=0.05,
                        max_span_deg=25.0):
    """Boolean mask over _RIM_BINS angular bins: which angles of the rim
    circle `key` are covered by FACET-authored wall stretches — triangles
    whose vertices lie on the wall surface implied by (side, slope) and
    that abut the rim plane. LDraw files resume a primitive-tiled wall as
    raw quads (60474: the outer wall beside each bite, half the
    center-hole wall); those stretches must count as wall coverage in
    hlr.smooth_rim_skips or the seam suppression leaves stub arcs over
    them. Guards: the facet must extend AWAY from the rim plane (a cap
    facet whose vertices merely touch the circle is not wall) and span
    under max_span_deg (an on-circle chord facet crossing the interior is
    not wall either — only its vertices are surface-tested). The radial
    band is asymmetric: polygonal tessellation puts stitching vertices up
    to a 16-gon's chord inset INSIDE the circle (60474's hole wall mixes
    on-circle corners with mid-chord points), but never outside."""
    mask = np.zeros(_RIM_BINS, bool)
    if tris is None or len(tris) == 0:
        return mask
    C = np.asarray(key[0], float)
    n = np.asarray(key[1], float)
    n = n / np.linalg.norm(n)
    r = float(key[2])
    tol = max(rel_tol * r, 1e-3)
    V = np.asarray(tris, float)                    # (T, 3, 3)
    h = (V - C) @ n                                # signed height per vertex
    sh = side * h
    ok = np.all(sh > -touch_tol, axis=1)           # wall side of the plane
    ok &= np.min(sh, axis=1) < touch_tol           # abuts the rim circle
    ok &= np.max(sh, axis=1) > touch_tol           # extends off the plane
    D = V - C - h[..., None] * n                   # radial components
    rad = np.linalg.norm(D, axis=2)
    exp = r + slope * h                            # wall radius at height
    ok &= np.all(rad <= exp + tol, axis=1)
    ok &= np.all(rad >= exp * math.cos(math.pi / 16) - tol, axis=1)
    if not ok.any():
        return mask
    u0, v0 = _rim_key_frame(key)
    ang = np.arctan2(D[ok] @ v0, D[ok] @ u0)       # (K, 3) vertex angles
    rel = (ang - ang[:, :1] + math.pi) % (2 * math.pi) - math.pi
    for a0, rl in zip(ang[:, 0], rel):
        sp = float(rl.max() - rl.min())
        if sp > math.radians(max_span_deg):
            continue
        th = np.linspace(a0 + rl.min(), a0 + rl.max(),
                         2 * max(1, int(sp / (2 * math.pi) * _RIM_BINS)) + 2)
        idx = np.floor((th % (2 * math.pi)) / (2 * math.pi)
                       * _RIM_BINS).astype(int) % _RIM_BINS
        mask[idx] = True
    return mask


def rim_cond_span_bins(key, cond, rel_tol=2e-3, touch_tol=0.05,
                       max_span_deg=30.0):
    """Boolean mask over _RIM_BINS angular bins: which angles of the rim
    circle `key` are covered by author-declared type-5 conditional lines —
    chords whose endpoints lie ON the circle. A condline along a section
    joint declares it smooth regardless of the slopes meeting there (4740's
    dish stacks cone bands of three different pitches and condlines every
    junction circle), so in hlr.smooth_rim_skips this coverage counts as an
    opposite-side continuation unconditionally. Real creases are authored
    as type-2 edges (4740's boss base) and contribute nothing here. Guards:
    both endpoints must sit in the rim plane and at the rim radius, and the
    chord must span under max_span_deg (a diameter's endpoints also lie on
    the circle; primitive tessellation chords stay at or under 22.5 deg)."""
    mask = np.zeros(_RIM_BINS, bool)
    if not cond:
        return mask
    C = np.asarray(key[0], float)
    n = np.asarray(key[1], float)
    n = n / np.linalg.norm(n)
    r = float(key[2])
    tol = max(rel_tol * r, 1e-3)
    E = np.asarray([np.asarray(q, float)[:2] for q in cond])   # (N, 2, 3)
    h = (E - C) @ n
    ok = np.all(np.abs(h) < touch_tol, axis=1)                 # in the plane
    D = E - C - h[..., None] * n
    rad = np.linalg.norm(D, axis=2)
    ok &= np.all(np.abs(rad - r) < tol, axis=1)                # on the circle
    if not ok.any():
        return mask
    u0, v0 = _rim_key_frame(key)
    ang = np.arctan2(D[ok] @ v0, D[ok] @ u0)                   # (K, 2)
    for a0, a1 in ang:
        rel = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        sp = abs(float(rel))
        if sp > math.radians(max_span_deg):
            continue
        lo = a0 + min(0.0, rel)
        th = np.linspace(lo, lo + sp,
                         2 * max(1, int(sp / (2 * math.pi) * _RIM_BINS)) + 2)
        idx = np.floor((th % (2 * math.pi)) / (2 * math.pi)
                       * _RIM_BINS).astype(int) % _RIM_BINS
        mask[idx] = True
    return mask


def facet_snap_rims(analytic, tris):
    """Rim circles that facet-authored wall stretches hug from inside:
    [(rim_key, snap_tol_world)]. Chord tessellation puts its stitching
    vertices up to the 16-gon inset INSIDE the true circle (2654a's
    boss-truncation ribbons resume the r=19 lip wall as flat rects at
    r~18.76), so fill seams and drawn chords along those stretches sit off
    the circle by more than any sampling tolerance. Marked circles carry a
    snap tolerance of chord-inset order — enough to pull the tessellation
    onto the circle, small enough not to reach neighboring authored
    radii (concentric lip rings sit several insets apart)."""
    if tris is None or len(tris) == 0:
        return []
    out, seen = [], set()
    for prim in analytic:
        for key, side, slope in prim.wall_rims():
            if key in seen:
                continue
            if not (rim_facet_span_bins(key, side, slope, tris).any()
                    or rim_facet_span_bins(key, -side, slope, tris).any()):
                continue
            seen.add(key)
            r = float(key[2])
            out.append((key, r * (1.0 - math.cos(math.pi / 16)) * 1.1))
    return out


def rim_uncovered_spans(prim, key, mask):
    """Local-angle (deg0, deg1) runs of the primitive's sector NOT covered
    by `mask` (canonical-frame bins, see rim_span_bins): the stretches of a
    wall's rim circle where no opposite wall continues it, so the rim stays
    a real drawn edge there."""
    th, idx = _rim_bin_idx(prim, key)
    keep = ~mask[idx]
    degs = np.degrees(th)
    spans = []
    i, n = 0, len(keep)
    while i < n:
        if keep[i]:
            j = i
            while j + 1 < n and keep[j + 1]:
                j += 1
            if degs[j] - degs[i] > 0.25:         # sub-bin jitter slivers
                spans.append((float(degs[i]), float(degs[j])))
            i = j + 1
        else:
            i += 1
    return spans


def _merged_wall(members):
    """One synthetic Cylinder/Cone covering a smooth chain of wall
    primitives (sections of the same infinite cylinder/cone). Returns None
    if the chain has no clean two free ends (degenerate or looped
    sharing)."""
    ends = {}
    for p in members:
        A = p.R[:, 1]
        for C, r in p._end_circles():
            key = rim_key(C, A, r)
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
    U0 = members[0].R[:, 0]
    u = U0 - float(U0 @ ahat) * ahat
    un = float(np.linalg.norm(u))
    if un < 1e-9:
        return None
    u = u / un
    v = np.cross(u, ahat)
    dr = r0 - r1
    if dr < 1e-9:
        return Cylinder(R=np.column_stack([r0 * u, A, r0 * v]), t=C0,
                        sector=360.0)
    return Cone(R=np.column_stack([dr * u, A, dr * v]), t=C0,
                sector=360.0, top=r1 / dr)


def merge_smooth_walls(analytic):
    """Collapse chains of full-sector Cylinder/Cone primitives that continue
    each other smoothly through a shared rim — equal slope on opposite sides
    of the rim plane, the same predicate that suppresses the rim's STROKE in
    hlr — into one synthetic primitive per chain, so the wall shades as ONE
    face with ONE gradient. Left separate, each section fits its own
    gradient axis and the shared rim shows a tone step (4589's con3-on-con4
    body: identical stops over different axis extents). Non-wall primitives,
    partial sectors, creases, and ambiguously shared rims pass through
    unchanged. The synthetic Cone's `top` may be non-integer."""
    walls = [i for i, p in enumerate(analytic)
             if isinstance(p, (Cylinder, Cone)) and p.is_full]
    by_key = defaultdict(list)
    for i in walls:
        for key, side, slope in analytic[i].wall_rims():
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
        if type(analytic[i]) is not type(analytic[j]):
            continue
        parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in walls:
        groups[find(i)].append(i)
    synth_at, drop = {}, set()
    for members in groups.values():
        if len(members) < 2:
            continue
        prim = _merged_wall([analytic[i] for i in members])
        if prim is not None:
            synth_at[min(members)] = prim
            drop.update(members)
    if not synth_at:
        return list(analytic)
    return [synth_at.get(i, p) for i, p in enumerate(analytic)
            if i in synth_at or i not in drop]


def _samples_for(op, n):
    """Return (xs, ys, params) sampling an op; params are t in [0,1] for lines
    and degrees for arcs (aligned with the op's depth_fn). `n` is a floor; the
    count is raised toward one sample per ~2 px so occlusion boundaries on long
    ops are not missed, capped to bound cost."""
    if op[0] == "line":
        _, x1, y1, x2, y2, _ = op
        length = math.hypot(x2 - x1, y2 - y1)
        n = int(min(4000, max(n, 2, length / 2)))
        ts = np.linspace(0.0, 1.0, n)
        return x1 + (x2 - x1) * ts, y1 + (y2 - y1) * ts, ts
    ell = arc_ellipse(op)
    t0, t1 = op[7], op[8]
    length = (np.hypot(*ell.u) + np.hypot(*ell.v)) / 2.0 * math.radians(abs(t1 - t0))
    n = int(min(4000, max(n, 2, length / 2)))
    degs = np.linspace(t0, t1, n)
    pts = ell.points(np.radians(degs))
    return pts[:, 0], pts[:, 1], degs


def _runs(mask):
    runs, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    return runs


def visible_subops(op_specs, occluders, ray_origin, fwd, eps, n=200):
    """Split each (op, depth_fn) into visible sub-ops against the occluders.

    `ray_origin(xs, ys) -> (N,3)` inverts the projection to world ray origins;
    `fwd` is the view direction. A sample is visible iff its own depth
    <= nearest occluder depth + eps.

    An optional 4th spec element `proxy(params) -> (xs, ys, depths)` moves the
    visibility test onto substitute geometry (fitted rounds test along their
    chord path, which lies on the mesh) while the emitted op stays the arc.
    """
    result = []
    for spec in op_specs:
        op, depth_fn = spec[0], spec[1]
        exclude = spec[2] if len(spec) > 2 else None
        proxy = spec[3] if len(spec) > 3 else None
        xs, ys, params = _samples_for(op, n)
        if proxy is not None:
            xs, ys, sd = proxy(params)
            sd = np.asarray(sd, float)
        else:
            sd = np.asarray(depth_fn(params), float)
        O = ray_origin(xs, ys)
        field = np.full(xs.shape, np.inf)
        for occ in occluders:
            if occ is exclude:
                continue
            field = np.minimum(field, occ.depth(O, fwd))
        vis = sd <= field + eps
        for (i, j) in _runs(vis):
            if i == j:
                continue                        # single isolated sample: skip
            if op[0] == "line":
                result.append(("line", float(xs[i]), float(ys[i]),
                               float(xs[j]), float(ys[j]), op[-1]))
            else:
                _, cx, cy, ux, uy, vx, vy, _, _, kind = op
                result.append(("arc", cx, cy, ux, uy, vx, vy,
                               float(params[i]), float(params[j]), kind))
    return result
