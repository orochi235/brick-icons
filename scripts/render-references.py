"""Compare our outline render against LDView in LDraw's own colors.

The specimen byte-diff gate proves the renderer is stable, not that it is
right. LDView reads the same .dat files and honors each polygon's colour code,
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
    """LDView's own render, with every polygon in its authored LDraw colour."""
    # part_color would become -DefaultColor3 and repaint colour 16, which is
    # the one thing a reference must not do.
    ref_cfg = dataclasses.replace(cfg, part_color=None)
    argv = render.build_argv(ref_cfg, render.resolve_part(cfg, part), out_png)
    subprocess.run(argv, check=True, capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--list", default="specimens.txt")
    ap.add_argument("--out", default="out/references")
    ap.add_argument("--px", type=int, default=620)
    args = ap.parse_args()

    ids = args.parts or read_list(Path(args.list))
    out = Path(args.out)
    (out / "ldview").mkdir(parents=True, exist_ok=True)
    cfg = load_config()

    subprocess.run([".venv/bin/python", "-m", "brick_icons.cli", *ids,
                    "--format", "svg", "--shading", "outline",
                    "--shade-style", "flat3", "--part-label",
                    "--out", str(out / "ours")], check=True)

    for n, pid in enumerate(ids, 1):
        ref, svg = out / "ldview" / f"{pid}.png", out / "ours" / f"{pid}.svg"
        print(f"[{n}/{len(ids)}] {pid} ... ", end="", flush=True)
        try:
            ldview_reference(cfg, pid, ref)
            ours = out / "ours" / f"{pid}.png"
            subprocess.run(["resvg", "--background", "white", "--width",
                            str(args.px * 2), str(svg), str(ours)], check=True)
            geom = [f"{args.px}x{args.px}", f"{args.px + 20}x{args.px + 20}"]
            subprocess.run(["magick", str(ref), str(ours), "-background",
                            "white", "-gravity", "center", "-resize", geom[0],
                            "-extent", geom[1], "-append",
                            str(out / f"{pid}-compare.png")], check=True)
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
