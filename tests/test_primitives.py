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


def _proj_xz(Pw):   # A=x, B=z, Z=y (look along +y)
    Pw = np.atleast_2d(Pw)
    return Pw[:, 0], Pw[:, 2], Pw[:, 1]


def test_drawn_edge_is_full_arc():
    rec = {"kind": "edge", "sector": 360.0, "inner": 0, "R": np.eye(3), "t": np.zeros(3)}
    ops = P.drawn_curves(rec, _proj_xz, s=1.0, cx=0.0, cy=0.0, half=0.0,
                         fwd=np.array([0, 1.0, 0]))
    assert len(ops) == 1 and ops[0][0] == "arc"
    assert ops[0][-1] == "edge"


def test_drawn_cylinder_has_two_silhouette_lines():
    # cylinder axis +y; view along +z so the side silhouette is well-defined
    def proj_z(Pw):
        Pw = np.atleast_2d(Pw)
        return Pw[:, 0], Pw[:, 1], Pw[:, 2]
    rec = {"kind": "cyli", "sector": 360.0, "inner": 0, "R": np.eye(3), "t": np.zeros(3)}
    ops = P.drawn_curves(rec, proj_z, s=1.0, cx=0.0, cy=0.0, half=0.0,
                         fwd=np.array([0, 0, 1.0]))
    sil_lines = [o for o in ops if o[0] == "line" and o[-1] == "sil"]
    assert len(sil_lines) == 2


def test_visibility_splits_op_by_occluder():
    # horizontal edge line across x in [0,10] at depth 0; an occluder slab
    # covers x in [4,6] nearer (depth -1) -> the middle is hidden.
    class Slab:
        def depth(self, O, F):
            x = O[:, 0]
            return np.where((x >= 4) & (x <= 6), -1.0, np.inf)

    op = ("line", 0.0, 0.0, 10.0, 0.0, "edge")
    depth_fn = lambda ts: np.zeros_like(np.asarray(ts, float))   # line lies at depth 0

    def ray_origin(xs, ys):
        return np.stack([xs, ys, np.zeros_like(xs)], 1)

    vis = P.visible_subops([(op, depth_fn)], [Slab()], ray_origin,
                           fwd=np.array([0, 0, 1.0]), eps=1e-6, n=101)
    lines = [o for o in vis if o[0] == "line"]
    assert len(lines) == 2                        # left of 4 and right of 6
    assert lines[0][1] < 4.0 and lines[1][3] > 6.0


def test_visibility_keeps_unoccluded_arc_whole():
    class Empty:
        def depth(self, O, F):
            return np.full(O.shape[0], np.inf)

    # parametric arc: center (50,50), u=(40,0), v=(0,40), params 0..360 deg
    op = ("arc", 50.0, 50.0, 40.0, 0.0, 0.0, 40.0, 0.0, 360.0, "edge")
    depth_fn = lambda degs: np.zeros_like(np.asarray(degs, float))

    def ray_origin(xs, ys):
        return np.stack([xs, ys, np.zeros_like(xs)], 1)

    vis = P.visible_subops([(op, depth_fn)], [Empty()], ray_origin,
                           fwd=np.array([0, 0, 1.0]), eps=1e-6, n=60)
    arcs = [o for o in vis if o[0] == "arc"]
    assert len(arcs) == 1 and np.isclose(arcs[0][7], 0.0) and arcs[0][8] >= 350.0
