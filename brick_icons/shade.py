from __future__ import annotations

import math
import numpy as np

from . import hlr


def _project_px(P, right, up, fwd, s, cx, cy, half):
    a, b, z = hlr.project(P, right, up, fwd)
    return (a - cx) * s + half, (b - cy) * s + half, z


def _radius_pts(rec, thetas, level, radius=None):
    """World points on the rec's circle at `thetas` (radians), `level` along axis
    (0 = base ring, 1 = top ring). `radius` overrides the unit radius (in
    primitive units); default is the ring's outer radius (inner+1) or 1.0."""
    R = np.asarray(rec["R"], float); C = np.asarray(rec["t"], float)
    if radius is None:
        radius = (rec["inner"] + 1) if rec["kind"] == "ring" else 1.0
    U, A, V = R[:, 0], R[:, 1], R[:, 2]
    base = C + level * A
    return base + radius * (np.cos(thetas)[:, None] * U + np.sin(thetas)[:, None] * V)


def faces_from_analytic(analytic, right, up, fwd, s, cx, cy, half):
    faces = []
    for rec in analytic:
        kind = rec["kind"]
        if kind == "edge":
            continue
        R = np.asarray(rec["R"], float)
        sect = math.radians(rec["sector"])
        if kind in ("disc", "ring"):
            th = np.linspace(0.0, sect, 64)
            if kind == "ring":
                # Annular band: outer arc forward, inner arc back, so the center
                # hole (the bore) is cut out instead of filled by a solid disc.
                outer = _radius_pts(rec, th, 0.0, radius=rec["inner"] + 1)
                inner = _radius_pts(rec, th, 0.0, radius=rec["inner"])
                w = np.concatenate([outer, inner[::-1]], axis=0)
            else:
                w = _radius_pts(rec, th, 0.0)
            px, py, z = _project_px(w, right, up, fwd, s, cx, cy, half)
            n = R[:, 1]; n = n / np.linalg.norm(n)
            nv = np.array([n @ right, n @ up, n @ fwd])
            if nv[2] > 0:
                nv = -nv
            faces.append({"poly": np.stack([px, py], 1), "normal": nv,
                          "depth": float(np.mean(z)), "zs": z, "kind": kind})
        elif kind == "cyli":
            face = _cyl_wall_face(rec, R, sect, right, up, fwd, s, cx, cy, half)
            if face is not None:
                faces.append(face)
    return faces


def _cyl_wall_face(rec, R, sect, right, up, fwd, s, cx, cy, half):
    """The camera-facing cylinder wall as ONE smooth arc-region polygon plus a
    linear-gradient spec (stops sample the Lambert shading around the visible
    span). Returns None if no wall faces the camera within the sector."""
    U, A, V = R[:, 0], R[:, 1], R[:, 2]
    a = float(U @ fwd); b = float(V @ fwd)
    if a == 0.0 and b == 0.0:
        return None                              # axis points at camera: no wall
    phi = math.atan2(b, a)
    theta_face = phi + math.pi                   # most camera-facing angle
    lo, hi = theta_face - math.pi / 2, theta_face + math.pi / 2
    if sect < 2 * math.pi - 1e-6:                # partial sector: clamp naively
        lo = max(lo, 0.0); hi = min(hi, sect)
        if hi - lo < 1e-3:
            return None
    ths = np.linspace(lo, hi, 40)
    top = _radius_pts(rec, ths, 1.0)
    bot = _radius_pts(rec, ths, 0.0)
    tpx, tpy, tz = _project_px(top, right, up, fwd, s, cx, cy, half)
    bpx, bpy, bz = _project_px(bot, right, up, fwd, s, cx, cy, half)
    poly = np.concatenate([np.stack([tpx, tpy], 1),
                           np.stack([bpx, bpy], 1)[::-1]], axis=0)
    zs = np.concatenate([tz, bz])
    # gradient axis: mid-height points at the two silhouette angles
    mid = _radius_pts(rec, np.array([lo, hi]), 0.5)
    mpx, mpy, _ = _project_px(mid, right, up, fwd, s, cx, cy, half)
    p0 = (float(mpx[0]), float(mpy[0])); p1 = (float(mpx[1]), float(mpy[1]))
    axis = np.array([p1[0] - p0[0], p1[1] - p0[1]]); L2 = float(axis @ axis) or 1.0
    samples = []
    for th in np.linspace(lo, hi, 9):
        n = math.cos(th) * U + math.sin(th) * V; n = n / np.linalg.norm(n)
        nv = np.array([n @ right, n @ up, n @ fwd])
        p = _radius_pts(rec, np.array([th]), 0.5)
        ppx, ppy, _ = _project_px(p, right, up, fwd, s, cx, cy, half)
        off = ((ppx[0] - p0[0]) * axis[0] + (ppy[0] - p0[1]) * axis[1]) / L2
        samples.append((float(np.clip(off, 0.0, 1.0)), nv))
    return {"poly": poly, "zs": zs, "depth": float(np.mean(zs)), "kind": "cyli",
            "grad_axis": (p0, p1), "grad_samples": samples}


def _hex(rgb):
    r, g, b = (max(0, min(255, round(c))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


class ShadingStyle:
    def tone(self, nv) -> str:
        raise NotImplementedError


class Flat3Style(ShadingStyle):
    """Flat faces: three tones by dominant orientation (top / left / right).
    Curved faces (cylinder walls) shade with a smooth Lambert ramp via `ramp`."""
    def __init__(self, part_color=(157, 157, 157)):
        self.part_color = tuple(part_color)
        self.top = _hex([c * 1.30 for c in part_color])
        self.left = _hex([c * 0.85 for c in part_color])
        self.right = _hex([c * 0.60 for c in part_color])
        # view-space light: upper-left, toward the viewer (matches left>right)
        L = np.array([-0.5, 0.6, -0.62]); self.light = L / np.linalg.norm(L)

    def tone(self, nv):
        if nv[1] > 0.5:
            return self.top
        return self.left if nv[0] < 0 else self.right

    def ramp(self, nv):
        """Continuous grey for a curved-surface normal (gradient stops)."""
        b = max(0.0, float(np.dot(np.asarray(nv, float), self.light)))
        factor = 0.55 + 0.85 * b
        return _hex([c * factor for c in self.part_color])


def _poly_d(poly):
    cmds = [f"M {poly[0,0]:.2f} {poly[0,1]:.2f}"]
    for p in poly[1:]:
        cmds.append(f"L {p[0]:.2f} {p[1]:.2f}")
    cmds.append("Z")
    return " ".join(cmds)


def fill_ops(faces, style):
    """Painter-sorted (far->near) fill ops. Flat faces: {'d','fill','depth'}.
    Gradient faces (cylinder walls): {'d','gradient','depth'} where gradient is
    {'x1','y1','x2','y2','stops':[(offset,color),...]}."""
    # Single far->near painter sort across ALL faces regardless of kind.
    # Occlusion is by depth: a stud protrudes toward the camera, so it is nearer
    # than the surface it sits on and paints on top; an interior tube/cone wall
    # sits behind its outer wall, so it is farther and paints under it. Splitting
    # flats-vs-curved cannot tell those two curved cases apart (both are curved),
    # and painting all curved last makes interior geometry show through walls.
    ops = []
    for f in sorted(faces, key=lambda f: -f["depth"]):
        if "grad_axis" in f:
            p0, p1 = f["grad_axis"]
            stops = sorted(((off, style.ramp(nv)) for off, nv in f["grad_samples"]),
                           key=lambda s: s[0])
            ops.append({"d": _poly_d(f["poly"]), "depth": f["depth"],
                        "gradient": {"x1": p0[0], "y1": p0[1], "x2": p1[0], "y2": p1[1],
                                     "stops": stops}})
        else:
            ops.append({"d": _poly_d(f["poly"]), "fill": style.tone(f["normal"]),
                        "depth": f["depth"]})
    return ops


def apply_affine_faces(faces, f, ox, oy):
    """Remap face polygons (and any gradient axis) through the fit affine."""
    out = []
    for face in faces:
        p = face["poly"]
        q = np.stack([p[:, 0] * f + ox, p[:, 1] * f + oy], axis=1)
        nf = {**face, "poly": q}
        if "grad_axis" in face:
            (a0, a1) = face["grad_axis"]
            nf["grad_axis"] = ((a0[0] * f + ox, a0[1] * f + oy),
                               (a1[0] * f + ox, a1[1] * f + oy))
        out.append(nf)
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


def highlight_ops(analytic, right, up, fwd, s, cx, cy, half, strength=0.15):
    """Very diffuse speculars on up-facing disc tops: soft radial gradient blobs."""
    ops = []
    for rec in analytic:
        if rec["kind"] != "disc":
            continue
        R = np.asarray(rec["R"], float)
        n = R[:, 1] / np.linalg.norm(R[:, 1])
        if abs(n @ up) < 0.5:            # not clearly up/down facing
            continue
        th = np.linspace(0, 2 * math.pi, 24)
        w = _radius_pts(rec, th, 0.0)
        px, py, _ = _project_px(w, right, up, fwd, s, cx, cy, half)
        cxp, cyp = float(px.mean()), float(py.mean())
        rr = float(max(px.max() - px.min(), py.max() - py.min()) / 2.0)
        ops.append({"cx": cxp, "cy": cyp, "r": rr, "opacity": strength})
    return ops


def remap_highlights(his, f, ox, oy, strength):
    return [{"cx": h["cx"] * f + ox, "cy": h["cy"] * f + oy, "r": h["r"] * f,
             "opacity": strength} for h in his]


def faces_from_tris(tri, right, up, fwd, s, cx, cy, half):
    """Camera-facing triangle faces as px-space polygons with outward view-space
    normals. Winding is trusted (repaired upstream): a triangle whose outward
    normal points away from the camera (nv[2] >= 0) is a back-face and is
    CULLED — never flipped. Flipping was the old hack that leaked bright
    top-tone slivers from hollow parts' undersides."""
    faces = []
    for v in tri:                       # v: (3,3) world coords, outward-CCW
        n = np.cross(v[1] - v[0], v[2] - v[0])
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            continue
        n = n / ln
        nv = np.array([n @ right, n @ up, n @ fwd])
        if nv[2] > -1e-6:
            continue                    # back-facing or edge-on: cull
        px, py, z = _project_px(v, right, up, fwd, s, cx, cy, half)
        poly = np.stack([px, py], axis=1)
        faces.append({"poly": poly, "normal": nv, "depth": float(np.mean(z)),
                      "kind": "tri"})
    return faces
