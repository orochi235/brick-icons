"""Before/after sheet for shade._donated_cut, both sides from THIS tree.

    .venv/bin/python scripts/donated-cut-before-after.py --out out/donated-cut 4070 32062

A part is `<id>` or `<id>:<slot>` (default occt). `before` moves a donated
spur exactly as cut (`_donated_cut` disarmed in-process); `after` is the code
as it stands. Each row is labeled with the part's worst run of sub-quarter-
pixel fill segments and its fill L-command count, before -> after, and
report.json holds those with the diff's changed components.
"""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

import brick_icons  # noqa: E402

assert Path(brick_icons.__file__).resolve().is_relative_to(ROOT), brick_icons.__file__

from PIL import Image  # noqa: E402

import _sheet  # noqa: E402
from brick_icons import cli, db, shade  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "sampled_fill_runs", ROOT / "scripts" / "sampled-fill-runs.py")
sfr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sfr)

WIDTH = 540


def render_svg(part, slot, out_dir, variant):
    real = shade._donated_cut
    if variant == "before":
        shade._donated_cut = lambda p, W: p
    try:
        args = cli._parse_args(db.canonical_argv(part, slot))
        cli.process_one(cli._config_from_args(args), part, out_dir)
    finally:
        shade._donated_cut = real
    return (out_dir / f"{part}.svg").read_text()


def fill_lines(svg):
    n = 0
    for m in re.finditer(r"<path\b([^>]*)>", svg):
        attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', m.group(1)))
        if attrs.get("fill") not in (None, "none", "#000000"):
            n += attrs.get("d", "").count("L")
    return n


def raster(svg, width=WIDTH):
    with tempfile.TemporaryDirectory() as td:
        s, p = Path(td) / "c.svg", Path(td) / "c.png"
        s.write_text(svg)
        subprocess.run(["resvg", "--width", str(width), "--background", "white",
                        str(s), str(p)], check=True, capture_output=True)
        return Image.open(p).convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", default="out/donated-cut")
    ap.add_argument("--title", default="donated spur cut: moved as cut (before) "
                                       "vs simplified (after)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows, report = [], []
    with tempfile.TemporaryDirectory() as td:
        for n, spec in enumerate(args.parts, 1):
            part, _, slot = spec.partition(":")
            slot = slot or "occt"
            svgs, stats = {}, {}
            for v in ("before", "after"):
                d = Path(td) / f"{part}-{slot}-{v}"
                svgs[v] = render_svg(part, slot, d, v)
                worst = max((r for *_, r, _ in sfr.runs(svgs[v], floor=0)),
                            default=0)
                stats[v] = {"worst_run": worst, "fill_L": fill_lines(svgs[v])}
            b, a = raster(svgs["before"]), raster(svgs["after"])
            _, comps, px = _sheet.diff_panel(b, a)
            label = (f"{part}\n{slot}\nrun {stats['before']['worst_run']}"
                     f" -> {stats['after']['worst_run']}\nfill L "
                     f"{stats['before']['fill_L']} -> {stats['after']['fill_L']}")
            rows.append((label, b, a))
            row = {"part": part, "slot": slot, "components": comps,
                   "pixels": int(px), "svg_changed": svgs["before"] != svgs["after"],
                   **{f"{k}_{v}": s[k] for v, s in stats.items() for k in s}}
            report.append(row)
            print(f"{n}/{len(args.parts)} {label.replace(chr(10), '  ')}  components {comps:3d}  "
                  f"pixels {int(px):5d}", flush=True)
    _sheet.sheet(args.title, rows, out=out / "sheet.png")
    (out / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(out / "sheet.png")


if __name__ == "__main__":
    main()
