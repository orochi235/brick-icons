"""Which surfaces a canvas pixel's line of sight crosses, nearest first.

An oracle that does not trust the occt engine's faces: it casts against the
part's own triangles (`edge_truth.load`, every primitive tessellated), so it
can say what a pixel should show without going through the paint order under
test.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

EPS = 1e-9


@dataclass
class Hit:
    depth: float          # along fwd; smaller is nearer the camera
    tri: int              # index into out["tri"]
    normal: np.ndarray    # unit, turned toward the camera: winding is not trusted


def pixel_ray(fit: dict, x: float, y: float, zoom: float = 1.0):
    """The world line through canvas pixel (x, y) of a render drawn at `zoom`
    times the fit's size: a point on it at depth 0, and the view direction.
    Inverts `edge_truth._to_px`; pass pixel centers (i + 0.5)."""
    right, up, fwd = (np.asarray(fit[k], float) for k in ("right", "up", "fwd"))
    k = fit["k"] * zoom
    a = (x - fit["kx"] * zoom) / k
    b = -(y - fit["ky"] * zoom) / k
    return a * right + b * up, fwd


def hits(tris, origin, direction) -> list[Hit]:
    """Every triangle the line origin + t*direction crosses, for any t,
    sorted nearest first (Moller-Trumbore, both windings)."""
    T = np.asarray(tris, float).reshape(-1, 3, 3)
    if not len(T):
        return []
    o, d = np.asarray(origin, float), np.asarray(direction, float)
    v0, e1, e2 = T[:, 0], T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > EPS
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = o - v0
    u = np.einsum("ij,ij->i", s, p) * inv
    q = np.cross(s, e1)
    v = (q @ d) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    ok &= (u >= 0) & (v >= 0) & (u + v <= 1)
    out = []
    for i in np.flatnonzero(ok):
        n = np.cross(e1[i], e2[i])
        n /= np.linalg.norm(n) or 1.0
        out.append(Hit(float(t[i] + o @ d), int(i), -n if n @ d > 0 else n))
    return sorted(out, key=lambda h: h.depth)
