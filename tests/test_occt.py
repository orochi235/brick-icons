import numpy as np
import pytest

occt = pytest.importorskip("brick_icons.occt", reason="needs the [occt] extra")


class P:
    """Minimal stand-in for a recognized primitive."""
    def __init__(self, kind, R, t, sector=360.0, top=1, inner=1):
        self.kind, self.R, self.t = kind, R, t
        self.sector, self.top, self.inner = sector, top, inner


def test_sheared_frame_is_rejected():
    """Non-orthogonal frames have no exact OCCT counterpart (5% of parts)."""
    R = np.array([[1.0, 0.3, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    assert occt.frame(P("cyli", R, np.zeros(3))) is None


def test_cone_radii_are_n_plus_one_and_n_scaled():
    """conN is radius N+1 at the base tapering to N, BOTH in primitive units,
    so the matrix scale multiplies both. Using the scale directly as the outer
    radius builds a plausible-looking part at the wrong size."""
    prim = P("con", np.diag([2.0, 5.0, 2.0]), np.zeros(3), top=3)
    r_base, r_top = occt.cone_radii(prim)
    assert r_base == pytest.approx(8.0)   # (3 + 1) * 2
    assert r_top == pytest.approx(6.0)    # 3 * 2


def test_edge_primitives_contribute_no_surface():
    assert occt.occt_faces(P("edge", np.eye(3), np.zeros(3))) == []


def test_3001_builds_and_sews(ldraw_dir):
    """The spike's step 2: a real brick builds with no exceptions."""
    shape = occt.build_shape(occt.flatten_part("3001", ldraw_dir))
    assert occt.count_faces(shape) > 0
