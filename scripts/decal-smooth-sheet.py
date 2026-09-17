"""Decal panels before and after freeform-ring smoothing, from one tree.

    .venv/bin/python scripts/decal-smooth-sheet.py --out out/decal-smooth.png 6057849d 6057849b

`before` disarms `unwrap._smooth_d` in-process, so both columns come from
the same checkout. Rasterized by resvg.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image

from brick_icons import cli, config, unwrap
from _sheet import sheet

W = 360


def render(part, out_dir, before):
    saved = unwrap._smooth_d
    if before:
        import shapely
        from brick_icons import geom2d
        unwrap._smooth_d = lambda pts, arcs=None: geom2d.path_d(
            shapely.Polygon(pts), arcs=arcs)
    try:
        cfg = config.load_config()
        (svg,) = cli.decal_one(cfg, part, out_dir, 900, "white")
    finally:
        unwrap._smooth_d = saved
    png = out_dir / f"{part}.png"
    subprocess.run(["resvg", "-w", str(W), str(svg), str(png)], check=True)
    return Image.open(png).convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", default="out/decal-smooth.png")
    a = ap.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for i, part in enumerate(a.parts, 1):
            b = render(part, Path(td) / f"b{i}", True)
            n = render(part, Path(td) / f"a{i}", False)
            rows.append((part, b, n))
            print(f"[{i}/{len(a.parts)}] {part}", flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    sheet("decal: freeform rings as chords (before) vs Bezier curves through "
          "the same vertices (after)", rows, out=a.out)
    print(a.out)


if __name__ == "__main__":
    main()
