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
