#!/usr/bin/env python3
"""Rank the corpus by how much the two engines disagree ON PAGE.

    scripts/engine-diff-census.py --out out/enginediff/rows.jsonl
    scripts/engine-diff-census.py --parts 9258 4913 --out /tmp/rows.jsonl

Renders each part under both engines at `--shading outline` and composites the
two inks. Reports, per part:

  shared_pct     ink both engines put down, over all ink either put down
  naive_only_pct / occt_only_pct   with the DIRECTION kept, because it says
                 which engine is adding. 9258 is naive_only 0.0 / occt_only
                 49.8 -- naive draws a 2x2 plate with no studs at all and occt
                 is the correct one, so a low score is not evidence against
                 occt.
  chunks_n / chunks_o   disagreement components of at least MIN_CHUNK px

RANK BY CHUNKS, NOT BY SHARED_PCT. Shared ink is area-weighted, so a real
defect on a large part scores better than a cosmetic one on a small part: of
four known open occt defects, three score 87-96% and would sort below
harmless differences. Antialias fringe scatters into many 1-4 px components
and a real defect is a handful of chunky ones, which is what MIN_CHUNK cuts.

Do NOT run this against the `white-*` census slots. Those SVGs are filled --
534 black and 302 white fills on the one sampled -- so solid area swamps the
stroke differences this is looking for.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import batch, cli as _cli  # noqa: E402

RESVG = os.environ.get("RESVG", "resvg")
RENDER_W = 512
MIN_CHUNK = 12          # px; below this a component is antialias fringe
INK = 0.5               # ink threshold on a 0..1 intensity map


def _ink(svg: Path, png: Path) -> np.ndarray:
    subprocess.run([RESVG, "--width", str(RENDER_W), str(svg), str(png)],
                   check=True, capture_output=True)
    im = Image.open(png).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return 1.0 - np.asarray(bg.convert("L"), np.float64) / 255.0


def _chunks(mask: np.ndarray) -> tuple[int, int]:
    """(components of at least MIN_CHUNK px, largest component px)."""
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if not n:
        return 0, 0
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    return int((sizes >= MIN_CHUNK).sum()), int(sizes.max())


def measure(part: str, work: Path) -> dict:
    inks = {}
    for eng in ("naive", "occt"):
        out = work / f"{part}-{eng}"
        out.mkdir(parents=True, exist_ok=True)
        ns = _cli.build_parser().parse_args(
            [part, "--format", "svg", "--shading", "outline",
             "--engine", eng, "--out", str(out)])
        _cli.process_one(_cli._config_from_args(ns), part, out)
        svgs = sorted(out.glob("*.svg"))
        if not svgs:
            return {"part": part, "error": "NoSvg", "detail": eng}
        inks[eng] = _ink(svgs[0], out / "r.png")
    a, b = inks["naive"], inks["occt"]
    if a.shape != b.shape:
        return {"part": part, "error": "SizeMismatch",
                "detail": f"{a.shape} vs {b.shape}"}
    ia, ib = a > INK, b > INK
    both = float((ia & ib).sum())
    only_n, only_o = (ia & ~ib), (~ia & ib)
    tot = both + float(only_n.sum()) + float(only_o.sum()) or 1.0
    cn, bn = _chunks(only_n)
    co, bo = _chunks(only_o)
    return {"part": part,
            "shared_pct": round(100.0 * both / tot, 2),
            "naive_only_pct": round(100.0 * only_n.sum() / tot, 2),
            "occt_only_pct": round(100.0 * only_o.sum() / tot, 2),
            "chunks_n": cn, "chunks_o": co,
            "biggest_n": bn, "biggest_o": bo,
            "chunks": cn + co}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parts", nargs="+",
                    help="part ids; a single comma-joined argument is split, "
                         "which is how one --each line carries a batch")
    ap.add_argument("--db", type=Path, default=ROOT / "corpus.db")
    ap.add_argument("--out", type=Path,
                    help="JSONL log; mutually exclusive with --out-dir")
    ap.add_argument("--out-dir", type=Path,
                    help="write rows-<first part>.jsonl here, so parallel "
                         "workers never append to one file")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--mem-gb", type=float, default=6.0)
    ap.add_argument("--retry-errors", action="store_true")
    ap.add_argument("--shard", type=int, help="0-based shard index")
    ap.add_argument("--of", type=int, help="how many shards in total")
    ap.add_argument("--from-library", action="store_true",
                    help="take the part list from the vendored LDraw tree "
                         "rather than corpus.db -- the library is synced to "
                         "every node and identical, where a node's corpus.db "
                         "may be an older copy and would shard differently")
    ap.add_argument("--resvg", default=None,
                    help="path to resvg; no fleet node carries it on the "
                         "agent PATH, so a job passes it explicitly")
    a = ap.parse_args()
    if a.resvg:
        globals()["RESVG"] = a.resvg
    if not (Path(RESVG).exists() or shutil.which(RESVG)):
        # A missing resvg fails every part in about a second, and the rows it
        # writes look like real render failures rather than a missing tool.
        ap.error(f"resvg not found at {RESVG!r}; pass --resvg")

    parts = [q for p in (a.parts or []) for q in p.split(",") if q]
    if not parts and a.from_library:
        from brick_icons import config as _cfg
        pdir = _cfg.load_config().ldraw_dir / "parts"
        parts = sorted(f.stem for f in pdir.glob("*.dat"))
    if not parts:
        con = sqlite3.connect(a.db)
        parts = [r[0] for r in con.execute(
            "select id from parts order by id")]
    if a.of:
        if a.shard is None or not 0 <= a.shard < a.of:
            ap.error(f"--shard must be 0..{a.of - 1}")
        parts = parts[a.shard::a.of]
    if not (a.out or a.out_dir):
        ap.error("pass --out or --out-dir")
    tag = f"shard{a.shard:04d}" if a.of else f"rows-{parts[0]}"
    out = a.out or (a.out_dir / f"{tag}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    a.out = out
    runner = batch.Runner(a.out, timeout=a.timeout, key="part",
                          isolate=True, mem_gb=a.mem_gb)
    todo = runner.remaining(parts, retry_errors=a.retry_errors)
    print(f"{len(todo)} of {len(parts)} parts to do -> {a.out}", flush=True)
    print(f"onto: plan 0/{len(todo)} engine-diff", flush=True)

    work = Path(tempfile.mkdtemp(prefix="enginediff-"))
    t0, bad = time.time(), 0
    for n, part in enumerate(todo, 1):
        row = runner.run(part, lambda p: measure(p, work))
        bad += bool(row.get("error"))
        print(f"onto: progress {n}/{len(todo)} engine-diff", flush=True)
        print(f"onto: failed {bad}/{len(todo)} engine-diff", flush=True)
        el = time.time() - t0
        rate = el / n
        print(f"  {n}/{len(todo)}  {part:<14} "
              f"shared={row.get('shared_pct', '--')!s:>6} "
              f"chunks={row.get('chunks', '--')!s:>4} "
              f"{row.get('error', ''):<14} "
              f"[{el:6.0f}s, {rate:4.1f}s/part, "
              f"eta {(len(todo) - n) * rate / 3600:5.2f}h]", flush=True)
        if runner.pruned():
            print("pruned by onto; stopping", flush=True)
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
