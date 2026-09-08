#!/usr/bin/env python3
"""Render a part with every `_pierce_seams` seam, with none, and with each one
dropped in turn.

    .venv/bin/python scripts/pierce-seam-ab.py 3626bpsk 67811 --out out/pierce-ab

`all` against `none` is the pass's whole effect; `drop-k` against `all` is what
seam k alone is responsible for. Nothing in the tree is edited -- the pass is
replaced in process, the way `scripts/snap-render-ab.py` splices the snap.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import cli, occt  # noqa: E402

_all = occt._pierce_seams
_kept: dict = {}


def render(part: str, out: Path, tag: str, pick, width: int, angle: str) -> Path:
    def patched(shape):
        seams = _all(shape)
        _kept["n"] = len(seams)
        if pick is None:
            return seams
        if pick == "none":
            return []
        return [s for i, s in enumerate(seams) if i != pick]
    argv = [part, "--format", "svg", "--shading", "outline", "--shade-style",
            "flat3", "--angle", angle, "--engine", "occt", "--out", str(out),
            "--width", str(width), "--height", str(width)]
    cfg = cli._config_from_args(cli.build_parser().parse_args(argv))
    occt._pierce_seams = patched
    try:
        cli.process_one(cfg, part, out)
    finally:
        occt._pierce_seams = _all
    dst = out / f"{part}.{tag}.svg"
    (out / f"{part}.svg").replace(dst)
    return dst


def raster(svg: Path, zoom: float) -> np.ndarray:
    png = svg.with_suffix(".png")
    subprocess.run(["resvg", "--zoom", str(zoom), str(svg), str(png)],
                   check=True, capture_output=True)
    return np.asarray(Image.open(png).convert("RGB")).astype(int)


def diff(a: np.ndarray, b: np.ndarray, chunk: int) -> tuple[int, int, int]:
    mask = np.abs(a - b).sum(2) > 24
    lab, n = ndimage.label(mask, np.ones((3, 3)))
    sizes = np.bincount(lab.ravel())[1:] if n else np.zeros(0, int)
    return int(mask.sum()), int((sizes >= chunk).sum()), \
        int(sizes.max()) if n else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", type=Path, default=Path("out/pierce-ab"))
    ap.add_argument("--width", type=int, default=512)
    ap.add_argument("--zoom", type=float, default=2.0)
    ap.add_argument("--angle", default="iso")
    ap.add_argument("--chunk", type=int, default=12)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    for part in args.parts:
        t = time.perf_counter()
        a = raster(render(part, args.out, "all", None, args.width, args.angle),
                   args.zoom)
        n = _kept.get("n", 0)
        b = raster(render(part, args.out, "none", "none", args.width, args.angle),
                   args.zoom)
        px, chunky, big = diff(a, b, args.chunk)
        print(f"{part}: {n} seams; all vs none  {px:6d}px  chunky {chunky:3d}"
              f"  largest {big:6d}  {time.perf_counter() - t:5.1f}s", flush=True)
        for k in range(n):
            c = raster(render(part, args.out, f"drop{k}", k, args.width,
                              args.angle), args.zoom)
            px, chunky, big = diff(a, c, args.chunk)
            print(f"  drop seam {k:2d} vs all  {px:6d}px  chunky {chunky:3d}"
                  f"  largest {big:6d}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
