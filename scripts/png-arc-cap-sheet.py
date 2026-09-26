#!/usr/bin/env python3
"""The PNG outputs with and without the arc stroke cap, one geometry pass each.

    .venv/bin/python scripts/png-arc-cap-sheet.py --out sheet.png 3811 3024

`process.THIN_ARCS` caps an arc's stroke at half its radius so a stud field
reads as studs. This draws each part's gray PNG twice from the same segments
-- cap off, cap on -- with the diff column, which is what shows whether the
cap reached a render path. Reports one line per part.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from brick_icons import hlr, process  # noqa: E402
import _sheet  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--px", type=int, default=1024)
    ap.add_argument("--line-px", type=float, default=2.0)
    ap.add_argument("parts", nargs="+")
    a = ap.parse_args()
    rows = []
    for k, p in enumerate(a.parts, 1):
        res = hlr.visible_segments(p, "vendor/ldraw")
        segs = hlr.fit_segments(res.segs, res.bbox, a.px, a.px, 6, 1.0)
        ims = {}
        for tag, on in (("cap off", False), ("cap on", True)):
            process.THIN_ARCS = on
            ims[tag] = process.draw_segments(segs, a.px, a.px, line_px=a.line_px,
                                             sil_px=a.line_px).convert("RGB")
        process.THIN_ARCS = True
        _d, comps, px = _sheet.diff_panel(ims["cap off"], ims["cap on"])
        print(f"{k:3d}/{len(a.parts)} {p:>8}  {comps} comp {px} px", flush=True)
        rows.append((p, ims["cap off"], ims["cap on"]))
    _sheet.sheet("PNG output: arc stroke cap off vs on", rows,
                 columns=("cap off", "cap on"), out=a.out)


if __name__ == "__main__":
    main()
