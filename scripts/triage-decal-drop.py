#!/usr/bin/env python
"""Which gate drops a printed part that has decoration and still draws no decal.

`triage-decal-empties.py` asks whether the .dat holds decoration at all. For
the parts where it does, this asks what happened to it: nothing bound to a
carrier, the print shattered across facet planes, or it survived as more
groups than `MAX_DECALS` allows.

    scripts/triage-decal-drop.py --sample 200 --out out/decal-drop.csv
"""
from __future__ import annotations

import argparse
import csv
import random
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brick_icons import unwrap
from brick_icons.hlr import part_geometry


def gate(part: str, ldraw: str) -> tuple[str, int, int]:
    tri, colors, analytic = part_geometry(part, ldraw)
    if not tri:
        return "no geometry", 0, 0
    groups = unwrap.decal_groups(tri, colors, analytic)
    kept = unwrap.significant_groups(groups)
    if kept:
        panels = unwrap.decal_panels(tri, colors, analytic)
        return ("drew" if panels else "regions collapsed"), len(groups), len(kept)
    if not groups:
        return "nothing bound to a carrier", 0, 0
    areas = [unwrap._print_area(g) for g in groups]
    total, top = sum(areas), max(areas)
    if total <= 0:
        return "bound, zero area", len(groups), 0
    if top / total < unwrap.SHATTER_SHARE:
        return "shattered across facets", len(groups), 0
    return "more groups than the cap", len(groups), sum(
        1 for a in areas if a >= top * unwrap.SLIVER_FRAC)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="corpus.db")
    ap.add_argument("--ldraw", default="vendor/ldraw")
    ap.add_argument("--triage", default="out/decal-triage.csv")
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="out/decal-drop.csv")
    args = ap.parse_args(argv)

    triage = {r["part_id"]: r["class"]
              for r in csv.DictReader(open(args.triage))}
    have_color = [p for p, k in triage.items() if "color" in k]
    random.Random(args.seed).shuffle(have_color)
    picks = have_color[:args.sample] if args.sample else have_color

    conn = sqlite3.connect(args.db)
    cats = dict(conn.execute("SELECT id, category FROM parts"))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tally: dict[str, int] = {}
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["part_id", "category", "triage", "gate", "groups",
                    "kept", "secs"])
        for i, pid in enumerate(picks, 1):
            t0 = time.time()
            try:
                why, n, k = gate(pid, args.ldraw)
            except Exception as exc:
                why, n, k = f"error: {type(exc).__name__}", 0, 0
            secs = time.time() - t0
            tally[why] = tally.get(why, 0) + 1
            w.writerow([pid, cats.get(pid), triage[pid], why, n, k,
                        f"{secs:.2f}"])
            fh.flush()
            print(f"{i}/{len(picks)}  {pid:16s} {why} "
                  f"({n} groups, {secs:.1f}s)", flush=True)

    print(f"\n{len(picks)} parts -> {out}")
    for why, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {n:6d}  {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
