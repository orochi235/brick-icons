#!/usr/bin/env python3
"""What dropping sliver rings from the stroked contour changes, and what it
leaves alone.

    .venv/bin/python scripts/thin-contour-drift.py --parts 5651 3023 003605b
    .venv/bin/python scripts/thin-contour-drift.py --n 60 --out out/thin-drift.jsonl

Draws each part twice in one process -- once with `geom2d.drop_thin` disarmed,
the way the contour was built before -- and counts the ink each pass puts down.
A part whose contour holds no sliver must come back pixel for pixel; a part
that loses more than a few hundred pixels is drawing a real shape thinner than
its own stroke and is the thing to look at.

Thin parts are the risk this measures: a sticker or a bar whose whole
silhouette is a few px across would vanish, not merely lose a tick.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import cli, geom2d  # noqa: E402

# Thin, curved and ordinary in turn: the slivers live on curved flanks, and
# the parts that could be lost whole are the flat ones.
DEFAULT_PARTS = ["5651", "5849", "79756", "24434", "5065", "5841", "5846",
                 "3941", "4740", "3626", "3023", "3069b", "4162", "3957",
                 "003605b", "6177970zc01", "98138pt1", "3068bp69"]


def render(part: str, out: Path, engine: str) -> Path | None:
    argv = [part, "--format", "svg", "--shading", "outline",
            "--shade-style", "white", "--angle", "iso", "--engine", engine,
            "--line-width", "2", "--silhouette-width", "2", "--out", str(out)]
    args = cli.build_parser().parse_args(argv)
    try:
        cli.process_one(cli._config_from_args(args), part, out)
    except Exception as exc:                       # a part that cannot draw
        print(f"    {part}: {type(exc).__name__}: {exc}")
        return None
    svg = out / f"{part}.svg"
    return svg if svg.exists() else None


def ink(svg: Path, width: int = 600) -> int:
    png = svg.with_suffix(".png")
    subprocess.run(["resvg", "--background", "white", "--width", str(width),
                    str(svg), str(png)], check=True)
    from PIL import Image
    return int((np.asarray(Image.open(png).convert("L")) < 128).sum())


def sample(n: int, db_path: str) -> list[str]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM parts WHERE obsolete = 0 ORDER BY id")]
    random.shuffle(ids)
    return ids[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", nargs="*", default=None)
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--engine", default="naive")
    ap.add_argument("--db", default="corpus.db")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    parts = args.parts or (sample(args.n, args.db) if args.n
                           else DEFAULT_PARTS)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for i, part in enumerate(parts, 1):
            before_fn = geom2d.drop_thin
            geom2d.drop_thin = lambda g, stroke: g
            try:
                before = render(part, tmp / "before", args.engine)
            finally:
                geom2d.drop_thin = before_fn
            after = render(part, tmp / "after", args.engine)
            if before is None or after is None:
                continue
            b, a = ink(before), ink(after)
            rows.append({"part": part, "before": b, "after": a, "delta": a - b})
            flag = "" if abs(a - b) < 300 else "   <-- look"
            print(f"{i}/{len(parts)} {part:<12} {b:>7} -> {a:>7} ink "
                  f"({a - b:+6d}){flag}")

    moved = [r for r in rows if r["delta"]]
    print(f"\n{len(moved)} of {len(rows)} parts moved; "
          f"largest loss {min((r['delta'] for r in rows), default=0)}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
