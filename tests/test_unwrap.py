import numpy as np
import pytest

from brick_icons import geom2d, unwrap


class FakeCylinder:
    """Stand-in for primitives.Cylinder: unit circle in R's x/z, axis R[:,1]."""
    def __init__(self, r=20.0, h=24.0):
        self.R = np.diag([r, h, r]).astype(float)
        self.t = np.zeros(3)


def test_binds_a_facet_on_the_wall_to_its_cylinder():
    cyl = FakeCylinder(r=20.0)
    on_wall = np.array([[20.0, 1.0, 0.0], [19.6, 1.0, 4.0], [20.0, 5.0, 0.0]])
    assert unwrap.bind(on_wall, [cyl]) is cyl


def test_does_not_bind_geometry_further_than_the_tolerance():
    cyl = FakeCylinder(r=20.0)
    standoff = np.array([[24.0, 1.0, 0.0], [24.0, 1.0, 4.0], [24.0, 5.0, 0.0]])
    assert unwrap.bind(standoff, [cyl]) is None


def test_tolerance_is_half_an_ldu():
    """0.5 LDU binds every measured case (3040bp08 worst at 0.345) with an
    order of magnitude under the smallest real feature (a stud is 12 across)."""
    assert unwrap.BIND_TOL == 0.5


def test_unbound_geometry_is_left_as_authored():
    """An unrecognized construction must degrade to today's output, never
    raise — 4,764 printed parts, most never eyeballed."""
    weird = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    assert unwrap.bind(weird, []) is None


def test_cylinder_unwrap_uses_arc_length_not_degrees():
    """Degrees against LDU is an arbitrary aspect; arc length makes the
    texture isometric with the surface, so a round lamp stays round."""
    cyl = FakeCylinder(r=20.0)
    quarter = np.array([[20.0, 0.0, 0.0], [0.0, 0.0, 20.0]])
    uv = unwrap.to_uv(quarter, cyl)
    assert uv[:, 1] == pytest.approx([0.0, 0.0])
    # a quarter turn at r=20 is 20 * pi/2 of arc
    assert uv[1, 0] - uv[0, 0] == pytest.approx(20.0 * np.pi / 2, rel=1e-6)


def test_cylinder_unwrap_round_trips():
    cyl = FakeCylinder(r=20.0)
    pts = np.array([[20.0, 3.0, 0.0], [0.0, 7.0, 20.0], [-20.0, 1.0, 0.0]])
    back = unwrap.to_xyz(unwrap.to_uv(pts, cyl), cyl)
    assert back == pytest.approx(pts, abs=1e-9)


def test_faceted_ring_reprojects_onto_the_exact_radius():
    """The point of the whole exercise: chord midpoints authored at r=19.616
    (a 16-gon inscribed in r=20) come back at exactly 20."""
    cyl = FakeCylinder(r=20.0)
    th = np.linspace(0, 2 * np.pi, 17)[:-1] + np.pi / 16
    chord = np.column_stack([19.616 * np.cos(th),
                             np.zeros(16), 19.616 * np.sin(th)])
    back = unwrap.to_xyz(unwrap.to_uv(chord, cyl), cyl)
    assert np.hypot(back[:, 0], back[:, 2]) == pytest.approx(20.0, abs=1e-9)


def test_planar_unwrap_is_the_identity_in_the_face_basis():
    plane = unwrap.Plane(normal=np.array([0.0, 1.0, 0.0]), offset=2.0)
    pts = np.array([[3.0, 2.0, 5.0], [-1.0, 2.0, 4.0]])
    back = unwrap.to_xyz(unwrap.to_uv(pts, plane), plane)
    assert back == pytest.approx(pts, abs=1e-9)
