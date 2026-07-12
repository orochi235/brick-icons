import math
import shutil
import numpy as np
import pytest
from pathlib import Path
from brick_icons import hlr, primitives

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


def test_flatten_populates_tri_meta_parallel_to_tri(tmp_path):
    from brick_icons import hlr
    import numpy as np
    # A minimal certified part: one CCW triangle, no subfiles.
    p = tmp_path / "cert.dat"
    p.write_text("0 BFC CERTIFY CCW\n3 16 0 0 0 10 0 0 0 10 0\n")
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(p, np.eye(3), np.zeros(3), out, [tmp_path])
    assert len(out["tri"]) == 1
    assert len(out["tri_meta"]) == 1
    assert out["tri_meta"][0] == {"certified": True, "invert": False}


def test_flatten_uncertified_marks_meta(tmp_path):
    from brick_icons import hlr
    import numpy as np
    p = tmp_path / "plain.dat"          # no BFC line at all
    p.write_text("3 16 0 0 0 10 0 0 0 10 0\n")
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(p, np.eye(3), np.zeros(3), out, [tmp_path])
    assert out["tri_meta"][0]["certified"] is False


def test_flatten_invertnext_flips_winding_flag(tmp_path):
    from brick_icons import hlr
    import numpy as np
    child = tmp_path / "child.dat"
    child.write_text("0 BFC CERTIFY CCW\n3 16 0 0 0 10 0 0 0 10 0\n")
    parent = tmp_path / "parent.dat"
    parent.write_text(
        "0 BFC CERTIFY CCW\n"
        "0 BFC INVERTNEXT\n"
        "1 16 0 0 0 1 0 0 0 1 0 0 0 1 child.dat\n")
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(parent, np.eye(3), np.zeros(3), out, [tmp_path])
    assert out["tri_meta"][0]["invert"] is True     # INVERTNEXT toggled it


def test_flatten_negative_determinant_flips_winding_flag(tmp_path):
    from brick_icons import hlr
    import numpy as np
    child = tmp_path / "child.dat"
    child.write_text("0 BFC CERTIFY CCW\n3 16 0 0 0 10 0 0 0 10 0\n")
    parent = tmp_path / "parent.dat"       # mirror on X: det < 0
    parent.write_text(
        "0 BFC CERTIFY CCW\n"
        "1 16 0 0 0 -1 0 0 0 1 0 0 0 1 child.dat\n")
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(parent, np.eye(3), np.zeros(3), out, [tmp_path])
    assert out["tri_meta"][0]["invert"] is True     # reflection toggled it


def test_flatten_quad_emits_two_tri_meta_entries(tmp_path):
    from brick_icons import hlr
    import numpy as np
    p = tmp_path / "quad.dat"
    p.write_text("0 BFC CERTIFY CCW\n4 16 0 0 0 10 0 0 10 10 0 0 10 0\n")
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(p, np.eye(3), np.zeros(3), out, [tmp_path])
    assert len(out["tri"]) == 2
    assert len(out["tri_meta"]) == 2
    assert out["tri_meta"][0] == out["tri_meta"][1] == {"certified": True, "invert": False}


def test_flatten_invertnext_does_not_leak_to_sibling(tmp_path):
    from brick_icons import hlr
    import numpy as np
    child = tmp_path / "child.dat"
    child.write_text("0 BFC CERTIFY CCW\n3 16 0 0 0 10 0 0 0 10 0\n")
    parent = tmp_path / "parent.dat"
    parent.write_text(
        "0 BFC CERTIFY CCW\n"
        "0 BFC INVERTNEXT\n"
        "1 16 0 0 0 1 0 0 0 1 0 0 0 1 child.dat\n"    # inverted
        "1 16 0 0 0 1 0 0 0 1 0 0 0 1 child.dat\n")   # sibling, NOT inverted
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(parent, np.eye(3), np.zeros(3), out, [tmp_path])
    assert out["tri_meta"][0]["invert"] is True     # first ref inverted
    assert out["tri_meta"][1]["invert"] is False    # sibling not inverted


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
    # parametric arc op: ('arc', cx, cy, ux, uy, vx, vy, t0, t1, kind)
    segs = [("arc", 5.0, 5.0, 4.0, 0.0, 0.0, 2.0, 0.0, 90.0, "edge")]
    fit = hlr.fit_segments(segs, (0, 0, 10, 10), 100, 100, margin=10, scale=1.0)
    assert fit[0][0] == "arc"
    # bbox 10x10 into 80px -> factor 8, offset 10; center 5*8+10=50; u,v scale by 8
    assert np.isclose(fit[0][1], 50.0) and np.isclose(fit[0][2], 50.0)
    assert np.isclose(fit[0][3], 32.0) and np.isclose(fit[0][6], 16.0)
    assert fit[0][7] == 0.0 and fit[0][8] == 90.0       # param range unchanged


def test_visible_segments_unresolvable_part_raises():
    with pytest.raises(FileNotFoundError):
        hlr.visible_segments("definitely-not-a-part", "vendor/ldraw", render_px=200)


def test_visible_segments_missing_dat_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        hlr.visible_segments(str(tmp_path / "nope.ldr"), tmp_path, render_px=200)


def test_visible_segments_empty_geometry(tmp_path):
    d = tmp_path / "empty.dat"
    d.write_text("0 just a comment, no geometry\n")
    res = hlr.visible_segments(str(d), tmp_path, render_px=200)
    assert res.segs == []
    assert res.bbox == (0.0, 0.0, 1.0, 1.0)


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_visible_segments_on_real_part():
    res = hlr.visible_segments("3701", LIB, lat=30, long=45, render_px=600)
    assert len(res.segs) > 50
    assert all(s[-1] in ("edge", "sil") for s in res.segs)
    assert res.bbox[2] > res.bbox[0] and res.bbox[3] > res.bbox[1]


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
    prim = out["analytic"][0]
    assert isinstance(prim, primitives.Edge) and prim.sector == 90.0
    assert np.allclose(prim.R, np.eye(3)) and np.allclose(prim.t, 0)


def test_flatten_aliases_stud10_to_full_stud(tmp_path):
    """stud10 (laterally truncated stud for round 2x2 parts) must resolve as
    a plain full stud: its faceted outward quarter (4 chord quads + 2 hard
    vertical joint edges + chorded top rim) renders as stripes and tone bands
    on the front stud of 3941. The truncation it models is <= 0.14 LDU —
    invisible at icon scale — so the icon substitutes the analytic stud."""
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "stud10.dat").write_text(
        "4 16 6 0 0  5.6145 0 1.9397  5.6145 -4 1.9397  6 -4 0\n")
    (tmp_path / "p" / "stud.dat").write_text(
        "1 16 0 0 0 6 0 0 0 -4 0 0 0 6 4-4cyli.dat\n"
        "1 16 0 -4 0 6 0 0 0 1 0 0 0 6 4-4disc.dat\n")
    part = tmp_path / "thing.dat"
    part.write_text("1 16 0 0 0  1 0 0  0 1 0  0 0 1  p\\stud10.dat\n")
    roots = hlr.default_roots(tmp_path)
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(part, np.eye(3), np.zeros(3), out, roots)
    kinds = sorted(p.kind for p in out["analytic"])
    assert kinds == ["cyli", "disc"]          # stud.dat contents, not stud10's
    assert out["tri"] == []                   # faceted quarter suppressed


def test_flatten_unknown_primitive_recurses(tmp_path):
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "1-16tndis.dat").write_text("3 16 0 0 0  1 0 0  0 0 1\n")
    part = tmp_path / "thing.dat"
    part.write_text("1 16 0 0 0  1 0 0  0 1 0  0 0 1  p\\1-16tndis.dat\n")
    roots = hlr.default_roots(tmp_path)
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(part, np.eye(3), np.zeros(3), out, roots)
    assert len(out["analytic"]) == 0
    assert len(out["tri"]) == 1


def test_analytic_cone_occludes_edge_behind_it():
    # A wide con0 with a straight type-2 edge passing horizontally BEHIND its
    # midsection: the visible edge must be split into two runs by the cone.
    # fwd = (0,0,1): larger z = farther. Edge at z=+20 passes behind the cone
    # midsection (world y=5, where the con0 scaled x10 has radius 5).
    out = {"2": [np.array([[-40.0, 5.0, 20.0], [40.0, 5.0, 20.0]])],
           "5": [], "tri": [], "tri_meta": [],
           "analytic": [primitives.Cone(R=np.diag([10.0, 10.0, 10.0]),
                                        t=np.zeros(3), sector=360.0,
                                        top=0.0)]}
    right, up, fwd = hlr.view_basis(0.0, 0.0)     # straight-on view
    res = hlr._visible_segments_analytic(out, right, up, fwd, render_px=200)
    edge_segs = [sg for sg in res.segs if sg[0] == "line" and sg[-1] == "edge"]
    assert len(edge_segs) == 2                    # hidden midsection removed


def test_stacked_cones_one_wall_face_with_own_occluder_ordering():
    # Two smooth-stacked frustums (same infinite cone): the fill pipeline
    # merges them into ONE outer wall face, and the synthetic merged primitive —
    # absent from the per-input-primitive occluder cache — must still get an own
    # occluder so witness ordering uses exact cone depths: the interior far
    # wall paints before the outer near wall.
    out = {"2": [], "5": [], "tri": [], "tri_meta": [],
           "analytic": [primitives.Cone(R=np.diag([10.0, 10.0, 10.0]),
                                        t=np.zeros(3), sector=360.0, top=2.0),
                        primitives.Cone(R=np.diag([10.0, 10.0, 10.0]),
                                        t=np.array([0.0, 10.0, 0.0]),
                                        sector=360.0, top=1.0)]}
    right, up, fwd = hlr.view_basis(20.0, 30.0)
    from brick_icons import shade
    seen = {}
    real_order = shade.order_faces

    def spy(faces, *a, own_occ=None, **kw):
        seen.update({id(f): own_occ.get(id(f)) for f in faces
                     if f.get("kind") in ("con", "cyli")})
        return real_order(faces, *a, own_occ=own_occ, **kw)

    shade.order_faces = spy
    try:
        res = hlr._visible_segments_analytic(out, right, up, fwd, render_px=200)
    finally:
        shade.order_faces = real_order
    outer = [f for f in res.faces if f["kind"] == "con" and not f.get("interior")]
    inner = [f for f in res.faces if f["kind"] == "con" and f.get("interior")]
    assert len(outer) == 1 and len(inner) == 1
    assert inner[0]["order"] < outer[0]["order"]
    # exact curved ordering requires an own occluder on EVERY wall face,
    # including ones whose merged primitive is synthesized inside shade
    assert seen and all(occ is not None for occ in seen.values())


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_cone_part_uses_analytic_cones():
    # 4589 (cone 1x1) body = 4-4con3 + 4-4con4: must arrive as analytic
    # primitives with cone occluders and produce cone wall fills, not tri clouds.
    res = hlr.visible_segments("4589", LIB, lat=30, long=45, render_px=900)
    assert "con" in {p.kind for p in res.analytic}
    con_faces = [f for f in res.faces if f.get("kind") == "con"]
    assert con_faces
    # fit cloud must cover the cone BASE (local radius N+1, not 1): every cone
    # wall vertex stays inside the render canvas
    for f in con_faces:
        assert f["poly"].min() >= 0.0 and f["poly"].max() <= 900.0
    # the con3/con4 joint circle is a smooth continuation: no drawn arc there
    # (it showed as a spurious black ring). The joint plane is at the shared
    # rim; assert fewer edge arcs than the naive 2-per-cone.
    con_prims = [p for p in res.analytic if isinstance(p, primitives.Cone)]
    assert len(con_prims) == 2


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_dish_top_merges_to_few_gradient_paths():
    # 3960's dish: hundreds of seam-grouped facets must merge to a handful of
    # fill ops (one region per smooth/coplanar surface), not one per facet.
    from brick_icons import shade
    res = hlr.visible_segments("3960", LIB, lat=30, long=45, render_px=900)
    ops = shade.fill_ops(res.faces, shade.Flat3Style())
    grads = [o for o in ops if "gradient" in o]
    assert 0 < len(grads) < 25
    assert len(ops) < 80


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_fragments_are_disjoint_no_hidden_fills():
    import re as _re
    from brick_icons import geom2d, shade
    res = hlr.visible_segments("3005", LIB, lat=30, long=45, render_px=900)
    ops = shade.fill_ops(res.faces, shade.Flat3Style())

    def to_geom(op):
        rings = []
        for sub in op["d"].split("M ")[1:]:
            pts = _re.findall(r"(-?\d+\.?\d*) (-?\d+\.?\d*)", sub)
            rings.append(np.array(pts, float))
        return geom2d.to_geom(rings[0], holes=rings[1:])

    gs = [to_geom(o) for o in ops]
    total = sum(geom2d.area(g) for g in gs)
    union = geom2d.area(geom2d.union_all(gs))
    assert union > 0
    assert abs(total - union) < 0.01 * union      # no overdraw: disjoint fragments


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_visible_segments_emits_arcs_for_round_part():
    res = hlr.visible_segments("3941", LIB, lat=30, long=45, render_px=900)
    assert any(o[0] == "arc" for o in res.segs)             # analytic curves present
    assert any(o[0] == "line" and o[-1] == "sil" for o in res.segs)  # cylinder silhouette
    assert res.bbox[2] > res.bbox[0] and res.bbox[3] > res.bbox[1]


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_visible_segments_returns_scale_factor():
    from brick_icons import hlr
    res = hlr.visible_segments("3005", "vendor/ldraw", render_px=400)
    assert res.s > 0
    assert isinstance(res.faces, list) and isinstance(res.analytic, list)
    # 3005 is a 1x1 brick: footprint 20 LDU. bbox px width / s is a few tens of LDU.
    bx0, by0, bx1, by1 = res.bbox
    ldu_w = (bx1 - bx0) / res.s
    assert 10 < ldu_w < 60


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_3941_base_silhouette_connects_to_rim():
    # The historic artifact: the body's vertical side silhouette did not connect
    # to the bottom-rim arc (a visible gap at the tangent), and the dilation fix
    # was resolution-fragile. With exact analytic occlusion the lower endpoint of
    # each tall body silhouette must sit on the bottom-rim arc at BOTH resolutions.
    from brick_icons import primitives as _P
    for rpx in (900, 2048):
        res = hlr.visible_segments("3941", LIB, lat=30, long=45, render_px=rpx)
        segs, bbox = res.segs, res.bbox
        diag = math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1])
        # arc sample cloud
        apts = []
        for o in segs:
            if o[0] == "arc":
                p = _P.arc_ellipse(o).points(np.radians(np.linspace(o[7], o[8], 64)))
                apts += [tuple(q) for q in p]
        apts = np.array(apts)
        # the two longest silhouette lines are the body's left/right sides
        sils = [o for o in segs if o[0] == "line" and o[-1] == "sil"]
        sils.sort(key=lambda o: math.hypot(o[3] - o[1], o[4] - o[2]), reverse=True)
        assert len(sils) >= 2 and len(apts) > 0
        for o in sils[:2]:
            low = np.array([o[1], o[2]]) if o[2] > o[4] else np.array([o[3], o[4]])
            d = np.min(np.hypot(apts[:, 0] - low[0], apts[:, 1] - low[1]))
            assert d < 0.02 * diag, f"silhouette base gap {d:.1f}px at {rpx} (diag {diag:.0f})"


def test_fit_affine_matches_fit_segments():
    from brick_icons import hlr
    bbox = (0.0, 0.0, 100.0, 50.0)
    f, ox, oy = hlr.fit_affine(bbox, W=256, H=170, margin=6, scale=1.0)
    seg = ("line", 0.0, 0.0, 100.0, 50.0, "edge")
    out = hlr.fit_segments([seg], bbox, 256, 170, 6, 1.0)[0]
    assert out[1] == 0.0 * f + ox and out[2] == 0.0 * f + oy
    assert abs(out[3] - (100.0 * f + ox)) < 1e-9


def test_flatten_mirror_invert_survives_nested_reference(tmp_path):
    """A mirror at level 1 must still flip winding for geometry at level 2+.
    The old code recomputed reflection from the ACCUMULATED matrix while also
    inheriting the parent's invert — every ancestor mirror XORed twice and
    cancelled (32062's mirrored axle end, 4019's mirrored gear half)."""
    import numpy as np
    from brick_icons import hlr
    leaf = tmp_path / "leaf.dat"
    leaf.write_text("0 BFC CERTIFY CCW\n3 16 0 0 0 10 0 0 0 10 0\n")
    mid = tmp_path / "mid.dat"          # plain pass-through reference
    mid.write_text("0 BFC CERTIFY CCW\n"
                   "1 16 0 0 0 1 0 0 0 1 0 0 0 1 leaf.dat\n")
    top = tmp_path / "top.dat"          # X mirror at the TOP level
    top.write_text("0 BFC CERTIFY CCW\n"
                   "1 16 0 0 0 -1 0 0 0 1 0 0 0 1 mid.dat\n")
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(top, np.eye(3), np.zeros(3), out, [tmp_path])
    assert out["tri_meta"][0]["invert"] is True   # one mirror => flipped


# --- dedupe_segments --------------------------------------------------------

def test_dedupe_collapses_duplicate_lines():
    seg = ("line", 0.0, 0.0, 10.0, 0.0, "edge")
    assert len(hlr.dedupe_segments([seg, seg, seg])) == 1


def test_dedupe_merges_overlapping_collinear_spans():
    a = ("line", 0.0, 0.0, 6.0, 0.0, "edge")
    b = ("line", 4.0, 0.0, 10.0, 0.0, "edge")
    (out,) = hlr.dedupe_segments([a, b])
    xs = sorted([out[1], out[3]])
    assert xs[0] == pytest.approx(0.0) and xs[1] == pytest.approx(10.0)


def test_dedupe_preserves_occlusion_gaps():
    a = ("line", 0.0, 0.0, 4.0, 0.0, "edge")
    b = ("line", 6.0, 0.0, 10.0, 0.0, "edge")   # 2 px gap: a real break
    assert len(hlr.dedupe_segments([a, b])) == 2


def test_dedupe_keeps_distinct_parallel_lines():
    a = ("line", 0.0, 0.0, 10.0, 0.0, "edge")
    b = ("line", 0.0, 1.0, 10.0, 1.0, "edge")
    assert len(hlr.dedupe_segments([a, b])) == 2


def test_dedupe_keeps_kinds_separate():
    a = ("line", 0.0, 0.0, 10.0, 0.0, "edge")
    b = ("line", 0.0, 0.0, 10.0, 0.0, "sil")    # widths may differ
    assert len(hlr.dedupe_segments([a, b])) == 2


def test_dedupe_collapses_duplicate_full_circles():
    c = ("arc", 50.0, 50.0, 30.0, 0.0, 0.0, 30.0, 0.0, 360.0, "edge")
    out = hlr.dedupe_segments([c, c, c])
    assert len(out) == 1 and abs(out[0][8] - out[0][7]) >= 359.9


def test_dedupe_merges_same_circle_different_parametrization():
    # same circle drawn with a rotated (u, v) frame: 90-deg phase shift
    a = ("arc", 0.0, 0.0, 10.0, 0.0, 0.0, 10.0, 0.0, 90.0, "edge")
    b = ("arc", 0.0, 0.0, 0.0, 10.0, -10.0, 0.0, 0.0, 90.0, "edge")  # = 90..180
    (out,) = hlr.dedupe_segments([a, b])
    assert abs(out[8] - out[7]) == pytest.approx(180.0, abs=0.1)


def test_dedupe_keeps_disjoint_arcs_of_one_circle():
    a = ("arc", 0.0, 0.0, 10.0, 0.0, 0.0, 10.0, 0.0, 45.0, "edge")
    b = ("arc", 0.0, 0.0, 10.0, 0.0, 0.0, 10.0, 180.0, 225.0, "edge")
    assert len(hlr.dedupe_segments([a, b])) == 2


def test_dedupe_wraparound_arcs_merge():
    a = ("arc", 0.0, 0.0, 10.0, 0.0, 0.0, 10.0, 300.0, 360.0, "edge")
    b = ("arc", 0.0, 0.0, 10.0, 0.0, 0.0, 10.0, 0.0, 60.0, "edge")
    (out,) = hlr.dedupe_segments([a, b])
    assert abs(out[8] - out[7]) == pytest.approx(120.0, abs=0.1)


def test_dedupe_legacy_tuples_normalized():
    out = hlr.dedupe_segments([(0.0, 0.0, 5.0, 0.0, "edge"),
                               (0.0, 0.0, 5.0, 0.0, "edge")])
    assert out == [("line", 0.0, 0.0, 5.0, 0.0, "edge")]


def _arc_radii(res):
    """World radii of the arc ops in a VisResult: a projected circle's major
    semi-axis is the unforeshortened radius, in px (divide out the fit)."""
    radii = set()
    for op in res.segs:
        if op[0] != "arc":
            continue
        M = np.array([[op[3], op[5]], [op[4], op[6]]], float)
        radii.add(round(float(np.linalg.svd(M, compute_uv=False)[0]) / res.s, 2))
    return sorted(radii)


def test_coplanar_ring_seam_suppressed():
    # two full rings tiling one flat annulus (1..2 and 2..3): their shared
    # r=2 circle is an interior seam, not an edge — only 1 and 3 draw
    out = {"2": [], "5": [], "tri": [], "tri_meta": [],
           "analytic": [primitives.Ring(R=np.eye(3), t=np.zeros(3),
                                        sector=360.0, inner=1),
                        primitives.Ring(R=np.eye(3), t=np.zeros(3),
                                        sector=360.0, inner=2)]}
    res = hlr._visible_segments_analytic(out, *hlr.view_basis(30, 45), 300)
    assert _arc_radii(res) == [1.0, 3.0]


def test_disc_ring_seam_suppressed():
    # a disc (r=1) continued by a ring (1..2): the r=1 circle is a seam
    out = {"2": [], "5": [], "tri": [], "tri_meta": [],
           "analytic": [primitives.Disc(R=np.eye(3), t=np.zeros(3), sector=360.0),
                        primitives.Ring(R=np.eye(3), t=np.zeros(3),
                                        sector=360.0, inner=1)]}
    res = hlr._visible_segments_analytic(out, *hlr.view_basis(30, 45), 300)
    assert _arc_radii(res) == [2.0]


def test_ring_seam_kept_across_planes():
    # same radii but different planes: r=2 is a real edge on both, kept
    out = {"2": [], "5": [], "tri": [], "tri_meta": [],
           "analytic": [primitives.Ring(R=np.eye(3), t=np.zeros(3),
                                        sector=360.0, inner=1),
                        primitives.Ring(R=np.eye(3), t=np.array([0.0, 4.0, 0.0]),
                                        sector=360.0, inner=2)]}
    res = hlr._visible_segments_analytic(out, *hlr.view_basis(30, 45), 300)
    assert _arc_radii(res) == [1.0, 2.0, 3.0]


def _arc_pt(op, t):
    th = math.radians(t)
    return np.array([op[1] + math.cos(th) * op[3] + math.sin(th) * op[5],
                     op[2] + math.cos(th) * op[4] + math.sin(th) * op[6]])


def _counterbore_trio():
    # F: full opening circle. B: smaller bore arc (center within 0.35*rF of
    # F's), visible span ending at the annulus pinch points. M: wall/annulus
    # separator, congruent to F, visible lens inside F bulging past the bore.
    F = ("arc", 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 360.0, "sil")
    B = ("arc", 0.0, 0.15, 0.55, 0.0, 0.0, 0.55, 195.0, 345.0, "sil")
    M = ("arc", 0.0, 0.30, 1.0, 0.0, 0.0, 1.0, 190.0, 350.0, "sil")
    return F, B, M


def test_snap_refits_separator_through_bore_pinch_points():
    # HANDOFF item 2: the separator is re-fit as the circumcircle (in the
    # bore's unit space) through (pinch1, pinch2, separator apex), so it
    # reads concentric/parallel to the bore instead of congruent to the
    # opening. Endpoints land on the bore's visible ends (pinch points).
    F, B, M = _counterbore_trio()
    out, refits = hlr._snap_rim_crossings([F, B, M])
    assert out[0] == F and out[1] == B  # opening and bore untouched
    new = out[2]
    assert new[0] == "arc" and new != M
    # the refit is reported so fill seams can follow the new boundary:
    # (old separator as drawn after pass-1, replacement, bore) per refit
    assert len(refits) == 1
    old_rec, new_rec, bore_rec = refits[0]
    assert old_rec[1:7] == M[1:7] and new_rec == new and bore_rec == B

    p1, p2 = _arc_pt(B, B[7]), _arc_pt(B, B[8])
    apex = _arc_pt(M, (M[7] + M[8]) / 2.0)
    ends = [_arc_pt(new, new[7]), _arc_pt(new, new[8])]
    assert min(np.linalg.norm(ends[0] - p1), np.linalg.norm(ends[0] - p2)) < 1e-6
    assert min(np.linalg.norm(ends[1] - p1), np.linalg.norm(ends[1] - p2)) < 1e-6
    assert np.linalg.norm(ends[0] - ends[1]) > 0.5  # distinct pinch points

    # the drawn sweep passes through the old apex (not the complement arc)
    ts = np.linspace(new[7], new[8], 8000)
    d = [np.linalg.norm(_arc_pt(new, t) - apex) for t in ts]
    assert min(d) < 1e-3

    # genuinely re-fit: radius near the bore's, not the opening's
    r_new = (math.hypot(new[3], new[4]) + math.hypot(new[5], new[6])) / 2.0
    assert r_new < 0.8  # was 1.0 (congruent to opening)


def test_snap_separator_refit_keeps_bore_aspect():
    # circumcircle is fit in the BORE's unit space, so for an elliptical
    # bore the replacement is an ellipse with the bore's aspect ratio.
    sq = math.sqrt
    q = 0.5  # y-squash applied to the whole scene
    F = ("arc", 0.0, 0.0, 1.0, 0.0, 0.0, q, 0.0, 360.0, "sil")
    B = ("arc", 0.0, 0.15 * q, 0.55, 0.0, 0.0, 0.55 * q, 195.0, 345.0, "sil")
    M = ("arc", 0.0, 0.30 * q, 1.0, 0.0, 0.0, q, 190.0, 350.0, "sil")
    out, _ = hlr._snap_rim_crossings([F, B, M])
    new = out[2]
    # actually re-fit (axes shrank toward the bore's scale) ...
    a1 = math.hypot(new[3], new[4])
    a2 = math.hypot(new[5], new[6])
    assert a1 < 0.8
    # ... with the bore's aspect ratio preserved
    assert a2 / a1 == pytest.approx(q, rel=1e-6)


def test_snap_no_refit_without_full_opening():
    # trio detection requires a FULL opening circle; with F partial the
    # separator must be left alone
    F, B, M = _counterbore_trio()
    F = F[:7] + (10.0, 350.0) + (F[9],)
    out, refits = hlr._snap_rim_crossings([F, B, M])
    # pass-1 endpoint snap may still nudge M's ends; the refit must not run:
    # M keeps its axes (congruent to the opening, radius 1.0)
    assert out[2][1:7] == M[1:7]
    assert refits == []


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_3700_reports_refit_and_ellipse_candidate():
    res = hlr.visible_segments("3700", LIB, lat=30, long=45, render_px=900)
    assert res.refits
    for old, new, bore in res.refits:
        assert new in res.segs           # the refit arc is what gets drawn
        # the new ellipse is an arc-recovery candidate so the moved fill
        # boundary emits as a true arc
        key = tuple(round(x, 6) for x in new[1:7])
        assert any(tuple(round(x, 6) for x in e[:6]) == key
                   for e in res.ellipses)


def test_snap_arc_end_onto_line_crossing():
    # HANDOFF: general endpoint snapping. A partial arc ending within
    # max_snap degrees of its analytic crossing with a drawn LINE snaps
    # onto the crossing, so the visibility-cut endpoint lands ON the stroke.
    c2 = math.cos(math.radians(2.0))
    A = ("arc", 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 90.0, 357.0, "sil")
    L = ("line", c2, -0.5, c2, 0.5, "sil")   # vertical chord, crossings at ±2°
    out, _ = hlr._snap_rim_crossings([A, L])
    assert out[1] == L                        # lines are targets, never moved
    snapped = out[0]
    assert snapped[8] == pytest.approx(358.0)  # -2° crossing
    end = _arc_pt(snapped, snapped[8])
    assert end[0] == pytest.approx(c2, abs=1e-9)


def test_no_snap_to_crossing_beyond_line_span():
    # same carrier line, but the drawn segment stops far from the crossing
    # point: the crossing is not on adjoining geometry, no snap
    c2 = math.cos(math.radians(2.0))
    A = ("arc", 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 90.0, 357.0, "sil")
    L = ("line", c2, 5.0, c2, 6.0, "sil")
    out, _ = hlr._snap_rim_crossings([A, L])
    assert out[0] == A


def test_snap_arc_end_onto_line_vertex():
    # a line ENDPOINT lying on the arc's carrier is a junction vertex; an
    # arc end within max_snap degrees snaps to the vertex's carrier angle
    A = ("arc", 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 90.0, 268.0, "sil")
    L = ("line", 0.0, -1.0, 1.5, -1.7, "sil")  # starts at (0,-1), heads away
    out, _ = hlr._snap_rim_crossings([A, L])
    snapped = out[0]
    assert snapped[8] == pytest.approx(270.0)
    end = _arc_pt(snapped, snapped[8])
    assert np.linalg.norm(end - np.array([0.0, -1.0])) < 1e-9


def test_no_snap_to_off_carrier_vertex():
    # a vertex radially off the carrier is unrelated geometry: snapping the
    # arc's angle toward it would leave the gap AND bend the arc's extent
    A = ("arc", 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 90.0, 268.0, "sil")
    L = ("line", 0.0, -1.4, 1.5, -2.1, "sil")  # nearest angle 270°, 0.4 off
    out, _ = hlr._snap_rim_crossings([A, L])
    assert out[0] == A


def test_rim_candidates_admit_16gon_facet_rings():
    # face polygons around holes/studs are LDraw 16-gons (22.5 deg steps)
    # inscribed in the true circle; recovery candidates from primitive rims
    # must carry a step that admits them (7th element > 22.5), else the
    # face fill cuts chords across thin slivers (3700's crescent tips)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [],
           "analytic": [primitives.Disc(R=np.eye(3), t=np.zeros(3), sector=360.0)]}
    res = hlr._visible_segments_analytic(out, *hlr.view_basis(30, 45), 300)
    assert res.ellipses
    assert all(len(e) == 7 and e[6] > 22.5 for e in res.ellipses)


def test_fit_ellipses_scales_snap_tolerance():
    # 8th candidate element is a SPATIAL snap tolerance and must ride the
    # fit affine; the 7th (max step) is angular and passes through
    out = hlr.fit_ellipses([(0, 0, 1, 0, 0, 1, 25.0, 2.0)], 2.0, 5.0, 5.0)
    assert out[0][6] == 25.0
    assert out[0][7] == 4.0


def _fold_span(cx, cy, r, t0, t1):
    return ("arc", float(cx), float(cy), float(r), 0.0, 0.0, float(r),
            float(t0), float(t1), "edge")


def test_fold_arc_loops_chains_spans_and_bridges_occlusion_gap():
    # HANDOFF: 3941 scallop spill. Drawn fitted-arc spans whose endpoints
    # coincide (authored junctions / pass-1 snaps) chain into the stylized
    # boundary of a sub-region (the axle-cross post outline); an occluded
    # section (front stud) leaves a gap that is bridged by a straight jump.
    # Lines and non-fold arcs never participate.
    key = tuple(round(v, 6) for v in (0.0, 0.0, 10.0, 0.0, 0.0, 10.0))
    segs = [_fold_span(0, 0, 10, 0, 120), _fold_span(0, 0, 10, 120, 240),
            _fold_span(0, 0, 10, 240, 350),        # 10 deg occluded gap
            ("line", 0.0, 0.0, 5.0, 5.0, "edge"),
            _fold_span(50, 0, 10, 0, 90)]          # non-fold arc: excluded
    loops = hlr._fold_arc_loops(segs, [key])
    assert len(loops) == 1
    from shapely import Point
    from brick_icons import geom2d
    poly = geom2d.region(loops[0])
    assert 300.0 < geom2d.area(poly) < 315.0       # ~pi*100 less chord bite
    assert poly.contains(Point(0.0, 0.0))


def test_fold_arc_loops_rejects_wide_bridges():
    # two short spans across the circle would need bridges longer than the
    # drawn arcs themselves: that is not a stylized outline, just unrelated
    # fragments — no loop may form
    key = tuple(round(v, 6) for v in (0.0, 0.0, 10.0, 0.0, 0.0, 10.0))
    segs = [_fold_span(0, 0, 10, 0, 60), _fold_span(0, 0, 10, 180, 240)]
    assert hlr._fold_arc_loops(segs, [key]) == []


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_3941_fold_loops_close_the_post_outline():
    # the ten axle-cross flank/notch spans chain into one closed loop (the
    # stud-occluded bottom section bridged); every drawn fold span lies on
    # the loop boundary
    from shapely import Point
    from brick_icons import geom2d
    res = hlr.visible_segments("3941", LIB)
    assert len(res.loops) == 1
    poly = geom2d.region(res.loops[0])
    spans = [op for op in res.segs if op[0] == "arc"
             and abs(op[8] - op[7]) < 359.9
             and tuple(round(v, 6) for v in op[1:7]) in set(res.fold_ells)]
    assert len(spans) >= 8
    for op in spans:
        tm = math.radians((op[7] + op[8]) / 2.0)
        mid = Point(op[1] + math.cos(tm) * op[3] + math.sin(tm) * op[5],
                    op[2] + math.cos(tm) * op[4] + math.sin(tm) * op[6])
        assert poly.exterior.distance(mid) < 0.05
