import math
import shutil
import numpy as np
import pytest
from pathlib import Path
from brick_icons import hlr

LIB = Path("vendor/ldraw")
HAVE_LIB = LIB.exists()


def test_flatten_collects_typed_geometry(tmp_path):
    d = tmp_path / "t.dat"
    d.write_text(
        "2 24 0 0 0 1 0 0\n"
        "3 16 0 0 0 1 0 0 0 1 0\n"
        "5 24 0 0 0 1 0 0 0 1 0 0 -1 0\n"
    )
    out = {"2": [], "5": [], "tri": []}
    hlr.flatten(d, np.eye(3), np.zeros(3), out, roots=[tmp_path])
    assert len(out["2"]) == 1 and out["2"][0].shape == (2, 3)
    assert len(out["tri"]) == 1 and out["tri"][0].shape == (3, 3)
    assert len(out["5"]) == 1 and out["5"][0].shape == (4, 3)


def test_flatten_composes_subfile_transform(tmp_path):
    (tmp_path / "child.dat").write_text("2 24 0 0 0 1 0 0\n")
    parent = tmp_path / "parent.dat"
    parent.write_text("1 16 10 0 0 1 0 0 0 1 0 0 0 1 child.dat\n")
    out = {"2": [], "5": [], "tri": []}
    hlr.flatten(parent, np.eye(3), np.zeros(3), out, roots=[tmp_path])
    seg = out["2"][0]
    assert np.allclose(seg[0], [10, 0, 0]) and np.allclose(seg[1], [11, 0, 0])


def test_front_view_axes():
    # front (lat=0,long=0): +X -> +screen_x ; LDraw +Y(down) -> +screen_y (down)
    right, up, fwd = hlr.view_basis(0.0, 0.0)
    P = np.array([[1, 0, 0], [0, 1, 0]], float)
    sx, sy, z = hlr.project(P, right, up, fwd)
    assert sx[0] > 0.5 and abs(sy[0]) < 1e-6      # +X is rightward
    assert sy[1] > 0.5                            # +Y(down) projects downward


def test_view_basis_orthonormal():
    r, u, f = hlr.view_basis(30.0, 45.0)
    for v in (r, u, f):
        assert abs(np.linalg.norm(v) - 1) < 1e-9
    assert abs(r @ u) < 1e-9 and abs(r @ f) < 1e-9 and abs(u @ f) < 1e-9


def test_conditional_same_side_predicate():
    # control points on the same side -> drawn; opposite -> not
    p1 = np.array([0.0, 0.0]); p2 = np.array([1.0, 0.0])
    assert hlr.same_side(p1, p2, np.array([0.5, 1.0]), np.array([0.5, 2.0])) is True
    assert hlr.same_side(p1, p2, np.array([0.5, 1.0]), np.array([0.5, -2.0])) is False


def test_zbuffer_hides_segment_behind_face():
    # a near triangle covering the center; a segment far behind it is culled
    tri_s = np.array([[[10, 10], [90, 10], [50, 90]]], float)
    tri_z = np.array([[0.0, 0.0, 0.0]], float)        # near (small z)
    zbuf = hlr.rasterize_zbuffer(tri_s, tri_z, 100, 100)
    behind = hlr.clip_visible((30, 40, 70, 40, "edge"), zbuf, 100, 100, depth=5.0, bias=0.01)
    assert behind == []                                # fully hidden
    front = hlr.clip_visible((30, 40, 70, 40, "edge"), zbuf, 100, 100, depth=-5.0, bias=0.01)
    assert len(front) == 1                             # in front -> visible


def test_fit_segments_centers_in_box():
    segs = [(0.0, 0.0, 10.0, 0.0, "edge"), (0.0, 0.0, 0.0, 10.0, "edge")]
    fit = hlr.fit_segments(segs, (0, 0, 10, 10), 100, 100, margin=10, scale=1.0)
    assert all(s[0] == "line" for s in fit)            # normalized to op form
    xs = [c for s in fit for c in (s[1], s[3])]
    ys = [c for s in fit for c in (s[2], s[4])]
    assert min(xs) >= 9 and max(xs) <= 91 and min(ys) >= 9 and max(ys) <= 91


def test_fit_segments_scales_arc_ops():
    segs = [("arc", 5.0, 5.0, 4.0, 2.0, 30.0, 0.0, 90.0, "edge")]
    fit = hlr.fit_segments(segs, (0, 0, 10, 10), 100, 100, margin=10, scale=1.0)
    assert fit[0][0] == "arc"
    # bbox 10x10 into 80px -> factor 8; semi-axes scale by 8
    assert np.isclose(fit[0][3], 32.0) and np.isclose(fit[0][4], 16.0)
    assert fit[0][5] == 30.0                            # rotation unchanged


def test_visible_segments_empty_geometry(tmp_path):
    d = tmp_path / "empty.dat"
    d.write_text("0 just a comment, no geometry\n")
    segs, bbox = hlr.visible_segments(str(d), tmp_path, render_px=200)
    assert segs == []
    assert bbox == (0.0, 0.0, 1.0, 1.0)


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_visible_segments_on_real_part():
    segs, bbox = hlr.visible_segments("3701", LIB, lat=30, long=45, render_px=600)
    assert len(segs) > 50
    assert all(s[-1] in ("edge", "sil") for s in segs)
    assert bbox[2] > bbox[0] and bbox[3] > bbox[1]


def test_dilate_zbuffer_neighborhood_max():
    z = np.zeros((5, 5))
    z[2, 2] = 9.0                       # one far cell
    d = hlr.dilate_zbuffer(z, 1)
    assert d[2, 2] == 9.0
    assert d[1, 1] == 9.0 and d[2, 3] == 9.0   # spread to neighbors
    assert d[0, 0] == 0.0               # outside the neighborhood, unchanged
    assert np.array_equal(hlr.dilate_zbuffer(z, 0), z)   # r=0 is a no-op


def test_dilated_occlusion_recovers_tangent_but_not_buried():
    # a near surface (depth 0) covering x in [0,55]; background (inf) to the right
    tri_s = np.array([[[0, 0], [55, 0], [55, 100]],
                      [[0, 0], [55, 100], [0, 100]]], float)
    tri_z = np.zeros((2, 3))
    zbuf = hlr.rasterize_zbuffer(tri_s, tri_z, 100, 100)
    zdil = hlr.dilate_zbuffer(zbuf, 3)
    tangent = (53, 10, 53, 40, "edge")   # 2px inside the boundary -> background nearby
    buried = (20, 10, 20, 40, "edge")    # deep inside the near surface
    # plain occlusion culls the tangent edge; dilated occlusion recovers it
    assert hlr.clip_visible(tangent, zbuf, 100, 100, 5.0, 0.01) == []
    assert len(hlr.clip_visible(tangent, zdil, 100, 100, 5.0, 0.01)) >= 1
    # a genuinely buried edge stays hidden even with dilation
    assert hlr.clip_visible(buried, zdil, 100, 100, 5.0, 0.01) == []


def test_flatten_substitutes_known_primitive(tmp_path):
    (tmp_path / "p" / "48").mkdir(parents=True)
    (tmp_path / "p" / "48" / "1-4edge.dat").write_text("0 quarter edge\n")
    part = tmp_path / "thing.dat"
    part.write_text("1 16 0 0 0  1 0 0  0 1 0  0 0 1  p\\48\\1-4edge.dat\n")
    roots = hlr.default_roots(tmp_path)
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(part, np.eye(3), np.zeros(3), out, roots)
    assert len(out["analytic"]) == 1
    rec = out["analytic"][0]
    assert rec["kind"] == "edge" and rec["sector"] == 90.0
    assert np.allclose(rec["R"], np.eye(3)) and np.allclose(rec["t"], 0)


def test_flatten_unknown_primitive_recurses(tmp_path):
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "4-4ndis.dat").write_text("3 16 0 0 0  1 0 0  0 0 1\n")
    part = tmp_path / "thing.dat"
    part.write_text("1 16 0 0 0  1 0 0  0 1 0  0 0 1  p\\4-4ndis.dat\n")
    roots = hlr.default_roots(tmp_path)
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(part, np.eye(3), np.zeros(3), out, roots)
    assert len(out["analytic"]) == 0
    assert len(out["tri"]) == 1


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_visible_segments_emits_arcs_for_round_part():
    segs, bbox = hlr.visible_segments("3941", LIB, lat=30, long=45, render_px=900)
    assert any(o[0] == "arc" for o in segs)             # analytic curves present
    assert any(o[0] == "line" and o[-1] == "sil" for o in segs)  # cylinder silhouette
    assert bbox[2] > bbox[0] and bbox[3] > bbox[1]


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_3941_base_gap_resolution_stable():
    # The base silhouette (vertical side line) must reach down to the bottom-rim
    # arc at both resolutions: the lowest silhouette endpoint and the lowest arc
    # point should be within a few percent of the bbox height (no disconnect gap).
    for rpx in (900, 2048):
        segs, bbox = hlr.visible_segments("3941", LIB, lat=30, long=45, render_px=rpx)
        h = bbox[3] - bbox[1]
        sil_ys = [max(o[2], o[4]) for o in segs if o[0] == "line" and o[-1] == "sil"]
        arc_ys = []
        for o in segs:
            if o[0] == "arc":
                import numpy as _np
                from brick_icons import primitives as _P
                e = _P._ellipse_from_arc(o[1], o[2], o[3], o[4], o[5])
                pts = e.points(_np.radians(_np.linspace(o[6], o[7], 16)))
                arc_ys += list(pts[:, 1])
        assert sil_ys and arc_ys
        gap = abs(max(sil_ys) - max(arc_ys))
        assert gap < 0.05 * h, f"base gap {gap:.1f} too large at {rpx} (h={h:.1f})"
