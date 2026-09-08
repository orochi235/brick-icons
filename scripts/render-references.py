"""Compare our outline render against LDView in LDraw's own colors.

The specimen byte-diff gate proves the renderer is stable, not that it is
right. LDView reads the same .dat files and honors each polygon's color code,
so it is a free ground truth for what a part is supposed to look like —
especially for printed parts, whose decoration our pipeline currently drops.

Emits, per part, a stacked PNG: LDView on top, ours below.

Usage: .venv/bin/python scripts/render-references.py [--list FILE] [part-id ...]
       (default list: specimens.txt; default out-dir: out/references)
Needs: resvg, imagemagick (see scripts/external-deps.lock)
"""
from __future__ import annotations

import argparse
import dataclasses
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brick_icons import render
from brick_icons.config import load_config


def read_list(path: Path) -> list[str]:
    return [s for ln in path.read_text().splitlines()
            if (s := ln.split("#")[0].strip())]


def ldview_reference(cfg, part: str, out_png: Path) -> None:
    """LDView's own render, with every polygon in its authored LDraw color."""
    # part_color would become -DefaultColor3 and repaint color 16, which is
    # the one thing a reference must not do.
    ref_cfg = dataclasses.replace(cfg, part_color=None)
    argv = render.build_argv(ref_cfg, render.resolve_part(cfg, part), out_png)
    subprocess.run(argv, check=True, capture_output=True)


def magick(*argv) -> str:
    done = subprocess.run(["magick", *map(str, argv)], check=True,
                          capture_output=True, text=True)
    return done.stdout.strip()


def our_half(svg: Path, stem: Path, px: int) -> tuple[Path, Path]:
    """(part raster trimmed to its ink, label raster), from one outline SVG.

    LDView renders with -AutoCrop, so its part fills the frame while ours keeps
    the icon's designed margin -- resizing both to the same box then draws them
    at different scales and the halves cannot be compared by eye. Trimming ours
    to its ink is what puts them on one scale, and the part label has to come
    off first or it is the bounding box. Rendering the SVG a second time
    without its one <text> element is cheaper than a second geometry pass, and
    the difference between the two rasters is the label.
    """
    bare = stem.with_name(f"{stem.name}-nolabel.svg")
    bare.write_text(re.sub(r"<text\b.*?</text>", "", svg.read_text(),
                           flags=re.S))
    labeled, plain = stem.with_suffix(".png"), stem.with_name(f"{stem.name}-nolabel.png")
    for src, dst in ((svg, labeled), (bare, plain)):
        subprocess.run(["resvg", "--background", "white", "--width", str(px * 2),
                        str(src), str(dst)], check=True)

    part = stem.with_name(f"{stem.name}-part.png")
    magick(plain, "-alpha", "off", "-trim", "+repage", part)
    label = stem.with_name(f"{stem.name}-label.png")
    # -alpha off before every trim: resvg writes an alpha channel even over an
    # opaque background, and trim reads the whole frame as transparent and
    # collapses to 1x1 rather than failing.
    where = magick(labeled, plain, "-compose", "difference", "-composite",
                   "-alpha", "off", "-trim", "-format", "%wx%h%X%Y", "info:")
    magick(labeled, "-crop", where, "+repage", label)
    return part, label


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--list", default="specimens.txt")
    ap.add_argument("--out", default="out/references")
    ap.add_argument("--px", type=int, default=620)
    ap.add_argument("--engine", default="occt",
                    choices=("naive", "occt", "cadquery"))
    args = ap.parse_args()

    ids = args.parts or read_list(Path(args.list))
    out = Path(args.out)
    (out / "ldview").mkdir(parents=True, exist_ok=True)
    cfg = load_config()

    subprocess.run([".venv/bin/python", "-m", "brick_icons.cli", *ids,
                    "--format", "svg", "--shading", "outline",
                    "--shade-style", "flat3", "--part-label",
                    "--engine", args.engine,
                    "--out", str(out / "ours")], check=True)

    fit, box = f"{args.px}x{args.px}", f"{args.px + 20}x{args.px + 20}"
    for n, pid in enumerate(ids, 1):
        ref, svg = out / "ldview" / f"{pid}.png", out / "ours" / f"{pid}.svg"
        print(f"[{n}/{len(ids)}] {pid} ... ", end="", flush=True)
        try:
            ldview_reference(cfg, pid, ref)
            part, label = our_half(svg, out / "ours" / pid, args.px)
            ours = out / "ours" / f"{pid}-half.png"
            magick(part, "-background", "white", "-gravity", "center",
                   "-resize", fit, "-extent", box,
                   label, "-gravity", "southwest", "-geometry", "+6+4",
                   "-composite", ours)
            magick(ref, "-background", "white", "-gravity", "center",
                   "-resize", fit, "-extent", box,
                   ours, "-append", out / f"{pid}-compare.png")
            print("ok")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"FAILED ({type(e).__name__})")

    sheets = sorted(out.glob("*-compare.png"))
    if sheets:
        # +append, not `magick montage`: montage renders a filename label even
        # when given an empty one, and dies here with "unable to read font ''".
        subprocess.run(["magick", *map(str, sheets), "-background", "white",
                        "+append", str(out / "references.png")], check=True)
        print(f"sheet: {out / 'references.png'} "
              f"(LDView on top, ours below; part id is in our half)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
