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


def _arc_endpoints(cx, cy, rx, ry, phi_deg, t0_deg, t1_deg):
    """Pixel endpoints of an elliptical arc at param angles t0/t1 (degrees)."""
    ca, sa = math.cos(math.radians(phi_deg)), math.sin(math.radians(phi_deg))

    def pt(t_deg):
        a = math.radians(t_deg)
        ux, uy = rx * math.cos(a), ry * math.sin(a)
        return cx + ca * ux - sa * uy, cy + sa * ux + ca * uy
    return pt(t0_deg), pt(t1_deg)


def segments_to_svg(segs, w, h, out_path, line_px=2, sil_px=3) -> Path:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
             f'preserveAspectRatio="xMidYMid meet">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<g stroke="black" fill="none" stroke-linecap="round">']
    for op in segs:
        if len(op) == 5:                              # legacy line tuple
            op = ("line",) + tuple(op)
        if op[0] == "line":
            _, x1, y1, x2, y2, kind = op
            sw = sil_px if kind == "sil" else line_px
            parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                         f'stroke-width="{sw}"/>')
        else:
            _, cx, cy, rx, ry, phi, t0, t1, kind = op
            sw = sil_px if kind == "sil" else line_px
            (x0, y0), (x1e, y1e) = _arc_endpoints(cx, cy, rx, ry, phi, t0, t1)
            large = 1 if abs(t1 - t0) > 180 else 0
            sweep = 1 if t1 > t0 else 0
            parts.append(f'<path d="M {x0:.2f} {y0:.2f} A {rx:.2f} {ry:.2f} {phi:.2f} '
                         f'{large} {sweep} {x1e:.2f} {y1e:.2f}" stroke-width="{sw}"/>')
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
