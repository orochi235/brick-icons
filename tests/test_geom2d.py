import numpy as np

from brick_icons import geom2d


def sq(x0, y0, x1, y1):
    return np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], float)


def test_tjunction_union_is_one_polygon():
    # bottom rect + top rect split in two (T-junction at (1,1)): union must be
    # ONE polygon of exact area — the 3960 dish 16-vs-48 ring case in miniature.
    a = geom2d.to_geom(sq(0, 0, 2, 1))
    b1 = geom2d.to_geom(sq(0, 1, 1, 2))
    b2 = geom2d.to_geom(sq(1, 1, 2, 2))
    u = geom2d.union_all([a, b1, b2])
    assert u.geom_type == "Polygon"
    assert abs(geom2d.area(u) - 4.0) < 1e-6


def test_self_overlap_union():
    u = geom2d.union_all([geom2d.to_geom(sq(0, 0, 2, 2)),
                          geom2d.to_geom(sq(1, 0, 3, 2))])
    assert abs(geom2d.area(u) - 6.0) < 1e-6


def test_difference_makes_hole_and_two_subpaths():
    outer = geom2d.to_geom(sq(0, 0, 4, 4))
    inner = geom2d.to_geom(sq(1, 1, 3, 3))
    d_geom = geom2d.difference(outer, inner)
    assert abs(geom2d.area(d_geom) - 12.0) < 1e-6
    d = geom2d.path_d(d_geom)
    assert d.count("M ") == 2 and d.count("Z") == 2


def test_holes_via_to_geom():
    g = geom2d.to_geom(sq(0, 0, 4, 4), holes=[sq(1, 1, 3, 3)])
    assert abs(geom2d.area(g) - 12.0) < 1e-6


def test_degenerate_inputs_never_raise():
    assert geom2d.area(geom2d.to_geom(np.array([(0, 0), (1, 1)], float))) == 0.0
    collinear = np.array([(0, 0), (1, 0), (2, 0)], float)
    assert geom2d.area(geom2d.to_geom(collinear)) == 0.0
    keyhole = np.array([(0, 0), (4, 0), (4, 4), (0, 4), (0, 0),
                        (1, 1), (1, 3), (3, 3), (3, 1), (1, 1)], float)
    g = geom2d.to_geom(keyhole)          # self-touching: must clean, not raise
    assert geom2d.area(g) > 0


def test_multipolygon_path_d():
    u = geom2d.union_all([geom2d.to_geom(sq(0, 0, 1, 1)),
                          geom2d.to_geom(sq(5, 5, 6, 6))])
    d = geom2d.path_d(u)
    assert d.count("M ") == 2
