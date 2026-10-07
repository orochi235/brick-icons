"""Render parts in a slot to SVG, twice -- `before` with process.JUNCTION_CAPS
set False in-process (the switch a junction-cap fix carries; without it the
two sides match), `after` as the tree stands -- into OUT/{before,after}.
Run on the fleet; scripts/stud-junction-sheet.py zooms and crops them here.

    .venv/bin/python scripts/stud-junction-svgs.py --out out/junction 3024 3001
"""
import argparse
import sys
import time
from pathlib import Path

# a named onto tree links the main copy's .venv, whose install points there
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brick_icons import cli, db, process


def render(part, slot, out_dir, before):
    saved = getattr(process, "JUNCTION_CAPS", None)
    if before and saved is not None:
        process.JUNCTION_CAPS = False
    try:
        args = cli._parse_args(db.canonical_argv(part, slot))
        cli.process_one(cli._config_from_args(args), part, out_dir)
    finally:
        if saved is not None:
            process.JUNCTION_CAPS = saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--slot", default="occt")
    ap.add_argument("--out", default="out/junction")
    a = ap.parse_args()
    print("brick_icons from", Path(cli.__file__).parent, flush=True)
    out = Path(a.out)
    for i, part in enumerate(a.parts, 1):
        for side in ("before", "after"):
            t0 = time.perf_counter()
            render(part, a.slot, out / side, side == "before")
            print(f"{i}/{len(a.parts)} {part} {side} "
                  f"{time.perf_counter() - t0:5.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
