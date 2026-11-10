"""Draw one part in several render slots from this tree, SVG and a large PNG.

    .venv/bin/python scripts/draw-slots.py 24434 naive occt --out out/probe

Writes <out>/<slot>/<part>.svg and .png -- the drawing at HEAD at full size,
for looking at a defect closely rather than through a thumbnail.
"""
import argparse
import subprocess
import time
from pathlib import Path

from brick_icons import cli, db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("part")
    ap.add_argument("slots", nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--width", type=int, default=1200)
    a = ap.parse_args()
    for i, slot in enumerate(a.slots, 1):
        d = a.out / slot
        d.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        args = cli._parse_args(db.canonical_argv(a.part, slot))
        cli.process_one(cli._config_from_args(args), a.part, d)
        subprocess.run(["resvg", "-w", str(a.width), str(d / f"{a.part}.svg"),
                        str(d / f"{a.part}.png")], check=True)
        print(f"[{i}/{len(a.slots)}] {slot} {time.perf_counter() - t0:.1f}s",
              flush=True)


if __name__ == "__main__":
    main()
