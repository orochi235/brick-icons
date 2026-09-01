import numpy as np
import pytest

cqsvg = pytest.importorskip("brick_icons.cqsvg",
                            reason="needs the [cadquery] extra")

from brick_icons import hlr, occt  # noqa: E402


SVG = """<svg>
    <g transform="scale(2, -2)">
       <!-- hidden lines -->
       <g stroke-dasharray="1,1">
\t\t\t<path d="M0.0,0.0 L1.0,1.0 " />
       </g>
       <!-- solid lines -->
       <g>
\t\t\t<path d="M2.0,4.0 L3.0,5.0 L4.0,7.0 " />
\t\t\t<path d="M-1.5,-2.5 L-1.0,-2.0 " />
       </g>
    </g>
</svg>
"""


def test_reads_the_visible_group_and_flips_y():
    ops = cqsvg.path_ops(SVG)
    assert ops == [("line", 2.0, -4.0, 3.0, -5.0, "line"),
                   ("line", 3.0, -5.0, 4.0, -7.0, "line"),
                   ("line", -1.5, 2.5, -1.0, 2.0, "line")]


def test_the_hidden_group_is_a_separate_read():
    assert cqsvg.path_ops(SVG, group="hidden") == \
        [("line", 0.0, 0.0, 1.0, -1.0, "line")]


def test_a_path_of_one_point_draws_nothing():
    assert cqsvg.path_ops('<!-- solid lines --><path d="M1.0,2.0 " />') == []


@pytest.fixture
def out_3001(ldraw_dir):
    return occt.flatten_part("3001", ldraw_dir)


def test_the_exporter_frames_the_part_where_occt_does(out_3001):
    """The exporter takes a projection direction and no roll, so the shape is
    turned into view space instead. If that rotation were wrong the drawing
    would still look like a brick -- just not the same brick occt drew."""
    right, up = hlr.view_basis(30.0, 45.0)[:2]
    cq = cqsvg.visible_segments(out_3001, right, up, 1024)
    ref = occt.visible_segments(dict(out_3001), right, up, 1024)
    assert cq.bbox == pytest.approx(ref.bbox, abs=0.5)


def test_every_op_is_a_line(out_3001):
    """`makeSVGedge` discretizes with GCPnts_QuasiUniformDeflection, so a
    circle arrives as a polyline and no arc is recoverable from it. The
    drawing is honest about that rather than refitting curves the exporter
    did not report."""
    res = cqsvg.visible_segments(out_3001, *hlr.view_basis(30.0, 45.0)[:2], 1024)
    assert res.segs
    assert {op[0] for op in res.segs} == {"line"}
    assert res.ellipses == ()


def test_hidden_edges_arrive_only_when_culling_is_off(out_3001):
    right, up = hlr.view_basis(30.0, 45.0)[:2]
    culled = cqsvg.visible_segments(out_3001, right, up, 1024, cull=True)
    every = cqsvg.visible_segments(out_3001, right, up, 1024, cull=False)
    assert len(every.segs) > len(culled.segs)


def test_the_engine_is_reachable_by_name():
    assert "cadquery" in hlr.VALID_ENGINES
    with pytest.raises(ValueError, match="unrecognized engine"):
        hlr.visible_segments("3001", "vendor/ldraw", engine="cadqery")


def test_view_shape_puts_right_on_x_and_up_on_y():
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    box = BRepPrimAPI_MakeBox(1.0, 2.0, 3.0).Shape()   # x=1, y=2, z=3
    # right = +Z, up = +Y: the 3-long side must measure along screen X
    turned = cqsvg.view_shape(box, np.array([0.0, 0.0, 1.0]),
                              np.array([0.0, 1.0, 0.0]))
    bb = Bnd_Box()
    BRepBndLib.Add_s(turned, bb)
    x0, y0, _, x1, y1, _ = bb.Get()
    assert (x1 - x0) == pytest.approx(3.0, abs=1e-6)
    assert (y1 - y0) == pytest.approx(2.0, abs=1e-6)
