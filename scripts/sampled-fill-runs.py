"""Find runs of sub-quarter-pixel L segments in a drawing's fills.

The measure of test_occt::test_a_fill_boundary_carries_no_sampled_boundary,
reported per fill path so the run can be located: its fill, its path index,
where it starts, and how long it is.

    .venv/bin/python scripts/sampled-fill-runs.py 4070 --widths 1.4 2
"""
import argparse
import math
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons.cli import build_parser, _config_from_args, process_one  # noqa: E402


def runs(svg: str, floor: int = 4):
    """Yield (path index, fill, run length, start point) for each run > floor."""
    for i, m in enumerate(re.finditer(r"<path\b([^>]*)>", svg)):
        attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', m.group(1)))
        fill = attrs.get("fill")
        if fill in (None, "none", "#000000"):
            continue
        run, cur, start = 0, None, None
        for c in re.finditer(r"([MLAZ])([^MLAZ]*)", attrs.get("d", "")):
            nums = [float(v) for v in re.findall(r"-?\d*\.?\d+", c.group(2))]
            if c.group(1) == "Z" or len(nums) < 2:
                if run > floor:
                    yield i, fill, run, start
                run, cur = 0, None
                continue
            pt = (nums[-2], nums[-1])
            short = (c.group(1) == "L" and cur is not None
                     and math.dist(cur, pt) < 0.25)
            if short:
                if run == 0:
                    start = cur
                run += 1
            else:
                if run > floor:
                    yield i, fill, run, start
                run = 0
            cur = pt
        if run > floor:
            yield i, fill, run, start


def render(part: str, width: float, out: Path, extra=()) -> str:
    args = build_parser().parse_args(
        [part, "--engine", "occt", "--format", "svg", "--shading", "outline",
         "--shade-style", "flat3", "--line-width", str(width),
         "--silhouette-width", str(width), "--out", str(out), *extra])
    process_one(_config_from_args(args), part, out)
    return (out / f"{part}.svg").read_text()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--widths", nargs="+", type=float, default=[1.4])
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        for part in args.parts:
            for w in args.widths:
                svg = render(part, w, Path(tmp) / f"{part}-{w}")
                found = list(runs(svg))
                worst = max((r for _, _, r, _ in found), default=0)
                print(f"{part} @ {w:4.2f} px  worst run {worst:3d}", flush=True)
                for i, fill, r, start in found:
                    x, y = start
                    print(f"    path {i:3d} {fill}  run {r:3d}  from "
                          f"({x:7.2f}, {y:7.2f})", flush=True)


if __name__ == "__main__":
    main()
