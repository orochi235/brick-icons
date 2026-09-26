#!/usr/bin/env python3
"""Does the working tree draw a part exactly as HEAD (or --ref) does, and how fast?

    .venv/bin/python scripts/head-ab.py --engine naive \
        --swap primitives.visible_subops shade.fill_ops -- 3001 3941 3036

Draws each part twice in one process: once as the working tree has it, once
with each `--swap`ped function replaced by HEAD's (or `--ref`'s) own source
for it, read with `git show`. It compares the filled SVG, rasterized: the PNG
outputs are line art with no fills, so a fill change cannot show in them. A change that is meant to be a pure speedup must come back with 0
changed pixels; anything else is the finding. Nothing is stashed or checked
out, so it is safe in a shared checkout.

Reports one line per part as it goes.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import cli  # noqa: E402


def head_module(name, ref="HEAD"):
    """`ref`'s `brick_icons/<name>.py`, loaded beside the live one."""
    src = subprocess.check_output(
        ["git", "-C", str(ROOT), "show", f"{ref}:brick_icons/{name}.py"], text=True)
    spec = importlib.util.spec_from_loader(f"brick_icons._head_{name}", loader=None)
    m = importlib.util.module_from_spec(spec)
    m.__package__ = "brick_icons"
    sys.modules[spec.name] = m          # dataclasses look their module up here
    exec(compile(src, f"{ref}:brick_icons/{name}.py", "exec"), m.__dict__)
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--engine", default="naive")
    ap.add_argument("--ref", default="HEAD",
                    help="the commit `before` takes its functions from")
    ap.add_argument("--swap", nargs="+", required=True,
                    help="module.function pairs to take from HEAD")
    ap.add_argument("--shade", default="flat3", help="--shade-style for both")
    ap.add_argument("--px", type=int, default=1024, help="raster width")
    ap.add_argument("--out", type=Path, help="keep the renders here")
    ap.add_argument("parts", nargs="+")
    a = ap.parse_args()

    swaps = []
    heads = {}
    for spec in a.swap:
        mod, fn = spec.rsplit(".", 1)
        live = importlib.import_module(f"brick_icons.{mod}")
        head = heads.setdefault(mod, head_module(mod, a.ref))
        swaps.append((live, fn, getattr(live, fn), getattr(head, fn)))

    def arm(use_head):
        for live, fn, now, then in swaps:
            setattr(live, fn, then if use_head else now)

    out = a.out or Path(tempfile.mkdtemp(prefix="head-ab-"))
    for k, p in enumerate(a.parts, 1):
        secs, imgs = {}, {}
        for tag, use_head in (("after", False), ("before", True)):
            arm(use_head)
            t0 = time.time()
            cli.main([p, "--engine", a.engine, "--shading", "outline",
                      "--shade-style", a.shade, "--format", "svg",
                      "--out", str(out / tag)])
            secs[tag] = time.time() - t0
            # the SVG, not the PNG outputs: those are thresholded line art
            # with no fills, so a fill change cannot show in them
            png = out / tag / f"{p}.png"
            subprocess.run(["resvg", "--width", str(a.px), "--background", "white",
                            str(out / tag / f"{p}.svg"), str(png)], check=True)
            imgs[tag] = np.asarray(Image.open(png).convert("RGB"))
        A, B = imgs["after"], imgs["before"]
        diff = int((A != B).any(-1).sum() if A.ndim == 3 else (A != B).sum())
        print(f"{k:3d}/{len(a.parts)} {p:>10}  before {secs['before']:7.1f}s  "
              f"after {secs['after']:7.1f}s  diff px {diff:7d}", flush=True)
    arm(False)
    if a.out is None:
        subprocess.run(["rm", "-rf", str(out)])


if __name__ == "__main__":
    main()
