#!/usr/bin/env python3
"""What does wrapping the Lambert terminator change in the DRAWING?

    .venv/bin/python scripts/lambert-wrap-ab.py 19121 35480 --wrap 0.5 \
        --sheet out/lambert-wrap-0.5.png

Each part is drawn twice in one process -- once at HEAD (`shade.LAMBERT_WRAP`
0, the textbook max(0, n.L)) and once with the wrap dialled up. Never stash or
check out to get the second render: this working directory is shared.

The change is a lighting-model change, so it moves every shaded render in the
corpus, not only the bores it is aimed at. Pass control parts with no recess
(3001, 4740) alongside the bore parts to see what it costs them.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import cli, shade  # noqa: E402
import _sheet  # noqa: E402


def draw(part: str, argv: list[str], wrap: float, zoom: int) -> Image.Image:
    tmp = Path(tempfile.mkdtemp())
    try:
        cfg = cli._config_from_args(
            cli.build_parser().parse_args(argv + ["--out", str(tmp)]))
        old, shade.LAMBERT_WRAP = shade.LAMBERT_WRAP, wrap
        try:
            cli.process_one(cfg, part, tmp)
        finally:
            shade.LAMBERT_WRAP = old
        subprocess.run(["resvg", "--zoom", str(zoom), str(tmp / f"{part}.svg"),
                        str(tmp / f"{part}.png")], check=True, capture_output=True)
        return Image.open(tmp / f"{part}.png").convert("RGB")
    finally:
        for f in tmp.iterdir():
            f.unlink()
        tmp.rmdir()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--wrap", type=float, action="append",
                    help="repeatable: one row per part per wrap")
    ap.add_argument("--engine", default="occt")
    ap.add_argument("--angle", default="iso")
    ap.add_argument("--zoom", type=int, default=3)
    ap.add_argument("--sheet", type=Path, required=True)
    args = ap.parse_args()

    argv = ["--engine", args.engine, "--shading", "outline",
            "--shade-style", "flat3", "--angle", args.angle, "--format", "svg"]
    wraps = args.wrap or [0.5]
    jobs = [(p, w) for p in args.parts for w in wraps]
    rows = []
    for i, (part, w) in enumerate(jobs, 1):
        before = draw(part, argv, 0.0, args.zoom)
        after = draw(part, argv, w, args.zoom)
        rows.append((f"{part}\nwrap {w}", before, after))
        print(f"{i}/{len(jobs)} {part} wrap {w}", flush=True)
    _sheet.sheet(f"Lambert terminator wrap -- {args.engine} flat3 {args.angle}",
                 rows, columns=("wrap 0 (HEAD)", "wrapped"), out=args.sheet)
    print(f"wrote {args.sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
