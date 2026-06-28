import math

import numpy as np

from brick_icons import primitives as P


def test_parse_edge_fractions():
    assert P.parse_primitive("4-4edge.dat") == ("edge", 360.0, 0)
    assert P.parse_primitive("1-4edge.dat") == ("edge", 90.0, 0)
    assert P.parse_primitive("3-4edge") == ("edge", 270.0, 0)
    assert P.parse_primitive("1-8edge.dat") == ("edge", 45.0, 0)


def test_parse_cyli_and_alias_cylo():
    assert P.parse_primitive("1-4cyli.dat") == ("cyli", 90.0, 0)
    assert P.parse_primitive("4-4cylo.dat") == ("cyli", 360.0, 0)


def test_parse_disc():
    assert P.parse_primitive("3-4disc.dat") == ("disc", 270.0, 0)


def test_parse_ring_inner_radius():
    assert P.parse_primitive("4-4ring3.dat") == ("ring", 360.0, 3)
    assert P.parse_primitive("4-4ring1.dat") == ("ring", 360.0, 1)


def test_unrecognized_returns_none():
    assert P.parse_primitive("4-4ndis.dat") is None      # fallback to faceted
    assert P.parse_primitive("1-4cyls.dat") is None       # sloped cut: fallback
    assert P.parse_primitive("1-8chrd.dat") is None       # chord: straight, fallback
    assert P.parse_primitive("box.dat") is None
    assert P.parse_primitive("stud4.dat") is None


def test_project_circle_to_ellipse_basis():
    def proj(Pw):   # simple projector: A=x, B=z, Z=y
        Pw = np.atleast_2d(Pw)
        return Pw[:, 0], Pw[:, 2], Pw[:, 1]
    R, t = np.eye(3), np.zeros(3)
    ell = P.project_circle(R, t, 2.0, proj, s=1.0, cx=0.0, cy=0.0, half=0.0)
    assert np.allclose(ell.center, [0.0, 0.0])
    assert np.allclose(np.hypot(*ell.u), 2.0) and np.allclose(np.hypot(*ell.v), 2.0)


def test_ellipse_svd_axes_circle():
    e = P.Ellipse(center=np.array([5.0, 7.0]), u=np.array([3.0, 0.0]), v=np.array([0.0, 3.0]))
    rx, ry, phi = e.svg_axes()
    assert np.isclose(rx, 3.0) and np.isclose(ry, 3.0)


def test_ellipse_point_param():
    e = P.Ellipse(center=np.array([0.0, 0.0]), u=np.array([2.0, 0.0]), v=np.array([0.0, 1.0]))
    p0 = e.point(0.0)
    p90 = e.point(math.pi / 2)
    assert np.allclose(p0, [2.0, 0.0]) and np.allclose(p90, [0.0, 1.0])


def test_cylinder_depth_hit_and_miss():
    R, t = np.eye(3), np.zeros(3)
    cyl = P.CylinderOccluder(R, t, sector=360.0)
    F = np.array([0.0, 0.0, 1.0])               # look along +z
    O = np.array([[0.0, 0.5, -5.0],              # through axis mid-height -> front wall z=-1
                  [5.0, 0.5, -5.0]])              # misses (x=5 outside r=1)
    d = cyl.depth(O, F)
    assert np.isclose(d[0], 4.0, atol=1e-6)       # lam to reach z=-1 from z=-5
    assert np.isinf(d[1])


def test_cylinder_depth_clamps_height():
    R, t = np.eye(3), np.zeros(3)
    cyl = P.CylinderOccluder(R, t, sector=360.0)
    F = np.array([0.0, 0.0, 1.0])
    O = np.array([[0.0, 5.0, -5.0]])              # above the top (y=5 > 1) -> miss
    assert np.isinf(cyl.depth(O, F)[0])


def test_disc_depth():
    R, t = np.eye(3), np.zeros(3)                 # disc in XZ plane at y=0, radius 1
    disc = P.DiscOccluder(R, t, sector=360.0, inner=0.0, outer=1.0)
    F = np.array([0.0, 1.0, 0.0])                 # look along +y onto the disc
    O = np.array([[0.3, -5.0, 0.2],                # inside radius -> lam=5
                  [2.0, -5.0, 0.0]])                # outside radius -> miss
    d = disc.depth(O, F)
    assert np.isclose(d[0], 5.0) and np.isinf(d[1])
