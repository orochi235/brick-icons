from __future__ import annotations

import math
import numpy as np

from . import hlr


def _project_px(P, right, up, fwd, s, cx, cy, half):
    a, b, z = hlr.project(P, right, up, fwd)
    return (a - cx) * s + half, (b - cy) * s + half, z


def _radius_pts(rec, thetas, level):
    """World points on the rec's circle at `thetas` (radians), `level` along axis
    (0 = base ring, 1 = top ring). Honors ring inner/outer radius."""
    R = np.asarray(rec["R"], float); C = np.asarray(rec["t"], float)
    r = (rec["inner"] + 1) if rec["kind"] == "ring" else 1.0
    U, A, V = R[:, 0], R[:, 1], R[:, 2]
    base = C + level * A
    return base + r * (np.cos(thetas)[:, None] * U + np.sin(thetas)[:, None] * V)


def faces_from_analytic(analytic, right, up, fwd, s, cx, cy, half, bands=6):
    faces = []
    for rec in analytic:
        kind = rec["kind"]
        if kind == "edge":
            continue
        R = np.asarray(rec["R"], float)
        sect = math.radians(rec["sector"])
        if kind in ("disc", "ring"):
            th = np.linspace(0.0, sect, 48)
            w = _radius_pts(rec, th, 0.0)
            px, py, z = _project_px(w, right, up, fwd, s, cx, cy, half)
            n = R[:, 1]; n = n / np.linalg.norm(n)
            nv = np.array([n @ right, n @ up, n @ fwd])
            if nv[2] > 0:
                nv = -nv
            faces.append({"poly": np.stack([px, py], 1), "normal": nv,
                          "depth": float(np.mean(z)), "kind": kind})
        elif kind == "cyli":
            edges = np.linspace(0.0, sect, bands + 1)
            for i in range(bands):
                a0, a1 = edges[i], edges[i + 1]
                th = np.array([a0, a1])
                base = _radius_pts(rec, th, 0.0)     # (2,3)
                top = _radius_pts(rec, th, 1.0)      # (2,3)
                quad = np.array([base[0], base[1], top[1], top[0]])
                am = 0.5 * (a0 + a1)
                U, V = R[:, 0], R[:, 2]
                n = math.cos(am) * U + math.sin(am) * V
                n = n / np.linalg.norm(n)
                nv = np.array([n @ right, n @ up, n @ fwd])
                if nv[2] > 0:
                    continue                         # band faces away: cull
                px, py, z = _project_px(quad, right, up, fwd, s, cx, cy, half)
                faces.append({"poly": np.stack([px, py], 1), "normal": nv,
                              "depth": float(np.mean(z)), "kind": kind})
    return faces


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
