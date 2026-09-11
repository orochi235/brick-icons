#!/usr/bin/env python3
"""Draw which parts a render batch reached, on a map that does not move.

    .venv/bin/python scripts/batch-map.py --runs 44,45,46,14 --out out/batch-map.png

One panel per run, one ink each, plus a grey panel of how many of them reached
each place. Nothing is mixed: two runs are compared by looking at the same
place in two panels, which is the whole point of a map that holds still.

A cell is a bin of `--per` parts, lit by the fraction of them the run drew, so
a half-covered stretch is a half-lit one.

The map is blocks keyed by the thousand-block of the part id, in prefix order.
A part's place has to survive the library growing, and plain id order does not
-- a new `3068bp42` sorts beside `3068b` and shifts every cell after it. Blocks
alone are not enough either: sorted inside the block, capacity recomputed, 250
new parts still move 86.6% of cells. What holds is freezing each block's base
and appending newcomers to the end of their own block. **This script recomputes
the bases every run**, which is right for one picture and wrong for comparing
one drawn today against one drawn next month; the frozen-base file is designed
and not built.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from collections import defaultdict

from PIL import Image, ImageDraw, ImageFilter, ImageFont

GROUND = (14, 15, 18)
# The wall's own slot hues, so a panel here and a column there agree.
INKS = [(57, 135, 229), (217, 89, 38), (201, 133, 0), (25, 158, 112),
        (213, 81, 129)]
DEPTH_INK = (225, 228, 235)
LEADING_NUMBER = re.compile(r"^(\d+)")


def block_of(part_id: str) -> str:
    """The thousand-block a part's id falls in; non-numeric ids get their own."""
    m = LEADING_NUMBER.match(part_id)
    return m.group(1).zfill(7)[:4] if m else "zz" + part_id[:1]


def place(part_ids, headroom: float, grain: int) -> tuple[dict[str, int], int]:
    members = defaultdict(list)
    for pid in part_ids:
        members[block_of(pid)].append(pid)
    pos, base = {}, 0
    for key in sorted(members):
        for i, pid in enumerate(members[key]):
            pos[pid] = base + i
        base += max(grain, -(-int(len(members[key]) * headroom) // grain) * grain)
    return pos, base


def font(size: int):
    for path in ("/System/Library/Fonts/SFNSMono.ttf",
                 "/System/Library/Fonts/Menlo.ttc"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="batch-map")
    ap.add_argument("--db", default="corpus.db")
    ap.add_argument("--runs", required=True,
                    help="comma-separated run ids, in the order to draw them")
    ap.add_argument("--out", required=True)
    ap.add_argument("--per", type=int, default=6, help="parts per cell")
    ap.add_argument("--cols", type=int, default=150)
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--blur", type=float, default=0.4)
    ap.add_argument("--headroom", type=float, default=1.5)
    ap.add_argument("--grain", type=int, default=32)
    args = ap.parse_args(argv)

    conn = sqlite3.connect(args.db)
    ids = [r[0] for r in conn.execute("SELECT id FROM parts ORDER BY id")]
    pos, span = place(ids, args.headroom, args.grain)
    nbins = -(-span // args.per)
    rows = -(-nbins // args.cols)

    # How many real parts each bin holds, so a fraction has a denominator.
    have = [0] * nbins
    for cell in pos.values():
        have[cell // args.per] += 1

    runs = []
    for rid in [int(r) for r in args.runs.split(",")]:
        hit = [r[0] for r in conn.execute(
            "SELECT DISTINCT part_id FROM measurements WHERE run_id = ?", (rid,))]
        slot = conn.execute("SELECT source FROM measurements WHERE run_id = ? "
                            "AND source IS NOT NULL LIMIT 1", (rid,)).fetchone()
        drew = [0] * nbins
        for pid in hit:
            if pid in pos:
                drew[pos[pid] // args.per] += 1
        runs.append({
            "id": rid, "slot": slot[0] if slot else f"run {rid}",
            "n": sum(1 for pid in hit if pid in pos),
            "frac": [d / h if h else 0.0 for d, h in zip(drew, have)],
        })
        print(f"{len(runs)}/{len(args.runs.split(','))}  run {rid}  "
              f"{runs[-1]['slot']}  {runs[-1]['n']:,} parts", flush=True)

    def panel(frac, ink):
        im = Image.new("RGB", (args.cols, rows), GROUND)
        px = im.load()
        for b, v in enumerate(frac):
            if v <= 0:
                continue
            px[b % args.cols, b // args.cols] = tuple(
                min(255, round(g + i * v)) for g, i in zip(GROUND, ink))
        im = im.filter(ImageFilter.GaussianBlur(args.blur))
        return im.resize((im.width * args.scale, im.height * args.scale),
                         Image.LANCZOS)

    tiles = [(r["slot"], f"run {r['id']} - {r['n']:,} parts",
              panel(r["frac"], INKS[i % len(INKS)]), INKS[i % len(INKS)])
             for i, r in enumerate(runs)]
    depth = [sum(r["frac"][b] for r in runs) / len(runs) for b in range(nbins)]
    tiles.append((f"all {len(runs)}, how many reached it",
                  f"0 to {len(runs)} deep", panel(depth, DEPTH_INK), DEPTH_INK))

    pad, cap, gap = 26, 44, 22
    pw, ph = tiles[0][2].size
    sheet = Image.new("RGB",
                      (pad * 2 + pw * 2 + gap,
                       pad + 44 + -(-len(tiles) // 2) * (cap + ph + gap) + pad),
                      GROUND)
    d = ImageDraw.Draw(sheet)
    d.text((pad, pad), f"{args.per} parts to a cell, lit by the fraction the run "
                       f"drew - the map is the same every panel",
           font=font(16), fill=(238, 239, 243))
    y = pad + 44
    for n, (name, sub, tile, ink) in enumerate(tiles):
        if n and n % 2 == 0:
            y += cap + ph + gap
        x = pad + (n % 2) * (pw + gap)
        d.text((x, y), name, font=font(13), fill=ink)
        d.text((x, y + 17), sub, font=font(11), fill=(150, 152, 160))
        sheet.paste(tile, (x, y + cap))
    sheet.save(args.out)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
