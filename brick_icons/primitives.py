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
