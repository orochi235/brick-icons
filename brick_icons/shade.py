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
                          "depth": float(np.mean(z)), "zs": z, "kind": kind,
                          "rec": rec})
        elif kind == "cyli":
            faces.extend(_cyl_wall_faces(rec, R, sect, right, up, fwd,
                                         s, cx, cy, half))
    return faces


def _arc_sector_spans(lo, length, sect):
    """Intersect the arc starting at `lo` (radians) of `length` with the
    sector [0, sect] on the circle. Returns [(a, b)] spans (b > a), at most
    two: a wrapped arc can re-enter the sector past 0. A full sector needs no
    clamping — the raw interval is returned so a seamless single face is kept
    even when it crosses 0/2pi (angles are plain reals downstream)."""
    if sect >= 2 * math.pi - 1e-6:
        return [(lo, lo + length)]
    two = 2 * math.pi
    lo = lo % two
    pieces = [(lo, min(lo + length, two))]
    if lo + length > two:
        pieces.append((0.0, lo + length - two))
    spans = []
    for a, b in pieces:
        a, b = max(a, 0.0), min(b, sect)
        if b - a > 1e-3:
            spans.append((a, b))
    return spans


def _cyl_wall_faces(rec, R, sect, right, up, fwd, s, cx, cy, half):
    """Cylinder wall fills: the camera-facing outer half AND the far half's
    interior surface (visible when looking into an open tube — leaving it out
    produced 4019's white voids). Each visible span becomes one arc-region
    polygon with a linear-gradient spec; a partial sector can split a span in
    two where the arc wraps past 0."""
    U, A, V = R[:, 0], R[:, 1], R[:, 2]
    a = float(U @ fwd); b = float(V @ fwd)
    if a == 0.0 and b == 0.0:
        return []                                # axis points at camera: no wall
    phi = math.atan2(b, a)
    theta_face = phi + math.pi                   # most camera-facing angle
    halves = [(theta_face - math.pi / 2, False),         # outer near half
              (theta_face + math.pi / 2, True)]          # interior far half
    faces = []
    for start, interior in halves:
        for lo, hi in _arc_sector_spans(start, math.pi, sect):
            f = _wall_span_face(rec, U, V, lo, hi, interior,
                                right, up, fwd, s, cx, cy, half)
            if f is not None:
                faces.append(f)
    return faces


def _wall_span_face(rec, U, V, lo, hi, interior, right, up, fwd, s, cx, cy, half):
    ths = np.linspace(lo, hi, 40)
    top = _radius_pts(rec, ths, 1.0)
    bot = _radius_pts(rec, ths, 0.0)
    tpx, tpy, tz = _project_px(top, right, up, fwd, s, cx, cy, half)
    bpx, bpy, bz = _project_px(bot, right, up, fwd, s, cx, cy, half)
    poly = np.concatenate([np.stack([tpx, tpy], 1),
                           np.stack([bpx, bpy], 1)[::-1]], axis=0)
    zs = np.concatenate([tz, bz])
    # gradient axis: mid-height points at the span's end angles
    mid = _radius_pts(rec, np.array([lo, hi]), 0.5)
    mpx, mpy, _ = _project_px(mid, right, up, fwd, s, cx, cy, half)
    p0 = (float(mpx[0]), float(mpy[0])); p1 = (float(mpx[1]), float(mpy[1]))
    axis = np.array([p1[0] - p0[0], p1[1] - p0[1]]); L2 = float(axis @ axis) or 1.0
    samples = []
    for th in np.linspace(lo, hi, 9):
        n = math.cos(th) * U + math.sin(th) * V; n = n / np.linalg.norm(n)
        if interior:
            n = -n                               # inward surface normal
        nv = np.array([n @ right, n @ up, n @ fwd])
        p = _radius_pts(rec, np.array([th]), 0.5)
        ppx, ppy, _ = _project_px(p, right, up, fwd, s, cx, cy, half)
        off = ((ppx[0] - p0[0]) * axis[0] + (ppy[0] - p0[1]) * axis[1]) / L2
        samples.append((float(np.clip(off, 0.0, 1.0)), nv))
    return {"poly": poly, "zs": zs, "depth": float(np.mean(zs)), "kind": "cyli",
            "rec": rec, "interior": interior,
            "span_deg": math.degrees(hi - lo),
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


def _face_samples(f, inset=0.3, max_verts=8):
    """Sample pixels for HSR: the centroid plus up to `max_verts` polygon
    vertices pulled `inset` toward it, with matching self-depths.

    The inset is load-bearing twice over: raw vertices sit ON edges shared
    with adjacent walls (tie-depth => never occluded => hidden slivers would
    survive), and inset points stay strictly inside curved-wall polygons so
    the own-occluder ray still hits the surface. Self-depth per sample comes
    from the same affine combination of the per-vertex depths `zs` (exact for
    planar faces; a chord approximation for curved ones, refined by the own
    occluder in the caller). Faces without aligned `zs` fall back to the mean
    depth."""
    poly = f["poly"]
    c = poly.mean(axis=0)
    idx = np.unique(np.linspace(0, len(poly) - 1,
                                min(len(poly), max_verts)).round().astype(int))
    pts = np.vstack([c[None, :], poly[idx] * (1 - inset) + c * inset])
    zs = f.get("zs")
    if zs is not None and len(zs) == len(poly):
        zc = float(np.mean(zs))
        ds = np.concatenate([[zc], np.asarray(zs, float)[idx] * (1 - inset) + zc * inset])
    else:
        ds = np.full(len(pts), f["depth"], float)
    return pts, ds


def cull_occluded_faces(faces, occluders, ray_origin, fwd, eps,
                        kinds=("tri",), own_occ=None):
    """Winding-independent hidden-surface removal for fill faces.

    A face is culled only when EVERY sample (centroid + inset vertices, see
    `_face_samples`) has some other occluder nearer than the face's own
    surface by more than eps. Single-sample culling is wrong in both
    directions: a stud covering just the centroid must not cull a whole top
    face (3001's top is two big tris whose centroids land inside stud
    footprints), while a fully hidden underside sliver must still die.

    Self-depth per sample prefers the face's OWN occluder along that ray (a
    curved band's interpolated depth is a chord, nearer-biased mean would make
    a wall cull itself); rays that miss the own occluder keep the interpolated
    value. The own occluder is excluded from the 'nearer?' scan; the -eps
    margin keeps coplanar neighbours (studs/tops sitting ON the plane) from
    culling a face.

    `own_occ` maps id(face) -> its occluder (analytic faces only). Faces whose
    kind is not in `kinds` pass through untouched."""
    kept = []
    kinds = set(kinds)
    own_occ = own_occ or {}
    for f in faces:
        if f.get("kind") not in kinds:
            kept.append(f)
            continue
        pts, self_d = _face_samples(f)
        O = ray_origin(pts[:, 0], pts[:, 1])
        mine = own_occ.get(id(f))
        if mine is not None:
            d_own = np.asarray(mine.depth(O, fwd), float)
            self_d = np.where(np.isfinite(d_own), d_own, self_d)
        nearest = np.full(len(pts), np.inf)
        for occ in occluders:
            if occ is mine:
                continue                          # don't let a face occlude itself
            nearest = np.minimum(nearest, occ.depth(O, fwd))
        if not bool(np.all(nearest < self_d - eps)):
            kept.append(f)
    return kept


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
                      "zs": z, "kind": "tri"})
    return faces
