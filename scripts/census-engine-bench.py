"""Render-phase cost for one engine, split into geometry and everything after.

`census-phase-probe.py` splits a census row into render / rasterize / truth_mask
/ compare and finds render is ~96% of it. This splits that render further: the
hidden-line call (`hlr.visible_segments`, which each engine implements) against
the shading, fill and SVG emit that follow it and are shared by all of them.

Run it at two revisions to attribute an engine change; `--rev` is stamped on
every row so the files stay comparable.
"""
import argparse, glob, json, subprocess, tempfile, time
from pathlib import Path

from brick_icons import cli, hlr

# Weighted toward the cheap end so the whole range is covered without the slow
# tail dominating the wall-clock.
BANDS = [(0, 5, 3), (5, 15, 3), (15, 40, 3), (40, 90, 3), (90, 200, 2)]

p = argparse.ArgumentParser()
p.add_argument("out", type=Path)
p.add_argument("--engine", default="occt")
p.add_argument("--angle", default="iso")
p.add_argument("--archive", default="out/census-run1", help="JSONLs to sample from")
p.add_argument("--rev", default=None, help="defaults to HEAD's short sha")
args = p.parse_args()
rev = args.rev or subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True).stdout.strip()

by_secs = {}
for f in glob.glob(f"{args.archive}/{args.engine}-*.jsonl"):
    for line in open(f, errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "error" in d or d.get("secs") is None:
            continue
        by_secs.setdefault(d["part"], d["secs"])

sample = []
for lo, hi, n in BANDS:
    pool = sorted(q for q, s in by_secs.items() if lo <= s < hi)
    step = max(1, len(pool) // n)
    sample += [(q, by_secs[q]) for q in pool[::step][:n]]
print(f"{rev}: {len(sample)} parts across {len(BANDS)} duration bands", flush=True)

geom = [0.0]
_orig = hlr.visible_segments


def _timed(*a, **k):
    t = time.perf_counter()
    try:
        return _orig(*a, **k)
    finally:
        geom[0] += time.perf_counter() - t


hlr.visible_segments = cli.hlr.visible_segments = _timed


def render(part):
    """The census's own mode -- see compare-silhouette-truth.py's one()."""
    with tempfile.TemporaryDirectory() as td:
        argv = [part, "--format", "svg", "--shading", "outline",
                "--shade-style", "flat3", "--angle", args.angle,
                "--engine", args.engine, "--line-width", "0",
                "--silhouette-width", "0", "--out", td]
        cfg = cli._config_from_args(cli.build_parser().parse_args(argv))
        geom[0] = 0.0
        t = time.perf_counter()
        cli.process_one(cfg, part, Path(td))
        return time.perf_counter() - t, geom[0]


render("3024")            # warm the OCP import out of the first row
rows = []
for i, (part, prior) in enumerate(sample, 1):
    try:
        total, g = render(part)
    except BaseException as e:
        print(f"  {i}/{len(sample)} {part}: FAILED {type(e).__name__}: {str(e)[:80]}",
              flush=True)
        continue
    rows.append({"rev": rev, "engine": args.engine, "part": part,
                 "prior_secs": prior, "render": round(total, 2),
                 "geometry": round(g, 2), "rest": round(total - g, 2)})
    print(f"  {i}/{len(sample)} {part}: {total:.2f}s  "
          f"geometry {g:.2f}  rest {total - g:.2f}  ({g / total * 100:.0f}% geom)",
          flush=True)
    args.out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
tot = sum(r["render"] for r in rows)
gtot = sum(r["geometry"] for r in rows)
print(f"total {tot:.2f}s  geometry {gtot:.2f}s ({gtot / tot * 100:.0f}%)", flush=True)
print("wrote", args.out, flush=True)
