#!/usr/bin/env python3
"""How square a recognized primitive's matrix actually is, across the library.

    .venv/bin/python scripts/measure-ortho-residuals.py --sample 500 \
        --out out/ortho-residuals.json

`occt.frame` drops a primitive whose axis column is not square to its
cross-section, at `ORTHO_TOL`. LDraw writes a placement matrix to three or four
decimals, so a rounded rotation is not orthonormal: 76382's hand sits under
0.985/0.696/0.707, whose Gram off-diagonal is 1.0e-3. Composed down a subpart
chain those residuals accumulate, and every rejection costs the part an exact
surface.

Reports the residual distribution so a tolerance can be chosen against measured
noise rather than guessed: `axis` is max(|u.a|, |v.a|), `shear` is |u.v|, and
`round` is |ru - rv| / max(ru, rv), which `is_round` tests at ROUND_TOL.
Authored skew (11090's 89.2-degree tube wall, 3820's 14-degree ring cap) sits
orders of magnitude above the rounding floor, so the two populations separate.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import occt  # noqa: E402
from brick_icons.config import load_config  # noqa: E402


def part_ids(ldraw_dir: Path) -> list[str]:
    return sorted(p.stem for p in (ldraw_dir / "parts").glob("*.dat"))


def residuals(prim) -> dict | None:
    """(axis, shear, round) residuals for one primitive, or None if degenerate."""
    U, A, V = prim.R[:, 0], prim.R[:, 1], prim.R[:, 2]
    ru, rv, h = (float(np.linalg.norm(x)) for x in (U, V, A))
    if min(ru, rv, h) < 1e-9:
        return None
    uh, vh, ah = U / ru, V / rv, A / h
    return {
        "kind": prim.kind,
        "axis": max(abs(float(uh @ ah)), abs(float(vh @ ah))),
        "shear": abs(float(uh @ vh)),
        "round": abs(ru - rv) / max(ru, rv),
    }


def quantiles(xs: list[float], qs=(0.5, 0.9, 0.99, 0.999, 1.0)) -> dict:
    if not xs:
        return {}
    a = np.sort(np.asarray(xs))
    return {f"p{q * 100:g}": float(np.quantile(a, q)) for q in qs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--list")
    ap.add_argument("--sample", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="out/ortho-residuals.json")
    args = ap.parse_args()

    cfg = load_config(None)
    if args.parts:
        ids = list(args.parts)
    elif args.list:
        ids = [s for ln in Path(args.list).read_text().splitlines()
               if (s := ln.split("#")[0].strip())]
    else:
        ids = part_ids(Path(cfg.ldraw_dir))
        random.Random(args.seed).shuffle(ids)
        ids = ids[:args.sample]

    rows, failed = [], []
    kinds_rejected = Counter()
    t0 = time.time()
    for i, pid in enumerate(ids, 1):
        try:
            prims = occt.flatten_part(pid, cfg.ldraw_dir)["analytic"]
        except Exception as exc:                    # a part we cannot even load
            failed.append({"part": pid, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[{i}/{len(ids)}] {pid} ... load failed", flush=True)
            continue
        n_rej = 0
        for p in prims:
            r = residuals(p)
            if r is None:
                continue
            r["part"] = pid
            r["rejected"] = occt.frame(p) is None
            if r["rejected"]:
                n_rej += 1
                kinds_rejected[p.kind] += 1
            rows.append(r)
        print(f"[{i}/{len(ids)}] {pid} ... {len(prims):4d} prims, "
              f"{n_rej:3d} rejected", flush=True)

    axis = [r["axis"] for r in rows]
    shear = [r["shear"] for r in rows]
    rnd = [r["round"] for r in rows]
    summary = {
        "parts": len(ids),
        "load_failed": len(failed),
        "prims": len(rows),
        "rejected": sum(r["rejected"] for r in rows),
        "rejected_by_kind": dict(kinds_rejected),
        "ortho_tol": occt.ORTHO_TOL,
        "round_tol": occt.ROUND_TOL,
        "axis": quantiles(axis),
        "shear": quantiles(shear),
        "round": quantiles(rnd),
        "secs": round(time.time() - t0, 1),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "rows": rows,
                               "failed": failed}, indent=1))

    print()
    print(f"{summary['prims']} primitives over {summary['parts']} parts; "
          f"{summary['rejected']} rejected by frame() at "
          f"ORTHO_TOL={occt.ORTHO_TOL:g}")
    print(f"rejected by kind: {dict(kinds_rejected)}")
    hdr = f"{'residual':10s}" + "".join(f"{k:>12s}" for k in quantiles(axis))
    print(hdr)
    for name, xs in (("axis", axis), ("shear", shear), ("round", rnd)):
        cells = "".join(f"{v:12.2e}" for v in quantiles(xs).values())
        print(f"{name:10s}{cells}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
