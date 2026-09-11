#!/usr/bin/env python3
"""Which of a part's surfaces never reach the sewn shape.

    .venv/bin/python scripts/surface-drop-probe.py 4913 14653-f1 79306-f1

`occt_faces` returns [] both for "no exact surface exists here" and "my
tolerance was too tight", and a dropped surface occludes nothing -- so
whatever sits behind it is judged visible and drawn. Same for `tri_face`,
which returns None on a degenerate triangle. This counts both, by primitive
kind, and says how much of the part's projected area the drops cover.
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import config, occt  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    args = ap.parse_args()
    ldraw = config.load_config().ldraw_dir
    for part in args.parts:
        out = occt.flatten_part(part, ldraw)
        prims = out["analytic"]
        drop = collections.Counter()
        keep = collections.Counter()
        for p in prims:
            (drop if not occt.occt_faces(p) else keep)[p.kind] += 1
        bad_tri = sum(1 for t in out["tri"]
                      if occt.tri_face(np.asarray(t, float)) is None)
        print(f"{part}: {len(prims)} prims, {len(out['tri'])} tris")
        for k in sorted(set(drop) | set(keep)):
            mark = "  <-- dropped" if drop[k] else ""
            print(f"    {k:6s} kept {keep[k]:4d}  dropped {drop[k]:4d}{mark}")
        if bad_tri:
            print(f"    tri    dropped {bad_tri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
