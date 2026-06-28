from __future__ import annotations
import math
from pathlib import Path
import numpy as np

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


def flatten(path: Path, R: np.ndarray, t: np.ndarray, out: dict,
            roots: list[Path], depth: int = 0) -> None:
    if depth > 30:
        return
    for ln in _lines(path):
        tok = ln.split()
        if not tok:
            continue
        typ = tok[0]
        if typ == "1" and len(tok) >= 15:
            x, y, z = map(float, tok[2:5])
            a, b, c, d, e, f, g, h, i = map(float, tok[5:14])
            M = np.array([[a, b, c], [d, e, f], [g, h, i]], float)
            T = np.array([x, y, z], float)
            sub = resolve(" ".join(tok[14:]), roots)
            if sub is not None:
                flatten(sub, R @ M, R @ T + t, out, roots, depth + 1)
        elif typ in ("2", "5") and len(tok) >= 8:
            pts = np.array(list(map(float, tok[2:])), float).reshape(-1, 3)
            out[typ].append(pts @ R.T + t)
        elif typ in ("3", "4"):
            n = 3 if typ == "3" else 4
            if len(tok) >= 2 + 3 * n:
                pts = np.array(list(map(float, tok[2:2 + 3 * n])), float).reshape(n, 3) @ R.T + t
                if n == 3:
                    out["tri"].append(pts)
                else:
                    out["tri"].append(pts[[0, 1, 2]])
                    out["tri"].append(pts[[0, 2, 3]])


SIGN_Z = -1.0          # tuned so parts face the camera (matches LDView iso)


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


def visible_segments(part: str, ldraw_dir, lat=30.0, long=45.0, render_px=900):
    roots = default_roots(ldraw_dir)
    path = resolve(part + ".dat", roots) if not str(part).endswith(".dat") else Path(part)
    out = {"2": [], "5": [], "tri": []}
    flatten(path, np.eye(3), np.zeros(3), out, roots)
    right, up, fwd = view_basis(lat, long)

    tri = np.array(out["tri"]) if out["tri"] else np.zeros((0, 3, 3))
    fitpts = tri.reshape(-1, 3) if len(tri) else np.array(out["2"]).reshape(-1, 3)
    sx, sy, _ = project(fitpts, right, up, fwd)
    minx, maxx, miny, maxy = sx.min(), sx.max(), sy.min(), sy.max()
    span = max(maxx - minx, maxy - miny) or 1.0
    s = (render_px - 20) / span
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2

    def to_px(P):
        a, b, z = project(P, right, up, fwd)
        return (a - cx) * s + render_px / 2, (b - cy) * s + render_px / 2, z

    if len(tri):
        tpx, tpy, tz = to_px(tri.reshape(-1, 3))
        tri_s = np.stack([tpx, tpy], 1).reshape(-1, 3, 2)
        tri_z = tz.reshape(-1, 3)
        zbuf = rasterize_zbuffer(tri_s, tri_z, render_px, render_px)
        zrange = tri_z.max() - tri_z.min() or 1.0
    else:
        zbuf = np.full((render_px, render_px), np.inf); zrange = 1.0

    segs = []
    for e in out["2"]:
        ax, ay, az = to_px(e[0:1]); bx, by, bz = to_px(e[1:2])
        segs += clip_visible((ax[0], ay[0], bx[0], by[0], "edge"), zbuf, render_px,
                             render_px, (az[0], bz[0]), EDGE_BIAS * zrange)
    for q in out["5"]:
        px, py, pz = to_px(q)
        p1 = np.array([px[0], py[0]]); p2 = np.array([px[1], py[1]])
        if math.hypot(*(p2 - p1)) < 0.5:
            continue
        if same_side(p1, p2, np.array([px[2], py[2]]), np.array([px[3], py[3]])):
            segs += clip_visible((px[0], py[0], px[1], py[1], "sil"), zbuf, render_px,
                                 render_px, (pz[0], pz[1]), SIL_BIAS * zrange)

    xs = [c for sg in segs for c in (sg[0], sg[2])] or [0, 1]
    ys = [c for sg in segs for c in (sg[1], sg[3])] or [0, 1]
    return segs, (min(xs), min(ys), max(xs), max(ys))


def fit_segments(segs, bbox, W, H, margin=6, scale=1.0):
    scale = max(0.01, min(1.0, scale))
    bx0, by0, bx1, by1 = bbox
    bw, bh = (bx1 - bx0) or 1.0, (by1 - by0) or 1.0
    iw = max(1.0, (W - 2 * margin) * scale); ih = max(1.0, (H - 2 * margin) * scale)
    f = min(iw / bw, ih / bh)
    ox = (W - bw * f) / 2 - bx0 * f
    oy = (H - bh * f) / 2 - by0 * f
    return [(x1 * f + ox, y1 * f + oy, x2 * f + ox, y2 * f + oy, k)
            for (x1, y1, x2, y2, k) in segs]
