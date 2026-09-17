#!/usr/bin/env python3
"""Which parts a re-render actually changed, between two trees of SVGs.

    .venv/bin/python scripts/render-tree-diff.py \
        renders/occt out/slot-occt-refresh/renders/occt \
        --out out/refresh-diff.jsonl --workers 6

`render-hash.py` answers the same question by DRAWING a part twice, which
needs both revisions runnable in one process. This one reads two trees that
already exist -- the store from before a refresh round and the round's own
output -- so the comparison costs a rasterize apiece and no engine at all.

Components, not pixels. Antialias fringe scatters into hundreds of one- and
two-pixel specks whenever anything moves at all, so a pixel count calls every
part changed; `MIN_PX` is the floor a component clears to be a real one. A
part with a handful of chunky components is where a drawing decision changed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

#: Pixels a diff component must reach to count as a change, not a fringe.
MIN_PX = 12
WIDTH = 384


def _raster(svg: Path, tmp: Path) -> np.ndarray | None:
    png = tmp / f"{svg.stem}-{abs(hash(str(svg.parent)))}.png"
    subprocess.run(["resvg", "-w", str(WIDTH), str(svg), str(png)],
                   capture_output=True)
    if not png.exists():
        return None
    im = Image.open(png).convert("RGBA")
    flat = Image.new("RGBA", im.size, "white")
    flat.alpha_composite(im)
    a = np.asarray(flat.convert("RGB"), dtype=np.int16)
    png.unlink(missing_ok=True)
    return a


def one(job) -> dict:
    part, before, after = job
    out = {"part": part}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        a, b = _raster(Path(before), tmp), _raster(Path(after), tmp)
    if a is None or b is None:
        return {**out, "state": "raster failed"}
    if a.shape != b.shape:
        return {**out, "state": "size changed", "comps": 999, "px": -1}
    mask = np.abs(a - b).max(axis=2) > 24
    lab, n = ndimage.label(mask)
    sizes = ndimage.sum(mask, lab, range(1, n + 1)) if n else np.array([])
    big = sizes[sizes >= MIN_PX]
    return {**out, "state": "moved" if big.size else "same",
            "comps": int(big.size), "px": int(big.sum()),
            "largest": int(big.max()) if big.size else 0}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--sheet", type=Path,
                    help="draw the biggest movers before and after, here")
    ap.add_argument("--sheet-rows", type=int, default=8)
    a = ap.parse_args(argv)

    before = {p.stem: p for p in a.before.glob("*.svg")}
    after = {p.stem: p for p in a.after.glob("*.svg")}
    parts = sorted(before.keys() & after.keys())
    print(f"{len(parts)} parts in both trees, {a.workers} workers", flush=True)

    jobs = [(p, str(before[p]), str(after[p])) for p in parts]
    rows = []
    with ProcessPoolExecutor(a.workers) as ex:
        for i, r in enumerate(ex.map(one, jobs, chunksize=8), 1):
            rows.append(r)
            if i % 100 == 0 or i == len(jobs):
                moved = sum(1 for x in rows if x.get("state") == "moved")
                print(f"{i:5d}/{len(jobs)}  moved {moved}", flush=True)

    moved = [r for r in rows if r.get("state") == "moved"]
    moved.sort(key=lambda r: -r.get("px", 0))
    print(f"\nmoved {len(moved)}  same "
          f"{sum(1 for r in rows if r.get('state') == 'same')}  "
          f"failed {sum(1 for r in rows if r.get('state') == 'raster failed')}")
    print("\n  biggest movers")
    print(f"  {'part':16s} {'comps':>6s} {'diff px':>9s} {'largest':>9s}")
    for r in moved[:15]:
        print(f"  {r['part']:16s} {r['comps']:6d} {r['px']:9d} "
              f"{r['largest']:9d}")
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        print(f"\nwrote {a.out}")
    if a.sheet:
        draw_sheet(moved[:a.sheet_rows], before, after, a.sheet,
                   a.before.name, a.after.name)
        print(f"wrote {a.sheet}")
    return 0


def draw_sheet(rows, before, after, out: Path, left: str, right: str) -> None:
    """The movers, before beside after. The panels are what varies, so they
    are labelled `before` and `after` and the row carries the part and the
    size of its change -- not the tree paths, which are the same on every
    row and say nothing about which side is new."""
    from PIL import ImageDraw, ImageFont
    panel, pad, label_w, head = 300, 10, 210, 58
    def font(n):
        return ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", n)
    sheet = Image.new("RGB", (label_w + 2 * (panel + pad) + pad,
                              head + len(rows) * (panel + 2 * pad)), "white")
    d = ImageDraw.Draw(sheet)
    d.text((pad, 10), "the occt drawings the refresh changed most",
           fill="black", font=font(21))
    d.text((pad, 36), f"left {left} (stored 2026-09-08) - right {right} "
                      f"(redrawn 2026-09-16, 18 drawing commits later)",
           fill="#555", font=font(12))
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for i, r in enumerate(rows):
            y = head + i * (panel + 2 * pad)
            d.text((pad, y + pad), r["part"], fill="black", font=font(15))
            d.text((pad, y + pad + 22),
                   f"{r['comps']} components, {r['px']:,} px",
                   fill="#444", font=font(12))
            for k, (name, svg) in enumerate(
                    (("before", before[r["part"]]), ("after", after[r["part"]]))):
                arr = _raster(svg, tmp)
                box = Image.new("RGB", (panel, panel), "white")
                if arr is not None:
                    im = Image.fromarray(arr.astype("uint8"))
                    im.thumbnail((panel, panel), Image.LANCZOS)
                    box.paste(im, ((panel - im.width) // 2,
                                   (panel - im.height) // 2))
                x = label_w + k * (panel + pad)
                sheet.paste(box, (x, y + pad))
                d.rectangle([x, y + pad, x + panel, y + pad + panel],
                            outline="#ccc")
                d.text((x + 4, y + pad + panel - 15), name, fill="#333",
                       font=font(12))
            d.line([(0, y), (sheet.width, y)], fill="#ddd")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


if __name__ == "__main__":
    raise SystemExit(main())
