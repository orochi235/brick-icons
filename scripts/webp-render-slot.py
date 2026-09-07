#!/usr/bin/env python3
"""Re-encode a raster render slot to WebP, in place.

    .venv/bin/python scripts/webp-render-slot.py renders/ldview

LDView writes 2048px PNGs at ~128 KB each, which is the corpus's largest
asset by a wide margin. At q90 the same image is 4.3x smaller and
indistinguishable at 1:1; the slot is read structurally, never pixelwise.
Skips a part that already has a .webp, so it resumes.
"""
from __future__ import annotations
import sys
from pathlib import Path
from PIL import Image

root = Path(sys.argv[1] if len(sys.argv) > 1 else "renders/ldview")
pngs = sorted(root.glob("*.png"))
before = after = 0
for i, p in enumerate(pngs, 1):
    dest = p.with_suffix(".webp")
    if dest.exists():
        p.unlink()
        continue
    with Image.open(p) as im:
        im.save(dest, "WEBP", quality=90, method=4)
    before += p.stat().st_size
    after += dest.stat().st_size
    p.unlink()
    if i % 200 == 0 or i == len(pngs):
        print(f"{i}/{len(pngs)}  {before/1e6:.0f} MB -> {after/1e6:.0f} MB", flush=True)
if before:
    print(f"done: {before/1e6:.0f} MB -> {after/1e6:.0f} MB ({before/after:.1f}x)")
