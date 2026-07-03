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


def _hex(rgb):
    r, g, b = (max(0, min(255, round(c))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


class ShadingStyle:
    def tone(self, nv) -> str:
        raise NotImplementedError


class Flat3Style(ShadingStyle):
    """Three tones by dominant face orientation: top / left / right."""
    def __init__(self, part_color=(157, 157, 157)):
        self.top = _hex([c * 1.30 for c in part_color])
        self.left = _hex([c * 0.85 for c in part_color])
        self.right = _hex([c * 0.60 for c in part_color])

    def tone(self, nv):
        if nv[1] > 0.5:
            return self.top
        return self.left if nv[0] < 0 else self.right


def _poly_d(poly):
    cmds = [f"M {poly[0,0]:.2f} {poly[0,1]:.2f}"]
    for p in poly[1:]:
        cmds.append(f"L {p[0]:.2f} {p[1]:.2f}")
    cmds.append("Z")
    return " ".join(cmds)


def fill_ops(faces, style):
    """Painter-sorted (far->near) fill ops: {'d': path, 'fill': color, 'depth': z}."""
    ops = []
    for f in sorted(faces, key=lambda f: -f["depth"]):
        ops.append({"d": _poly_d(f["poly"]), "fill": style.tone(f["normal"]),
                    "depth": f["depth"]})
    return ops


def apply_affine_faces(faces, f, ox, oy):
    """Remap face polygons through the same fit affine used for segments."""
    out = []
    for face in faces:
        p = face["poly"]
        q = np.stack([p[:, 0] * f + ox, p[:, 1] * f + oy], axis=1)
        out.append({**face, "poly": q})
    return out


STYLES = {"flat3": Flat3Style}


def make_style(name, part_color=(157, 157, 157)):
    return STYLES[name](part_color=part_color)


def parse_hex_color(spec, default=(157, 157, 157)):
    """'0xRRGGBB' or '#RRGGBB' or 'RRGGBB' -> (r, g, b); default on failure."""
    if not spec:
        return default
    s = str(spec).lstrip("#").lower()
    if s.startswith("0x"):
        s = s[2:]
    try:
        v = int(s, 16)
        return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
    except ValueError:
        return default


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
