#!/usr/bin/env python3
"""Find runs of sub-quarter-pixel L segments in an occt render's fills.

The measure `test_a_fill_boundary_carries_no_sampled_boundary` gates on,
printed per stroke width with where each long run sits and how long its
segments are, so a failing run can be told from ordinary geometry.

    .venv/bin/python scripts/probe-sampled-runs.py 4070 --width 2 --width 1.4
"""
import argparse
import math
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brick_icons.cli import build_parser, _config_from_args, process_one  # noqa: E402


def runs(svg: str, short_px: float):
    """Yield (fill, run length, segment lengths, first point) per run >= 2."""
    for m in re.finditer(r"<path\b([^>]*)>", svg):
        attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', m.group(1)))
        fill = attrs.get("fill")
        if fill in (None, "none", "#000000"):
            continue
        cur, seg, start = None, [], None
        for c in re.finditer(r"([MLAZ])([^MLAZ]*)", attrs.get("d", "")):
            nums = [float(v) for v in re.findall(r"-?\d*\.?\d+", c.group(2))]
            if c.group(1) == "Z" or len(nums) < 2:
                if len(seg) > 1:
                    yield fill, seg, start
                cur, seg = None, []
                continue
            pt = (nums[-2], nums[-1])
            d = math.dist(cur, pt) if cur is not None else None
            if c.group(1) == "L" and d is not None and d < short_px:
                if not seg:
                    start = cur
                seg.append(d)
            else:
                if len(seg) > 1:
                    yield fill, seg, start
                seg = []
            cur = pt
        if len(seg) > 1:
            yield fill, seg, start


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("part")
    ap.add_argument("--width", type=float, action="append", required=True)
    ap.add_argument("--short", type=float, default=0.25)
    args = ap.parse_args()
    for w in args.width:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config_from_args(build_parser().parse_args(
                [args.part, "--engine", "occt", "--format", "svg",
                 "--shading", "outline", "--shade-style", "flat3",
                 "--line-width", str(w), "--silhouette-width", str(w),
                 "--out", tmp]))
            process_one(cfg, args.part, Path(tmp))
            svg = (Path(tmp) / f"{args.part}.svg").read_text()
        found = sorted(runs(svg, args.short), key=lambda r: -len(r[1]))
        worst = len(found[0][1]) if found else 0
        print(f"{args.part} width {w:3.1f}: worst run {worst:3d}, "
              f"{len(found)} runs of 2+", flush=True)
        for fill, seg, start in found[:5]:
            print(f"    {fill} {len(seg):3d} segs from "
                  f"({start[0]:7.2f},{start[1]:7.2f}), "
                  f"len {min(seg):.3f}-{max(seg):.3f} px, "
                  f"total {sum(seg):5.2f} px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
