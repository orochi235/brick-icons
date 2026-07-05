from __future__ import annotations

import math
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from . import process

_VIEWBOX = re.compile(r'viewBox="([^"]+)"')
_TRANSFORM = re.compile(r'<g transform="([^"]+)"')
_PATH_D = re.compile(r'<path[^>]*\sd="([^"]+)"')


def _potrace(mask_L: Image.Image) -> tuple[list[str], str, str]:
    """Trace a 1-bit mask; return (path_d_list, viewbox, g_transform)."""
    with tempfile.TemporaryDirectory() as td:
        pbm = Path(td) / "m.pbm"
        svg = Path(td) / "m.svg"
        mask_L.convert("1").save(pbm)
        subprocess.run(["potrace", "-s", "-o", str(svg), str(pbm),
                        "--turdsize", "2", "--alphamax", "1.0", "--opttolerance", "0.2"],
                       check=True, capture_output=True)
        txt = svg.read_text()
    vb = _VIEWBOX.search(txt).group(1)
    tf_match = _TRANSFORM.search(txt)
    if not tf_match:
        return [], vb, ""          # empty mask -> no paths
    return _PATH_D.findall(txt), vb, tf_match.group(1)


def _write_svg(out_path: Path, viewbox: str, transform: str,
               layers: list[tuple[list[str], str]]) -> None:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" '
             f'preserveAspectRatio="xMidYMid meet">',
             '<rect width="100%" height="100%" fill="white"/>']
    if transform:
        parts.append(f'<g transform="{transform}" stroke="none">')
        for ds, fill in layers:
            for d in ds:
                parts.append(f'<path d="{d}" fill="{fill}"/>')
        parts.append("</g>")
    parts.append("</svg>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts))


def _arc_to_svg(op):
    """Convert a parametric arc op ('arc', cx, cy, ux, uy, vx, vy, t0, t1, kind)
    to an SVG elliptical-arc path 'd'. The point at param t is
    center + cos t*u + sin t*v; semi-axes/rotation come from the SVD of [u v]."""
    _, cx, cy, ux, uy, vx, vy, t0, t1, _ = op
    u = np.array([ux, uy]); v = np.array([vx, vy])
    M = np.column_stack([u, v])
    U_, S_, _ = np.linalg.svd(M)
    rx, ry = float(S_[0]), float(S_[1])
    phi = math.degrees(math.atan2(U_[1, 0], U_[0, 0]))

    def pt(t_deg):
        a = math.radians(t_deg)
        p = np.array([cx, cy]) + math.cos(a) * u + math.sin(a) * v
        return p[0], p[1]
    # increasing param sweeps u->v; sign of cross(u,v) gives screen orientation
    sweep = 1 if (ux * vy - uy * vx) * (1 if t1 >= t0 else -1) > 0 else 0

    # A single SVG elliptical-arc segment whose endpoints coincide renders as
    # nothing, so a full ellipse (e.g. a fully-visible stud top rim, span ~360)
    # must be split into two sub-arcs, each < 180 (large flag 0).
    if abs(t1 - t0) >= 359.9:
        tm = (t0 + t1) / 2.0
        x0, y0 = pt(t0); xm, ym = pt(tm); x1e, y1e = pt(t1)
        return (f'M {x0:.2f} {y0:.2f} A {rx:.2f} {ry:.2f} {phi:.2f} '
                f'0 {sweep} {xm:.2f} {ym:.2f} '
                f'A {rx:.2f} {ry:.2f} {phi:.2f} 0 {sweep} {x1e:.2f} {y1e:.2f}')

    x0, y0 = pt(t0); x1e, y1e = pt(t1)
    large = 1 if abs(t1 - t0) > 180 else 0
    return (f'M {x0:.2f} {y0:.2f} A {rx:.2f} {ry:.2f} {phi:.2f} '
            f'{large} {sweep} {x1e:.2f} {y1e:.2f}')


def segments_to_svg(segs, w, h, out_path, line_px=2, sil_px=2,
                    physical=None, s=None, line_mm=0.2, sil_mm=0.2,
                    fills=None) -> Path:
    if physical is not None:
        w_mm, h_mm = physical
        root = (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{w_mm:.2f}mm" height="{h_mm:.2f}mm" '
                f'viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet">')
        line_px = line_mm / 0.4 * s
        sil_px = sil_mm / 0.4 * s
    else:
        root = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
                f'preserveAspectRatio="xMidYMid meet">')
    parts = [root, '<rect width="100%" height="100%" fill="white"/>']
    if fills:
        # Each fill is stroked in its own paint (~0.8px) so antialiasing seams
        # between abutting coplanar faces don't show; gradient fills (cylinder
        # walls) carry a <linearGradient> def instead of a flat color.
        defs, body = [], ['<g stroke-linejoin="round">']
        # Smooth-group facets share one gradient object; dedupe defs by
        # content so a 50-facet curve emits one <linearGradient>, not 50.
        def_ids = {}
        for i, fo in enumerate(fills):
            if "gradient" in fo:
                g = fo["gradient"]
                stops = "".join(
                    f'<stop offset="{o * 100:.1f}%" stop-color="{c}"/>' for o, c in g["stops"])
                if g.get("type") == "radial":
                    # unit-circle gradient space mapped onto the group's
                    # bounding ellipse; fx/fy shift the bright spot lightward
                    tf = (f'matrix({g["r"]:.2f} 0 0 {g["r"] * g["ratio"]:.2f} '
                          f'{g["cx"]:.2f} {g["cy"]:.2f})')
                    key = ("radial", tf, f'{g["fx"]:.3f},{g["fy"]:.3f}', stops)
                    gid = def_ids.get(key)
                    if gid is None:
                        gid = f"g{i}"
                        def_ids[key] = gid
                        defs.append(
                            f'<radialGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                            f'cx="0" cy="0" r="1" fx="{g["fx"]:.3f}" fy="{g["fy"]:.3f}" '
                            f'gradientTransform="{tf}">{stops}</radialGradient>')
                else:
                    key = (f'{g["x1"]:.2f},{g["y1"]:.2f},{g["x2"]:.2f},{g["y2"]:.2f}', stops)
                    gid = def_ids.get(key)
                    if gid is None:
                        gid = f"g{i}"
                        def_ids[key] = gid
                        defs.append(
                            f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                            f'x1="{g["x1"]:.2f}" y1="{g["y1"]:.2f}" '
                            f'x2="{g["x2"]:.2f}" y2="{g["y2"]:.2f}">{stops}</linearGradient>')
                paint = f"url(#{gid})"
            else:
                paint = fo["fill"]
            body.append(f'<path d="{fo["d"]}" fill="{paint}" fill-rule="evenodd" '
                        f'stroke="{paint}" stroke-width="0.8"/>')
        body.append("</g>")
        if defs:
            parts.append("<defs>" + "".join(defs) + "</defs>")
        parts += body
    parts.append('<g stroke="black" fill="none" stroke-linecap="round">')
    for op in segs:
        if len(op) == 5:                              # legacy line tuple
            op = ("line",) + tuple(op)
        if op[0] == "line":
            _, x1, y1, x2, y2, kind = op
            sw = sil_px if kind == "sil" else line_px
            parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                         f'stroke-width="{sw:.2f}"/>')
        else:
            sw = sil_px if op[-1] == "sil" else line_px
            parts.append(f'<path d="{_arc_to_svg(op)}" stroke-width="{sw:.2f}"/>')
    parts += ["</g>", "</svg>"]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts))
    return out_path


def cel_svg(rgba: Image.Image, out_path: Path, levels: int = 4) -> Path:
    rgba = rgba.convert("RGBA")
    g = process.posterize(process.to_grayscale(rgba), levels)
    arr = np.asarray(g)
    sil = np.asarray(process._silhouette_mask(rgba), int) > 16
    layers: list[tuple[list[str], str]] = []
    vb = tf = None
    for v in sorted(set(np.unique(arr).tolist())):
        if v >= 255:
            continue
        mask = (arr <= v) & sil          # cumulative: this dark or darker
        if mask.sum() == 0:
            continue
        mL = Image.fromarray(np.where(mask, 0, 255).astype(np.uint8), "L")
        ds, vbb, tff = _potrace(mL)
        if not ds:
            continue
        vb = vb or vbb
        tf = tf or tff
        layers.append((ds, f"#{v:02x}{v:02x}{v:02x}"))
    layers.reverse()                     # lightest/largest first, darker on top
    _write_svg(Path(out_path), vb or "0 0 1 1", tf or "", layers)
    return Path(out_path)
