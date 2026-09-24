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
import json
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


def _floor_share(im):
    """Fraction of the drawn part that sat on the shading floor tone.

    The floor is the ONE grey every normal facing away from the light collapses
    to, so this is the area the wrap has to act on -- a part with none of it is
    not a terminator-floor defect however bad its shading looks."""
    import numpy as np
    from brick_icons import shade
    floor = shade.Flat3Style().ramp_b(0.0)
    rgb = tuple(int(floor[k:k + 2], 16) for k in (1, 3, 5))
    a = np.asarray(im, int)
    drawn = a.max(axis=2) > 0
    if not drawn.any():
        return 0.0
    return float((np.abs(a - np.array(rgb)).max(axis=2) == 0).sum() / drawn.sum())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--wrap", type=float, action="append",
                    help="repeatable: one row per part per wrap")
    ap.add_argument("--engine", default="occt")
    ap.add_argument("--angle", default="iso")
    ap.add_argument("--zoom", type=int, default=3)
    ap.add_argument("--sheet", type=Path)
    ap.add_argument("--rows", type=Path,
                    help="append one JSON row per part: diff size and "
                         "how much of the wrap-0 drawing sat on the floor tone")
    ap.add_argument("--top", type=int,
                    help="sheet only the N parts with the largest diff")
    args = ap.parse_args()

    argv = ["--engine", args.engine, "--shading", "outline",
            "--shade-style", "flat3", "--angle", args.angle, "--format", "svg"]
    wraps = args.wrap or [0.5]
    jobs = [(p, w) for p in args.parts for w in wraps]
    for out in (args.rows, args.sheet):
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
    rows, stats = [], []
    for i, (part, w) in enumerate(jobs, 1):
        before = draw(part, argv, 0.0, args.zoom)
        after = draw(part, argv, w, args.zoom)
        rows.append((f"{part}\nwrap {w}", before, after))
        mask = _sheet.changed(before, after)
        px = int(mask.sum())
        comps = _sheet.components(mask)
        floor = _floor_share(before)
        stats.append({"part": part, "wrap": w, "components": comps,
                      "pixels": px, "floor_share": round(floor, 4)})
        if args.rows:
            with args.rows.open("a") as fh:
                fh.write(json.dumps(stats[-1]) + "\n")
        print(f"{i}/{len(jobs)} {part:12} {comps:4d} comp {px:8d} px  "
              f"floor {floor:6.2%}", flush=True)
    if args.top:
        order = sorted(range(len(rows)), key=lambda k: -stats[k]["pixels"])
        rows = [rows[k] for k in order[:args.top]]
    if args.sheet:
        _sheet.sheet(f"Lambert terminator wrap -- {args.engine} flat3 {args.angle}",
                     rows, columns=("wrap 0 (HEAD)", "wrapped"), out=args.sheet)
        print(f"wrote {args.sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
