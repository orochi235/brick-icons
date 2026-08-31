"""Compare two renders by connected component.

A small pixel diff is not agreement. Antialias fringe scatters into hundreds of
tiny components and a real defect is a handful of chunky ones, so the component
count and the component sizes are the answer; `pixels` is a footnote.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def _label(mask: np.ndarray) -> list[int]:
    """Sizes of 4-connected True regions, by iterative flood fill."""
    h, w = mask.shape
    seen = np.zeros((h, w), bool)
    sizes = []
    for sy, sx in zip(*np.nonzero(mask)):
        if seen[sy, sx]:
            continue
        stack, size = [(sy, sx)], 0
        seen[sy, sx] = True
        while stack:
            y, x = stack.pop()
            size += 1
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        sizes.append(size)
    return sizes


def compare(a: Image.Image, b: Image.Image, threshold: int = 16,
            min_size: int = 1, max_listed: int = 32,
            out_png: Path | str | None = None) -> dict:
    """Component count and sizes for the pixels where `a` and `b` differ."""
    ga = np.asarray(a.convert("L"), np.int16)
    gb = np.asarray(b.convert("L"), np.int16)
    if ga.shape != gb.shape:
        raise ValueError(f"size mismatch: {ga.shape} vs {gb.shape}")
    mask = np.abs(ga - gb) > threshold
    sizes = sorted((s for s in _label(mask) if s >= min_size), reverse=True)
    if out_png is not None:
        vis = np.where(mask, 0, 255).astype(np.uint8)
        Image.fromarray(vis, "L").save(out_png)
    return {"components": len(sizes), "sizes": sizes[:max_listed],
            "pixels": int(mask.sum())}
