"""Map a decal into its carrier's parameter space and back onto the exact
surface.

Every carrier goes through here — planar, cylinder and cone — because the
planar map being the identity is a degenerate case of the general one, not a
reason to skip it. One path means the flat case cannot drift; and unwrapping
first dissolves authored faceting (3941p01's panel is 36 quads approximating a
16-gon, which in (theta, h) is one rounded rectangle), so re-projection onto
the analytic carrier yields exact arcs instead of inheriting the author's
segment count.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

BIND_TOL = 0.5          # LDU; see the plan's measured table


def _axis_frame(prim):
    """(origin, axis unit vector, radius) for a cylinder/cone-like primitive."""
    A = prim.R[:, 1]
    h = float(np.linalg.norm(A))
    return prim.t, A / h if h else A, float(np.linalg.norm(prim.R[:, 0]))


def _circle_frame(prim):
    """(origin, axis, radius, e1, e2) with theta running the way LDraw's own
    cylinder primitives do — vertex k at (cos, y, sin) in the prim's columns.
    Cross-product e2 keeps the basis orthogonal even when R is slightly off;
    the sign check keeps it pointing where an inverted matrix says it should."""
    o, a, r = _axis_frame(prim)
    e1 = prim.R[:, 0] / np.linalg.norm(prim.R[:, 0])
    e2 = np.cross(e1, a)
    if float(e2 @ prim.R[:, 2]) < 0:
        e2 = -e2
    return o, a, r, e1, e2


def _radial_gap(pts, prim) -> float:
    o, a, r = _axis_frame(prim)
    d = np.asarray(pts, float) - o
    perp = d - np.outer(d @ a, a)
    return float(np.max(np.abs(np.linalg.norm(perp, axis=1) - r)))


def _gap(pts, carrier) -> float:
    """Distance from `pts` to the carrier surface, by carrier kind. A planar
    carrier measures offset FROM the face; a radial metric would report
    position ALONG it, which is why 6141p01 and 3001p01 read 6.5 and 2.0 LDU
    under the axis measure — artifacts, not standoffs."""
    if isinstance(carrier, Plane):
        n = carrier.normal / np.linalg.norm(carrier.normal)
        return float(np.max(np.abs(np.asarray(pts, float) @ n - carrier.offset)))
    return _radial_gap(pts, carrier)


def bind(pts, carriers, tol: float = BIND_TOL):
    """The carrier `pts` lies on, or None. None means 'leave as authored'."""
    best, best_gap = None, tol
    for c in carriers:
        try:
            gap = _gap(pts, c)
        except (AttributeError, ValueError, IndexError):
            continue
        if gap <= best_gap:
            best, best_gap = c, gap
    return best


@dataclass
class Plane:
    """A flat carrier. Its unwrap is the identity in the face's own basis."""
    normal: np.ndarray
    offset: float
    _basis: tuple = field(default=None, repr=False)

    def basis(self):
        if self._basis is None:
            n = self.normal / np.linalg.norm(self.normal)
            seed = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 \
                else np.array([1.0, 0.0, 0.0])
            u = np.cross(n, seed)
            u /= np.linalg.norm(u)
            self._basis = (n, u, np.cross(n, u))
        return self._basis


def to_uv(pts, carrier):
    """Carrier parameter space, in LDU on both axes so one uniform scale
    keeps the texture isometric."""
    pts = np.asarray(pts, float)
    if isinstance(carrier, Plane):
        n, u, v = carrier.basis()
        return np.column_stack([pts @ u, pts @ v])
    o, a, r, e1, e2 = _circle_frame(carrier)
    d = pts - o
    height = d @ a
    perp = d - np.outer(height, a)
    return np.column_stack([r * np.arctan2(perp @ e2, perp @ e1), height])


def to_xyz(uv, carrier):
    """Back onto the EXACT surface — this is where the sagitta closes."""
    uv = np.asarray(uv, float)
    if isinstance(carrier, Plane):
        n, u, v = carrier.basis()
        return (np.outer(uv[:, 0], u) + np.outer(uv[:, 1], v)
                + carrier.offset * n)
    o, a, r, e1, e2 = _circle_frame(carrier)
    th = uv[:, 0] / r
    return (o + np.outer(r * np.cos(th), e1) + np.outer(r * np.sin(th), e2)
            + np.outer(uv[:, 1], a))
