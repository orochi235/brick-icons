"""A decal's flat texture must come out the way the part wears it.

The basis was seeded off a fixed axis, so the in-plane rotation was arbitrary:
3040bp08's slope face unwrapped with v pointing DOWN the part. Glyphs were
never mirrored — (u, v, n) is right-handed about the outward normal — so this
is a rotation choice, not a reflection one.
"""
import numpy as np
import pytest

from brick_icons import unwrap

UP = np.array([0.0, -1.0, 0.0])          # LDraw up


def test_a_wall_decal_unwraps_with_up_pointing_up():
    plane = unwrap.Plane(normal=np.array([0.0, 0.0, -1.0]), offset=0.0)
    n, u, v = plane.basis()
    assert float(v @ UP) == pytest.approx(1.0)


def test_a_slope_decal_unwraps_with_up_pointing_up():
    """3040bp08's 45 degree face measured v . up = -0.707 — upside down."""
    n = np.array([0.0, -0.7071067811865476, -0.7071067811865476])
    n_, u, v = unwrap.Plane(normal=n, offset=0.0).basis()
    assert float(v @ UP) > 0.7


def test_a_top_face_falls_back_to_plus_z():
    """A top face's normal IS up, so the plane has no up to inherit. +Z is
    where LDraw authors put the top of a glyph: 2431pt2's "Octan" and
    3068bpfi's "FABULAND" both lay out 180 deg off under -Z."""
    n, u, v = unwrap.Plane(normal=np.array([0.0, -1.0, 0.0]), offset=0.0).basis()
    assert float(v @ np.array([0.0, 0.0, 1.0])) == pytest.approx(1.0)


@pytest.mark.parametrize("normal", [
    (0.0, 0.0, -1.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 1.0, 0.0),
    (0.0, -0.7071067811865476, -0.7071067811865476),
])
def test_the_frame_stays_right_handed_about_the_outward_normal(normal):
    """Right-handed about the OUTWARD normal is what keeps glyphs unmirrored."""
    n, u, v = unwrap.Plane(normal=np.array(normal), offset=0.0).basis()
    assert np.cross(u, v) == pytest.approx(n, abs=1e-9)


@pytest.mark.parametrize("normal", [
    (0.0, 0.0, -1.0), (0.0, -1.0, 0.0),
    (0.0, -0.7071067811865476, -0.7071067811865476),
])
def test_the_round_trip_survives_the_new_basis(normal):
    n = np.array(normal, float)
    plane = unwrap.Plane(normal=n, offset=2.0)
    pts = np.array([[3.0, 5.0, -7.0], [-1.0, 2.0, 4.0]])
    pts = pts - np.outer(pts @ n - 2.0, n)          # put them on the plane
    back = unwrap.to_xyz(unwrap.to_uv(pts, plane), plane)
    assert back == pytest.approx(pts, abs=1e-9)
