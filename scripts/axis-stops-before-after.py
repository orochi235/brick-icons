"""One sheet: parts drawn with linear-gradient stops at mid-bin (before) and
at their samples' mean offset (after), both from THIS tree.

    .venv/bin/python scripts/axis-stops-before-after.py --out out/axis.png \
        3649 4070 3062b:occt

A part is `<id>` or `<id>:<slot>`; with no slot it is drawn in the
outline-flat3 golden combo under occt. `before` moves each binned stop back
to its bin's center in-process. Prints each part's changed-component count.
Rasterized by resvg at --px.
"""
import argparse
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image  # noqa: E402

from brick_icons import cli, db, shade  # noqa: E402
from brick_icons.caption import Shot  # noqa: E402
from _sheet import diff_panel, sheet  # noqa: E402

GOLDEN = tomllib.loads((ROOT / "tests/goldens/manifest.toml").read_text())


def mid_bin(fn, nbins=8):
    def wrapped(samples, style, nbins=nbins):
        stops = fn(samples, style, nbins)
        if len(stops) < 3:
            return stops
        inner = [((min(int(o * nbins), nbins - 1) + 0.5) / nbins, c)
                 for o, c in stops[1:-1]]
        return [stops[0], *inner, stops[-1]]
    return wrapped


def argv(part, slot):
    if slot:
        return db.canonical_argv(part, slot)
    return [part, "--engine", "occt",
            *GOLDEN["combo"]["outline-flat3"]["args"]]


def render(part, slot, out_dir, before, px):
    saved = shade._axis_binned_stops
    if before:
        shade._axis_binned_stops = mid_bin(saved)
    try:
        args = cli._parse_args(argv(part, slot))
        t0 = time.perf_counter()
        cli.process_one(cli._config_from_args(args), part, out_dir)
        secs = time.perf_counter() - t0
    finally:
        shade._axis_binned_stops = saved
    svg = out_dir / f"{part}.svg"
    png = out_dir / f"{part}.png"
    subprocess.run(["resvg", "-w", str(px), str(svg), str(png)], check=True)
    im = Image.open(png).convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    bg.alpha_composite(im)
    return Shot.of(bg.convert("RGB"), part, svg, secs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--px", type=int, default=512)
    ap.add_argument("--keep", type=Path, help="keep the renders here")
    ap.add_argument("--title", default="linear-gradient stops: mid-bin (before) "
                                       "vs at their samples (after)")
    a = ap.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = a.keep or tmp
        for k, spec in enumerate(a.parts, 1):
            part, _, slot = spec.partition(":")
            shots = []
            for side in ("before", "after"):
                d = Path(tmp) / side / (slot or "golden")
                d.mkdir(parents=True, exist_ok=True)
                shots.append(render(part, slot, d, side == "before", a.px))
            _, n, px = diff_panel(shots[0].image, shots[1].image)
            print(f"{k}/{len(a.parts)}  {part:>12} {slot or 'golden':<12} "
                  f"{n:3d} comp {px:6d} px", flush=True)
            rows.append((f"{part}\n{slot or 'outline-flat3 occt'}", *shots))
    sheet(a.title, rows, out=a.out)
    print(a.out)


main()
