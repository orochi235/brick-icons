from pathlib import Path

import numpy as np

from brick_icons import edge_truth, hlr, raycast

LDRAW = Path(__file__).resolve().parents[1] / "vendor" / "ldraw"


def _fit():
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    return {"right": list(right), "up": list(up), "fwd": list(fwd),
            "k": 2.0, "kx": 100.0, "ky": 80.0}


def _px(fit, P):
    x, y, _ = edge_truth._to_px(np.asarray([P]), fit, 1)
    return float(x[0]), float(y[0])


def test_a_ray_through_a_projected_point_passes_through_it():
    fit = _fit()
    P = np.array([3.0, -7.0, 11.0])
    o, d = raycast.pixel_ray(fit, *_px(fit, P))
    off = (P - o) - ((P - o) @ d) * d
    assert np.linalg.norm(off) < 1e-9


def test_the_nearest_hit_on_3001_between_its_studs_is_the_top():
    """(0, 0, 0) is the middle of 3001's top face, between its studs; the
    top is up in LDraw's -y, and it is the first thing the camera sees."""
    out = edge_truth.load("3001", hlr.default_roots(LDRAW))
    fit = _fit()
    o, d = raycast.pixel_ray(fit, *_px(fit, [0.0, 0.0, 0.0]))
    hs = raycast.hits(out["tri"], o, d)
    assert len(hs) >= 2
    first = hs[0]
    assert abs(first.depth - 0.0) < 1e-6
    assert abs(abs(first.normal[1]) - 1.0) < 1e-6
    assert first.normal @ d < 0
    assert all(a.depth <= b.depth for a, b in zip(hs, hs[1:]))
