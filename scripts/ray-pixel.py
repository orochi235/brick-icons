"""What a pixel of a render should show: every surface its line of sight
crosses, nearest first, cast against the part's own triangles.

Reads the render's `<part>.fit.json` (the CLI writes it beside the SVG).
`--zoom` is the PNG's size over the fit's; it is worked out from `--png` when
given. `--line` sweeps the pixels from one point to another and prints the
nearest hit of each, which is what tells a streak that is real geometry --
the far side of a hole, a different surface -- from one that is paint.

    .venv/bin/python scripts/ray-pixel.py 3649 --fit out/x/3649.fit.json \\
        --png out/x/3649.png --at 224,137
    .venv/bin/python scripts/ray-pixel.py 3649 --fit ... --line 214,137,234,137
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from brick_icons import edge_truth, hlr, raycast  # noqa: E402


def _lit(fit, n):
    """Lambert term of the style's VIEW-space light on a world normal, or
    None for a render with no light."""
    if "light" not in fit:
        return None
    view = np.array([n @ np.asarray(fit[k], float) for k in ("right", "up", "fwd")])
    return float(view @ np.asarray(fit["light"], float))


def _row(fit, h):
    lit = _lit(fit, h.normal)
    n = " ".join(f"{c:+.3f}" for c in h.normal)
    return (f"depth {h.depth:9.3f}  tri {h.tri:6d}  normal ({n})"
            + (f"  lit {lit:+.3f}" if lit is not None else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("part")
    ap.add_argument("--fit", required=True, help="the render's fit.json")
    ap.add_argument("--png", help="the raster the pixel coordinates are in")
    ap.add_argument("--zoom", type=float, help="raster size over fit size")
    ap.add_argument("--at", help="x,y: list every hit at this pixel")
    ap.add_argument("--line", help="x0,y0,x1,y1: nearest hit of each pixel")
    a = ap.parse_args()
    fit = json.loads(Path(a.fit).read_text())
    zoom = a.zoom
    if zoom is None and a.png:
        from PIL import Image
        zoom = Image.open(a.png).width / fit["width"]
    zoom = zoom or 1.0
    tris = edge_truth.load(a.part, hlr.default_roots(ROOT / "vendor" / "ldraw"))["tri"]
    if a.at:
        x, y = (float(v) for v in a.at.split(","))
        hs = raycast.hits(tris, *raycast.pixel_ray(fit, x + 0.5, y + 0.5, zoom))
        print(f"{a.part} px ({x:g}, {y:g}) zoom {zoom:g}: {len(hs)} hits")
        for h in hs:
            print("  " + _row(fit, h))
    if a.line:
        x0, y0, x1, y1 = (float(v) for v in a.line.split(","))
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for i in range(n):
            f = i / max(n - 1, 1)
            x, y = round(x0 + (x1 - x0) * f), round(y0 + (y1 - y0) * f)
            hs = raycast.hits(tris, *raycast.pixel_ray(fit, x + 0.5, y + 0.5, zoom))
            print(f"({x:4d}, {y:4d})  " + (_row(fit, hs[0]) if hs else "background"))


main()
