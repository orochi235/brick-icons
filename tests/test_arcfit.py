"""Condline-guided arc fitting for hand-faceted rounds (e.g. 54200's
rounded top corners: raw quads with type-5 seams, no curve primitives)."""
import math
from pathlib import Path

import numpy as np
import pytest

from brick_icons import arcfit, hlr

LIB = Path("vendor/ldraw")
HAVE_LIB = LIB.exists()


def _circle_pts(deg_list, r=2.0, center=(0.0, 0.0, 0.0)):
    c = np.asarray(center, float)
    return [c + np.array([r * math.cos(math.radians(d)),
                          r * math.sin(math.radians(d)), 0.0])
            for d in deg_list]


def _edge(a, b):
    return np.array([a, b], float)


def _cond_at(p, q):
    """Type-5 row whose EDGE is p->q (control points are dummies off-plane)."""
    p, q = np.asarray(p, float), np.asarray(q, float)
    return np.array([p, q, p + [0, 0, 1], q + [0, 0, -1]], float)


def test_two_segment_corner_with_condline_fits_arc():
    v0, v1, v2 = _circle_pts([0, 45, 90])
    # tangent continuations at both ends, like a real rounded corner
    tang0 = _edge(v0, v0 + np.array([0, -10, 0]))    # tangent at 0 deg
    tang2 = _edge(v2, v2 + np.array([-10, 0, 0]))    # tangent at 90 deg
    edges = [_edge(v0, v1), _edge(v1, v2), tang0, tang2]
    conds = [_cond_at(v1, v1 + np.array([0, 0, 5.0]))]
    arcs, kept = arcfit.fit_edge_arcs(edges, conds)
    assert len(arcs) == 1 and len(kept) == 2
    arc = arcs[0]
    assert np.allclose(arc["C"], [0, 0, 0], atol=1e-6)
    assert math.isclose(np.linalg.norm(arc["U"]), 2.0, rel_tol=1e-6)
    assert math.isclose(abs(arc["t1"] - arc["t0"]), 90.0, abs_tol=1e-6)
    # endpoints of the arc are the chain ends
    ends = {tuple(np.round(arcfit.arc_point(arc, arc["t0"]), 6)),
            tuple(np.round(arcfit.arc_point(arc, arc["t1"]), 6))}
    assert ends == {tuple(np.round(v0, 6)), tuple(np.round(v2, 6))}


def test_tangency_constrains_fit_no_bulge():
    # interior vertex nudged outward (authoring slop): a plain 3-point circle
    # would overshoot the adjoining lines ("bread-loaf" bulge); the tangency
    # constraints must pin the circle so it joins the lines seamlessly
    c, r = np.array([3.0, 0.0, 0.0]), 3.0
    v0 = np.array([0.0, 0.0, 0.0])                   # angle 180
    v2 = np.array([3.0, 3.0, 0.0])                   # angle 90
    mid = c + (r + 0.008) * np.array([math.cos(math.radians(135)),
                                      math.sin(math.radians(135)), 0.0])
    tang0 = _edge(v0, v0 + np.array([0, -10, 0]))    # vertical line at v0
    tang2 = _edge(v2, v2 + np.array([10, 0, 0]))     # horizontal line at v2
    edges = [_edge(v0, mid), _edge(mid, v2), tang0, tang2]
    conds = [_cond_at(mid, mid + np.array([0, 0, 5.0]))]
    arcs, kept = arcfit.fit_edge_arcs(edges, conds)
    assert len(arcs) == 1 and len(kept) == 2
    assert np.allclose(arcs[0]["C"], c, atol=1e-9)
    assert math.isclose(np.linalg.norm(arcs[0]["U"]), r, rel_tol=1e-9)


def test_asymmetric_two_edge_chain_stays_lines():
    # lopsided sweeps (45 vs 9 deg, ratio 5) with nothing to join to: the
    # signature of a fabricated fit (two chords of DIFFERENT true arcs);
    # leave alone. Sited past 32062's axle end (4.16), the shallowest
    # fabricated fit in the specimen list -- see SYM_RATIO.
    v0, v1, v2 = _circle_pts([0, 45, 54])
    edges = [_edge(v0, v1), _edge(v1, v2)]
    conds = [_cond_at(v1, v1 + np.array([0, 0, 5.0]))]
    arcs, kept = arcfit.fit_edge_arcs(edges, conds)
    assert arcs == [] and len(kept) == 2


def test_symmetric_two_edge_chain_without_anchor_fits():
    # uniform subdivision (45/45) is how authors facet real rounds (axle
    # profile lobe tips join their flanks at a hard corner, so there is no
    # tangent anchor); the free fit must still recover it
    v0, v1, v2 = _circle_pts([0, 45, 90])
    edges = [_edge(v0, v1), _edge(v1, v2)]
    conds = [_cond_at(v1, v1 + np.array([0, 0, 5.0]))]
    arcs, kept = arcfit.fit_edge_arcs(edges, conds)
    assert len(arcs) == 1 and len(kept) == 0
    assert np.allclose(arcs[0]["C"], [0, 0, 0], atol=1e-6)


def test_misaligned_neighbors_do_not_distort_fit():
    # adjoining edges well off the end tangent must not anchor (and so not
    # drag) the fit; the symmetric chain still fits freely, exactly
    v0, v1, v2 = _circle_pts([0, 45, 90])
    off0 = _edge(v0, v0 + 10 * np.array([math.sin(math.radians(35)),
                                         -math.cos(math.radians(35)), 0.0]))
    off2 = _edge(v2, v2 + 10 * np.array([-math.cos(math.radians(35)),
                                         -math.sin(math.radians(35)), 0.0]))
    edges = [_edge(v0, v1), _edge(v1, v2), off0, off2]
    conds = [_cond_at(v1, v1 + np.array([0, 0, 5.0]))]
    arcs, kept = arcfit.fit_edge_arcs(edges, conds)
    assert len(arcs) == 1 and len(kept) == 2
    assert np.allclose(arcs[0]["C"], [0, 0, 0], atol=1e-6)


def test_junction_without_condline_stays_lines():
    v0, v1, v2 = _circle_pts([0, 45, 90])
    edges = [_edge(v0, v1), _edge(v1, v2)]
    arcs, kept = arcfit.fit_edge_arcs(edges, [])
    assert arcs == [] and len(kept) == 2


def test_collinear_chain_stays_lines():
    a, b, c = [0, 0, 0], [1, 0, 0], [2, 0, 0]
    edges = [_edge(a, b), _edge(b, c)]
    conds = [_cond_at(b, [1, 0, 5])]
    arcs, kept = arcfit.fit_edge_arcs(edges, conds)
    assert arcs == [] and len(kept) == 2


def test_hard_corner_stays_lines():
    a, b, c = [1, 0, 0], [0, 0, 0], [0, 1, 0]        # 90 deg turn at b
    edges = [_edge(a, b), _edge(b, c)]
    conds = [_cond_at(b, [0, 0, 5])]
    arcs, kept = arcfit.fit_edge_arcs(edges, conds)
    assert arcs == [] and len(kept) == 2


def test_tangent_straight_run_not_consumed():
    # 54200's shape: a 2-chord round whose end continues tangentially into a
    # long straight edge, every junction condline-marked. The straight edge's
    # far end is off the circle, so it must survive as a line.
    v0, v1, v2 = _circle_pts([0, 45, 90])
    tangent_dir = np.array([-1.0, 0.0, 0.0])         # tangent at 90 deg
    v3 = v2 + 16.0 * tangent_dir
    edges = [_edge(v0, v1), _edge(v1, v2), _edge(v2, v3)]
    conds = [_cond_at(v1, v1 + np.array([0, 0, 5.0])),
             _cond_at(v2, v2 + np.array([0, 0, 5.0]))]
    arcs, kept = arcfit.fit_edge_arcs(edges, conds)
    assert len(arcs) == 1 and len(kept) == 1
    assert math.isclose(abs(arcs[0]["t1"] - arcs[0]["t0"]), 90.0, abs_tol=1e-6)
    assert np.allclose(kept[0], _edge(v2, v3))


def test_fine_tessellation_stays_lines():
    # 7.5 deg steps (48-gon smoothness): primitive-grade tessellation is not
    # a hand-faceted round; leave it alone
    degs = [0, 7.5, 15, 22.5, 30]
    pts = _circle_pts(degs, r=20.0)
    edges = [_edge(pts[i], pts[i + 1]) for i in range(4)]
    conds = [_cond_at(p, p + np.array([0, 0, 5.0])) for p in pts[1:4]]
    arcs, kept = arcfit.fit_edge_arcs(edges, conds)
    assert arcs == [] and len(kept) == 4


def test_vertex_with_three_edges_is_not_smooth():
    v0, v1, v2 = _circle_pts([0, 45, 90])
    edges = [_edge(v0, v1), _edge(v1, v2), _edge(v1, [5, 5, 5])]
    conds = [_cond_at(v1, v1 + np.array([0, 0, 5.0]))]
    arcs, kept = arcfit.fit_edge_arcs(edges, conds)
    assert arcs == [] and len(kept) == 3


@pytest.mark.skipif(not HAVE_LIB, reason="vendor/ldraw missing")
def test_54200_renders_corner_arcs():
    res = hlr.visible_segments("54200", LIB)
    arcs = [op for op in res.segs if op[0] == "arc"]
    assert arcs, "cheese slope should emit fitted arcs for its rounded corners"
    assert all(op[-1] == "edge" for op in arcs)


@pytest.mark.skipif(not HAVE_LIB, reason="vendor/ldraw missing")
def test_3941_stud_truncation_fits_arcs():
    """stud10's lateral cut is two chords between two authored creases. The
    chord that continues past each crease lies half its own 22.5-degree sweep
    off the stud circle's tangent, which reads as a tangent continuation and
    anchored the fit onto a radius (4.7) the chain's own vertices are nowhere
    near. Rejecting the chain drew the whole truncated quarter as a kinked
    polyline against the smooth 270-degree arc beside it.
    """
    roots = hlr.default_roots(LIB)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(hlr._resolve_input("3941", roots), np.eye(3), np.zeros(3),
                out, roots)
    arcs, _kept = arcfit.fit_edge_arcs(out["2"], out["5"])
    studs = [a for a in arcs if abs(a["C"][1] + 4.0) < 1e-9]
    assert len(studs) == 4, "one truncation arc per stud"
    for a in studs:
        assert math.isclose(float(np.linalg.norm(a["U"])), 6.8, rel_tol=2e-3)


def test_a_false_tangent_anchor_falls_back_to_the_free_fit():
    """The unit form of the above: an off-tangent neighbour must not veto a
    chain whose own vertices sit on a circle."""
    v0, v1, v2 = _circle_pts([0, 22.5, 45])
    # a neighbour 12 degrees off the end tangent -- inside ANCHOR_ANG, but the
    # tangency it implies puts v1 well off any circle through v0 and v2
    d = np.array([math.cos(math.radians(-90 + 12)),
                  math.sin(math.radians(-90 + 12)), 0.0])
    edges = [_edge(v0, v1), _edge(v1, v2), _edge(v0, v0 + 10 * d)]
    conds = [_cond_at(v1, v1 + np.array([0, 0, 5.0]))]
    arcs, kept = arcfit.fit_edge_arcs(edges, conds)
    assert len(arcs) == 1 and len(kept) == 1
    assert math.isclose(np.linalg.norm(arcs[0]["U"]), 2.0, rel_tol=1e-6)


@pytest.mark.skipif(not HAVE_LIB, reason="vendor/ldraw missing")
def test_54200_inner_corner_rounds_are_not_read_as_lopsided():
    """The cheese slope's corner fillet is authored in even steps, but the
    crease where it meets the slope face is that fillet cut by a SLANTED
    plane, so it projects to an ellipse and its sweeps come out 1.57:1. Under
    a 1.25 cap that read as a fabricated fit and the inner corner drew as a
    38-degree kink beside the smooth outer one."""
    roots = hlr.default_roots(LIB)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(hlr._resolve_input("54200", roots), np.eye(3), np.zeros(3),
                out, roots)
    arcs, _kept = arcfit.fit_edge_arcs(out["2"], out["5"])
    ridge = [a for a in arcs if a["P"][:, 1].max() < -13.0]
    assert len(ridge) == 4, "both corners, outer ridge and inner crease"
    inner = [a for a in ridge if a["P"][:, 2].max() < 9.9]
    assert len(inner) == 2, "the inner crease of each corner"


@pytest.mark.skipif(not HAVE_LIB, reason="vendor/ldraw missing")
def test_32062_axle_end_is_still_too_lopsided_to_fit():
    """The other side of SYM_RATIO. 32062's axle-end bevel chains measure
    4.16:1 and are chords of DIFFERENT arcs, so a circle through them bulges
    OUTSIDE the axle: every arc the shipped cap admits stays within the
    profile's own 6.0 radius, and raising the cap past 4.16 pushes one to
    6.59 -- the blob the render shows at each end."""
    roots = hlr.default_roots(LIB)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(hlr._resolve_input("32062", roots), np.eye(3), np.zeros(3),
                out, roots)

    def worst_radius(cap):
        keep, arcfit.SYM_RATIO = arcfit.SYM_RATIO, cap
        try:
            arcs, _ = arcfit.fit_edge_arcs(out["2"], out["5"])
        finally:
            arcfit.SYM_RATIO = keep
        pts = np.array([arcfit.arc_point(a, t) for a in arcs
                        for t in np.linspace(a["t0"], a["t1"], 33)])
        return float(np.hypot(pts[:, 1], pts[:, 2]).max())

    assert worst_radius(arcfit.SYM_RATIO) == pytest.approx(6.0, abs=1e-3)
    assert worst_radius(5.0) > 6.5
