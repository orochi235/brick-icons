"""Where each render phase starts, as a share of the render, from census rows --
the weights `brick_icons.progress.STARTS` holds -- and how far a bar built on
them strays from the clock.

    .venv/bin/python scripts/calibrate-progress.py [--min-secs 5]

Only renders of at least --min-secs count: nobody watches a two-second bar,
and the fast and slow bands spend their time in different places (import is
44% of a sub-5s occt render and 0% of a 30s one).

The score is the mean gap, in points, between a phase-only bar and elapsed
time over each render, sampled at every phase boundary and weighted by the
time spent there. Progress reported inside a phase is not modeled -- it can
only narrow the gap.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics

from brick_icons import progress


def openings(engine: str, p: dict) -> dict[str, float] | None:
    """Seconds into the render at which each milestone opens."""
    g = p.get("render/geometry")
    r = p.get("render")
    if not g or not r:
        return None
    get = lambda k: p.get(f"render/{k}", 0.0)        # noqa: E731
    post = get("geometry/dedupe") + get("geometry/snap") + get("geometry/cull")
    at = {"geometry": 0.0, "studs": g, "fill": g + get("studs")}
    if engine == "occt":
        pre = g - get("geometry/import") - get("geometry/engine") - post
        at["geometry/import"] = pre
        at["geometry/engine"] = pre + get("geometry/import")
        at["geometry/engine/faces"] = at["geometry/engine"] + sum(
            get(f"geometry/engine/{k}") for k in
            ("build_shape", "crescents", "hlr", "loci", "face_polys"))
        at["geometry/dedupe"] = at["geometry/engine"] + get("geometry/engine")
    else:
        at["geometry/engine"] = g - get("geometry/engine") - post
        at["geometry/dedupe"] = g - post
    return at


def score(starts: dict[str, float], at: dict[str, float], r: float) -> float:
    """Time-weighted mean |bar - clock| in points over one render."""
    edges = sorted((t, starts.get(k, 0.0)) for k, t in at.items()) + [(r, 1.0)]
    gap, bar = 0.0, 0.0
    for (t0, f0), (t1, _) in zip(edges, edges[1:]):
        bar = max(bar, f0)
        if t1 <= t0:
            continue
        # clock runs t0/r..t1/r while the bar holds; mean |bar - clock| on it
        a, b = t0 / r, t1 / r
        if bar <= a:
            m = (a + b) / 2 - bar
        elif bar >= b:
            m = bar - (a + b) / 2
        else:
            m = ((bar - a) ** 2 + (b - bar) ** 2) / 2 / (b - a)
        gap += m * (t1 - t0)
    return 100 * gap / r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="corpus.db")
    ap.add_argument("--min-secs", type=float, default=5)
    args = ap.parse_args()
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    for engine in ("occt", "naive"):
        rows = []
        for (ph,) in db.execute(
                "select phases from measurements where engine=? and error is "
                "null and phases is not null and json_extract(phases, "
                "'$.render') >= ?", (engine, args.min_secs)):
            p = json.loads(ph)
            at = openings(engine, p)
            if at:
                rows.append((at, p["render"]))
        if not rows:
            continue
        keys = sorted(rows[0][0], key=lambda k: statistics.mean(
            a[k] / r for a, r in rows))
        fitted = {k: round(statistics.mean(a[k] / r for a, r in rows), 3)
                  for k in keys}
        print(f"{engine}: {len(rows)} renders >= {args.min_secs:g}s")
        for k in keys:
            have = progress.STARTS.get(engine, {}).get(k)
            have = "   -  " if have is None else f"{have:6.3f}"
            print(f"  {k:24s} measured {fitted[k]:6.3f}  in use {have}")
        for name, starts in (("measured", fitted),
                             ("in use", progress.STARTS.get(engine, {}))):
            s = sorted(score(starts, a, r) for a, r in rows)
            print(f"  {name:8s} mean error {statistics.mean(s):5.1f} points  "
                  f"p90 {s[len(s) * 9 // 10]:5.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
