#!/usr/bin/env python3
"""Re-derive the occt backfill's cost from run 1 timings, and say how the
population's duration mix compares with the 120-part speedup sample's."""
import json, glob, sys
from pathlib import Path

REPO = Path.home() / "src/brick-icons"

secs = {}
files = sorted(glob.glob(str(REPO / "out/census-run1/occt-*.jsonl")))
for i, f in enumerate(files, 1):
    n = 0
    for line in Path(f).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("error") or "secs" not in row:
            continue
        secs[row["part"]] = row["secs"]
        n += 1
    print(f"{i}/{len(files)} {Path(f).name}: {n} measured rows", flush=True)

print(f"\nrun 1 occt: {len(secs)} parts with a measured duration\n", flush=True)

BANDS = [(0,10),(10,30),(30,60),(60,120),(120,10**9)]
def describe(name, parts):
    have = [secs[p] for p in parts if p in secs]
    miss = len(parts) - len(have)
    tot = sum(have)
    print(f"{name}: {len(parts)} parts, {len(have)} with a run-1 time, {miss} without")
    print(f"  pre-fix total {tot/3600:.1f} core-hours (mean {tot/max(len(have),1):.1f}s)")
    for lo, hi in BANDS:
        n = sum(1 for s in have if lo <= s < hi)
        share = 100*n/max(len(have),1)
        band_t = sum(s for s in have if lo <= s < hi)
        label = f"{lo}-{hi}s" if hi < 10**9 else f"{lo}s+"
        print(f"    {label:>10}  {n:5d} parts ({share:4.1f}%)  {band_t/3600:5.2f} ch")
    print(flush=True)
    return tot, have

def load(p):
    return [l.strip() for l in Path(REPO/p).read_text().splitlines() if l.strip()]

bf_tot, bf = describe("occt backfill (4733)", load("out/census/occt-backfill.txt"))
dg_tot, dg = describe("occt degenerate (985)", load("out/census/occt-degenerate.txt"))
sm_tot, sm = describe("speedup sample (120)", load("docs/census-timings/occt-diff-sample120.txt"))
all_tot, allp = describe("every measured occt part", list(secs))

print("=== corrected estimates ===")
print(f"the 120-part sample measured 3.24x on a mix averaging {sm_tot/max(len(sm),1):.1f}s/part")
for name, tot, have in (("backfill", bf_tot, bf), ("degenerate", dg_tot, dg)):
    print(f"{name}: {tot/3600:.1f} ch pre-fix -> {tot/3600/3.24:.1f} ch at 3.24x, "
          f"{tot/3600/2.12:.1f} ch at 2.12x; mean {tot/max(len(have),1):.1f}s/part")
