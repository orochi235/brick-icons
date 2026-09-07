#!/usr/bin/env python3
"""Hash every part's rendered pixels, so two revisions can be diffed.

    .venv/bin/python scripts/render-hash.py --list out/census/parts.txt \
        --out out/abhash/control.jsonl

One line per part: the sha256 of the rasterized RGB, the ink pixel count, and
the render time. Run it at two revisions and diff the shas to get exactly the
parts whose drawing moved.

This exists because the census cannot answer that question. It scores
`alpha > 128` against the part's own polygons, so a change to which color
wins *inside* the silhouette -- paint order, fill merging, gradients -- leaves
every census number identical. The alpha channel is the wrong instrument for a
paint-order change; RGB is the right one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
from brick_icons.batch import Runner  # noqa: E402


def one(part: str, args, tmp: Path) -> dict:
    argv = [part, "--format", "svg", "--shading", "outline",
            "--shade-style", args.shade_style, "--angle", args.angle,
            "--engine", args.engine, "--render-px", str(args.render_px),
            "--out", str(tmp)]
    cfg = cli._config_from_args(cli.build_parser().parse_args(argv))
    t0 = time.perf_counter()
    cli.process_one(cfg, part, tmp)
    secs = round(time.perf_counter() - t0, 2)

    svg, png = tmp / f"{part}.svg", tmp / f"{part}.png"
    subprocess.run(["resvg", "--zoom", str(args.zoom), str(svg), str(png)],
                   check=True, capture_output=True)
    rgba = np.array(Image.open(png).convert("RGBA"))
    # RGB under the alpha mask: transparent pixels carry undefined color, and
    # hashing them makes two identical drawings disagree.
    ink = rgba[:, :, 3] > 128
    rgb = rgba[:, :, :3].copy()
    rgb[~ink] = 0
    return {"part": part, "sha": hashlib.sha256(rgb.tobytes()).hexdigest(),
            "ink_px": int(ink.sum()), "secs": secs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", help="file with one part per line")
    ap.add_argument("--parts", help="comma-separated ids, for onto --each")
    ap.add_argument("--out", help="jsonl to append to")
    ap.add_argument("--out-dir", help="write <first part>.jsonl here instead")
    ap.add_argument("--engine", default="occt")
    ap.add_argument("--angle", default="iso")
    ap.add_argument("--shade-style", default="flat3")
    ap.add_argument("--render-px", type=int, default=512)
    ap.add_argument("--zoom", type=float, default=1.0)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--isolate", action="store_true",
                    help="render in a forked child, so --timeout can stop it")
    ap.add_argument("--mem-gb", dest="mem_gb", type=float, default=8)
    args = ap.parse_args()

    if args.parts:
        parts = [p.strip() for p in args.parts.split(",") if p.strip()]
    elif args.list:
        parts = [s for ln in Path(args.list).read_text().splitlines()
                 if (s := ln.split("#")[0].strip())]
    else:
        print("need --list or --parts", file=sys.stderr)
        return 2
    if args.out_dir:
        # Named for the batch's first part, the way census-batch.sh does it: a
        # retry that starts elsewhere must not append to another batch's file.
        out = Path(args.out_dir) / f"{parts[0]}.jsonl"
    elif args.out:
        out = Path(args.out)
    else:
        print("need --out or --out-dir", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)

    runner = Runner(out, timeout=args.timeout, key="part",
                    isolate=args.isolate, mem_gb=args.mem_gb)
    before = len(parts)
    parts = runner.remaining(parts)
    print(f"resuming: {before - len(parts)} done, {len(parts)} left", flush=True)
    print(f"onto: plan {before - len(parts)}/{before}", flush=True)

    n = len(parts)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for i, part in enumerate(parts, 1):
            def work(pid, tmp=tmp):
                return one(pid, args, tmp)
            r = runner.run(part, work)
            if "error" in r:
                print(f"{i}/{n} {part} FAILED {r['error']} [{r.get('secs')}s]",
                      flush=True)
            else:
                print(f"{i}/{n} {part} {r['sha'][:12]} {r['ink_px']}px "
                      f"[{r['secs']}s]", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
