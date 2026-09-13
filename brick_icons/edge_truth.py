"""Which declared edges a stroked drawing leaves out.

A part file declares its edges: every type-2 line, and each type-5 line whose
condition holds at the pose. This finds the visible ones under the drawing's
own camera and reports where the drawing put no ink on them. Missing only: occt
draws junctions between exact surfaces that parts never declare, so ink with no
declared edge under it is not a defect.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from brick_icons import goldens, hlr

SAMPLE_STEP = 0.5   # canvas px between samples along an edge
TOLERANCE = 1.5     # canvas px of slack past the stroke's half-width
MIN_GAP = 4.0       # canvas px; shorter uncovered runs are antialias noise


def load(part: str | Path, roots: list[Path], pose=None) -> dict:
    """The part's declarations and triangles. No "analytic" key, so every
    primitive tessellates -- the oracle must not share the engine's
    substitutions."""
    out: dict = {"2": [], "5": [], "tri": [], "tri_meta": []}
    root = np.eye(3) if pose is None else np.asarray(pose, float)
    hlr.flatten(hlr._resolve_input(str(part), roots), root, np.zeros(3), out,
                roots)
    return out


def _to_px(P: np.ndarray, fit: dict, zoom: int):
    P = np.asarray(P, float)
    k = fit["k"] * zoom
    return (P @ fit["right"]) * k + fit["kx"] * zoom, \
        -(P @ fit["up"]) * k + fit["ky"] * zoom, P @ fit["fwd"]


def visible_edges(out: dict, fit: dict, zoom: int) -> list[tuple]:
    """Visible declared edges as (x1, y1, x2, y2, kind) in canvas px, kind
    "edge" for type 2 and "sil" for type 5. Occlusion is the naive engine's:
    its z-buffer, dilation and biases, and nothing downstream of them."""
    W, H = fit["width"] * zoom, fit["height"] * zoom
    tri = np.asarray(out["tri"], float).reshape(-1, 3, 3)
    if len(tri):
        tx, ty, tz = _to_px(tri.reshape(-1, 3), fit, zoom)
        zbuf = hlr.rasterize_zbuffer(np.stack([tx, ty], 1).reshape(-1, 3, 2),
                                     tz.reshape(-1, 3), W, H)
        zrange = float(np.ptp(tz)) or 1.0
    else:
        zbuf, zrange = np.full((H, W), np.inf), 1.0
    zedge = hlr.dilate_zbuffer(zbuf, max(2, round(max(W, H) * hlr.EDGE_DILATE)))

    runs = []
    for e in out["2"]:
        x, y, z = _to_px(np.asarray(e, float).reshape(2, 3), fit, zoom)
        runs += hlr.clip_visible((x[0], y[0], x[1], y[1], "edge"), zedge, W, H,
                                 (z[0], z[1]), hlr.EDGE_BIAS * zrange)
    for q in out["5"]:
        x, y, z = _to_px(np.asarray(q, float).reshape(4, 3), fit, zoom)
        p1, p2 = np.array([x[0], y[0]]), np.array([x[1], y[1]])
        if np.hypot(*(p2 - p1)) < 0.5 * zoom:
            continue
        if hlr.same_side(p1, p2, np.array([x[2], y[2]]), np.array([x[3], y[3]])):
            runs += hlr.clip_visible((x[0], y[0], x[1], y[1], "sil"), zbuf, W, H,
                                     (z[0], z[1]), hlr.SIL_BIAS * zrange)
    return [(x1 / zoom, y1 / zoom, x2 / zoom, y2 / zoom, kind)
            for x1, y1, x2, y2, kind in runs]


def ink_mask(rgba: np.ndarray) -> np.ndarray:
    """Dark drawn pixels. White fills and white seal strokes are not drawing."""
    lum = rgba[:, :, :3].astype(float) @ np.array([0.299, 0.587, 0.114])
    return (rgba[:, :, 3] > 128) & (lum < 128)


def score(segs: list[tuple], ink: np.ndarray, zoom: int,
          stroke_width: float) -> dict:
    """Declared length, uncovered length and gaps, all in canvas px."""
    H, W = ink.shape
    pts = []
    for x1, y1, x2, y2, _ in segs:
        n = max(2, int(np.ceil(np.hypot(x2 - x1, y2 - y1) / SAMPLE_STEP)) + 1)
        t = np.linspace(0.0, 1.0, n)
        pts.append(np.stack([x1 + (x2 - x1) * t, y1 + (y2 - y1) * t], 1))
    if not pts:
        return {"declared_len": 0.0, "missing_len": 0.0, "missing_comps": 0,
                "gaps": []}
    P = np.concatenate(pts)
    xi = np.clip((P[:, 0] * zoom).astype(int), 0, W - 1)
    yi = np.clip((P[:, 1] * zoom).astype(int), 0, H - 1)
    reach = (stroke_width / 2 + TOLERANCE) * zoom
    dist = ndimage.distance_transform_edt(~ink) if ink.any() \
        else np.full(ink.shape, np.inf)
    bare = dist[yi, xi] > reach

    mask = np.zeros(ink.shape, bool)
    mask[yi[bare], xi[bare]] = True
    # Neighboring samples sit SAMPLE_STEP * zoom apart; grow them into runs.
    grown = ndimage.binary_dilation(
        mask, iterations=max(1, int(np.ceil(SAMPLE_STEP * zoom))))
    labels, _ = ndimage.label(grown)
    owner = labels[yi[bare], xi[bare]]
    gaps = []
    for comp in np.unique(owner):
        mine = P[bare][owner == comp]
        length = len(mine) * SAMPLE_STEP
        if length < MIN_GAP:
            continue
        gaps.append({"len": round(length, 1),
                     "x": [round(float(mine[:, 0].min()), 1),
                           round(float(mine[:, 0].max()), 1)],
                     "y": [round(float(mine[:, 1].min()), 1),
                           round(float(mine[:, 1].max()), 1)]})
    gaps.sort(key=lambda g: -g["len"])
    return {"declared_len": round(len(P) * SAMPLE_STEP, 1),
            "missing_len": round(sum(g["len"] for g in gaps), 1),
            "missing_comps": len(gaps), "gaps": gaps[:16]}


def score_drawing(part: str, svg: Path, fit: dict, roots: list[Path],
                  stroke_width: float, pose=None, zoom: int = 4,
                  png: Path | None = None) -> dict:
    """Score one SVG against its part. `png` reuses a raster already made at
    this zoom; otherwise resvg draws one beside the SVG and removes it."""
    made = png is None
    if made:
        png = svg.with_suffix(".edges.png")
        subprocess.run(["resvg", "--zoom", str(zoom), str(svg), str(png)],
                       check=True, capture_output=True)
    try:
        ink = ink_mask(np.array(Image.open(png).convert("RGBA")))
    finally:
        if made:
            png.unlink(missing_ok=True)
    segs = visible_edges(load(part, roots, pose), fit, zoom)
    return {"sha256": goldens.sha256(svg.read_bytes()),
            **score(segs, ink, zoom, stroke_width)}
