from __future__ import annotations
import math
from collections import defaultdict, namedtuple
from pathlib import Path
import numpy as np

from . import primitives
from . import repair

VisResult = namedtuple("VisResult", "segs bbox s faces analytic")

_text_cache: dict[Path, list[str]] = {}


def default_roots(ldraw_dir: Path) -> list[Path]:
    ldraw_dir = Path(ldraw_dir)
    return [ldraw_dir / "p" / "48", ldraw_dir / "p",
            ldraw_dir / "parts", ldraw_dir / "parts" / "s", ldraw_dir / "models"]


def resolve(name: str, roots: list[Path]) -> Path | None:
    name = name.replace("\\", "/").strip()
    base = name.split("/")[-1]
    for root in roots:
        for cand in (root / name, root / base):
            if cand.exists():
                return cand
    return None


def _lines(path: Path) -> list[str]:
    if path not in _text_cache:
        _text_cache[path] = Path(path).read_text(errors="replace").splitlines()
    return _text_cache[path]


def _bfc_certified(ln: str) -> bool:
    """True if a line certifies BFC winding ('0 BFC CERTIFY ...' or a bare
    '0 BFC CW|CCW' orientation statement — either establishes trusted winding)."""
    tok = ln.split()
    if len(tok) >= 3 and tok[0] == "0" and tok[1] == "BFC":
        flags = tok[2:]
        if "NOCERTIFY" in flags:
            return False
        return "CERTIFY" in flags or "CW" in flags or "CCW" in flags
    return False


def flatten(path: Path, R: np.ndarray, t: np.ndarray, out: dict,
            roots: list[Path], depth: int = 0,
            inherited_invert: bool = False) -> None:
    if depth > 30:
        return
    out.setdefault("tri_meta", [])
    # `inherited_invert` fully encodes ancestor mirrors + INVERTNEXTs; each
    # reference below XORs in only its OWN matrix's reflection. Recomputing
    # reflection from the accumulated basis here would count every ancestor
    # mirror a second time and cancel it (lost the flip for geometry nested
    # two+ levels under a mirrored reference: 32062's axle end, 4019's gear
    # half). Only the root call's own basis is folded in here.
    base_invert = inherited_invert
    if depth == 0:
        base_invert ^= bool(np.linalg.det(R) < 0)
    lines = _lines(path)
    certified = any(_bfc_certified(ln) for ln in lines)
    local_cw = False            # CCW is the LDraw default winding
    invert_next = False
    for ln in lines:
        tok = ln.split()
        if not tok:
            continue
        typ = tok[0]
        if typ == "0":
            cmd = tok[1:]
            if len(cmd) >= 2 and cmd[0] == "BFC":
                flags = cmd[1:]
                if "CW" in flags:
                    local_cw = True
                if "CCW" in flags:
                    local_cw = False
                if "INVERTNEXT" in flags:
                    invert_next = True
            continue
        if typ == "1":
            if len(tok) >= 15:
                x, y, z = map(float, tok[2:5])
                a, b, c, d, e, f, g, h, i = map(float, tok[5:14])
                M = np.array([[a, b, c], [d, e, f], [g, h, i]], float)
                T = np.array([x, y, z], float)
                ref = " ".join(tok[14:])
                ref = primitives.ALIAS_REFS.get(
                    ref.replace("\\", "/").split("/")[-1].lower(), ref)
                Rsub, tsub = R @ M, R @ T + t
                prim = primitives.from_ref(ref, Rsub, tsub)
                if prim is not None and "analytic" in out:
                    out["analytic"].append(prim)
                else:
                    sub = resolve(ref, roots)
                    if sub is not None:
                        m_reflect = bool(np.linalg.det(M) < 0)
                        flatten(sub, Rsub, tsub, out, roots, depth + 1,
                                inherited_invert=base_invert ^ invert_next
                                ^ m_reflect)
            invert_next = False
        elif typ in ("2", "5") and len(tok) >= 8:
            pts = np.array(list(map(float, tok[2:])), float).reshape(-1, 3)
            out[typ].append(pts @ R.T + t)
        elif typ in ("3", "4"):
            n = 3 if typ == "3" else 4
            if len(tok) >= 2 + 3 * n:
                pts = np.array(list(map(float, tok[2:2 + 3 * n])), float).reshape(n, 3) @ R.T + t
                tri_invert = base_invert ^ local_cw
                meta = {"certified": certified, "invert": tri_invert}
                if n == 3:
                    out["tri"].append(pts)
                    out["tri_meta"].append(dict(meta))
                else:
                    out["tri"].append(pts[[0, 1, 2]])
                    out["tri_meta"].append(dict(meta))
                    out["tri"].append(pts[[0, 2, 3]])
                    out["tri_meta"].append(dict(meta))


SIGN_Z = -1.0          # tuned so parts face the camera (matches LDView iso)
MESH_CACHE_DIR = Path(".cache/mesh")


def view_basis(lat: float, long: float):
    la, lo = math.radians(lat), math.radians(long)
    up_world = np.array([0.0, -1.0, 0.0])          # LDraw Y is down
    d = np.array([math.cos(la) * math.sin(lo), -math.sin(la),
                  SIGN_Z * math.cos(la) * math.cos(lo)])
    forward = -d / np.linalg.norm(d)
    right = np.cross(forward, up_world); right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return right, up, forward


def project(P: np.ndarray, right, up, forward):
    return P @ right, -(P @ up), P @ forward       # sx, sy(image-down), depth


def same_side(p1, p2, c1, c2) -> bool:
    e = p2 - p1
    cr1 = e[0] * (c1[1] - p1[1]) - e[1] * (c1[0] - p1[0])
    cr2 = e[0] * (c2[1] - p1[1]) - e[1] * (c2[0] - p1[0])
    return bool(cr1 * cr2 > 0)


def rasterize_zbuffer(tri_s: np.ndarray, tri_z: np.ndarray, W: int, H: int) -> np.ndarray:
    zbuf = np.full((H, W), np.inf)
    for v, zz in zip(tri_s, tri_z):
        minx = max(int(np.floor(v[:, 0].min())), 0); maxx = min(int(np.ceil(v[:, 0].max())), W - 1)
        miny = max(int(np.floor(v[:, 1].min())), 0); maxy = min(int(np.ceil(v[:, 1].max())), H - 1)
        if maxx < minx or maxy < miny:
            continue
        gx, gy = np.meshgrid(np.arange(minx, maxx + 1), np.arange(miny, maxy + 1))
        x0, y0 = v[0]; x1, y1 = v[1]; x2, y2 = v[2]
        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denom) < 1e-9:
            continue
        a = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / denom
        b = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / denom
        cc = 1 - a - b
        inside = (a >= -1e-4) & (b >= -1e-4) & (cc >= -1e-4)
        z = a * zz[0] + b * zz[1] + cc * zz[2]
        sub = zbuf[miny:maxy + 1, minx:maxx + 1]
        m = inside & (z < sub)
        sub[m] = z[m]
    return zbuf


def dilate_zbuffer(zbuf: np.ndarray, r: int) -> np.ndarray:
    """Neighborhood-max of a z-buffer over a (2r+1) box: each cell becomes the
    farthest depth nearby. Used for edge occlusion so silhouette-tangent edges
    (with background on one side) survive while buried edges stay hidden."""
    if r <= 0:
        return zbuf
    d = zbuf.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx or dy:
                d = np.maximum(d, np.roll(np.roll(zbuf, dy, 0), dx, 1))
    return d


def clip_visible(seg, zbuf, W, H, depth, bias):
    """Return list of visible sub-segments. `depth` may be a scalar (uniform) or
    (z1, z2) for per-endpoint depth. Samples the z-buffer along the segment."""
    x1, y1, x2, y2, kind = seg
    z1, z2 = (depth, depth) if np.isscalar(depth) else depth
    n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 2))
    ts = np.linspace(0, 1, n)
    xs = x1 + (x2 - x1) * ts; ys = y1 + (y2 - y1) * ts; zs = z1 + (z2 - z1) * ts
    xi = np.clip(xs.astype(int), 0, W - 1); yi = np.clip(ys.astype(int), 0, H - 1)
    vis = zs <= zbuf[yi, xi] + bias
    runs, i = [], 0
    while i < n:
        if vis[i]:
            j = i
            while j + 1 < n and vis[j + 1]:
                j += 1
            runs.append((xs[i], ys[i], xs[j], ys[j], kind))
            i = j + 1
        else:
            i += 1
    return runs


EDGE_BIAS = 0.004      # fraction of depth range
SIL_BIAS = 0.03        # larger: silhouette lines sit on their own surface
EDGE_DILATE = 0.0024   # z-buffer dilation radius as a FRACTION of render_px:
                       # occlude edges against a neighborhood-max ("farthest nearby
                       # surface") buffer. Lets a silhouette-tangent edge (background
                       # just outside it, e.g. a cylinder's bottom-rim where body
                       # meets base) survive, while edges buried behind a surface on
                       # all sides stay hidden. A flat depth bias can't separate
                       # those two; see part 3941. Fraction (not px) so the effect is
                       # resolution-independent across render_px.


def _fit_params(allpts, right, up, fwd, render_px):
    """Pixel-fit (s, cx, cy) and depth range from a world point cloud."""
    a, b, z = project(allpts, right, up, fwd)
    minx, maxx, miny, maxy = a.min(), a.max(), b.min(), b.max()
    span = max(maxx - minx, maxy - miny) or 1.0
    s = (render_px - 20) / span
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    zrange = (z.max() - z.min()) or 1.0
    return s, cx, cy, zrange


def _ops_bbox(segs):
    xs, ys = [], []
    for op in segs:
        if op[0] == "line":
            xs += [op[1], op[3]]; ys += [op[2], op[4]]
        else:
            pts = primitives.arc_ellipse(op).points(
                np.radians(np.linspace(op[7], op[8], 12)))
            xs += list(pts[:, 0]); ys += list(pts[:, 1])
    xs = xs or [0, 1]; ys = ys or [0, 1]
    return (min(xs), min(ys), max(xs), max(ys))


def _visible_segments_faceted(out, right, up, fwd, render_px):
    """Original z-buffer pipeline; used when no analytic primitives are present."""
    tri = np.array(out["tri"]) if out["tri"] else np.zeros((0, 3, 3))
    fitpts = tri.reshape(-1, 3) if len(tri) else np.array(out["2"]).reshape(-1, 3)
    if len(fitpts) == 0:
        return VisResult([], (0.0, 0.0, 1.0, 1.0), 1.0, [], [])
    sx, sy, _ = project(fitpts, right, up, fwd)
    minx, maxx, miny, maxy = sx.min(), sx.max(), sy.min(), sy.max()
    span = max(maxx - minx, maxy - miny) or 1.0
    s = (render_px - 20) / span
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    proj = primitives.Projection(right, up, fwd, s, cx, cy, render_px / 2)

    if len(tri):
        tpx, tpy, tz = proj.to_px(tri.reshape(-1, 3))
        tri_s = np.stack([tpx, tpy], 1).reshape(-1, 3, 2)
        tri_z = tz.reshape(-1, 3)
        zbuf = rasterize_zbuffer(tri_s, tri_z, render_px, render_px)
        zrange = tri_z.max() - tri_z.min() or 1.0
    else:
        zbuf = np.full((render_px, render_px), np.inf); zrange = 1.0
    zedge = dilate_zbuffer(zbuf, max(2, round(render_px * EDGE_DILATE)))

    segs = []
    for e in out["2"]:
        ax, ay, az = proj.to_px(e[0:1]); bx, by, bz = proj.to_px(e[1:2])
        segs += clip_visible((ax[0], ay[0], bx[0], by[0], "edge"), zedge, render_px,
                             render_px, (az[0], bz[0]), EDGE_BIAS * zrange)
    for q in out["5"]:
        px, py, pz = proj.to_px(q)
        p1 = np.array([px[0], py[0]]); p2 = np.array([px[1], py[1]])
        if math.hypot(*(p2 - p1)) < 0.5:
            continue
        if same_side(p1, p2, np.array([px[2], py[2]]), np.array([px[3], py[3]])):
            segs += clip_visible((px[0], py[0], px[1], py[1], "sil"), zbuf, render_px,
                                 render_px, (pz[0], pz[1]), SIL_BIAS * zrange)

    xs = [c for sg in segs for c in (sg[0], sg[2])] or [0, 1]
    ys = [c for sg in segs for c in (sg[1], sg[3])] or [0, 1]
    from . import shade
    faces = shade.faces_from_tris(tri, proj, cond_edges=out["5"]) if len(tri) else []
    faces = shade.order_faces(faces, eps=EDGE_BIAS * zrange)
    return VisResult(segs, (min(xs), min(ys), max(xs), max(ys)), s, faces, [])


def _visible_segments_analytic(out, right, up, fwd, render_px):
    """Exact pipeline: analytic occlusion oracle + true arc/line drawn ops."""
    analytic = out["analytic"]
    half = render_px / 2.0

    cloud = []
    if out["tri"]:
        cloud.append(np.array(out["tri"]).reshape(-1, 3))
    if out["2"]:
        cloud.append(np.array(out["2"]).reshape(-1, 3))
    for prim in analytic:
        cloud.append(prim.fit_pts())
    allpts = np.vstack(cloud)
    s, cx, cy, zrange = _fit_params(allpts, right, up, fwd, render_px)
    eps = 1e-3 * zrange
    proj = primitives.Projection(right, up, fwd, s, cx, cy, half)

    # occluders: analytic surfaces + flat triangles. Only ORIGINAL primitives
    # join the stroke-visibility list; walls merged later inside
    # faces_from_analytic build their own (cached) occluder lazily for
    # witness ordering, and must NOT be added here — their member surfaces
    # already cover the same geometry.
    occluders = [p.occluder() for p in analytic if p.occluder() is not None]
    if out["tri"]:
        occluders.append(primitives.TriangleOccluder(np.array(out["tri"])))

    # drawn ops: analytic curves (+ a cylinder excludes itself from its
    # silhouette). A wall's rim arc is suppressed when a FULL-sector wall of
    # equal slope continues on the other side of the circle plane (stacked
    # cone/cylinder sections): that whole rim is a smooth joint, not an edge.
    full_smooth = defaultdict(set)
    for prim in analytic:
        if prim.is_full:
            for key, side, slope in prim.wall_rims():
                full_smooth[key].add((side, slope))
    shared_rims = set()
    for prim in analytic:
        for key, side, slope in prim.wall_rims():
            if (-side, slope) in full_smooth[key]:
                shared_rims.add((key, side))
    specs = []
    for prim in analytic:
        own = prim.occluder()
        for op, dfn in prim.drawn_with_depth(proj, skip_rims=shared_rims):
            specs.append((op, dfn, own if op[-1] == "sil" else None))
    # non-substituted straight edges (box edges, chords) and conditionals
    for e in out["2"]:
        px, py, z = proj.to_px(e)
        specs.append((("line", float(px[0]), float(py[0]),
                       float(px[1]), float(py[1]), "edge"),
                      primitives._line_depth_fn(float(z[0]), float(z[1]))))
    for q in out["5"]:
        px, py, z = proj.to_px(q)
        p1 = np.array([px[0], py[0]]); p2 = np.array([px[1], py[1]])
        if math.hypot(*(p2 - p1)) < 0.5:
            continue
        if same_side(p1, p2, np.array([px[2], py[2]]), np.array([px[3], py[3]])):
            specs.append((("line", float(px[0]), float(py[0]),
                           float(px[1]), float(py[1]), "sil"),
                          primitives._line_depth_fn(float(z[0]), float(z[1]))))

    segs = primitives.visible_subops(specs, occluders, proj.ray_origin, fwd,
                                     eps, n=64)
    from . import shade
    tri_faces = shade.faces_from_tris(np.array(out["tri"]), proj,
                                      cond_edges=out["5"]) if out["tri"] else []
    an_faces = shade.faces_from_analytic(analytic, proj)
    own_occ = {id(f): f["prim"].occluder() for f in an_faces
               if f["prim"].occluder() is not None}
    # Witness-depth ordering replaces both the mean-depth painter sort and the
    # occlusion cull: hidden faces paint first and get covered.
    faces = shade.order_faces(tri_faces + an_faces, proj, eps, own_occ=own_occ)
    return VisResult(segs, _ops_bbox(segs), s, faces, analytic)


def _resolve_input(part: str, roots: list[Path]) -> Path:
    """Resolve a part id or .dat/.ldr/.mpd path to a file, or raise a clear error."""
    s = str(part)
    if s.lower().endswith((".dat", ".ldr", ".mpd")):
        p = Path(s)
        if not p.exists():
            raise FileNotFoundError(f"part file not found: {s}")
        return p
    path = resolve(s + ".dat", roots)
    if path is None:
        raise FileNotFoundError(f"could not resolve part {part!r} under {[str(r) for r in roots]}")
    return path


def visible_segments(part: str, ldraw_dir, lat=30.0, long=45.0, render_px=900):
    roots = default_roots(ldraw_dir)
    path = _resolve_input(part, roots)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    flatten(path, np.eye(3), np.zeros(3), out, roots)
    if out["tri"]:
        # Repair returns outward-oriented tris as float32 (cache dtype); the
        # ~7 sig-fig precision is ample at icon scale. Keep out["tri"] a LIST
        # of (3,3) rows — _visible_segments_* test it with `if out["tri"]:`.
        fixed = repair.repaired_tris(np.array(out["tri"]), out["tri_meta"],
                                     MESH_CACHE_DIR)
        out["tri"] = list(fixed)
    right, up, fwd = view_basis(lat, long)
    if out["analytic"]:
        return _visible_segments_analytic(out, right, up, fwd, render_px)
    return _visible_segments_faceted(out, right, up, fwd, render_px)


def fit_affine(bbox, W, H, margin=6, scale=1.0):
    """Uniform scale+offset mapping the segment bbox into a W x H canvas."""
    scale = max(0.01, min(1.0, scale))
    bx0, by0, bx1, by1 = bbox
    bw, bh = (bx1 - bx0) or 1.0, (by1 - by0) or 1.0
    iw = max(1.0, (W - 2 * margin) * scale); ih = max(1.0, (H - 2 * margin) * scale)
    f = min(iw / bw, ih / bh)
    ox = (W - bw * f) / 2 - bx0 * f
    oy = (H - bh * f) / 2 - by0 * f
    return f, ox, oy


def fit_segments(segs, bbox, W, H, margin=6, scale=1.0):
    f, ox, oy = fit_affine(bbox, W, H, margin, scale)
    out = []
    for op in segs:
        if len(op) == 5:                               # legacy line tuple
            op = ("line",) + tuple(op)
        if op[0] == "line":
            _, x1, y1, x2, y2, k = op
            out.append(("line", x1 * f + ox, y1 * f + oy, x2 * f + ox, y2 * f + oy, k))
        else:
            _, cx, cy, ux, uy, vx, vy, t0, t1, k = op
            out.append(("arc", cx * f + ox, cy * f + oy,
                        ux * f, uy * f, vx * f, vy * f, t0, t1, k))
    return out
