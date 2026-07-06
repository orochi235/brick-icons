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
# size. stud10 is the laterally-truncated stud of round 2x2 parts — its
# faceted outward quarter (chord quads + hard vertical joint edges) draws as
# stripes and tone bands on the camera-facing stud, while the truncation it
# models is <= 0.14 LDU: substitute the plain analytic stud.
ALIAS_REFS = {"stud10.dat": "stud.dat"}


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
    C = np.asarray(t, float)
    U = R[:, 0] * radius
    V = R[:, 2] * radius
    pts = np.stack([C, C + U, C + V])
    A, B, Z = to_AB(pts)
    px = (A - cx) * s + half
    py = (B - cy) * s + half
    center = np.array([px[0], py[0]])
    u = np.array([px[1] - px[0], py[1] - py[0]])
    v = np.array([px[2] - px[0], py[2] - py[0]])
    depth_coeffs = (float(Z[0]), float(Z[1] - Z[0]), float(Z[2] - Z[0]))
    return Ellipse(center, u, v, depth_coeffs)


def _local_basis(R, t):
    """Local axes and radius/scale from a primitive transform."""
    R = np.asarray(R, float)
    U, A, V = R[:, 0], R[:, 1], R[:, 2]
    r = (np.linalg.norm(U) + np.linalg.norm(V)) / 2.0
    ah = np.linalg.norm(A)
    return U, V, A, r, ah


def _angle_in_sector(local_x, local_z, sector):
    """Boolean mask: do local (x,z) coords fall within [0, sector] degrees?"""
    if sector >= 360.0 - 1e-9:
        return np.ones(np.shape(local_x), bool)
    ang = np.degrees(np.arctan2(local_z, local_x)) % 360.0
    return ang <= sector + 1e-6


class CylinderOccluder:
    """Finite cylinder: radius r, axis A from C to C+A, optional angular sector.

    `depth(O, F)` returns the nearest ray hit parameter lambda (depth along F)
    for each ray origin in O, inf on miss.
    """

    def __init__(self, R, t, sector):
        self.C = np.asarray(t, float)
        self.U, self.V, self.A, self.r, self.ah = _local_basis(R, t)
        self.ahat = self.A / (self.ah or 1.0)
        self.sector = sector
        self.uhat = self.U / (self.r or 1.0)
        self.vhat = self.V / (self.r or 1.0)

    def _hits(self, O, F, clamp=True):
        """Both wall intersections per ray as (lam_near, lam_far); invalid
        hits (out of height / sector / miss) are +inf / -inf respectively.
        clamp=False skips the height/sector bounds — an ordering proxy for
        rays that cross the circle where the finite wall doesn't exist."""
        O = np.atleast_2d(O).astype(float)
        F = np.asarray(F, float)
        d = F - (F @ self.ahat) * self.ahat          # ray dir minus axial part
        oc = O - self.C
        oc_perp = oc - np.outer(oc @ self.ahat, self.ahat)
        a = float(d @ d)
        near = np.full(O.shape[0], np.inf)
        far = np.full(O.shape[0], -np.inf)
        if a < 1e-12:                                 # ray parallel to axis
            return near, far
        b = 2.0 * (oc_perp @ d)
        c = np.sum(oc_perp * oc_perp, axis=1) - self.r ** 2
        disc = b * b - 4 * a * c
        ok = disc >= 0
        sq = np.sqrt(np.where(ok, disc, 0.0))
        for lam in ((-b - sq) / (2 * a), (-b + sq) / (2 * a)):
            if clamp:
                P_ = O + lam[:, None] * F
                rel = P_ - self.C
                h = rel @ self.ahat
                lx = rel @ self.uhat
                lz = rel @ self.vhat
                valid = (ok & (h >= -1e-6) & (h <= self.ah + 1e-6)
                         & _angle_in_sector(lx, lz, self.sector))
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
    """Planar disc / annulus in the primitive's local XZ plane (normal = axis A)."""

    def __init__(self, R, t, sector, inner, outer):
        self.C = np.asarray(t, float)
        self.U, self.V, self.A, self.r, _ = _local_basis(R, t)
        self.n = self.A / (np.linalg.norm(self.A) or 1.0)
        self.inner = inner * self.r
        self.outer = outer * self.r
        self.sector = sector
        self.uhat = self.U / (self.r or 1.0)
        self.vhat = self.V / (self.r or 1.0)

    def depth(self, O, F):
        O = np.atleast_2d(O).astype(float)
        F = np.asarray(F, float)
        denom = float(F @ self.n)
        out = np.full(O.shape[0], np.inf)
        if abs(denom) < 1e-12:                        # ray parallel to plane
            return out
        lam = ((self.C - O) @ self.n) / denom
        Phit = O + lam[:, None] * F
        rel = Phit - self.C
        lx = rel @ self.uhat
        lz = rel @ self.vhat
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
        canonical direction, rounded. A rim arc is suppressed iff a FULL-
        sector wall with EQUAL slope lies on the OPPOSITE side (stacked
        cone/cylinder sections, e.g. 4589's con3-on-con4 joint) — only then
        is the whole rim a smooth joint. Same-side sharing, unequal slopes
        (creases), or partial-sector sharers (3941's base lip: 45-degree
        sectors with cutout gaps, where the body's rim stays a real edge)
        keep the arc."""
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

    def _skip_flags(self, skip_rims):
        skip_rims = skip_rims or set()
        rims = self.wall_rims() if skip_rims else []
        skip_base = bool(rims) and (rims[0][0], rims[0][1]) in skip_rims
        skip_top = len(rims) > 1 and (rims[1][0], rims[1][1]) in skip_rims
        return skip_base, skip_top

    def drawn_with_depth(self, proj, skip_rims=None):
        """Return [(op, depth_fn)] pre-occlusion drawn-op candidates.

        depth_fn maps an op's sample params to camera depth: degrees for arc
        ops, t in [0,1] for line ops. `skip_rims` is a set of (rim_key, side)
        pairs (see wall_rims) whose base/top arcs must not be emitted: rims
        where a full-sector wall continues smoothly on the other side of the
        circle plane (stacked section joints)."""
        raise NotImplementedError


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

    def drawn_with_depth(self, proj, skip_rims=None):
        ell = proj.circle(self.R, self.t, 1.0)
        return [(_arc_op(ell, 0.0, self.sector, "edge"), _arc_depth_fn(ell))]


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

    def drawn_with_depth(self, proj, skip_rims=None):
        outer = proj.circle(self.R, self.t, self.inner + 1)
        inner = proj.circle(self.R, self.t, self.inner)
        return [(_arc_op(outer, 0.0, self.sector, "edge"), _arc_depth_fn(outer)),
                (_arc_op(inner, 0.0, self.sector, "edge"), _arc_depth_fn(inner))]


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

    def fit_pts(self, n=16):
        ang = np.linspace(0.0, math.radians(self.sector), n)
        return np.vstack([self.ring_pts(ang, 0.0),      # base + top rings
                          self.ring_pts(ang, 1.0)])

    def drawn_with_depth(self, proj, skip_rims=None):
        skip_base, skip_top = self._skip_flags(skip_rims)
        U, A, V = self.R[:, 0], self.R[:, 1], self.R[:, 2]
        fwd = np.asarray(proj.fwd, float)
        # silhouette generators: radial normal perpendicular to view ->
        # cos t (U.fwd) + sin t (V.fwd) = 0  ->  t = atan2(-(U.fwd), (V.fwd)).
        uf, vf = float(U @ fwd), float(V @ fwd)
        theta = math.atan2(-uf, vf)
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
        if not skip_base:
            pairs.append((_arc_op(base, 0.0, self.sector, "edge"),
                          _arc_depth_fn(base)))
        if not skip_top:
            pairs.append((_arc_op(top, 0.0, self.sector, "edge"),
                          _arc_depth_fn(top)))
        return pairs


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

    def fit_pts(self, n=16):
        ang = np.linspace(0.0, math.radians(self.sector), n)
        return np.vstack([self.ring_pts(ang, 0.0),      # base + top rings
                          self.ring_pts(ang, 1.0)])

    def drawn_with_depth(self, proj, skip_rims=None):
        skip_base, skip_top = self._skip_flags(skip_rims)
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
        if not skip_base:
            pairs.append((_arc_op(base, 0.0, self.sector, "edge"),
                          _arc_depth_fn(base)))
        if topc is not None and not skip_top:
            pairs.append((_arc_op(topc, 0.0, self.sector, "edge"),
                          _arc_depth_fn(topc)))
        return pairs


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
    coincident rims from different records compare equal."""
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


def wall_rims(rec):
    """[(key, side, slope)] for a WALL record's rim circles (cyli/con).

    `side` is which side of the circle plane the wall lies on (+-1 along the
    key's canonical axis); `slope` is d(radius)/d(height) in that canonical
    direction, rounded. A record's rim arc is suppressed iff a FULL-sector
    wall with EQUAL slope lies on the OPPOSITE side (stacked cone/cylinder
    sections, e.g. 4589's con3-on-con4 joint) — only then is the whole rim a
    smooth joint. Same-side sharing, unequal slopes (creases), or partial-
    sector sharers (3941's base lip: 45-degree sectors with cutout gaps, where
    the body's rim stays a real edge) keep the arc."""
    R = np.asarray(rec["R"], float)
    t = np.asarray(rec["t"], float)
    A = R[:, 1]
    ahat = A / (np.linalg.norm(A) or 1.0)
    ru = float(np.linalg.norm(R[:, 0]))
    ah = float(np.linalg.norm(A)) or 1.0
    if rec["kind"] == "cyli":
        rate = 0.0
        rims = [(t, ru, +1), (t + A, ru, -1)]           # (center, radius, side along +A)
    elif rec["kind"] == "con":
        N = rec["inner"]
        rate = -ru / ah                                 # radius shrinks toward +A
        rims = [(t, (N + 1) * ru, +1)]
        if N > 0:
            rims.append((t + A, N * ru, -1))
    else:
        return []
    out = []
    for C, radius, side in rims:
        key = rim_key(C, A, radius)
        aligned = float(np.dot(ahat, key[1])) > 0       # canonical axis sign
        out.append((key,
                    side if aligned else -side,
                    round(rate if aligned else -rate, 3)))
    return out


def drawn_with_depth(rec, to_AB, s, cx, cy, half, fwd, skip_rims=None):
    """Return [(op, depth_fn)] for one analytic record.

    depth_fn maps an op's sample params to camera depth: degrees for arc ops,
    t in [0,1] for line ops. Ops are pre-occlusion candidates. `skip_rims` is
    a set of (rim_key, side) pairs (see wall_rims) whose base/top arcs must
    not be emitted: rims where a full-sector wall continues smoothly on the
    other side of the circle plane (stacked section joints)."""
    kind, sector = rec["kind"], rec["sector"]
    R, t = rec["R"], rec["t"]
    skip_rims = skip_rims or set()
    rims = wall_rims(rec) if skip_rims else []
    skip_base = bool(rims) and (rims[0][0], rims[0][1]) in skip_rims
    skip_top = len(rims) > 1 and (rims[1][0], rims[1][1]) in skip_rims
    pairs = []
    if kind in ("edge", "disc", "ring"):
        outer = (rec["inner"] + 1) if kind == "ring" else 1.0
        ell = project_circle(R, t, outer, to_AB, s, cx, cy, half)
        pairs.append((_arc_op(ell, 0.0, sector, "edge"), _arc_depth_fn(ell)))
        if kind == "ring" and rec["inner"] > 0:
            elli = project_circle(R, t, rec["inner"], to_AB, s, cx, cy, half)
            pairs.append((_arc_op(elli, 0.0, sector, "edge"), _arc_depth_fn(elli)))
    elif kind == "cyli":
        R = np.asarray(R, float)
        U, V, A = R[:, 0], R[:, 2], R[:, 1]
        fwd = np.asarray(fwd, float)
        # silhouette generators: radial normal perpendicular to view ->
        # cos t (U.fwd) + sin t (V.fwd) = 0  ->  t = atan2(-(U.fwd), (V.fwd)).
        uf, vf = float(U @ fwd), float(V @ fwd)
        theta = math.atan2(-uf, vf)
        base = project_circle(R, t, 1.0, to_AB, s, cx, cy, half)
        top = project_circle(R, np.asarray(t, float) + A, 1.0, to_AB, s, cx, cy, half)
        for th in (theta, theta + math.pi):
            deg = math.degrees(th) % 360.0
            if sector >= 360.0 - 1e-9 or deg <= sector + 1e-6:
                pb, pt = base.point(th), top.point(th)
                op = ("line", float(pb[0]), float(pb[1]), float(pt[0]), float(pt[1]), "sil")
                pairs.append((op, _line_depth_fn(base.depth(th), top.depth(th))))
        if not skip_base:
            pairs.append((_arc_op(base, 0.0, sector, "edge"), _arc_depth_fn(base)))
        if not skip_top:
            pairs.append((_arc_op(top, 0.0, sector, "edge"), _arc_depth_fn(top)))
    elif kind == "con":
        R = np.asarray(R, float)
        N = float(rec["inner"])
        A3 = R[:, 1]
        fwd = np.asarray(fwd, float)
        base = project_circle(R, t, N + 1.0, to_AB, s, cx, cy, half)
        topc = (project_circle(R, np.asarray(t, float) + A3, N, to_AB, s, cx, cy, half)
                if N > 0 else None)
        if topc is None:                        # apex: project the point itself
            aa, bb, zz = to_AB((np.asarray(t, float) + A3)[None, :])
            apex_xy = ((aa[0] - cx) * s + half, (bb[0] - cy) * s + half)
            apex_z = float(zz[0])
        # silhouette generators: local cone normal is constant along a
        # generator, m(th) = (cos th, 1, sin th); world n.fwd = 0 reduces via
        # g = R^-1 @ fwd to g0 cos th + g2 sin th = -g1 (0, 1, or 2 solutions).
        g = np.linalg.inv(R) @ fwd
        A_, B_, C_ = float(g[0]), float(g[2]), float(-g[1])
        hyp = math.hypot(A_, B_)
        if hyp > 1e-12 and abs(C_) <= hyp:
            phi0 = math.atan2(B_, A_)
            dth = math.acos(max(-1.0, min(1.0, C_ / hyp)))
            for th in (phi0 + dth, phi0 - dth):
                deg = math.degrees(th) % 360.0
                if sector >= 360.0 - 1e-9 or deg <= sector + 1e-6:
                    pb = base.point(th)
                    if topc is not None:
                        pt_, zt = topc.point(th), topc.depth(th)
                    else:
                        pt_, zt = apex_xy, apex_z
                    op = ("line", float(pb[0]), float(pb[1]),
                          float(pt_[0]), float(pt_[1]), "sil")
                    pairs.append((op, _line_depth_fn(base.depth(th), zt)))
        if not skip_base:
            pairs.append((_arc_op(base, 0.0, sector, "edge"), _arc_depth_fn(base)))
        if topc is not None and not skip_top:
            pairs.append((_arc_op(topc, 0.0, sector, "edge"), _arc_depth_fn(topc)))
    return pairs


def drawn_curves(rec, to_AB, s, cx, cy, half, fwd):
    """Pre-occlusion drawn ops (tuples only) for one analytic record."""
    return [op for op, _ in drawn_with_depth(rec, to_AB, s, cx, cy, half, fwd)]


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
    """
    result = []
    for spec in op_specs:
        op, depth_fn = spec[0], spec[1]
        exclude = spec[2] if len(spec) > 2 else None
        xs, ys, params = _samples_for(op, n)
        O = ray_origin(xs, ys)
        field = np.full(xs.shape, np.inf)
        for occ in occluders:
            if occ is exclude:
                continue
            field = np.minimum(field, occ.depth(O, fwd))
        sd = np.asarray(depth_fn(params), float)
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
