"""Decoration is ink, not relief: its boundary is not a crease, so it must not
stroke. The fills moved into UV; these are the strokes."""
import numpy as np
import pytest

from brick_icons import shade


class FakePrim:
    kind = "disc"
    sector = 360.0

    def __init__(self, color=16, r=1.5, centre=(0.0, 0.0, 0.0), axis_len=1.0):
        self.color = color
        self.R = np.diag([r, axis_len, r]).astype(float)
        self.t = np.array(centre, float)

    def radius_at(self, level):
        return 1.0

    def fit_pts(self, n=16):
        """Mirrors primitives.Primitive.ring_pts: the circle spanned by R's
        first and third columns, not an assumed XZ plane."""
        th = np.linspace(0, 2 * np.pi, n, endpoint=False)
        U, V = self.R[:, 0], self.R[:, 2]
        return self.t + (np.cos(th)[:, None] * U + np.sin(th)[:, None] * V)


def test_a_colored_primitive_is_ink():
    """3040bp08's lamps are 7 discs in LDraw 14 and 3942bp01's stripes are 16
    cones in LDraw 4; both drew a rim stroke around every one."""
    lamp = FakePrim(color=14)
    assert id(lamp) in shade.ink_prims([lamp], None, None)


def test_body_colored_geometry_still_strokes():
    """The part's own edges are relief and must keep their strokes."""
    wall = FakePrim(color=16)
    assert shade.ink_prims([wall], None, None) == set()


class FakeCylinder:
    sector = 360.0

    def __init__(self, r=20.0, h=24.0):
        self.R = np.diag([r, h, r]).astype(float)
        self.t = np.zeros(3)

    def radius_at(self, level):
        return 1.0


def _wall_quads(r, a0_deg, a1_deg, v0, v1, step=5):
    tris = []
    edges = np.radians(np.arange(a0_deg, a1_deg + step, step))
    for t0, t1 in zip(edges[:-1], edges[1:]):
        c = [np.array([r * np.cos(t), v, r * np.sin(t)])
             for t in (t0, t1) for v in (v0, v1)]
        tris += [np.array([c[0], c[2], c[3]]), np.array([c[0], c[3], c[1]])]
    return tris


def _disc_on_wall(theta_deg, height, r=1.5, standoff=19.7, color=16):
    """A flat disc lying against the cylinder wall, the way 3941p01's buttons
    are authored — tangent at r=19.71, just inside the r=20 wall, with its
    normal pointing radially outward."""
    th = np.radians(theta_deg)
    normal = np.array([np.cos(th), 0.0, np.sin(th)])
    tangent = np.array([-np.sin(th), 0.0, np.cos(th)])
    up = np.array([0.0, 1.0, 0.0])
    d = FakePrim(color=color, r=r)
    d.R = np.column_stack([r * tangent, normal, r * up])
    d.t = standoff * normal + height * up
    return d


def test_a_body_colored_disc_inside_a_decal_is_part_of_the_print():
    """3941p01's buttons are LDraw 16 discs lying flush on the wall INSIDE the
    black panel — holes in its region. Color alone cannot tell them from the
    part's own geometry; enclosure by the decal can."""
    cyl = FakeCylinder()
    panel = _wall_quads(20.0, 0, 40, 4.0, 12.0)
    button = _disc_on_wall(theta_deg=20.0, height=8.0)
    ink = shade.ink_prims([cyl, button], panel, [0] * len(panel))
    assert id(button) in ink


def test_a_disc_outside_the_decal_keeps_its_stroke():
    cyl = FakeCylinder()
    panel = _wall_quads(20.0, 0, 40, 4.0, 12.0)
    stud = _disc_on_wall(theta_deg=200.0, height=8.0)
    ink = shade.ink_prims([cyl, stud], panel, [0] * len(panel))
    assert id(stud) not in ink
