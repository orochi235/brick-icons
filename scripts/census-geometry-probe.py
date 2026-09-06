"""Split the geometry phase into its own stages, over a duration-stratified sample.

`census-engine-bench.py` splits a render into geometry (`hlr.visible_segments`)
and everything after. This splits the geometry half: the LDraw load, the mesh
repair, the arc fit, and -- for occt -- shape build, HLR, authored-edge match,
contour polys and face ordering. Each row also carries the part's size (tris,
authored lines, analytic prims, sewn faces) so cost can be regressed on it.

    .venv/bin/python scripts/census-geometry-probe.py out/geom.jsonl --engine occt
"""
from __future__ import annotations

import argparse, json, sqlite3, time
from pathlib import Path

import numpy as np

from brick_icons import hlr, arcfit, repair

BANDS = [(0, 2, 3), (2, 5, 3), (5, 15, 3), (15, 40, 3), (40, 90, 3), (90, 200, 2)]

p = argparse.ArgumentParser()
p.add_argument("out", type=Path)
p.add_argument("--engine", default="occt")
p.add_argument("--db", default="corpus.db")
p.add_argument("--run", type=int, default=None, help="measurements run_id to sample from")
p.add_argument("--bands", default=None, help="lo:hi:n,... overriding the default")
args = p.parse_args()

bands = BANDS
if args.bands:
    bands = [tuple(float(x) if i < 2 else int(x) for i, x in enumerate(b.split(":")))
             for b in args.bands.split(",")]

con = sqlite3.connect(args.db)
run = args.run
if run is None:
    run = con.execute("select run_id from measurements where engine=? and error is null "
                      "group by run_id order by count(*) desc limit 1", (args.engine,)).fetchone()[0]
sample = []
for lo, hi, n in bands:
    rows = con.execute(
        "select part_id, secs from measurements where run_id=? and engine=? and error is null "
        "and secs >= ? and secs < ? order by part_id", (run, args.engine, lo, hi)).fetchall()
    step = max(1, len(rows) // n)
    sample += rows[::step][:int(n)]
print(f"run {run}: {len(sample)} {args.engine} parts across {len(bands)} bands", flush=True)

TIMES: dict[str, float] = {}
COUNTS: dict[str, int] = {}


def timed(mod, name, key):
    orig = getattr(mod, name)

    def wrap(*a, **k):
        t = time.perf_counter()
        try:
            return orig(*a, **k)
        finally:
            TIMES[key] = TIMES.get(key, 0.0) + time.perf_counter() - t
    setattr(mod, name, wrap)


timed(repair, "repaired_tris", "repair")
timed(arcfit, "fit_edge_arcs", "arcfit")
if args.engine == "occt":
    from brick_icons import occt
    for name, key in [("build_shape", "build_shape"), ("hlr_edges", "hlr_edges"),
                      ("authored_loci", "authored_loci"), ("select_authored", "select_authored"),
                      ("face_polys", "face_polys"), ("ordered_faces", "ordered_faces"),
                      ("_boundary_conics", "boundary_conics"), ("analytic_creases", "creases")]:
        timed(occt, name, key)
    _bs = occt.build_shape

    def counting_build(out):
        shape = _bs(out)
        COUNTS["faces"] = occt.count_faces(shape)
        return shape
    occt.build_shape = counting_build
else:
    for name, key in [("_visible_segments_analytic", "engine_analytic"),
                      ("_visible_segments_faceted", "engine_faceted"),
                      ("_snap_rim_crossings", "snap"), ("cull_orphan_runs", "cull"),
                      ("dedupe_segments", "dedupe")]:
        timed(hlr, name, key)

_orig_flat = hlr.flatten


def counting_flatten(path, R, t, out, roots, *a, **k):
    r = _orig_flat(path, R, t, out, roots, *a, **k)
    COUNTS["tri"] = len(out["tri"]); COUNTS["l2"] = len(out["2"])
    COUNTS["l5"] = len(out["5"]); COUNTS["prims"] = len(out["analytic"])
    return r


hlr.flatten = counting_flatten
timed(hlr, "flatten", "load")

LD = Path("vendor/ldraw")
hlr.visible_segments("3024", LD, engine=args.engine)   # warm imports/caches

rows = []
for i, (part, prior) in enumerate(sample, 1):
    TIMES.clear(); COUNTS.clear()
    t0 = time.perf_counter()
    try:
        res = hlr.visible_segments(part, LD, engine=args.engine)
    except BaseException as e:
        print(f"  {i}/{len(sample)} {part}: FAILED {type(e).__name__}: {str(e)[:70]}", flush=True)
        continue
    total = time.perf_counter() - t0
    row = {"engine": args.engine, "part": part, "prior_secs": prior,
           "geometry": round(total, 3), "ops": len(res.segs),
           **{k: int(v) for k, v in COUNTS.items()},
           **{k: round(v, 3) for k, v in sorted(TIMES.items())}}
    row["other"] = round(total - sum(TIMES.values()), 3)
    rows.append(row)
    top = sorted(TIMES.items(), key=lambda kv: -kv[1])[:3]
    print(f"  {i}/{len(sample)} {part}: geom {total:6.2f}s  "
          f"tris {COUNTS.get('tri', 0):>6} faces {COUNTS.get('faces', 0):>6}  "
          + "  ".join(f"{k} {v:.2f}" for k, v in top), flush=True)
    args.out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

tot = sum(r["geometry"] for r in rows)
agg: dict[str, float] = {}
for r in rows:
    for k, v in r.items():
        if k in ("engine", "part") or not isinstance(v, (int, float)):
            continue
        agg[k] = agg.get(k, 0.0) + v
print(f"\ntotal geometry {tot:.1f}s over {len(rows)} parts", flush=True)
for k, v in sorted(agg.items(), key=lambda kv: -kv[1]):
    if k in ("geometry", "prior_secs", "tri", "l2", "l5", "prims", "faces", "ops"):
        continue
    print(f"  {k:>16}: {v:7.1f}s  {v / tot * 100:5.1f}%")
print("wrote", args.out, flush=True)
