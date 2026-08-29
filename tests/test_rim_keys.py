"""Rim circles that are physically the same must compare equal.

LDraw writes transform matrices at limited decimal precision, so instances of
one sub-part land ~1e-4 apart — only about 8x under rim_key's 1e-3 quantum.
A rim whose radius sits near a bin boundary therefore splits into two keys,
and smooth_rim_skips sees half the coverage it should.
"""
import numpy as np

from brick_icons import hlr, primitives


# measured from 3942bp01's band at y=19.556: one full 360 deg band plus eight
# 45 deg sectors, all the same circle, spread by authored matrix precision
BAND_RADII = (14.4443, 14.44437465147346, 14.444503539306186)
BAND_CENTRES = ((0.0, 19.5561, 0.0), (0.0, 19.556, 0.0), (0.0, 19.556, 0.0))


def test_rims_within_authored_precision_share_one_key():
    keys = [primitives.rim_key(c, (0.0, 1.0, 0.0), r)
            for c, r in zip(BAND_CENTRES, BAND_RADII)]
    assert len(set(keys)) > 1, "fixture must span a rounding boundary"
    canon = primitives.canonical_rim_keys(keys)
    assert len({canon[k] for k in keys}) == 1


def test_genuinely_different_rims_stay_apart():
    """The cone's bands are 1.111 LDU apart in radius; merging those would
    suppress real edges."""
    keys = [primitives.rim_key((0.0, 19.556, 0.0), (0.0, 1.0, 0.0), r)
            for r in (14.444, 15.555)]
    canon = primitives.canonical_rim_keys(keys)
    assert len({canon[k] for k in keys}) == 2


def test_clustering_is_deterministic_whatever_order_it_sees():
    keys = [primitives.rim_key(c, (0.0, 1.0, 0.0), r)
            for c, r in zip(BAND_CENTRES, BAND_RADII)]
    a = primitives.canonical_rim_keys(keys)
    b = primitives.canonical_rim_keys(list(reversed(keys)))
    assert {a[k] for k in keys} == {b[k] for k in keys}


def test_3942bp01_band_seam_is_suppressed():
    """The whole point: the stacked cone bands meet smoothly, so the junction
    at y=19.556 must not draw a horizontal line across the print."""
    roots = hlr.default_roots("vendor/ldraw")
    path = hlr._resolve_input("3942bp01", roots)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(path, np.eye(3), np.zeros(3), out, roots)
    skips = hlr.smooth_rim_skips(out["analytic"], np.array(out["tri"]),
                                 cond=out["5"])
    seam = [(k, v) for k, v in skips.items()
            if k[0] != "flat" and abs(k[0][0][1] - 19.556) < 0.01]
    assert seam, "no rim recorded at the y=19.556 junction"
    for key, mask in seam:
        covered = mask if mask is True else bool(np.all(mask))
        assert covered is True, f"{key[1]:+d} side still draws its seam"
