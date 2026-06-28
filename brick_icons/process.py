from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter, ImageOps, ImageDraw


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
    return Image.fromarray(np.round(q).astype(np.uint8), "L")


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


def _dilate(mask: np.ndarray, px: float) -> np.ndarray:
    """Thicken a boolean ink mask to ~`px` wide via max-filter dilation."""
    px = int(round(px))
    if px <= 1:
        return mask
    size = px if px % 2 == 1 else px + 1          # MaxFilter requires odd size
    img = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), "L")
    return np.asarray(img.filter(ImageFilter.MaxFilter(size)), int) > 0


def _resize_ink(mask: np.ndarray, out_w: int, out_h: int) -> np.ndarray:
    """Downscale a boolean ink mask while preserving thin lines: any output cell
    touched by ink stays ink. (LANCZOS averaging washes 1px lines out to ~white,
    which is what silently dropped interior edges on the label-size downscale.)"""
    img = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), "L")
    small = img.resize((max(1, out_w), max(1, out_h)), Image.BOX)
    return np.asarray(small, int) > 12


def outline_masks(rgba: Image.Image, edge_thr: int = 28) -> tuple[np.ndarray, np.ndarray]:
    """Native-resolution (silhouette, interior) boolean line masks, each ~1px.
    silhouette = contour of the alpha; interior = tonal edges strictly inside it."""
    rgba = rgba.convert("RGBA")
    a = _silhouette_mask(rgba)
    dil = a.filter(ImageFilter.MaxFilter(3))
    ero = a.filter(ImageFilter.MinFilter(3))
    sil = (np.asarray(dil, int) - np.asarray(ero, int)) > 0
    g = to_grayscale(rgba)
    edges = np.asarray(g.filter(ImageFilter.FIND_EDGES), int)
    inside = np.asarray(ero, int) > 16            # eroded alpha keeps edges off the rim
    interior = (edges > edge_thr) & inside
    return sil, interior


def _compose_lines(sil: np.ndarray, interior_mask: np.ndarray, sil_width: float,
                   line_width: float, interior: bool = True) -> Image.Image:
    lines = _dilate(sil, sil_width)
    if interior:
        lines = lines | _dilate(interior_mask, line_width)
    return Image.fromarray(np.where(lines, 0, 255).astype(np.uint8), "L")


def make_outline(rgba: Image.Image, interior: bool = True, line_width: float = 2,
                 sil_width: float = 3, edge_thr: int = 28) -> Image.Image:
    """Black line-art on white at native resolution (SVG / gray master). Widths
    are native pixels; the CLI scales output-px widths up by the contain ratio so
    the SVG and gray master match the printed mono's stroke weight."""
    sil, inter = outline_masks(rgba, edge_thr)
    return _compose_lines(sil, inter, sil_width, line_width, interior)


def contain_factor(nw: int, nh: int, w: int, h: int, margin: int = 6,
                   scale: float = 1.0) -> float:
    """Scale factor mapping a native (nw,nh) image into the (w,h) label inner box,
    matching fit_contain's geometry."""
    scale = max(0.01, min(1.0, scale))
    inner_w = max(1.0, (w - 2 * margin) * scale)
    inner_h = max(1.0, (h - 2 * margin) * scale)
    return min(inner_w / nw, inner_h / nh)


def outline_mono(rgba: Image.Image, w: int, h: int, margin: int = 6, scale: float = 1.0,
                 line_width: float = 2, sil_width: float = 3, interior: bool = True,
                 edge_thr: int = 28) -> Image.Image:
    """1-bit outline at label resolution. Builds 1px masks at native res, then
    ink-preservingly downscales them and dilates to the requested output-px widths
    -- so interior detail survives the downscale at any thickness."""
    rgba = rgba.convert("RGBA")
    sil, inter = outline_masks(rgba, edge_thr)
    nh, nw = sil.shape
    f = contain_factor(nw, nh, w, h, margin, scale)
    ow, oh = max(1, round(nw * f)), max(1, round(nh * f))
    small = _compose_lines(_resize_ink(sil, ow, oh), _resize_ink(inter, ow, oh),
                           sil_width, line_width, interior)
    canvas = Image.new("L", (w, h), 255)
    canvas.paste(small, ((w - ow) // 2, (h - oh) // 2))
    return canvas.convert("1")


def draw_segments(segs, w, h, line_px=2, sil_px=3, supersample=3):
    """Anti-aliased black line-art on white. 'sil' segments use sil_px width."""
    ss = max(1, supersample)
    img = Image.new("L", (w * ss, h * ss), 255)
    dr = ImageDraw.Draw(img)
    for x1, y1, x2, y2, kind in segs:
        wpx = max(1, round((sil_px if kind == "sil" else line_px) * ss))
        dr.line([(x1 * ss, y1 * ss), (x2 * ss, y2 * ss)], fill=0, width=wpx)
    return img.resize((w, h), Image.LANCZOS)


def segments_mono(segs, w, h, line_px=2, sil_px=3, threshold=160):
    g = draw_segments(segs, w, h, line_px, sil_px)
    return g.point(lambda p: 255 if p >= threshold else 0).convert("1")


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
