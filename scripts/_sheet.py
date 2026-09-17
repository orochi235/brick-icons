"""Shared drawing for before/after sheets: the diff panel and the grid.

A sheet is a title, a labeled column per panel and one row per part. The
third column is always the diff -- `after` faded toward white with every
changed pixel painted DIFF_COLOR and the changed-component count under the
row label -- because two panels that look alike hide a one-stroke change
and two that differ leave the reader hunting for where.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

DIFF_COLOR = (214, 0, 147)
DIFF_THRESHOLD = 64      # max channel delta that counts as a changed pixel
MIN_PX = 12              # component size below which a change is AA fringe
FADE = 0.75              # how far `after` fades toward white under the paint


def changed(a, b):
    """Boolean mask of pixels that differ between two same-size RGB images."""
    A, B = np.asarray(a, int), np.asarray(b, int)
    if A.shape != B.shape:
        h, w = min(A.shape[0], B.shape[0]), min(A.shape[1], B.shape[1])
        A, B = A[:h, :w], B[:h, :w]
    return np.abs(A - B).max(axis=2) > DIFF_THRESHOLD


def components(mask, min_px=MIN_PX):
    """Changed components at least `min_px` pixels: the real changes."""
    lab, n = ndimage.label(mask)
    if not n:
        return 0
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    return int((sizes >= min_px).sum())


def diff_panel(before, after):
    """(image, components, pixels): `after` faded, changed pixels painted.

    Both counts, because they fail differently: an outline that moves by a
    sagitta is thousands of pixels in slivers too thin to make one component
    (6057849d's smoothing counted 0 components), and antialias fringe is
    hundreds of pixels that make no component at all.
    """
    mask = changed(before, after)
    A = np.asarray(after.convert("RGB"), float)[:mask.shape[0], :mask.shape[1]]
    faded = A * (1 - FADE) + 255 * FADE
    faded[mask] = DIFF_COLOR
    return (Image.fromarray(faded.astype(np.uint8), "RGB"), components(mask),
            int(mask.sum()))


def sheet(title, rows, columns=("before", "after"), out=None):
    """rows: [(label, before, after)] -> the sheet image (saved to `out`)."""
    font = ImageFont.load_default(size=16)
    small = ImageFont.load_default(size=13)
    panels = []
    for label, b, a in rows:
        d, n, px = diff_panel(b, a)
        panels.append((label, (n, px), [b, a, d]))
    W = max(im.width for _l, _n, ims in panels for im in ims)
    gutter, top, left = 12, 56, 130
    heights = [max(im.height for im in ims) for _l, _n, ims in panels]
    img = Image.new("RGB", (left + 3 * W + 4 * gutter,
                            top + sum(heights) + gutter * len(rows)), "white")
    dr = ImageDraw.Draw(img)
    dr.text((gutter, 8), title, fill="black", font=font)
    for k, name in enumerate((*columns, "diff")):
        dr.text((left + gutter + k * (W + gutter), 32), name, fill="black", font=font)
    y = top
    for (label, n, ims), h in zip(panels, heights):
        dr.text((gutter, y + 4), label, fill="black", font=font)
        comps, px = n
        dr.text((gutter, y + 4 + 22 * (label.count("\n") + 1)),
                f"{comps} comp, {px} px", fill=DIFF_COLOR if px else "gray",
                font=small)
        for k, im in enumerate(ims):
            img.paste(im, (left + gutter + k * (W + gutter), y))
        y += h + gutter
    if out is not None:
        img.save(out)
    return img
