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


# --- arc recovery ----------------------------------------------------------

def circle_pts(cx, cy, r, n=64, t0=0.0, t1=2 * np.pi):
    t = np.linspace(t0, t1, n, endpoint=abs((t1 - t0) - 2 * np.pi) > 1e-9)
    return np.stack([cx + r * np.cos(t), cy + r * np.sin(t)], 1)


CIRCLE = [(50.0, 50.0, 30.0, 0.0, 0.0, 30.0)]      # r=30 circle at (50,50)


def test_full_circle_ring_recovers_two_arcs():
    g = geom2d.to_geom(circle_pts(50, 50, 30))
    d = geom2d.path_d(g, geom2d.arc_candidates(CIRCLE))
    assert d.count(" A ") == 2 and " L " not in d


def test_clipped_circle_keeps_straight_cut_as_line():
    disc = geom2d.to_geom(circle_pts(50, 50, 30))
    cut = geom2d.to_geom(sq(50, 0, 100, 100))       # remove right half
    d = geom2d.path_d(geom2d.difference(disc, cut),
                      geom2d.arc_candidates(CIRCLE))
    assert " A " in d                                # surviving arc recovered
    # the vertical cut is one straight stretch, not arcs: its endpoints are
    # on the circle but the chord exceeds MAX_STEP
    assert 1 <= d.count(" L ") <= 4


def test_recovery_needs_candidates():
    g = geom2d.to_geom(circle_pts(50, 50, 30))
    assert " A " not in geom2d.path_d(g)             # no candidates: polylines


def test_crumb_polygons_culled_by_min_area():
    u = geom2d.union_all([geom2d.to_geom(sq(0, 0, 10, 10)),
                          geom2d.to_geom(sq(20, 20, 20.1, 20.1))])
    assert geom2d.path_d(u, min_area=0.2).count("M ") == 1
    assert geom2d.path_d(u).count("M ") == 2         # default keeps all


def test_arc_endpoints_are_ring_vertices():
    import re
    pts = circle_pts(50, 50, 30)
    d = geom2d.path_d(geom2d.to_geom(pts), geom2d.arc_candidates(CIRCLE))
    ring = {(round(x, 2), round(y, 2)) for x, y in pts}
    # arc endpoints (last two numbers of each A) must be actual ring
    # vertices so seams with neighbors and L stretches stay watertight
    ends = re.findall(r"A [\d.]+ [\d.]+ [\d.-]+ \d \d ([\d.-]+) ([\d.-]+)", d)
    assert ends and all((float(x), float(y)) in ring for x, y in ends)
