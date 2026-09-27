"""Stud instancing: classification, withholding, and the placed drawing."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from shapely.geometry import Point, box

from brick_icons import cli, hlr, instancing, primitives, timing

LIB = Path("vendor/ldraw")
HAVE_LIB = LIB.exists()
RIGHT, UP, FWD = hlr.view_basis(30.0, 45.0)


def _stud_out():
    """One stud as flatten leaves it: stud.dat's wall and top at the origin,
    tagged stud 1, with its reference recorded."""
    wall = primitives.Cylinder(R=np.diag([6.0, -4.0, 6.0]), t=np.zeros(3))
    top = primitives.Disc(R=np.diag([6.0, 1.0, 6.0]),
                          t=np.array([0.0, -4.0, 0.0]))
    for p in (wall, top):
        p.stud = 1
    return {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": [wall, top],
            "2_stud": [], "5_stud": [],
            "stud_refs": {1: {"path": Path("p/stud.dat"), "R": np.eye(3),
                              "t": np.zeros(3), "color": 16, "body": 16,
                              "invert": False}}}


def _ground(out, tris):
    """Add non-stud triangles to `out`."""
    for v in tris:
        out["tri"].append(np.asarray(v, float))
        out["tri_meta"].append({"certified": True, "invert": False,
                                "color": 16, "body": 16, "stud": None})
    return out


def _screen_quad(a0, a1, b0, b1, depth):
    """Two triangles square to the view at camera depth `depth`, spanning
    projected A in [a0, a1] and B in [b0, b1]."""
    def at(a, b):
        return depth * FWD + a * RIGHT - b * UP
    q = [at(a0, b0), at(a1, b0), at(a1, b1), at(a0, b1)]
    return [np.array([q[0], q[1], q[2]]), np.array([q[0], q[2], q[3]])]


def _bar():
    """A fat cylinder standing in front of the stud's right half."""
    return primitives.Cylinder(R=np.column_stack([8 * RIGHT, 40 * UP, 8 * FWD]),
                               t=-30 * FWD + 6 * RIGHT - 20 * UP)


def test_a_stud_nothing_hides_is_clear():
    [v] = instancing.classify(_stud_out(), RIGHT, UP, FWD)
    assert v.role == "clear" and v.ref.id == 1


def test_a_plane_behind_a_stud_does_not_hide_it():
    out = _ground(_stud_out(), _screen_quad(-30, 30, -30, 30, 20.0))
    [v] = instancing.classify(out, RIGHT, UP, FWD)
    assert v.role == "clear"


def test_a_stud_behind_a_plane_is_hidden():
    out = _ground(_stud_out(), _screen_quad(-30, 30, -30, 30, -20.0))
    [v] = instancing.classify(out, RIGHT, UP, FWD)
    assert v.role == "hidden"


def test_a_stud_half_behind_a_plane_is_cut_by_its_outline():
    out = _ground(_stud_out(), _screen_quad(0, 30, -30, 30, -20.0))
    [v] = instancing.classify(out, RIGHT, UP, FWD)
    assert v.role == "cut"
    a, b, _ = hlr.project(np.array([[0.0, -4.0, 0.0]]), RIGHT, UP, FWD)
    shown = v.shown()
    assert shown.contains(Point(a[0] - 3, b[0]))
    assert not shown.contains(Point(a[0] + 3, b[0]))


def test_a_stud_half_behind_a_cylinder_falls_back_to_the_engine():
    out = _stud_out()
    out["analytic"].append(_bar())
    [v] = instancing.classify(out, RIGHT, UP, FWD)
    assert v.role == "fallback"


def test_a_definition_is_keyed_on_file_basis_color_and_winding_not_position():
    def ref(t, R=np.eye(3), color=16, invert=False, path="p/stud.dat"):
        return instancing.StudRef(1, Path(path), np.asarray(R, float),
                                  np.asarray(t, float), color, 16, invert)
    base = ref([0, 0, 0])
    assert ref([20, 0, 40]).key == base.key
    assert ref([0, 0, 0], R=np.eye(3) + 1e-7).key == base.key
    assert ref([0, 0, 0], color=4).key != base.key
    assert ref([0, 0, 0], invert=True).key != base.key
    assert ref([0, 0, 0], path="p/stud2.dat").key != base.key
    assert ref([0, 0, 0], R=np.diag([1.0, 1.0, -1.0])).key != base.key


def test_studs_are_placed_far_to_near():
    ref = instancing.StudRef(1, Path("p/stud.dat"), np.eye(3), np.zeros(3),
                             16, 16, False)
    near = instancing.Verdict(ref, "clear", hull=box(0, 0, 1, 1), depth=1.0)
    far = instancing.Verdict(ref, "cut", hull=box(0, 0, 1, 1),
                             cover=box(0, 0, 0.5, 1), depth=5.0)
    gone = instancing.Verdict(ref, "hidden", depth=9.0)
    plan = instancing.Plan([near, far, gone], (RIGHT, UP, FWD))
    assert plan.placed() == [far, near]
    assert plan.counts() == {"clear": 1, "cut": 1, "hidden": 1, "fallback": 0}


def test_withhold_takes_placed_studs_out_of_the_drawing_and_counts_them():
    out = _stud_out()
    keep_edge, stud_edge = np.zeros((2, 3)), np.ones((2, 3))
    out["2"], out["2_stud"] = [keep_edge, stud_edge], [None, 1]
    timing.reset()
    plan = instancing.withhold(out, RIGHT, UP, FWD)
    assert [v.role for v in plan.verdicts] == ["clear"]
    assert all(p.withheld for p in out["analytic"])
    assert len(out["2"]) == 1 and out["2"][0] is keep_edge
    assert out["stud_held"].holds(np.array([[0.0, -4.0, 0.0], [6.0, -4.0, 0.0]]))
    assert timing.counts() == {"studs_clear": 1, "studs_cut": 0,
                               "studs_hidden": 0, "studs_fallback": 0}


def test_withhold_leaves_a_fallback_stud_to_the_engine():
    out = _stud_out()
    out["analytic"].append(_bar())
    plan = instancing.withhold(out, RIGHT, UP, FWD)
    assert plan.counts()["fallback"] == 1
    assert not any(p.withheld for p in out["analytic"])
    assert "stud_held" not in out


def test_an_envelope_holds_only_what_lies_inside_its_stud():
    out = _stud_out()
    ref = instancing.refs_of(out)[0]
    env = instancing.Envelopes([(ref, instancing.stud_points(out["analytic"], []))])
    assert env.holds(np.array([[0.0, -2.0, 0.0], [0.0, -4.0, 6.0]]))
    assert not env.holds(np.array([[0.0, 3.0, 0.0]]))           # under the base
    assert not env.holds(np.array([[0.0, -2.0, 0.0], [20.0, -2.0, 0.0]]))


def test_a_wall_s_limbs_run_base_to_top_square_to_the_view():
    wall = _stud_out()["analytic"][0]
    limbs = instancing.limb_points(wall, FWD)
    assert len(limbs) == 2
    for base, top in limbs:
        assert abs((base - wall.t) @ FWD) < 1e-9
        assert np.allclose(top - base, wall.R[:, 1])


def test_the_bbox_grows_over_every_placed_stud():
    ref = instancing.StudRef(1, Path("p/stud.dat"), np.eye(3), np.zeros(3),
                             16, 16, False)
    plan = instancing.Plan([instancing.Verdict(ref, "clear",
                                               hull=box(-6, -6, 6, 6))],
                           (RIGHT, UP, FWD))
    ident = primitives.Projection(RIGHT, UP, FWD, s=1.0, cx=0.0, cy=0.0, half=0.0)
    assert instancing.grow_bbox((0.0, 0.0, 1.0, 1.0), plan, ident) == (-6.0, -6.0, 6.0, 6.0)
    px = primitives.Projection(RIGHT, UP, FWD, s=2.0, cx=1.0, cy=1.0, half=100.0)
    assert instancing.grow_bbox((90.0, 90.0, 95.0, 95.0), plan, px) == (86.0, 86.0, 110.0, 110.0)


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_every_stud_of_a_2x4_brick_is_clear_and_leaves_the_naive_drawing():
    timing.reset()
    off = hlr.visible_segments("3001", LIB, render_px=600, engine="naive")
    on = hlr.visible_segments("3001", LIB, render_px=600, engine="naive",
                              stud_instancing="all")
    assert off.studs is None
    assert on.studs.counts() == {"clear": 8, "cut": 0, "hidden": 0, "fallback": 0}
    assert {k: v for k, v in timing.counts().items() if k.startswith("studs_")} \
        == {"studs_clear": 8, "studs_cut": 0, "studs_hidden": 0, "studs_fallback": 0}
    assert len(off.segs) - len(on.segs) >= 16
    assert len(off.faces) - len(on.faces) >= 16
    assert not any(f.get("prim") is not None and f["prim"].stud is not None
                   for f in on.faces)
    assert on.bbox[1] <= off.bbox[1] + 1.0          # the studs stay in frame
    with pytest.raises(ValueError):
        hlr.visible_segments("3001", LIB, engine="naive", stud_instancing="some")


def _ends_under_studs(res):
    """Line ops with an end inside what a placed stud shows, op space."""
    region = instancing.shown_ops(res.studs, res.proj)
    return [op for op in res.segs if op[0] == "line"
            and any(region.distance(Point(p)) <= 1.0
                    for p in (op[1:3], op[3:5]))]


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_a_part_edge_ending_under_a_placed_stud_survives_the_orphan_cull():
    off = hlr.visible_segments("3001", LIB, render_px=600, engine="naive")
    on = hlr.visible_segments("3001", LIB, render_px=600, engine="naive",
                              stud_instancing="all")
    # 3001's back top edges run between the studs and end where one hides them
    assert len(on.segs) >= 15
    assert _ends_under_studs(on)
    again = hlr.visible_segments("3001", LIB, render_px=600, engine="naive")
    assert again.segs == off.segs


IDENT = primitives.Projection(RIGHT, UP, FWD, s=1.0, cx=0.0, cy=0.0, half=0.0)


def _inst(verdicts, monkeypatch, segs):
    plan = instancing.Plan(verdicts, (RIGHT, UP, FWD))
    res = hlr.VisResult([], (0.0, 0.0, 1.0, 1.0), 1.0, [], [], proj=IDENT,
                        studs=plan)
    inst = instancing.Instancer(res, "naive", LIB)
    lone = hlr.VisResult(segs, (0.0, 0.0, 1.0, 1.0), 1.0, [], [], proj=IDENT)
    monkeypatch.setattr(inst, "lone", lambda ref: lone)
    return inst


def _ref():
    return instancing.StudRef(1, Path("p/stud.dat"), np.eye(3), np.zeros(3),
                              16, 16, False)


def test_origin_fit_puts_the_reference_origin_on_canvas_zero():
    res = hlr.VisResult([], (0, 0, 1, 1), 4.0, [], [], proj=primitives.Projection(
        RIGHT, UP, FWD, s=4.0, cx=1.0, cy=2.0, half=50.0))
    k, kx, ky = hlr.canvas_affine(res, *instancing.origin_fit(res, 8.0))
    assert k == pytest.approx(8.0) and kx == pytest.approx(0.0) \
        and ky == pytest.approx(0.0)


def test_svg_and_png_place_the_same_stroke_ops(monkeypatch):
    v = instancing.Verdict(_ref(), "clear", hull=box(-6, -6, 6, 6), a=3.0, b=4.0)
    inst = _inst([v], monkeypatch, [("line", 0.0, 0.0, 1.0, 0.0, "edge")])
    svg = "".join(inst.svg_parts((2.0, 10.0, 20.0), 1.0))
    assert '<use href="#sd0s" x="16.00" y="28.00"/>' in svg
    assert '<line x1="0.00" y1="0.00" x2="2.00" y2="0.00" stroke-width="1.00"/>' in svg
    assert "sd0f" not in svg                              # no style, no fills
    assert inst.png_ops((2.0, 10.0, 20.0), 1.0) == [
        ("line", 16.0, 28.0, 18.0, 28.0, "edge")]


def test_a_cut_stud_is_clipped_alike_in_both_writers(monkeypatch):
    v = instancing.Verdict(_ref(), "cut", hull=box(-6, -6, 6, 6),
                           cover=box(0, -10, 10, 10))
    inst = _inst([v], monkeypatch, [("line", -4.0, 0.0, 4.0, 0.0, "edge")])
    svg = "".join(inst.svg_parts((1.0, 0.0, 0.0), 1.0))
    assert '<clipPath id="sc0">' in svg and '<g clip-path="url(#sc0)">' in svg
    [(kind, x1, y1, x2, y2, tag)] = inst.png_ops((1.0, 0.0, 0.0), 1.0)
    assert sorted([x1, x2]) == pytest.approx([-4.0, 0.0]) and y1 == y2 == 0.0


def test_the_contour_hides_behind_placed_studs(monkeypatch):
    clear = instancing.Verdict(_ref(), "clear", hull=box(-6, -6, 6, 6))
    inst = _inst([clear], monkeypatch, [])
    assert inst.hide_region((1.0, 0.0, 0.0), 2.0).area == pytest.approx(144.0)
    cut = instancing.Verdict(_ref(), "cut", hull=box(-6, -6, 6, 6),
                             cover=box(0, -10, 10, 10))
    inst = _inst([cut], monkeypatch, [])
    assert inst.hide_region((1.0, 0.0, 0.0), 2.0).area == pytest.approx(40.0)


def test_part_strokes_give_way_to_a_placed_stud():
    arc = ("arc", 50.0, 50.0, 3.0, 0.0, 0.0, 3.0, 0.0, 360.0, "edge")
    ops = [("line", 0.0, 0.0, 10.0, 0.0, "edge"), arc]
    got = instancing.cut_ops(ops, box(4, -1, 20, 1))
    assert got[-1] == arc                       # untouched: kept as it was
    [(_k, x1, _y1, x2, _y2, tag)] = got[:-1]
    assert sorted([x1, x2]) == pytest.approx([0.0, 4.0]) and tag == "edge"
    assert instancing.cut_ops(ops, None) == ops


def test_clip_ops_cuts_arcs_and_lines_to_a_region():
    ops = [("line", -4.0, 0.0, 4.0, 0.0, "edge"),
           ("arc", 0.0, 0.0, 3.0, 0.0, 0.0, 3.0, 0.0, 360.0, "sil")]
    got = instancing.clip_ops(ops, box(-10, -10, 0, 10))
    assert got[0][0] == "line" and got[0][-1] == "edge"
    assert all(max(op[1], op[3]) <= 1e-9 for op in got)
    assert any(op[-1] == "sil" for op in got)


SVG = ["--engine", "naive", "--format", "svg", "--shading", "outline",
       "--shade-style", "flat3"]


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_off_never_reaches_instancing_and_draws_as_the_default(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("--stud-instancing off reached brick_icons.instancing")
    monkeypatch.setattr(instancing, "withhold", boom)
    monkeypatch.setattr(instancing, "Instancer", boom)
    argv = ["3001", "--engine", "naive", "--format", "both", "--shading",
            "outline", "--shade-style", "flat3"]
    assert cli.main(argv + ["--out", str(tmp_path / "default")]) == 0
    assert cli.main(argv + ["--stud-instancing", "off",
                            "--out", str(tmp_path / "off")]) == 0
    for name in ("3001.svg", "3001.gray.png", "3001.mono.png"):
        assert (tmp_path / "default" / name).read_bytes() \
            == (tmp_path / "off" / name).read_bytes(), name


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_all_places_every_clear_stud_between_fills_and_strokes(tmp_path):
    assert cli.main(["3001", *SVG, "--stud-instancing", "all",
                     "--out", str(tmp_path)]) == 0
    svg = (tmp_path / "3001.svg").read_text()
    assert svg.count('<use href="#sd0s"') == 8 and svg.count('<use href="#sd0f"') == 8
    assert (svg.index('<g stroke-linejoin="round">') < svg.index('<g class="studs">')
            < svg.index('<g stroke="black"'))
    assert 'clip-path="url(#cclip)"' in svg          # contour hidden behind studs


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_translucent_and_wireframe_renders_draw_studs_through_the_engine(tmp_path):
    assert cli.main(["3001", *SVG, "--stud-instancing", "all", "--opacity", "0.5",
                     "--out", str(tmp_path / "t")]) == 0
    assert cli.main(["3001", "--engine", "naive", "--format", "svg", "--wireframe",
                     "--stud-instancing", "all", "--out", str(tmp_path / "w")]) == 0
    for d in ("t", "w"):
        assert "<use" not in (tmp_path / d / "3001.svg").read_text()


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_the_pngs_and_the_physical_svg_place_studs_too(tmp_path):
    assert cli.main(["3001", "--engine", "naive", "--shading", "outline",
                     "--format", "png", "--mode", "both", "--stud-instancing", "all",
                     "--out", str(tmp_path / "p")]) == 0
    mono = np.asarray(Image.open(tmp_path / "p" / "3001.mono.png"))
    assert (mono == 0).any()
    assert cli.main(["3001", *SVG, "--scale-mode", "physical", "--stud-instancing",
                     "all", "--out", str(tmp_path / "m")]) == 0
    assert '<use href="#sd0s"' in (tmp_path / "m" / "3001.svg").read_text()
