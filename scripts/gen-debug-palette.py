#!/usr/bin/env python
"""Regenerate trace.DEBUG_PALETTE: the most separated colors the page allows.

The palette answers "which element owns this pixel", so two elements anywhere
in one render must not read alike -- and adjacent ones least of all. Hand-picked
hues cap out around a dozen because hue is one axis; packing CIELAB uses
lightness and chroma too. The gamut left after excluding what reads as the page
(L > 85), as the ink (L < 30) or as body tone (chroma < 18) holds 38 colors at
dE 30, 51 at dE 25 and 87 at dE 20.

Two passes: farthest-point sampling picks the set, then a farthest-next walk
orders it so consecutive entries are further apart than the set's own floor.

Usage: .venv/bin/python scripts/gen-debug-palette.py [N] [--floor dE]
"""
from __future__ import annotations

import argparse

import numpy as np


def srgb_to_lab(rgb):
    c = rgb.astype(float) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805],
                  [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]])
    xyz = (c @ M.T) / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16,
                     500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], -1)


def candidates(step=6, lo=30.0, hi=85.0, min_chroma=18.0):
    g = np.arange(0, 256, step)
    rgb = np.stack(np.meshgrid(g, g, g, indexing="ij"), -1).reshape(-1, 3)
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    lab = srgb_to_lab(rgb)
    keep = (lab[:, 0] >= lo) & (lab[:, 0] <= hi)
    keep &= np.hypot(lab[:, 1], lab[:, 2]) >= min_chroma
    return rgb[keep], lab[keep]


def pack(lab, n):
    """Farthest-point sampling: each pick is the point furthest from the set."""
    picks = [int(np.argmax(np.hypot(lab[:, 1], lab[:, 2])))]
    d = np.linalg.norm(lab - lab[picks[0]], axis=1)
    while len(picks) < n:
        j = int(np.argmax(d))
        picks.append(j)
        d = np.minimum(d, np.linalg.norm(lab - lab[j], axis=1))
    return picks


def walk(lab, picks):
    """Order the set so each entry is the furthest remaining from the last."""
    left = list(picks)
    out = [left.pop(0)]
    while left:
        last = lab[out[-1]]
        k = max(range(len(left)), key=lambda i: np.linalg.norm(lab[left[i]] - last))
        out.append(left.pop(k))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=48)
    ap.add_argument("--floor", type=float, default=25.0)
    a = ap.parse_args()

    rgb, lab = candidates()
    picks = walk(lab, pack(lab, a.n))
    P = lab[picks]
    pair = min(float(np.linalg.norm(P[i] - P[j]))
               for i in range(len(P)) for j in range(i + 1, len(P)))
    cons = min(float(np.linalg.norm(P[i] - P[i + 1])) for i in range(len(P) - 1))
    print(f"# {len(picks)} colors, min dE any pair {pair:.1f}, consecutive {cons:.1f}")
    if pair < a.floor:
        raise SystemExit(f"min pair dE {pair:.1f} below the {a.floor} floor: ask for fewer")
    for i in range(0, len(picks), 6):
        row = ", ".join('"#%02x%02x%02x"' % tuple(rgb[k]) for k in picks[i:i + 6])
        print(f"    {row},")


if __name__ == "__main__":
    main()
