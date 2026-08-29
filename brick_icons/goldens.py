"""Structural summaries of rendered SVG, for engine-swap conformance.

An SVG hash pins the naive engine against drift. It cannot compare two
engines: OCCT reads a circle off the edge where the naive path refits a
polyline, so the text differs everywhere while the drawing is the same. The
summary is the comparable form — counts and extents that both engines should
agree on, plus the arc/line split that shows the swap doing its job.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from collections import Counter

# Coordinate pairs consumed per command, and the offset of the point within
# each group. Arcs carry `rx ry rot large sweep x y`; only the trailing pair
# is a position, and counting the radii as one pulls the bbox to the radius.
_ARITY = {"M": (2, 0), "L": (2, 0), "T": (2, 0),
          "C": (6, 4), "S": (4, 2), "Q": (4, 2),
          "A": (7, 5), "Z": (0, 0)}

_CMD = re.compile(r"([MLTCSQAZmltcsqaz])([^MLTCSQAZmltcsqaz]*)")
_NUM = re.compile(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _points(d: str):
    """Yield (command, [(x, y), ...]) for each run in a path's `d`."""
    for letter, body in _CMD.findall(d):
        cmd = letter.upper()
        nums = [float(n) for n in _NUM.findall(body)]
        stride, at = _ARITY.get(cmd, (2, 0))
        pts = []
        if stride:
            for i in range(0, len(nums) - stride + 1, stride):
                pts.append((nums[i + at], nums[i + at + 1]))
        yield cmd, pts


def _tag(el) -> str:
    return el.tag.rsplit("}", 1)[-1]


class _Summary:
    def __init__(self):
        self.commands: Counter[str] = Counter()
        self.fills: Counter[str] = Counter()
        self.paths = 0
        self.lines = 0
        self.gradients = 0
        self.stops = 0
        self.transforms = 0
        self.xs: list[float] = []
        self.ys: list[float] = []

    def walk(self, el, fill: str | None):
        name = _tag(el)
        # A clipPath is a mask, not ink: its geometry is neither counted nor
        # allowed to widen the bbox.
        if name in ("clipPath", "mask", "defs"):
            self._count_defs(el)
            return
        fill = el.get("fill", fill)
        if el.get("transform"):
            self.transforms += 1
        if name == "path":
            self.paths += 1
            self._paint(fill)
            for cmd, pts in _points(el.get("d", "")):
                self.commands[cmd] += 1
                for x, y in pts:
                    self.xs.append(x)
                    self.ys.append(y)
        elif name == "line":
            self.lines += 1
            try:
                self.xs += [float(el.get("x1")), float(el.get("x2"))]
                self.ys += [float(el.get("y1")), float(el.get("y2"))]
            except (TypeError, ValueError):
                pass
        for child in el:
            self.walk(child, fill)

    def _count_defs(self, el):
        for node in el.iter():
            tag = _tag(node)
            if tag in ("linearGradient", "radialGradient"):
                self.gradients += 1
            elif tag == "stop":
                self.stops += 1

    def _paint(self, fill: str | None):
        if fill is None:
            return
        # url(#gN) ids are allocation order, not content: identical drawings
        # would report different palettes purely from gradient numbering.
        self.fills["gradient" if fill.startswith("url(") else fill] += 1


def summarize_svg(text: str) -> dict:
    """Counts, palette and extent for one rendered SVG."""
    root = ET.fromstring(text)
    s = _Summary()
    s.walk(root, root.get("fill"))
    return {
        "viewBox": root.get("viewBox"),
        "paths": s.paths,
        "lines": s.lines,
        "fills": dict(sorted(s.fills.items())),
        "gradients": s.gradients,
        "gradient_stops": s.stops,
        "commands": dict(sorted(s.commands.items())),
        "transforms": s.transforms,
        # Coordinates under a transform are in the transformed space. Reporting
        # them raw gives an extent unrelated to the drawing, so say nothing
        # rather than something wrong.
        "bbox": ([min(s.xs), min(s.ys), max(s.xs), max(s.ys)]
                 if s.xs and not s.transforms else None),
    }


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()
