#!/usr/bin/env python3
"""Print-area distribution per decal group, to site the sliver threshold.

Emits one row per part: the group areas sorted big-first and normalised to
the largest, so a threshold expressed as a fraction of the dominant print can
be read off the corpus instead of guessed.

    python scripts/measure-decal-slivers.py --out /tmp/slivers.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from brick_icons import hlr, unwrap  # noqa: E402
from brick_icons.config import load_config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "goldens" / "decal-corpus.txt"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(CORPUS))
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    parts = [l.strip() for l in Path(a.corpus).read_text().splitlines()
             if l.strip() and not l.startswith("#")]
    if a.limit:
        parts = parts[:a.limit]
    cfg = load_config(toml_path=str(Path(a.root) / "labels.toml"),
                      overrides={}, root=a.root)

    rows = []
    for i, part in enumerate(parts, 1):
        t0 = time.time()
        try:
            tri, tri_colors, analytic = hlr.part_geometry(part, cfg.ldraw_dir)
            groups = unwrap.decal_groups(tri, tri_colors, analytic)
            areas = [float(sum(r.area for _c, r in g[2])) for g in groups]
        except Exception as e:                      # noqa: BLE001
            print(f"{i}/{len(parts)} {part}  ERROR {type(e).__name__}: {e}",
                  flush=True)
            rows.append({"part": part, "error": type(e).__name__})
            continue
        top = areas[0] if areas else 0.0
        frac = [x / top for x in areas] if top > 0 else []
        rows.append({"part": part, "n": len(areas), "areas": areas,
                     "frac": frac})
        print(f"{i}/{len(parts)} {part}  {len(areas)} groups  "
              f"{time.time()-t0:.1f}s  frac[:6]="
              f"{[round(f, 4) for f in frac[:6]]}", flush=True)

    if a.out:
        Path(a.out).write_text(json.dumps(rows, indent=1))
        print(f"\nwrote {a.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
