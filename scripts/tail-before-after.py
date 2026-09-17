"""One sheet: parts drawn before and after the shared stylization tail, both
from THIS tree.

    .venv/bin/python scripts/tail-before-after.py --out out/tail-sheet.png \
        3700 32527 6589:white-naive

A part is `<id>` or `<id>:<slot>`; the slot defaults to white-occt. `before`
disarms the new code in-process, so both panels come from one checkout and
nothing is stashed: for occt the legacy tail (silhouette fit and a
default-tolerance orphan cull, no snap, no refit, no fold protection) and no
fitted-arc fill candidates; for every engine the refit pass without its
pinch guard. Rasterized by resvg.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image

from brick_icons import arcfit, cli, db, hlr, occt
from _sheet import sheet

W = 420


def legacy_tail(res, segs, cull, px):
    segs, sil_ells = arcfit.fit_silhouette_arcs(segs)
    if cull:
        segs = hlr.cull_orphan_runs(segs)
    return res._replace(segs=segs, ellipses=list(res.ellipses) + sil_ells)


def render(part, slot, out_dir, before):
    saved = (hlr._stylize, occt._fit_arc_candidates, hlr.PINCH_ON_F_TOL)
    if before:
        hlr.PINCH_ON_F_TOL = float("inf")
        if slot.endswith("occt"):
            hlr._stylize = legacy_tail
            occt._fit_arc_candidates = lambda *a: []
    try:
        args = cli._parse_args(db.canonical_argv(part, slot))
        cli.process_one(cli._config_from_args(args), part, out_dir)
    finally:
        hlr._stylize, occt._fit_arc_candidates, hlr.PINCH_ON_F_TOL = saved
    svg = out_dir / f"{part}.svg"
    png = out_dir / f"{part}.png"
    subprocess.run(["resvg", "-w", str(W), str(svg), str(png)], check=True)
    return Image.open(png).convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", default="out/tail-sheet.png")
    a = ap.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for i, spec in enumerate(a.parts, 1):
            part, _, slot = spec.partition(":")
            slot = slot or "white-occt"
            b = render(part, slot, Path(td) / f"before-{i}", True)
            n = render(part, slot, Path(td) / f"after-{i}", False)
            rows.append((f"{part}\n{slot}", b, n))
            print(f"[{i}/{len(a.parts)}] {part} {slot}", flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    sheet("stylization tail: before (old occt-only tail, unguarded refit) vs "
          "after (shared tail, pinch guard)", rows, out=a.out)
    print(a.out)


if __name__ == "__main__":
    main()
