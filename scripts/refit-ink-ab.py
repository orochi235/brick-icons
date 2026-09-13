#!/usr/bin/env python3
"""What does a separator refit change in the DRAWING, part by part?

    .venv/bin/python scripts/refit-ink-ab.py --list parts.txt --sheet out/refit-ab.png

Each part is drawn twice in one process -- once at HEAD and once with pass 2
disarmed by dropping `SEP_REFIT_MAX_GROWTH` to 0, which makes every refit fail
its own sweep gate. Never stash or check out to get the second render: this
working directory is shared.

The silhouette oracle cannot answer this. It draws strokeless so its fills
carry the silhouette, and a refit's spurious ring is an INTERIOR STROKE -- it
contributes no silhouette at all, and both passes measure identically. So this
compares the stroked drawings and counts diff components, which is the
measure a stroke-sized change shows up in.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import cli, hlr  # noqa: E402

FONT = "/System/Library/Fonts/Helvetica.ttc"


def draw(part: str, cfg_argv: list[str], zoom: int) -> np.ndarray:
    tmp = Path(tempfile.mkdtemp())
    cfg = cli._config_from_args(cli.build_parser().parse_args(cfg_argv + ["--out", str(tmp)]))
    cli.process_one(cfg, part, tmp)
    subprocess.run(["resvg", "--zoom", str(zoom), str(tmp / f"{part}.svg"),
                    str(tmp / f"{part}.png")], check=True, capture_output=True)
    return np.array(Image.open(tmp / f"{part}.png").convert("L"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--list", type=Path)
    ap.add_argument("--engine", default="naive")
    ap.add_argument("--zoom", type=int, default=2)
    ap.add_argument("--sheet", type=Path)
    ap.add_argument("--out", type=Path, help="append one JSON row per part")
    args = ap.parse_args()

    parts = list(args.parts)
    if args.list:
        parts += [ln.split()[0] for ln in args.list.read_text().split("\n") if ln.strip()]

    armed_cap = hlr.SEP_REFIT_MAX_GROWTH
    panels, rows = [], []
    for n, part in enumerate(parts, 1):
        argv = [part, "--format", "svg", "--shading", "outline",
                "--shade-style", "flat3", "--angle", "iso", "--engine", args.engine]
        imgs = {}
        try:
            for label, cap in (("armed", armed_cap), ("disarmed", 0.0)):
                hlr.SEP_REFIT_MAX_GROWTH = cap
                imgs[label] = draw(part, argv, args.zoom)
        except BaseException as exc:
            print(f"{n}/{len(parts)} {part:<14} ERROR {type(exc).__name__}", flush=True)
            continue
        finally:
            hlr.SEP_REFIT_MAX_GROWTH = armed_cap
        a, d = imgs["armed"], imgs["disarmed"]
        if a.shape != d.shape:
            print(f"{n}/{len(parts)} {part:<14} shape differs {a.shape} vs {d.shape}", flush=True)
            continue
        diff = np.abs(a.astype(int) - d.astype(int)) > 40
        comps = ndimage.label(diff)[1]
        rows.append((part, int(diff.sum()), comps))
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("a") as fh:
                fh.write(json.dumps({"part": part, "diff_px": int(diff.sum()),
                                     "comps": int(comps),
                                     "shape": list(a.shape)}) + "\n")
        print(f"{n}/{len(parts)} {part:<14} diff {int(diff.sum()):7d} px  "
              f"{comps:3d} components", flush=True)
        if comps and args.sheet:
            panels.append((part, comps, a, d, diff))

    print(f"\n{sum(1 for _p, px, c in rows if c)} of {len(rows)} parts change when pass 2 is disarmed")
    if args.sheet and panels:
        cell = max(max(p[2].shape) for p in panels)
        f = ImageFont.truetype(FONT, 20)
        tiles = []
        for part, comps, a, d, diff in panels:
            t = Image.new("RGB", (cell * 2 + 8, cell + 34), "white")
            for k, img in enumerate((d, a)):        # disarmed LEFT, armed RIGHT
                rgb = np.dstack([img] * 3).astype(np.uint8)
                if k == 1:
                    rgb[diff] = (216, 27, 27)
                t.paste(Image.fromarray(rgb), (k * (cell + 8), 34))
            dr = ImageDraw.Draw(t)
            dr.text((2, 6), f"{part}  disarmed", fill="black", font=f)
            dr.text((cell + 10, 6), f"armed  ({comps} comp)", fill="#b00", font=f)
            tiles.append(t)
        cols = min(4, len(tiles))
        rowsn = (len(tiles) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (tiles[0].width + 10) + 10,
                                  rowsn * (tiles[0].height + 10) + 56), "white")
        ImageDraw.Draw(sheet).text(
            (10, 14), "separator refit A/B: what pass 2 adds (red = changed pixels)",
            fill="black", font=ImageFont.truetype(FONT, 30))
        for i, t in enumerate(tiles):
            sheet.paste(t, (10 + (i % cols) * (t.width + 10),
                            56 + (i // cols) * (t.height + 10)))
        args.sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(args.sheet)
        print(f"sheet -> {args.sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
