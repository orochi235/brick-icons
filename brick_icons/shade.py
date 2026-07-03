from __future__ import annotations

import math
import numpy as np

from . import hlr


def _project_px(P, right, up, fwd, s, cx, cy, half):
    a, b, z = hlr.project(P, right, up, fwd)
    return (a - cx) * s + half, (b - cy) * s + half, z


def faces_from_tris(tri, right, up, fwd, s, cx, cy, half):
    """Front-facing triangle faces as px-space polygons with view-space normals."""
    faces = []
    for v in tri:                       # v: (3,3) world coords
        n = np.cross(v[1] - v[0], v[2] - v[0])
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            continue
        n = n / ln
        nv = np.array([n @ right, n @ up, n @ fwd])
        # front-facing when normal points back toward camera: nv[2] < 0. Orient + cull.
        if nv[2] > 0:
            n, nv = -n, -nv
        if nv[2] > -1e-6:
            continue                    # edge-on: skip
        px, py, z = _project_px(v, right, up, fwd, s, cx, cy, half)
        poly = np.stack([px, py], axis=1)
        faces.append({"poly": poly, "normal": nv, "depth": float(np.mean(z)),
                      "kind": "tri"})
    return faces
