"""cadquery's own SVG exporter, as an engine. The only module that imports
cadquery.

It answers one question: what does an off-the-shelf BRep-to-drawing exporter
make of these parts? So `getSVG` is called for real and its output is parsed
back into ops, rather than its HLR block being reimplemented here with our
own edge selection -- that would measure this codebase, not the exporter.

What it costs, all of it visible in the drawing: `makeSVGedge` discretizes
every edge, so there are no arcs; the template concatenates sharp, smooth and
outline edges into one group, so nothing survives to tag a stroke `sil`; and
the exporter draws every edge the shape has, so a facet boundary that
`ShapeUpgrade_UnifySameDomain` did not merge is drawn like any other.
"""
from __future__ import annotations

import re

import numpy as np

try:
    from cadquery.occ_impl.exporters.svg import getSVG
    from cadquery.occ_impl.shapes import Shape
except ImportError as e:                      # pragma: no cover
    raise ImportError(
        "--engine cadquery needs the cadquery extra: pip install -e '.[cadquery]'"
    ) from e

from OCP.gp import gp_Trsf
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform

from . import occt

# `getSVG` takes a projection direction and no roll, so the shape is turned
# into view space instead and projected down +Z, where gp_Ax2's X direction is
# +X. Screen X is then `right` and screen Y is `up`, the frame the rest of the
# codebase draws in.
PROJECTION_DIR = (0.0, 0.0, 1.0)

_PATH_D = re.compile(r'<path d="([^"]*)"')
_POINT = re.compile(r"[ML](-?[\d.eE+-]+),(-?[\d.eE+-]+)")
_SOLID = "<!-- solid lines -->"


def view_shape(shape, right, up):
    """`shape` rotated so that `right` lies along +X and `up` along +Y."""
    right = np.asarray(right, float)
    up = np.asarray(up, float)
    n = np.cross(right, up)
    t = gp_Trsf()
    t.SetValues(right[0], right[1], right[2], 0.0,
                up[0], up[1], up[2], 0.0,
                n[0], n[1], n[2], 0.0)
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def path_ops(svg: str, group: str = "visible", kind: str = "line"):
    """Every `<path>` of one of the exporter's two groups, as line ops.

    Y is negated on the way out: the exporter's own transform carries a
    `scale(u, -u)`, so its path data is Y-up and op space is Y-down.
    """
    head, _, tail = svg.partition(_SOLID)
    body = tail if group == "visible" else head
    ops = []
    for d in _PATH_D.findall(body):
        pts = [(float(x), -float(y)) for x, y in _POINT.findall(d)]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            ops.append(("line", x1, y1, x2, y2, kind))
    return ops


def visible_segments(out, right, up, render_px, cull=True):
    from .hlr import VisResult, _ops_bbox
    shape = view_shape(occt.build_shape(out), right, up)
    svg = getSVG(Shape(shape), {
        "projectionDir": PROJECTION_DIR,
        "showAxes": False,
        # The exporter draws hidden edges dashed in a group of their own. We
        # want them as ordinary ops, so they are read from the same group the
        # visible ones are and are simply absent when culling.
        "showHidden": False,
    })
    ops = path_ops(svg)
    if not cull:
        hidden = getSVG(Shape(shape), {"projectionDir": PROJECTION_DIR,
                                       "showAxes": False, "showHidden": True})
        ops = path_ops(hidden, group="hidden") + ops
    if not ops:
        raise RuntimeError("cadquery's exporter produced no paths")
    bbox = _ops_bbox(ops)
    span = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) or 1.0
    return VisResult(ops, bbox, (render_px - 20) / span,
                     faces=(), analytic=(), ellipses=(), sil_polys=())
