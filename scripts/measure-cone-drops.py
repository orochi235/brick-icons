#!/usr/bin/env python3
"""Which cones never reach the sewn shape, and why.

    scripts/measure-cone-drops.py                 # every part with a cone
    scripts/measure-cone-drops.py --parts 35485 72024

`occt_faces` returns [] for a cone by exactly two routes: `frame` rejects a
skew axis (only `cyli` gets the oblique retry -- see occt_faces), or the cone
is elliptical and falls past the branch that has no `con` case. A dropped
surface occludes nothing, so whatever sits behind it is judged visible.

Do NOT size this work off `skew-deg` in part_features. That is a per-part MAX
over all round primitives, and the axis column is unread for rings, discs and
edges -- an author may leave it anywhere -- so the top of that ranking is junk
axis columns `frame` already absorbs through PLANAR_KINDS, not oblique cones.
It saturates too: 24 parts tie at exactly 90 and a long plateau ties at
80.208. Ask `frame` directly, which is what this does.
"""
from __future__ import annotations

import argparse
import collections
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import config, hlr, occt  # noqa: E402


def drop_reason(prim) -> str | None:
    """Why `occt_faces` yields nothing for this cone, or None if it builds."""
    if occt.occt_faces(prim):
        return None
    f = occt.frame(prim)
    if f is None:
        return "skew" if occt.frame(prim, skew_axis=True) is not None else "degenerate"
    return "elliptical" if not occt.is_round(f[4], f[5]) else "build_threw"


def cones_of(part: str, roots) -> list:
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(hlr._resolve_input(part, roots), np.eye(3), np.zeros(3), out, roots)
    return [p for p in out["analytic"] if p.kind == "con"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parts", nargs="+", help="parts to scan (default: every "
                                               "part the corpus flags `cone`)")
    ap.add_argument("--db", type=Path, default=ROOT / "corpus.db")
    ap.add_argument("--top", type=int, default=12, help="worst parts to list")
    a = ap.parse_args()

    parts = a.parts
    if not parts:
        con = sqlite3.connect(a.db)
        parts = [r[0] for r in con.execute(
            "select part_id from part_features where feature='cone' "
            "order by part_id")]

    cfg = config.load_config()
    roots = hlr.default_roots(cfg.ldraw_dir)
    tot: collections.Counter[str] = collections.Counter()
    hits: dict[str, collections.Counter[str]] = {}
    seen = t0 = 0
    t0 = time.time()
    for n, part in enumerate(parts, 1):
        try:
            cones = cones_of(part, roots)
        except Exception:
            continue
        seen += len(cones)
        for p in cones:
            why = drop_reason(p)
            if why is None:
                continue
            tot[why] += 1
            hits.setdefault(part, collections.Counter())[why] += 1
        if n % 500 == 0 or n == len(parts):
            print(f"  {n}/{len(parts)}  {time.time() - t0:6.1f}s  {dict(tot)}",
                  flush=True)

    print(f"\nscanned {len(parts)} parts, {seen} cones, "
          f"{time.time() - t0:.1f}s")
    print(f"parts with at least one dropped cone: {len(hits)}")
    for why in ("skew", "elliptical", "build_threw", "degenerate"):
        print(f"  {why:<12} {tot[why]:>6}")
    print(f"\nworst {a.top} parts:")
    for p, d in sorted(hits.items(), key=lambda kv: -sum(kv[1].values()))[:a.top]:
        print(f"  {p:<14} {sum(d.values()):>4}  {dict(d)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
