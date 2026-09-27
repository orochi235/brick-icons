from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageOps, ImageDraw, ImageFont


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


def icon_weight(width, px_per_ldu, cap_ldu, floor):
    """One stroke weight for a whole icon, in its output px: `width`, but
    never wider than `cap_ldu` LDU of the part as drawn and never thinner
    than `floor`. A part shrunk hard to fit its canvas keeps its detail
    instead of drowning in a fixed-width stroke (35011, 51542, 65068).
    `cap_ldu` <= 0 turns the scaling off."""
    if cap_ldu <= 0:
        return width
    return min(width, max(floor, cap_ldu * px_per_ldu))


def op_points(op, n=12):
    """A stroke op as a short polyline in its own space."""
    if len(op) == 5:                                   # legacy line tuple
        op = ("line",) + tuple(op)
    if op[0] == "line":
        return [(op[1], op[2]), (op[3], op[4])]
    _, cx, cy, ux, uy, vx, vy, t0, t1, _ = op
    return [(cx + math.cos(t) * ux + math.sin(t) * vx,
             cy + math.cos(t) * uy + math.sin(t) * vy)
            for t in (math.radians(t0 + (t1 - t0) * i / (n - 1))
                      for i in range(n))]


class StudTier:
    """The lighter stroke studs draw at: `px` wide, for every op lying wholly
    inside `zone`, the union of the studs' projected footprints (same space
    as the ops). A stud is what the part DECLARED as one -- geometry under a
    `p/stud*.dat` reference -- never a circle of the right size."""

    def __init__(self, zone, px):
        import shapely
        self.zone, self.px = zone, px
        shapely.prepare(zone)

    def covers(self, op):
        import shapely
        xy = np.asarray(op_points(op, 5), float)
        return bool(shapely.contains_xy(self.zone, xy[:, 0], xy[:, 1]).all())

    def px_at(self, geom, default):
        """The stroke width drawn around `geom`: the stud tier when it lies
        in a stud, else `default`. A thinness test measured against the
        wrong one reads a stud's own wall as a sliver and inks it (3811)."""
        import shapely
        p = geom.representative_point()
        return self.px if shapely.contains_xy(self.zone, p.x, p.y) else default

    def scaled(self, k):
        from shapely import affinity
        return StudTier(affinity.scale(self.zone, k, k, origin=(0, 0)),
                        self.px * k)


def local_px(geom, line_px, studs=None):
    """The line weight a region sits among -- see StudTier.px_at."""
    return line_px if studs is None else studs.px_at(geom, line_px)


def stroke_width(op, line_px, sil_px, studs=None):
    """The width an op draws at: the stud tier inside a stud, else `sil_px`
    for a silhouette and `line_px` for everything else. Every writer and
    every fill rule that sizes a stroke asks here."""
    if studs is not None and studs.covers(op):
        return studs.px
    return sil_px if op[-1] == "sil" else line_px


def draw_segments(segs, w, h, line_px=2, sil_px=2, supersample=3,
                  contour_rings=None, contour_px=None, studs=None):
    """Anti-aliased black line-art on white. Accepts line ops and arc ops;
    'sil' segments use sil_px width. Arc ops are sampled into polylines.
    contour_rings (closed silhouette rings, px) draw first with round
    joints: PIL strokes are butt-capped, so outline corners are otherwise
    left with unfilled outer wedges (notched corners)."""
    ss = max(1, supersample)
    img = Image.new("L", (w * ss, h * ss), 255)
    dr = ImageDraw.Draw(img)
    for ring in contour_rings or []:
        wpx = max(1, round((contour_px if contour_px is not None else sil_px) * ss))
        pts = [(x * ss, y * ss) for x, y in ring]
        # re-append the first two points so the seam vertex gets a joint too
        dr.line(pts + pts[:2], fill=0, width=wpx, joint="curve")
    for op in segs:
        if len(op) == 5:                               # legacy line tuple
            op = ("line",) + tuple(op)
        wpx = max(1, round(stroke_width(op, line_px, sil_px, studs) * ss))
        if op[0] == "line":
            _, x1, y1, x2, y2, _ = op
            dr.line([(x1 * ss, y1 * ss), (x2 * ss, y2 * ss)], fill=0, width=wpx)
        else:
            _, cx, cy, ux, uy, vx, vy, t0, t1, _ = op
            n = max(2, int(abs(t1 - t0) / 2) + 2)
            pts = []
            for k in range(n):
                ang = math.radians(t0 + (t1 - t0) * k / (n - 1))
                c, s = math.cos(ang), math.sin(ang)
                pts.append(((cx + c * ux + s * vx) * ss, (cy + c * uy + s * vy) * ss))
            dr.line(pts, fill=0, width=wpx, joint="curve")
    return img.resize((w, h), Image.LANCZOS)


def segments_mono(segs, w, h, line_px=2, sil_px=2, threshold=160,
                  contour_rings=None, contour_px=None, studs=None):
    g = draw_segments(segs, w, h, line_px, sil_px,
                      contour_rings=contour_rings, contour_px=contour_px,
                      studs=studs)
    return g.point(lambda p: 255 if p >= threshold else 0).convert("1")


def stamp_label(img: Image.Image, text: str) -> Image.Image:
    """Render tag in fixed small print, tucked into the bottom-left corner.
    Absolute size, deliberately NOT scaled to the part — an identification aid
    for review renders. In place."""
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=7)
    d.text((2, img.height - 9), text, fill="black", font=font)
    return img


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
