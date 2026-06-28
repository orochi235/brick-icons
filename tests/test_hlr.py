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
