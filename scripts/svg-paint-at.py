"""Which SVG elements paint a pixel: every filled element, topmost first, with
its fill and the attributes that name where it came from.

Repaints each element alone in a flat key color (strokes off) through resvg
and reads the pixel back, so clip paths, gradients and paint order count as
they do in the render. `--line` sweeps a row or column and prints the
topmost element per pixel, which is how a hard tone edge inside one surface is
traced to the fill that draws it.

    .venv/bin/python scripts/svg-paint-at.py out/x/32062.svg --at 201.5,136.2
    .venv/bin/python scripts/svg-paint-at.py out/x/32062.svg --line 185,136,206,136
"""
import argparse
import io
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

NS = "{http://www.w3.org/2000/svg}"
ZOOM = 4


def _raster(svg_bytes, zoom):
    png = subprocess.run(["resvg", "-z", str(zoom), "-", "-c"], input=svg_bytes,
                         capture_output=True, check=True).stdout
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))


def _filled(root):
    out = []
    for el in root.iter():
        tag = el.tag.replace(NS, "")
        if tag in ("path", "polygon", "rect", "circle", "ellipse") and \
                el.get("fill", "black") != "none" and not _in_defs(root, el):
            out.append(el)
    return out


def _in_defs(root, el, _cache={}):
    if id(root) not in _cache:
        s = set()
        for d in root.iter(NS + "defs"):
            s.update(id(e) for e in d.iter())
        for d in root.iter(NS + "clipPath"):
            s.update(id(e) for e in d.iter())
        _cache[id(root)] = s
    return id(el) in _cache[id(root)]


def coverage(svg_path, zoom=ZOOM):
    """(elements, stack): stack[i] is element i's alpha mask at `zoom`."""
    ET.register_namespace("", NS[1:-1])
    tree = ET.parse(svg_path)
    root = tree.getroot()
    els = _filled(root)
    saved = [(e.get("fill"), e.get("stroke"), e.get("opacity"), e.get("fill-opacity"))
             for e in els]
    for e in els:
        e.set("opacity", "0")
    for e in root.iter():
        if e.tag.replace(NS, "") in ("line", "polyline") or \
                (e.get("fill") == "none" and not _in_defs(root, e)):
            e.set("opacity", "0")
    stack = []
    for i, e in enumerate(els):
        e.set("opacity", "1")
        e.set("fill", "#ff0000")
        e.set("fill-opacity", "1")
        e.set("stroke", "none")
        stack.append(_raster(ET.tostring(root), zoom)[..., 3])
        e.set("opacity", "0")
    for e, (f, s, o, fo) in zip(els, saved):
        for k, v in (("fill", f), ("stroke", s), ("opacity", o), ("fill-opacity", fo)):
            if v is None:
                e.attrib.pop(k, None)
            else:
                e.set(k, v)
    return els, stack


def describe(i, e):
    attrs = {k: v for k, v in e.attrib.items() if k != "d" and k != "points"}
    d = e.get("d", "")
    return f"#{i:3d} {attrs}  d[{len(d)}]={d[:60]!r}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("svg")
    ap.add_argument("--at", help="x,y in viewBox units")
    ap.add_argument("--line", help="x0,y0,x1,y1 in viewBox units")
    ap.add_argument("--zoom", type=int, default=ZOOM)
    a = ap.parse_args()
    els, stack = coverage(a.svg, a.zoom)
    z = a.zoom

    def at(x, y):
        px, py = int(x * z), int(y * z)
        return [i for i in range(len(els)) if stack[i][py, px] > 127][::-1]

    if a.at:
        x, y = (float(v) for v in a.at.split(","))
        for i in at(x, y):
            print(describe(i, els[i]))
    if a.line:
        x0, y0, x1, y1 = (float(v) for v in a.line.split(","))
        n = int(max(abs(x1 - x0), abs(y1 - y0)) * z) + 1
        seen = {}
        for k in range(n):
            f = k / max(n - 1, 1)
            x, y = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
            hit = at(x, y)
            print(f"({x:7.2f}, {y:7.2f})  top {hit[:1]}  all {hit}")
            for i in hit:
                seen[i] = els[i]
        for i, e in sorted(seen.items()):
            print(describe(i, e))


if __name__ == "__main__":
    sys.exit(main())
