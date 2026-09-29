"""Size and visible-object count of a render, for tracking what a drawing costs.

An object is a shape element that puts paint on the canvas: a fill that is not
`none`, or a stroke that is not `none` with a width above zero, at nonzero
opacity. Nothing inside `defs`, `clipPath`, `mask` and the like counts -- they
paint only through something else -- and a translucent slot's zero-width edges
count for nothing, which is what they draw.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

_SHAPES = {"path", "line", "polyline", "polygon", "rect", "circle", "ellipse",
           "use", "text", "image"}
_UNPAINTED = {"defs", "clipPath", "mask", "pattern", "symbol", "marker",
              "linearGradient", "radialGradient", "filter", "title", "desc",
              "metadata", "style"}
#: Shapes with no interior: a fill on these paints nothing.
_OPEN = {"line"}
_INHERITED = ("fill", "stroke", "stroke-width", "fill-opacity",
              "stroke-opacity", "visibility")


def _props(el: ET.Element) -> dict[str, str]:
    props = {k: v.strip() for k, v in el.attrib.items()}
    for decl in el.attrib.get("style", "").split(";"):
        if ":" in decl:
            k, v = decl.split(":", 1)
            props[k.strip()] = v.strip()
    return props


def _number(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value.rstrip("px%"))
    except ValueError:
        return default


def painted_count(text: str) -> int:
    """How many shape elements in an SVG put paint on the canvas."""
    root = ET.fromstring(text)
    count = 0

    def walk(el: ET.Element, inherited: dict[str, str], opacity: float) -> None:
        nonlocal count
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in _UNPAINTED:
            return
        props = _props(el)
        if props.get("display") == "none":
            return
        opacity *= _number(props.get("opacity"), 1.0)
        here = {**inherited, **{k: props[k] for k in _INHERITED if k in props}}
        if tag in _SHAPES and opacity > 0 and here.get("visibility") != "hidden":
            fills = (tag not in _OPEN and here.get("fill", "black") != "none"
                     and _number(here.get("fill-opacity"), 1.0) > 0)
            strokes = (here.get("stroke", "none") != "none"
                       and _number(here.get("stroke-width"), 1.0) > 0
                       and _number(here.get("stroke-opacity"), 1.0) > 0)
            count += fills or strokes
        for child in el:
            walk(child, here, opacity)

    walk(root, {}, 1.0)
    return count


def render_stats(path: Path | str) -> dict:
    """`bytes` and `objects` of a render file -- `objects` is None for a
    raster, which has none -- and `drawn_at`, when the file was written."""
    path = Path(path)
    st = path.stat()
    objects = (painted_count(path.read_text()) if path.suffix == ".svg"
               else None)
    drawn_at = datetime.fromtimestamp(st.st_mtime, timezone.utc)
    return {"bytes": st.st_size, "objects": objects,
            "drawn_at": drawn_at.isoformat(timespec="seconds")}
