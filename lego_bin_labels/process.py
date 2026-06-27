from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter, ImageOps


def flatten_rgb(rgba: Image.Image) -> Image.Image:
    rgba = rgba.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    bg.alpha_composite(rgba)
    return bg.convert("RGB")


def to_grayscale(rgba: Image.Image) -> Image.Image:
    return flatten_rgb(rgba).convert("L")


def apply_levels(g: Image.Image, black: int = 0, white: int = 255,
                 gamma: float = 1.0) -> Image.Image:
    if white <= black:
        white = black + 1
    a = np.asarray(g, np.float64)
    a = np.clip((a - black) / (white - black), 0.0, 1.0)
    if gamma != 1.0:
        a = a ** (1.0 / gamma)
    return Image.fromarray((a * 255.0 + 0.5).astype(np.uint8), "L")


def posterize(g: Image.Image, levels: int = 4) -> Image.Image:
    levels = max(2, levels)
    a = np.asarray(g, np.float64)
    q = np.round(a / 255 * (levels - 1)) / (levels - 1) * 255
    return Image.fromarray(q.astype(np.uint8), "L")


def fit_contain(g: Image.Image, w: int, h: int, margin: int = 6,
                scale: float = 1.0) -> Image.Image:
    scale = max(0.01, min(1.0, scale))
    inner = (max(1, round((w - 2 * margin) * scale)),
             max(1, round((h - 2 * margin) * scale)))
    scaled = ImageOps.contain(g, inner, Image.LANCZOS)
    canvas = Image.new("L", (w, h), 255)
    canvas.paste(scaled, ((w - scaled.width) // 2, (h - scaled.height) // 2))
    return canvas


def _silhouette_mask(rgba: Image.Image, thr: int = 16) -> Image.Image:
    return rgba.convert("RGBA").split()[-1].point(lambda p: 255 if p > thr else 0)


def make_outline(rgba: Image.Image, interior: bool = True,
                 sil_w: int = 2, edge_thr: int = 28) -> Image.Image:
    """Black line-art on white: silhouette contour + optional interior edges."""
    rgba = rgba.convert("RGBA")
    a = _silhouette_mask(rgba)
    dil = a.filter(ImageFilter.MaxFilter(sil_w * 2 + 1))
    ero = a.filter(ImageFilter.MinFilter(sil_w * 2 + 1))
    lines = (np.asarray(dil, int) - np.asarray(ero, int)) > 0
    if interior:
        g = to_grayscale(rgba)
        edges = np.asarray(g.filter(ImageFilter.FIND_EDGES), int)
        inside = np.asarray(a, int) > 16
        lines = lines | ((edges > edge_thr) & inside)
    return Image.fromarray(np.where(lines, 0, 255).astype(np.uint8), "L")


_BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]],
                   dtype=np.float64)


def dither_threshold(g: Image.Image, threshold: int = 128) -> Image.Image:
    return g.point(lambda p: 255 if p >= threshold else 0).convert("1")


def dither_floyd(g: Image.Image) -> Image.Image:
    return g.convert("1")


def dither_ordered(g: Image.Image) -> Image.Image:
    n = 4
    thresh = (_BAYER4 + 0.5) / (n * n) * 255.0
    a = np.asarray(g, np.float64)
    tile = np.tile(thresh, (a.shape[0] // n + 1, a.shape[1] // n + 1))[:a.shape[0], :a.shape[1]]
    return Image.fromarray(np.where(a > tile, 255, 0).astype(np.uint8), "L").convert("1")


def dither_atkinson(g: Image.Image) -> Image.Image:
    a = np.asarray(g, np.float64).copy()
    h, w = a.shape
    for y in range(h):
        for x in range(w):
            old = a[y, x]
            new = 255.0 if old >= 128 else 0.0
            a[y, x] = new
            err = (old - new) / 8.0
            for dx, dy in ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    a[ny, nx] += err
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "L").convert("1")


_DITHERERS = {"threshold": dither_threshold, "floyd": dither_floyd,
              "ordered": dither_ordered, "atkinson": dither_atkinson}


def dither(g: Image.Image, algo: str, threshold: int = 128) -> Image.Image:
    if algo not in _DITHERERS:
        raise ValueError(f"unknown dither algo: {algo!r} (have {list(_DITHERERS)})")
    if algo == "threshold":
        return dither_threshold(g, threshold)
    return _DITHERERS[algo](g)
