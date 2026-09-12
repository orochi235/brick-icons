#!/usr/bin/env python
"""Lay a slot's line art over the LDView reference for the same part.

The drawing is multiplied onto the reference, so a stroke the part has no
edge for sits on flat shading and a missing contour shows as a shading
boundary with nothing on it. Both are the questions a defect entry asks, and
neither is answerable from the line art alone.

Both images are trimmed to their own ink and stretched to one box: the two
renderers fit the part to the canvas differently, and an untrimmed overlay is
off by the difference in margin.

Usage: overlay-reference.py 5841 5843 --slot white-occt --out out/overlays
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FONT = "/System/Library/Fonts/Helvetica.ttc"

SLOT_ARGS = {
    "white-occt": ["--engine", "occt", "--shade-style", "white"],
    "white-naive": ["--engine", "naive", "--shade-style", "white"],
    "occt": ["--engine", "occt", "--shade-style", "flat3"],
    "naive": ["--engine", "naive", "--shade-style", "flat3"],
}


def run(*cmd) -> None:
    subprocess.run([str(c) for c in cmd], check=True,
                   stdout=subprocess.DEVNULL)


def render(part: str, slot: str, out: Path) -> Path:
    svg = out / f"{part}.svg"
    if not svg.exists():
        run(sys.executable, "-m", "brick_icons.cli", part,
            "--format", "svg", "--shading", "outline", "--angle", "iso",
            "--line-width", "2", "--silhouette-width", "2",
            *SLOT_ARGS[slot], "--out", out)
    return svg


def overlay(part: str, svg: Path, reference: Path, out: Path,
            width: int) -> Path:
    art = out / f"{part}-art.png"
    run("resvg", "--width", width * 2, svg, art)
    ref_t = out / f"{part}-ref.png"
    art_t = out / f"{part}-art-t.png"
    run("magick", reference, "-trim", "+repage", ref_t)
    run("magick", art, "-fuzz", "5%", "-trim", "+repage", art_t)
    size = subprocess.run(["magick", "identify", "-format", "%wx%h", art_t],
                          capture_output=True, text=True, check=True).stdout
    dst = out / f"{part}-overlay.png"
    run("magick", ref_t, "-resize", f"{size}!", art_t,
        "-compose", "multiply", "-composite", "-resize", f"{width}x", dst)
    return dst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--slot", default="white-occt", choices=sorted(SLOT_ARGS))
    ap.add_argument("--out", default="out/overlays")
    ap.add_argument("--reference-dir", default="renders/reference")
    ap.add_argument("--width", type=int, default=440)
    ap.add_argument("--sheet", default=None, help="montage every overlay here")
    args = ap.parse_args()

    out = Path(args.out) / args.slot
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for i, part in enumerate(args.parts, 1):
        ref = Path(args.reference_dir) / f"{part}.webp"
        if not ref.exists():
            print(f"{i}/{len(args.parts)} {part}: no reference render")
            continue
        svg = render(part, args.slot, out)
        dst = overlay(part, svg, ref, out, args.width)
        label = out / f"{part}-labeled.png"
        run("magick", dst, "-font", FONT,
            "-gravity", "north", "-background", "white", "-splice", "0x26",
            "-pointsize", "20", "-fill", "black", "-annotate", "+0+3",
            f"{part}  {args.slot} over reference", label)
        made.append(label)
        print(f"{i}/{len(args.parts)} {part} -> {dst}")

    if args.sheet and made:
        run("montage", *made, "-font", FONT, "-tile", "2x",
            "-geometry", "+6+6", "-background", "white", args.sheet)
        print(f"sheet -> {args.sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
