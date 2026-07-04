"""Mesh-repair: give every triangle correct outward-facing winding.

Two tiers (see docs/superpowers/specs/2026-07-04-mesh-repair-design.md):
- certified tris: orient directly from the BFC `invert` flag flatten computed;
- uncertified tris: ray-cast outside test (count mesh crossings along the
  candidate normal; odd crossings => normal points inward => flip).

Repair is view-independent and cached to .cache/mesh/ keyed by a content hash
of the raw flatten output.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np


def ray_crossings(origin, direction, tris, eps=1e-7) -> int:
    """Number of triangles in `tris` (shape (M,3,3)) that the ray
    origin + lambda*direction crosses at lambda > eps. Möller-style plane +
    barycentric test; degenerate/parallel hits are skipped."""
    O = np.asarray(origin, float)
    D = np.asarray(direction, float)
    # Deterministic per-ray jitter breaks exact ray/edge or ray/vertex
    # coincidences. LDraw geometry is heavily axis- and 45°-aligned, so a
    # single FIXED jitter direction could stay systematically aligned with
    # shared edges; seeding the perturbation from the ray varies its direction
    # while staying reproducible (a pure function of the inputs).
    digest = hashlib.sha1(
        np.concatenate([O, D]).astype(np.float64).tobytes()).digest()
    h = np.frombuffer(digest[:12], dtype=np.uint32).astype(float)
    j = (h / float(np.iinfo(np.uint32).max)) * 2.0 - 1.0   # 3 signed in [-1, 1]
    j = j / (np.linalg.norm(j) or 1.0)
    D = D + j * 1e-4 * max(float(np.linalg.norm(D)), 1.0)
    count = 0
    for tri in tris:
        v0, v1, v2 = tri
        e0, e1 = v1 - v0, v2 - v0
        n = np.cross(e0, e1)
        denom = float(D @ n)
        if abs(denom) < 1e-12:
            continue                          # parallel to the triangle plane
        lam = float((v0 - O) @ n) / denom
        if lam <= eps:
            continue                          # behind or at the origin
        P = O + lam * D
        e2 = P - v0
        d00 = float(e0 @ e0); d01 = float(e0 @ e1); d11 = float(e1 @ e1)
        d20 = float(e2 @ e0); d21 = float(e2 @ e1)
        denb = d00 * d11 - d01 * d01
        if abs(denb) < 1e-18:
            continue
        b = (d11 * d20 - d01 * d21) / denb
        w = (d00 * d21 - d01 * d20) / denb
        u = 1.0 - b - w
        if u >= -1e-9 and b >= -1e-9 and w >= -1e-9:
            count += 1
    return count
