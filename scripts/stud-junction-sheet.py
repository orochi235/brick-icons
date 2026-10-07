"""Before/after/diff sheet of the SVGs scripts/stud-junction-svgs.py wrote,
cropped to where they differ and zoomed: a sub-pixel change is invisible at
icon size. Each part gets one row at icon size (1x, the changed-component
count that matters) and a row per changed spot, cropped and drawn at --zoom.

    .venv/bin/python scripts/stud-junction-sheet.py out/junction \
        --out out/junction/sheet.png 3024 3001
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PIL import Image

from _sheet import sheet
from brick_icons.lab import diff as _diff


def raster(svg: Path, png: Path, width: int, view=None) -> Image.Image:
    src = svg
    if view is not None:
        x, y, w, h = view
        text = re.sub(r'viewBox="[^"]*"', f'viewBox="{x} {y} {w} {h}"',
                      svg.read_text(), count=1)
        src = png.with_suffix(".svg")
        src.write_text(text)
    subprocess.run(["resvg", "--background", "white", "-w", str(width),
                    str(src), str(png)], check=True)
    return Image.open(png).convert("RGB")


def spots(before, after, k, n):
    """Up to `n` biggest changed regions as (cx, cy) in canvas px, from a
    render at `k` px per canvas px."""
    d = np.abs(np.asarray(before, int) - np.asarray(after, int)).max(axis=2)
    lab, sizes = _diff.label(d > 0)
    out = []
    for i in np.argsort(sizes)[::-1][:n]:
        if sizes[i] < 4:
            break
        ys, xs = np.nonzero(lab == i + 1)
        out.append((xs.mean() / k, ys.mean() / k))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--zoom", type=int, default=48)
    ap.add_argument("--span", type=float, default=8.0,
                    help="crop side, canvas px")
    ap.add_argument("--spots", type=int, default=2)
    ap.add_argument("--title", default="contour band at a stud junction")
    a = ap.parse_args()
    root = Path(a.root)
    rows = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for part in a.parts:
            sb, sa = root / "before" / f"{part}.svg", root / "after" / f"{part}.svg"
            vb = [float(v) for v in re.search(
                r'viewBox="([^"]*)"', sa.read_text()).group(1).split()]
            native = int(vb[2])
            b1 = raster(sb, td / f"{part}-b1.png", native)
            a1 = raster(sa, td / f"{part}-a1.png", native)
            up = 8 * native
            b2 = raster(sb, td / f"{part}-b2.png", up)
            a2 = raster(sa, td / f"{part}-a2.png", up)
            rows.append((f"{part} 1x", b1.resize((384, int(384 * b1.height / b1.width))),
                         a1.resize((384, int(384 * a1.height / a1.width)))))
            # the 1x row's count must be the native one, not the resized one
            n1 = _diff.panel(b1, a1)[1]
            rows[-1] = (f"{part} 1x ({n1} at 1x)", *rows[-1][1:])
            for cx, cy in spots(b2, a2, up / vb[2], a.spots):
                s = a.span
                view = (vb[0] + cx - s / 2, vb[1] + cy - s / 2, s, s)
                w = int(s * a.zoom)
                tag = f"{part}@{cx:.0f},{cy:.0f}"
                bz = raster(sb, td / f"{tag}-bz.png", w, view)
                az = raster(sa, td / f"{tag}-az.png", w, view)
                rows.append((f"{part} {a.zoom}x\nat {cx:.0f},{cy:.0f}", bz, az))
            print(f"{part}: {n1} changed components at 1x", flush=True)
    sheet(a.title, rows, out=a.out)
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
