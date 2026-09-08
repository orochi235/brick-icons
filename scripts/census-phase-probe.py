"""Per-phase timings for a sample of parts spanning run 1's duration range.

Calls the instrumented one() directly, so the phases here are exactly the ones
the census will record from now on.
"""
import json, sys, time, glob, importlib.util, tempfile, argparse
from pathlib import Path

spec = importlib.util.spec_from_file_location("cst", "scripts/compare-silhouette-truth.py")
cst = importlib.util.module_from_spec(spec); spec.loader.exec_module(cst)

ENGINE = "naive"
# Weighted toward the cheap end so the whole x-range is covered without the
# slow tail dominating the wall-clock.
BANDS = [(0, 2, 6), (2, 5, 6), (5, 15, 6), (15, 40, 5), (40, 90, 4), (90, 200, 3), (200, 1e9, 2)]

by_secs = {}
for f in glob.glob(f"out/census-run1/{ENGINE}-*.jsonl"):
    for line in open(f, errors="ignore"):
        line = line.strip()
        if not line: continue
        try: d = json.loads(line)
        except json.JSONDecodeError: continue
        if "error" in d or d.get("secs") is None: continue
        by_secs.setdefault(d["part"], d["secs"])

sample = []
for lo, hi, n in BANDS:
    pool = sorted(p for p, s in by_secs.items() if lo <= s < hi)
    step = max(1, len(pool) // n)
    sample += [(p, by_secs[p]) for p in pool[::step][:n]]
print(f"sampling {len(sample)} parts across {len(BANDS)} duration bands", flush=True)

args = argparse.Namespace(engine=ENGINE, angle="iso", zoom=8, floor=200)
out_path = Path(sys.argv[1])
rows = []
for i, (part, prior) in enumerate(sample, 1):
    t0 = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory() as td:
            r = cst.one(part, args, Path(td))
        ph = r["phase"]
        rows.append({"part": part, "prior_secs": prior,
                     "total": round(time.perf_counter() - t0, 2), **ph})
        print(f"  {i}/{len(sample)} {part}: {rows[-1]['total']:.2f}s  "
              f"render {ph['render']:.2f}  raster {ph['rasterize']:.2f}  "
              f"truth {ph['truth_mask']:.2f}  cmp {ph['compare']:.2f}", flush=True)
    except BaseException as e:
        print(f"  {i}/{len(sample)} {part}: FAILED {type(e).__name__}: {str(e)[:80]}", flush=True)
    out_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
print("wrote", out_path, flush=True)
