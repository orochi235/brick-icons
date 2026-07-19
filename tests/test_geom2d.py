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


def test_full_circle_ring_recovers_quarter_arcs():
    # <=90 deg chunks: near-180 spans have near-antipodal endpoints, which
    # amplify coordinate rounding into a visible center shift when the
    # renderer re-derives the ellipse center from the endpoints
    g = geom2d.to_geom(circle_pts(50, 50, 30))
    d = geom2d.path_d(g, geom2d.arc_candidates(CIRCLE))
    # 4 chunks nominally; float noise at exact 90-deg boundaries may split 5
    assert 4 <= d.count(" A ") <= 5 and " L " not in d


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


def test_candidate_step_override_recovers_coarse_arc():
    # square whose top-right corner is a 2-chord 90 deg round (45 deg per
    # edge, far beyond MAX_STEP): only a candidate carrying its own step
    # (7th element, degrees) may recover it
    r = 20.0
    corner = circle_pts(80, 20, r, n=3, t0=-np.pi / 2, t1=0.0)  # (80,0)->(100,20)
    ring = np.vstack([[[0, 0]], corner, [[100, 100], [0, 100]]])
    g = geom2d.to_geom(ring)
    coarse = [(80.0, 20.0, r, 0.0, 0.0, r, 50.0)]
    assert " A " in geom2d.path_d(g, geom2d.arc_candidates(coarse))
    default = [(80.0, 20.0, r, 0.0, 0.0, r)]
    assert " A " not in geom2d.path_d(g, geom2d.arc_candidates(default))


def test_buffer_d_mitered_square():
    # outward buffer with mitered joins: corners stay sharp (vertex at
    # (-1,-1)) and the boundary is pure polyline
    d = geom2d.buffer_d(geom2d.to_geom(sq(0, 0, 10, 10)), 1.0)
    assert "-1.00 -1.00" in d and "11.00 11.00" in d
    assert " A " not in d


def test_buffer_d_shrinks_holes():
    outer = geom2d.to_geom(sq(0, 0, 20, 20))
    hole = geom2d.to_geom(sq(8, 8, 12, 12))
    d = geom2d.buffer_d(geom2d.difference(outer, hole), 1.0)
    assert d.count("M ") == 2                       # ring + hole survive
    assert "9.00 9.00" in d                         # hole shrank by 1


def test_rings_returns_exterior_and_holes():
    g = geom2d.difference(geom2d.to_geom(sq(0, 0, 20, 20)),
                          geom2d.to_geom(sq(8, 8, 12, 12)))
    rs = geom2d.rings(g)
    assert len(rs) == 2 and all(r.shape[1] == 2 for r in rs)


def test_contour_d_dissolves_hairline_slivers():
    # face-sampling mismatches leave hairline sliver holes along interior
    # rims; stroked as a contour they render as ticks. contour_d must
    # dissolve them; plain path_d keeps them (fills care about exactness)
    outer = geom2d.to_geom(sq(0, 0, 20, 20))
    sliver = geom2d.to_geom(np.array([(5, 10), (15, 10), (15, 10.02), (5, 10.02)], float))
    g = geom2d.difference(outer, sliver)
    assert geom2d.path_d(g).count("M ") == 2         # sliver hole is real
    d = geom2d.contour_d(g)
    assert d.count("M ") == 1                        # ...but not a contour
    assert "0.00 0.00" in d and "20.00 20.00" in d   # outline unchanged


def test_contour_d_drops_subpixel_rings():
    outer = geom2d.to_geom(sq(0, 0, 20, 20))
    dot = geom2d.to_geom(np.array([(10, 10), (10.5, 10), (10.5, 10.5), (10, 10.5)], float))
    d = geom2d.contour_d(geom2d.difference(outer, dot))
    assert d.count("M ") == 1


def test_densify_on_arcs_subdivides_facet_chords():
    # a 16-gon ring inscribed in a candidate circle (22.5 deg steps): edges
    # on the candidate get intermediate TRUE-circle vertices so booleans cut
    # along the circle, not the chords; off-circle edges stay untouched
    ring = np.vstack([circle_pts(50, 50, 30, n=16), [[120, 50], [120, 120], [50, 120]]])
    cands = geom2d.arc_candidates([(50.0, 50.0, 30.0, 0.0, 0.0, 30.0, 25.0)])
    out = geom2d.densify_on_arcs(ring, cands)
    assert len(out) > len(ring) + 30            # 16-gon edges subdivided
    d = np.abs(np.hypot(out[:, 0] - 50, out[:, 1] - 50) - 30)
    on_circle = (d < 1e-6).sum()
    assert on_circle >= 16 + 15 * 3             # originals + 3 inserted/edge
    # the three appended square corners survive verbatim
    for p in [[120, 50], [120, 120], [50, 120]]:
        assert (np.abs(out - p).sum(axis=1) < 1e-9).any()


def test_densify_without_candidates_is_identity():
    ring = circle_pts(50, 50, 30, n=16)
    out = geom2d.densify_on_arcs(ring, [])
    assert np.array_equal(out, ring)



def test_densify_snaps_vertices_onto_loose_tol_candidate():
    # A fitted-arc candidate carries a per-candidate snap tolerance (8th
    # ellipse element): arcfit's stylized arcs deviate from the authored
    # facet corners by more than ARC_TOL, so fills following the authored
    # vertices scallop outside the drawn stroke (3941's X outline). Ring
    # vertices within the tolerance snap ONTO the ellipse and the edge
    # densifies along it.
    import math
    a = math.radians(22.5)
    ring = np.array([[10.5, 0.0],
                     [10.2 * math.cos(a), 10.2 * math.sin(a)],
                     [2.0, 6.0]])
    cands = geom2d.arc_candidates([(0, 0, 10, 0, 0, 10, 30.0, 1.0)])
    out = geom2d.densify_on_arcs(ring, cands)
    r = np.hypot(out[:, 0], out[:, 1])
    on = np.abs(r - 10.0) < 1e-6
    assert on.sum() >= 4                 # 2 snapped corners + inserted points
    assert not (np.abs(out - [10.5, 0.0]).sum(axis=1) < 1e-9).any()
    assert (np.abs(out - [2.0, 6.0]).sum(axis=1) < 1e-9).any()  # bystander


def test_densify_tight_tol_leaves_off_arc_vertices_alone():
    # without the 8th element the old contract holds: off-ellipse vertices
    # (beyond ARC_TOL) are untouched
    import math
    a = math.radians(22.5)
    ring = np.array([[10.5, 0.0],
                     [10.2 * math.cos(a), 10.2 * math.sin(a)],
                     [2.0, 6.0]])
    cands = geom2d.arc_candidates([(0, 0, 10, 0, 0, 10, 30.0)])
    out = geom2d.densify_on_arcs(ring, cands)
    assert np.array_equal(out, ring)


# --- wide-pass arc recovery (contour silhouettes) ---------------------------

def _half_disc(step_deg, r=30.0, jitter=0.0):
    """Upper half-disc ring sampled at step_deg, closed by the diameter
    chord. `jitter` pushes every other vertex radially outward."""
    n = int(round(180.0 / step_deg)) + 1
    t = np.linspace(0.0, np.pi, n)
    rr = np.full(n, r)
    if jitter:
        rr[1::2] += jitter
    return np.stack([50 + rr * np.cos(t), 50 + rr * np.sin(t)], 1)


def test_wide_recovery_snaps_jittered_horizon_run():
    # 2654a's dome horizon: a cone-stack silhouette whose vertices sit
    # alternately ON the footprint circle and ~0.1 px off it (frustum seam
    # rims project slightly inside/outside). Strict ARC_TOL fragments the
    # run into lone edges -> all polylines; the contour's wide pass accepts
    # the run and emits arcs.
    g = geom2d.to_geom(_half_disc(3.0, jitter=0.1))
    cands = geom2d.arc_candidates(CIRCLE)
    assert " A " not in geom2d.path_d(g, cands)          # strict: fragmented
    d = geom2d.path_d(g, cands, wide=True)
    assert " A " in d
    assert d.count(" L ") <= 2                           # diameter chord only


def test_wide_recovery_accepts_facet_grade_sweeps():
    # 3941's truncated rear studs: authored facet rims sweep ~19 deg per
    # edge (beyond MAX_STEP) with vertices on the stud circle. The wide
    # pass admits facet-grade steps for multi-edge runs.
    g = geom2d.to_geom(_half_disc(18.0))
    cands = geom2d.arc_candidates(CIRCLE)
    assert " A " not in geom2d.path_d(g, cands)
    d = geom2d.path_d(g, cands, wide=True)
    assert " A " in d and d.count(" L ") <= 2


def test_wide_recovery_keeps_coarse_polygons_faceted():
    # a hexagon inscribed in the candidate circle has every vertex ON it —
    # only the 60-deg sweep says it is an intentional polygon. It must
    # survive the wide pass untouched.
    g = geom2d.to_geom(_half_disc(60.0))
    assert " A " not in geom2d.path_d(g, geom2d.arc_candidates(CIRCLE),
                                      wide=True)


def test_wide_recovery_demotes_short_wide_runs():
    # two facet-grade edges alone (a chamfer that merely touches the
    # circle) are not evidence of a round: wide-pass runs need >= 3 edges.
    t = np.radians([0.0, 20.0, 40.0])
    arc = np.stack([50 + 30 * np.cos(t), 50 + 30 * np.sin(t)], 1)
    ring = np.vstack([arc, [[95.0, 95.0], [95.0, 40.0]]])
    d = geom2d.path_d(geom2d.to_geom(ring), geom2d.arc_candidates(CIRCLE),
                      wide=True)
    assert " A " not in d


def test_negative_snap_tol_pulls_inward_only():
    # facet-hugged rim candidates (hlr/facet_snap_rims) snap chord
    # tessellation onto the circle. Tessellation only ever sits INSIDE the
    # true circle, so their tolerance is one-sided (encoded negative):
    # an inset vertex snaps out onto the arc, while a vertex the same
    # distance OUTSIDE the circle is untouched geometry and must not move
    # (3941's body rim grew a white crescent when it did).
    import math
    a = math.radians(22.5)
    ring = np.array([[9.6, 0.0],
                     [9.6 * math.cos(a), 9.6 * math.sin(a)],
                     [10.4, 8.0]])
    cands = geom2d.arc_candidates([(0, 0, 10, 0, 0, 10, 25.0, -0.5)])
    out = geom2d.densify_on_arcs(ring, cands)
    r = np.hypot(out[:, 0], out[:, 1])
    assert (np.abs(r - 10.0) < 1e-6).sum() >= 2       # inset pair snapped
    assert (np.abs(out - [10.4, 8.0]).sum(axis=1) < 1e-9).any()  # outsider
