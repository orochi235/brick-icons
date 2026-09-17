#!/usr/bin/env python3
"""Does moving a part in world space change how it draws?

    .venv/bin/python scripts/probe-position-sensitivity.py --sample 240 \
        --workers 8 --out out/position-sensitivity.jsonl

A drawing should depend on a part's shape and the camera, never on where the
part happens to sit. It does not quite: on 2026-09-16 `2654b` drew one 22 px
patch differently at +4 and +6 LDU and identically again at +8, while `3024`
was byte-stable at every offset. That on-off-on pattern is a comparison
against an absolute tolerance, not arithmetic noise -- noise would drift, and
a sign test would switch once and stay switched.

So this asks two things across a sample:

  how many parts move at all when translated, and by how much
  whether moving correlates with the part straddling y = 0

The second is the hypothesis this was built to test: that a part with half
its geometry in negative space gets different arithmetic. `straddles` records
it per part so the answer is a contingency table rather than an impression.

Each offset is a one-line `.ldr` wrapper placing the part, so the geometry
handed to the engine is identical and only the translation differs.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402

#: Pixels a diff component must reach to be a change, not an antialias fringe.
MIN_PX = 12
WIDTH = 512
#: LDU offsets along Y. 0 is the baseline every other offset is scored against.
OFFSETS = (0, 4, 8)


def _bounds_y(part: str) -> tuple[float, float] | None:
    from brick_icons import hlr, repair
    roots = hlr.default_roots(ROOT / "vendor" / "ldraw")
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    try:
        hlr.flatten(hlr._resolve_input(part, roots), np.eye(3), np.zeros(3),
                    out, roots)
    except Exception:
        return None
    if not out["tri"]:
        return None
    t = np.asarray(repair.repaired_tris(np.array(out["tri"]), out["tri_meta"],
                                        hlr.MESH_CACHE_DIR), float).reshape(-1, 3)
    return float(t[:, 1].min()), float(t[:, 1].max())


def _draw(part: str, dy: int, into: Path) -> np.ndarray | None:
    ldr = into / f"{part}_{dy}.ldr"
    ldr.write_text(f"0 shift {dy}\n1 16 0 {dy} 0 1 0 0 0 1 0 0 0 1 {part}.dat\n")
    argv = list(db._CANONICAL["occt"])
    if "--format" not in argv:
        argv += ["--format", "svg"]
    r = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "brick_icons.cli",
                        str(ldr), *argv, "--out", str(into)],
                       capture_output=True, text=True, cwd=ROOT, timeout=300)
    if r.returncode != 0:
        return None
    svgs = sorted(into.glob(f"{ldr.stem}.*svg"))
    if not svgs:
        return None
    png = svgs[0].with_suffix(".p.png")
    subprocess.run(["resvg", "-w", str(WIDTH), str(svgs[0]), str(png)],
                   capture_output=True)
    if not png.exists():
        return None
    im = Image.open(png).convert("RGBA")
    flat = Image.new("RGBA", im.size, "white")
    flat.alpha_composite(im)
    return np.asarray(flat.convert("RGB"), dtype=np.int16)


def _diff(a, b) -> tuple[int, int] | None:
    if a is None or b is None or a.shape != b.shape:
        return None
    mask = np.abs(a - b).max(axis=2) > 24
    lab, n = ndimage.label(mask)
    sizes = ndimage.sum(mask, lab, range(1, n + 1)) if n else np.array([])
    big = sizes[sizes >= MIN_PX]
    return int(big.size), int(big.sum())


def one(part: str) -> dict:
    row: dict = {"part": part}
    b = _bounds_y(part)
    if b is None:
        return {**row, "state": "no mesh"}
    lo, hi = b
    row["y_lo"], row["y_hi"] = round(lo, 3), round(hi, 3)
    row["straddles"] = bool(lo < 0 < hi)
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            base = _draw(part, OFFSETS[0], tmp)
            if base is None:
                return {**row, "state": "render failed"}
            worst_c = worst_px = 0
            per = {}
            for dy in OFFSETS[1:]:
                d = _diff(base, _draw(part, dy, tmp))
                if d is None:
                    per[dy] = None
                    continue
                per[dy] = d
                worst_c, worst_px = max(worst_c, d[0]), max(worst_px, d[1])
    except subprocess.TimeoutExpired:
        return {**row, "state": "timeout"}
    return {**row, "state": "moved" if worst_c else "stable",
            "comps": worst_c, "px": worst_px,
            "per_offset": {str(k): v for k, v in per.items()}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--sample", type=int, default=240,
                    help="random in-scope parts to draw, when none are named")
    ap.add_argument("--seed", type=int, default=16)
    ap.add_argument("--list", type=Path,
                    help="file of part ids, one per line. A fleet node has no "
                         "corpus.db -- it is local and gitignored -- so a "
                         "sample drawn from the database must be built here "
                         "and shipped, the way batch lists are.")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)

    parts = list(a.parts)
    if not parts and a.list:
        parts = a.list.read_text().split()
    if not parts:
        conn = db.connect()
        pool = [r[0] for r in conn.execute(
            "SELECT id FROM parts WHERE obsolete = 0 ORDER BY id")]
        random.seed(a.seed)
        parts = random.sample(pool, min(a.sample, len(pool)))
    print(f"{len(parts)} parts, offsets {OFFSETS} LDU in Y, "
          f"{a.workers} workers", flush=True)

    rows = []
    with ProcessPoolExecutor(a.workers) as ex:
        for i, r in enumerate(ex.map(one, parts), 1):
            rows.append(r)
            print(f"{i:4d}/{len(parts)} {r['part']:16s} {r['state']:14s} "
                  f"{r.get('comps', '-')}", flush=True)

    ok = [r for r in rows if r["state"] in ("moved", "stable")]
    moved = [r for r in ok if r["state"] == "moved"]
    print(f"\n{len(ok)} drew; {len(moved)} moved, {len(ok) - len(moved)} stable")
    if ok:
        print("\n  does straddling y=0 predict moving?")
        print(f"  {'straddles':>10s} {'moved':>6s} {'stable':>7s}")
        for s in (True, False):
            grp = [r for r in ok if r["straddles"] is s]
            m = sum(1 for r in grp if r["state"] == "moved")
            print(f"  {str(s):>10s} {m:6d} {len(grp) - m:7d}")
    if moved:
        moved.sort(key=lambda r: -r["px"])
        print("\n  biggest movers")
        for r in moved[:12]:
            print(f"    {r['part']:16s} {r['comps']:3d} comps {r['px']:7d} px"
                  f"   straddles={r['straddles']}")
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
