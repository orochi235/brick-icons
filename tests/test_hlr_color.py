import numpy as np
import pytest

from brick_icons import hlr

PART = """\
0 BFC CERTIFY CCW
4 16 0 0 0 1 0 0 1 0 1 0 0 1
4 14 0 1 0 1 1 0 1 1 1 0 1 1
3 4 0 2 0 1 2 0 1 2 1
"""


@pytest.fixture
def part(tmp_path):
    p = tmp_path / "t.dat"
    p.write_text(PART)
    return p


def test_flatten_records_a_color_per_triangle(part):
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(part, np.eye(3), np.zeros(3), out, [part.parent])
    # two quads -> two tris each, one tri -> one: 5 triangles
    assert len(out["tri"]) == 5
    assert len(out["tri_meta"]) == 5
    assert [m["color"] for m in out["tri_meta"]] == [16, 16, 14, 14, 4]


def test_flatten_resolves_color_16_against_the_reference(tmp_path):
    """Color 16 in a subfile inherits the referring line's color."""
    (tmp_path / "sub.dat").write_text("0 BFC CERTIFY CCW\n"
                                      "3 16 0 0 0 1 0 0 1 1 0\n")
    top = tmp_path / "top.dat"
    top.write_text("0 BFC CERTIFY CCW\n"
                   "1 14 0 0 0 1 0 0 0 1 0 0 0 1 sub.dat\n")
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(top, np.eye(3), np.zeros(3), out, [tmp_path])
    assert [m["color"] for m in out["tri_meta"]] == [14]


from brick_icons import repair


def test_repair_preserves_triangle_order_and_count(tmp_path):
    tris = np.array([
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        [[0, 0, 1], [0, 1, 1], [1, 0, 1]],
        [[2, 0, 0], [3, 0, 0], [2, 1, 0]],
    ], float)
    meta = [{"certified": True, "invert": False, "color": c}
            for c in (16, 14, 4)]
    fixed = repair.repaired_tris(tris, meta, tmp_path)
    assert len(fixed) == len(tris)
    # a flip permutes vertices WITHIN a triangle, never triangles themselves,
    # so each output triangle keeps its input's vertex set
    for got, want in zip(fixed, tris):
        assert {tuple(v) for v in np.round(got, 6)} == \
               {tuple(v) for v in np.round(want, 6)}


def test_repair_cache_key_ignores_color(tmp_path):
    """Color cannot affect orientation; keying on it would invalidate every
    cached mesh for no gain."""
    tris = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], float)
    a = [{"certified": True, "invert": False, "color": 16}]
    b = [{"certified": True, "invert": False, "color": 4}]
    assert repair._cache_key(tris, a) == repair._cache_key(tris, b)
