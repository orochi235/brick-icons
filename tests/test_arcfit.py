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
    # lopsided sweeps (45 vs 20 deg) with nothing to join to: the signature
    # of a fabricated fit (two chords of DIFFERENT true arcs); leave alone
    v0, v1, v2 = _circle_pts([0, 45, 65])
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
