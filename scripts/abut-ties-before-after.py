"""One sheet: parts drawn with and without shade.ABUT_TIES_ONLY, both from
THIS tree.

    .venv/bin/python scripts/abut-ties-before-after.py --out out/abut.png \
        15068dy6 30225bp1:white-occt

A part is `<id>` or `<id>:<slot>`; the slot defaults to occt. `before`
disarms the rule in-process, so a pair of faces with no exact overlap can
again take a depth order from a plane read past its own edge. Prints each
part's changed-component count. Rasterized by resvg.
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image

from brick_icons import cli, db, shade
from brick_icons.caption import Shot
from _sheet import diff_panel, sheet

W = 420


def render(part, slot, out_dir, before):
    saved = shade.ABUT_TIES_ONLY
    shade.ABUT_TIES_ONLY = not before
    try:
        args = cli._parse_args(db.canonical_argv(part, slot))
        t0 = time.perf_counter()
        cli.process_one(cli._config_from_args(args), part, out_dir)
        secs = time.perf_counter() - t0
    finally:
        shade.ABUT_TIES_ONLY = saved
    svg = out_dir / f"{part}.svg"
    png = out_dir / f"{part}.png"
    subprocess.run(["resvg", "-w", str(W), str(svg), str(png)], check=True)
    return Shot.of(Image.open(png).convert("RGB"), part, svg, secs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title",
                    default="pairs with no exact overlap may only tie "
                            "(shade.ABUT_TIES_ONLY)")
    a = ap.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for k, spec in enumerate(a.parts, 1):
            part, _, slot = spec.partition(":")
            slot = slot or "occt"
            shots = []
            for side in ("before", "after"):
                d = Path(tmp) / side / slot
                d.mkdir(parents=True, exist_ok=True)
                shots.append(render(part, slot, d, side == "before"))
            _, n, px = diff_panel(shots[0].image, shots[1].image)
            print(f"{k}/{len(a.parts)}  {part:>12} {slot:<12} {n:3d} comp {px:6d} px",
                  flush=True)
            rows.append((f"{part}\n{slot}", *shots))
    sheet(a.title, rows, out=a.out)
    print(a.out)


main()
