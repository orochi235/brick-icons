#!/usr/bin/env python3
"""Rank what the silhouette-truth census found. Reads out/census/*.jsonl.

    .venv/bin/python scripts/census-report.py            # progress + worst 25
    .venv/bin/python scripts/census-report.py --top 60 --engine occt

MISSING is the column that finds bugs: part the render omits, in components
above the reporting floor. EXTRA is mostly antialias and arc-over-chord bulge,
so it is ranked by DISTANCE (99th percentile), never by area.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "out" / "census"


def load(engine: str | None) -> list[dict]:
    rows = []
    for f in sorted(DIR.glob("*.jsonl")):
        eng = f.stem.split("-s")[0]
        if engine and eng != engine:
            continue
        for ln in f.read_text().splitlines():
            if ln.strip():
                rows.append(json.loads(ln))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["naive", "occt"])
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    rows = load(args.engine)
    if not rows:
        print("no results yet")
        return 0
    total = len((DIR / "order.txt").read_text().splitlines())

    for eng in sorted({r["engine"] for r in rows}):
        mine = [r for r in rows if r["engine"] == eng]
        ok = [r for r in mine if "error" not in r]
        errs = Counter(r["error"] for r in mine if "error" in r)
        secs = sum(r.get("secs", 0) for r in mine)
        print(f"{eng}: {len(mine)}/{total} parts ({100*len(mine)/total:.1f}%), "
              f"{len(ok)} rendered, {len(mine)-len(ok)} failed, "
              f"{secs/3600:.1f} cpu-hours, {secs/max(len(mine),1):.0f}s/part")
        for name, n in errs.most_common():
            print(f"    {n:5d}  {name}")

    print(f"\n--- worst MISSING (render omits real geometry), top {args.top}")
    have = [r for r in rows if "error" not in r and r["missing"]]
    have.sort(key=lambda r: -r["missing_px"])
    for r in have[:args.top]:
        big = r["missing"][0]
        print(f"{r['part']:>12} {r['engine']:<6} {r['missing_px']:>7}px "
              f"{len(r['missing'])} comps, largest {big['px']}px "
              f"at x{big['x']} y{big['y']}")

    print(f"\n--- worst EXTRA by distance (ink far outside the part), top {args.top}")
    far = [r for r in rows if "error" not in r and r["extra_dist_px"].get("99")]
    far.sort(key=lambda r: -r["extra_dist_px"]["99"])
    for r in far[:args.top]:
        d = r["extra_dist_px"]
        print(f"{r['part']:>12} {r['engine']:<6} 99th {d['99']:>6}px  max {d['100']:>6}px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
