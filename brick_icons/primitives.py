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

import numpy as np

_FRAC = re.compile(r"^(\d+)-(\d+)(edge|cyli|cylo|disc|ring)(\d*)$")


def parse_primitive(name: str):
    """basename -> (kind, sector_deg, inner_radius) or None.

    None means "not a substitutable curved primitive" -> the caller should fall
    back to faceted polygon recursion. kind in {'edge','cyli','disc','ring'};
    'cylo' is aliased to 'cyli'.
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

    def depth(self, O, F):
        O = np.atleast_2d(O).astype(float)
        F = np.asarray(F, float)
        d = F - (F @ self.ahat) * self.ahat          # ray dir minus axial part
        oc = O - self.C
        oc_perp = oc - np.outer(oc @ self.ahat, self.ahat)
        a = float(d @ d)
        out = np.full(O.shape[0], np.inf)
        if a < 1e-12:                                 # ray parallel to axis
            return out
        b = 2.0 * (oc_perp @ d)
        c = np.sum(oc_perp * oc_perp, axis=1) - self.r ** 2
        disc = b * b - 4 * a * c
        ok = disc >= 0
        sq = np.sqrt(np.where(ok, disc, 0.0))
        for lam in ((-b - sq) / (2 * a), (-b + sq) / (2 * a)):
            P_ = O + lam[:, None] * F
            rel = P_ - self.C
            h = rel @ self.ahat
            lx = rel @ self.uhat
            lz = rel @ self.vhat
            valid = (ok & (lam > -1e-9) & (h >= -1e-6) & (h <= self.ah + 1e-6)
                     & _angle_in_sector(lx, lz, self.sector))
            out = np.minimum(out, np.where(valid, lam, np.inf))
        return out


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
        valid = ((lam > -1e-9) & (rad >= self.inner - 1e-6) & (rad <= self.outer + 1e-6)
                 & _angle_in_sector(lx, lz, self.sector))
        return np.where(valid, lam, out)


def _arc_op(ell, t0_deg, t1_deg, kind):
    rx, ry, phi = ell.svg_axes()
    return ("arc", float(ell.center[0]), float(ell.center[1]),
            rx, ry, phi, float(t0_deg), float(t1_deg), kind)


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


def drawn_with_depth(rec, to_AB, s, cx, cy, half, fwd):
    """Return [(op, depth_fn)] for one analytic record.

    depth_fn maps an op's sample params to camera depth: degrees for arc ops,
    t in [0,1] for line ops. Ops are pre-occlusion candidates.
    """
    kind, sector = rec["kind"], rec["sector"]
    R, t = rec["R"], rec["t"]
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
        pairs.append((_arc_op(base, 0.0, sector, "edge"), _arc_depth_fn(base)))
        pairs.append((_arc_op(top, 0.0, sector, "edge"), _arc_depth_fn(top)))
    return pairs


def drawn_curves(rec, to_AB, s, cx, cy, half, fwd):
    """Pre-occlusion drawn ops (tuples only) for one analytic record."""
    return [op for op, _ in drawn_with_depth(rec, to_AB, s, cx, cy, half, fwd)]


def _ellipse_from_arc(cx, cy, rx, ry, phi_deg):
    a = math.radians(phi_deg)
    maj = np.array([math.cos(a), math.sin(a)]) * rx
    minr = np.array([-math.sin(a), math.cos(a)]) * ry
    return Ellipse(np.array([cx, cy]), maj, minr)


def _samples_for(op, n):
    """Return (xs, ys, params) sampling an op; params are t in [0,1] for lines
    and degrees for arcs (aligned with the op's depth_fn)."""
    n = max(2, n)
    if op[0] == "line":
        _, x1, y1, x2, y2, _ = op
        ts = np.linspace(0.0, 1.0, n)
        return x1 + (x2 - x1) * ts, y1 + (y2 - y1) * ts, ts
    _, cx, cy, rx, ry, phi, t0, t1, _ = op
    degs = np.linspace(t0, t1, n)
    pts = _ellipse_from_arc(cx, cy, rx, ry, phi).points(np.radians(degs))
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
    for op, depth_fn in op_specs:
        xs, ys, params = _samples_for(op, n)
        O = ray_origin(xs, ys)
        field = np.full(xs.shape, np.inf)
        for occ in occluders:
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
                _, cx, cy, rx, ry, phi, _, _, kind = op
                result.append(("arc", cx, cy, rx, ry, phi,
                               float(params[i]), float(params[j]), kind))
    return result
