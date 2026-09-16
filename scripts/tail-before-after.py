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

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

from brick_icons import arcfit, cli, db, hlr, occt

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


def components(a, b, min_px=12):
    d = np.abs(np.asarray(a, int) - np.asarray(b, int)).max(axis=2) > 64
    lab, n = ndimage.label(d)
    if not n:
        return 0
    sizes = ndimage.sum(d, lab, range(1, n + 1))
    return int((sizes >= min_px).sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", default="out/tail-sheet.png")
    a = ap.parse_args()
    font = ImageFont.load_default(size=16)
    small = ImageFont.load_default(size=13)
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for i, spec in enumerate(a.parts, 1):
            part, _, slot = spec.partition(":")
            slot = slot or "white-occt"
            b = render(part, slot, Path(td) / f"before-{i}", True)
            n = render(part, slot, Path(td) / f"after-{i}", False)
            rows.append((f"{part}\n{slot}", b, n, components(b, n)))
            print(f"[{i}/{len(a.parts)}] {part} {slot}: {rows[-1][3]} changed "
                  "components", flush=True)
    h = max(im.height for _p, im, _n, _c in rows)
    gutter, top, left = 12, 56, 120
    sheet = Image.new("RGB", (left + 2 * W + 3 * gutter, top + len(rows) * (h + gutter)),
                      "white")
    d = ImageDraw.Draw(sheet)
    d.text((gutter, 8), "stylization tail: before (old occt-only tail, unguarded "
           "refit) vs after (shared tail, pinch guard)", fill="black", font=font)
    for k, label in enumerate(("before", "after")):
        d.text((left + gutter + k * (W + gutter), 32), label, fill="black", font=font)
    for r, (part, b, n, c) in enumerate(rows):
        y = top + r * (h + gutter)
        d.text((gutter, y + 4), part, fill="black", font=font)
        d.text((gutter, y + 46), f"{c} comp", fill="gray", font=small)
        sheet.paste(b, (left + gutter, y))
        sheet.paste(n, (left + 2 * gutter + W, y))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(a.out)
    print(a.out)


if __name__ == "__main__":
    main()
