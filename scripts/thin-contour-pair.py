#!/usr/bin/env python3
"""A labeled before/after for the sliver-ring drop, from one tree.

    .venv/bin/python scripts/thin-contour-pair.py 5651 3626 --out out/thin-pair.png

`before` is drawn with `geom2d.drop_thin` disarmed in-process, so both panels
come from the same checkout -- this working directory is shared, and a stash
or a checkout to get the old drawing would take it out from under another
session.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import cli, geom2d  # noqa: E402

FONT = "/System/Library/Fonts/Helvetica.ttc"


def render(part: str, out: Path, engine: str) -> Path:
    argv = [part, "--format", "svg", "--shading", "outline",
            "--shade-style", "white", "--angle", "iso", "--engine", engine,
            "--line-width", "2", "--silhouette-width", "2", "--out", str(out)]
    args = cli.build_parser().parse_args(argv)
    cli.process_one(cli._config_from_args(args), part, out)
    return out / f"{part}.svg"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--engine", default="naive")
    ap.add_argument("--width", type=int, default=460)
    ap.add_argument("--out", default="out/thin-pair.png")
    args = ap.parse_args()

    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for i, part in enumerate(args.parts, 1):
            keep = geom2d.drop_thin
            geom2d.drop_thin = lambda g, stroke: g
            try:
                before = render(part, tmp / "before", args.engine)
            finally:
                geom2d.drop_thin = keep
            after = render(part, tmp / "after", args.engine)
            pngs = []
            for tag, svg in (("before", before), ("after", after)):
                png = tmp / f"{part}-{tag}.png"
                subprocess.run(["resvg", "--background", "white", "--width",
                                str(args.width), str(svg), str(png)],
                               check=True)
                lab = tmp / f"{part}-{tag}-l.png"
                subprocess.run(["magick", str(png), "-font", FONT,
                                "-gravity", "north", "-background", "white",
                                "-splice", "0x26", "-pointsize", "20",
                                "-annotate", "+0+3", tag, str(lab)], check=True)
                pngs.append(str(lab))
            row = tmp / f"{part}-row.png"
            subprocess.run(["magick", *pngs, "+append", "-font", FONT,
                            "-gravity", "northwest", "-background", "white",
                            "-splice", "0x26", "-pointsize", "20",
                            "-annotate", "+6+3", f"{part}  ({args.engine})",
                            str(row)], check=True)
            rows.append(str(row))
            print(f"{i}/{len(args.parts)} {part}")

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["magick", *rows, "-append", str(out)], check=True)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
