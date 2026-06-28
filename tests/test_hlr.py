import numpy as np
import pytest
from pathlib import Path
from brick_icons import hlr


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
