#!/usr/bin/env python3
"""Generate the badge marks that curves, not corners, decide.

    .venv/bin/python scripts/gen-badge-marks.py

Prints TypeScript for `lab/src/corpus/badges.ts`. Each shape is built on a
1000-unit grid and sampled densely, then normalized into the unit box the
marks draw in -- placing a dozen bezier control points by eye in that box
could not hold a taper or an arrowhead, and every attempt read as something
else: the horseshoe as a letter U, the brush as a bottle.
"""
from __future__ import annotations

import math
import pathlib
import re

GRID = 500.0  # half-width of the design box; output is divided by this


def arc(cx, cy, r, a0, a1, n):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / (n - 1)),
             cy + r * math.sin(a0 + (a1 - a0) * i / (n - 1)))
            for i in range(n)]


def horseshoe():
    """A U -- tall, narrow mouth, long limbs. The squares that make it a
    magnet are cut in `badges.ts` in the field color, near the tips and flush
    with the outer edge so the limb stays whole behind them."""
    cy, ro, ri = 110.0, 400.0, 145.0
    tip = -400.0
    # Sampling pi -> 0 passes through pi/2, which in a y-down space is the
    # bottom. pi -> 2*pi passes 3*pi/2 and puts the bend on top, which is an
    # upside-down U with notches in the wrong place.
    pts = [(-ro, tip)]
    pts += arc(0, cy, ro, math.pi, 0, 90)
    pts += [(ro, tip), (ri, tip)]
    pts += arc(0, cy, ri, 0, math.pi, 90)
    pts += [(-ri, tip)]
    return pts


def redo_arrow():
    """The arrow from `scripts/redo.svg`, drawn rather than computed: it was
    an arc with a triangle glued on, and the drawing carries the taper and
    the head's aim together."""
    return _from_doc(_svg_paths("redo.svg", SHAPE_FILL)[0])


def redo_sparkle():
    """The sparkle beside the arrow's tail, from the same drawing."""
    return [_from_doc(pts) for pts in _svg_paths("redo.svg", ACCENT_FILL)]


# --- scripts/bristles.svg -------------------------------------------------
# A hand-drawn bristle head, sampled rather than approximated: the shape is
# the whole cue and every parametric stand-in for it read as something else.

def tokens(d):
    for m in re.finditer(r'([MmCcZzLlSsHhVv])|(-?\d*\.?\d+(?:e-?\d+)?)', d):
        yield m.group(1) or float(m.group(2))

def sample(d, per=24):
    ts = list(tokens(d))
    i, cmd, cur, start, out = 0, None, (0.0, 0.0), (0.0, 0.0), []
    prev2 = None   # previous cubic's second control point, for S/s
    def bez(p0, p1, p2, p3, n):
        for k in range(1, n + 1):
            t = k / n; u = 1 - t
            yield (u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0],
                   u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1])
    while i < len(ts):
        if isinstance(ts[i], str):
            cmd = ts[i]; i += 1
            if cmd in 'Zz':
                continue
        if cmd in 'Mm':
            x, y = ts[i], ts[i+1]; i += 2
            cur = (cur[0]+x, cur[1]+y) if cmd == 'm' else (x, y)
            start = cur; out.append(cur); cmd = 'l' if cmd == 'm' else 'L'
        elif cmd in 'Cc':
            vals = ts[i:i+6]; i += 6
            if cmd == 'c':
                p1 = (cur[0]+vals[0], cur[1]+vals[1]); p2 = (cur[0]+vals[2], cur[1]+vals[3])
                p3 = (cur[0]+vals[4], cur[1]+vals[5])
            else:
                p1 = (vals[0], vals[1]); p2 = (vals[2], vals[3]); p3 = (vals[4], vals[5])
            out += list(bez(cur, p1, p2, p3, per)); cur = p3; prev2 = p2
        elif cmd in 'Ss':
            vals = ts[i:i+4]; i += 4
            p1 = (2*cur[0] - prev2[0], 2*cur[1] - prev2[1]) if prev2 else cur
            if cmd == 's':
                p2 = (cur[0]+vals[0], cur[1]+vals[1]); p3 = (cur[0]+vals[2], cur[1]+vals[3])
            else:
                p2 = (vals[0], vals[1]); p3 = (vals[2], vals[3])
            out += list(bez(cur, p1, p2, p3, per)); cur = p3; prev2 = p2
        elif cmd in 'Ll':
            x, y = ts[i], ts[i+1]; i += 2
            cur = (cur[0]+x, cur[1]+y) if cmd == 'l' else (x, y); out.append(cur)
        elif cmd in 'HhVv':
            v = ts[i]; i += 1
            if cmd == 'H': cur = (v, cur[1])
            elif cmd == 'h': cur = (cur[0]+v, cur[1])
            elif cmd == 'V': cur = (cur[0], v)
            else: cur = (cur[0], cur[1]+v)
            out.append(cur)
        else:
            raise SystemExit(f'unhandled command {cmd!r}')
    return out


#: How a drawing names its parts. Illustrator renumbers style classes on
#: every save -- the same path came back as `st1` after being written as
#: `st2` -- so a path is found by the fill it was drawn with, never by class.
SHAPE_FILL = "#fbb03b"
ACCENT_FILL = "lime"


def _svg_paths(name, fill):
    svg = (pathlib.Path(__file__).resolve().parent / name).read_text()
    classes = {cls for cls, body in
               re.findall(r"\.(st\d+)\s*\{([^}]*)\}", svg)
               if re.search(rf"fill:\s*{re.escape(fill)}\s*[;}}]", body)}
    # A class can also be declared in a shared rule: `.st0, .st1 { ... }`.
    for group, body in re.findall(r"((?:\.st\d+\s*,\s*)+\.st\d+)\s*\{([^}]*)\}", svg):
        if re.search(rf"fill:\s*{re.escape(fill)}\s*[;}}]", body):
            classes |= set(re.findall(r"\.(st\d+)", group))
    out = []
    for cls, d in re.findall(r'class="(st\d+)"[^>]*\sd="([^"]+)"', svg):
        if cls in classes:
            pts = sample(d)
            if len(pts) >= 4:
                out.append(pts)
    return out


#: The document both drawings use: 1920x1080, the mark's origin at its
#: center, and one mark unit every 400 units of it.
DOC_CENTER = (960.0, 540.0)
DOC_UNIT = 400.0


def _from_doc(pts):
    return [((x - DOC_CENTER[0]) / DOC_UNIT * GRID,
             (y - DOC_CENTER[1]) / DOC_UNIT * GRID) for x, y in pts]


def _place(pts, scale, cx, bottom):
    return [((x - cx) * scale, (y - bottom) * scale + 1.0 * GRID) for x, y in pts]


def brush():
    """The bristle head from `scripts/bristles.svg`, filling the box: there
    is no ferrule under it, so nothing to stand on and no reason to leave it
    the room. Sampled
    rather than approximated -- the outline is the whole cue, and every
    parametric stand-in for it read as a bottle or a light bulb."""
    from shapely.geometry import Polygon

    pts = _svg_paths("bristles.svg", SHAPE_FILL)[0]
    ys = [p[1] for p in pts]
    xs = [p[0] for p in pts]
    scale = 2.0 * GRID / (max(ys) - min(ys))
    cx, bottom = (min(xs) + max(xs)) / 2, max(ys)
    placed = _place(pts, scale, cx, bottom)
    # A closing: dilate then erode, which fills concavities narrower than
    # twice its radius and leaves the convex outline alone. It takes the
    # involution out of the tip's hook without touching the belly.
    shape = Polygon(placed).buffer(0).buffer(48.0).buffer(-48.0)
    if shape.geom_type == "MultiPolygon":
        shape = max(shape.geoms, key=lambda g: g.area)
    ring = shape.exterior
    count = max(180, int(ring.length / 11.0))
    smoothed = [ring.interpolate(i / count, normalized=True).coords[0]
                for i in range(count)]
    return smoothed, scale, cx, bottom


def paint(scale, cx, bottom):
    """The smudge, drawn in the same file and placed by the bristles' own
    transform. Clipped to the bristles: the drawing overlaps their edge, and
    paint outside the brush is just a blob on the field."""
    from shapely.geometry import Polygon

    bristles = Polygon(brush()[0]).buffer(0)
    out = []
    for pts in _svg_paths("bristles.svg", ACCENT_FILL):
        poly = Polygon(_place(pts, scale, cx, bottom)).buffer(0)
        hit = poly.intersection(bristles)
        parts = list(hit.geoms) if hit.geom_type == "MultiPolygon" else [hit]
        out += [list(part.exterior.coords) for part in parts
                if not part.is_empty and part.area > 1.0]
    return out


HEADER = """/* Generated by scripts/gen-badge-marks.py -- do not edit by hand.
 *
 * Flat x,y pairs in the unit box the badge marks draw in, sampled densely
 * from the shapes that script builds. The curve is the whole cue: placed by
 * hand in this box the horseshoe read as a letter U and the brush as a
 * bottle.
 */

"""


HEADER = """/* Generated by scripts/gen-badge-marks.py -- do not edit by hand.
 *
 * Flat x,y pairs in the unit box the badge marks draw in, sampled densely
 * from the shapes that script builds. The curve is the whole cue: placed by
 * hand in this box the horseshoe read as a letter U and the brush as a
 * bottle.
 */

"""


def minifig():
    """`3626b`'s own outline seen face on -- its triangles and its analytic
    cylinders unioned, then resampled at a fine step. Simplified coarsely it
    facets, which is the tessellation the OCCT engine exists to avoid, and it
    shows on a dome at badge size."""
    import numpy as np
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union
    from brick_icons import hlr

    roots = hlr.default_roots("vendor/ldraw")
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(hlr._resolve_input("3626b", roots), np.eye(3), np.zeros(3), out, roots)
    polys = []
    for t in np.array(out["tri"]):
        poly = Polygon([(float(v[0]), float(v[1])) for v in t])
        if poly.area > 1e-7:
            polys.append(poly if poly.is_valid else poly.buffer(0))
    for prim in out["analytic"]:
        R, t = np.asarray(prim.R), np.asarray(prim.t)
        rx, h, y0, x0 = abs(R[0, 0]), abs(R[1, 1]), float(t[1]), float(t[0])
        if type(prim).__name__ == "Cylinder":
            polys.append(box(x0 - rx, y0, x0 + rx, y0 + h))
    shape = unary_union(polys).buffer(0.3).buffer(-0.3)
    if shape.geom_type == "MultiPolygon":
        shape = max(shape.geoms, key=lambda g: g.area)
    ring = shape.simplify(0.06).exterior
    # Resample at a fixed step so the dome carries points where it curves.
    step = 0.9
    n = max(120, int(ring.length / step))
    pts = [ring.interpolate(i / n, normalized=True).coords[0] for i in range(n)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    half = max(max(xs) - min(xs), max(ys) - min(ys)) / 2
    norm = [((x - cx) / half, (y - cy) / half) for x, y in pts]
    # Narrow the barrel without touching the stud or the neck: the two ends
    # are what say minifig head rather than cylinder, and they are already
    # the narrowest parts of the outline.
    def waist(x, y):
        t = min(1.0, max(0.0, (abs(y) - 0.42) / 0.38))
        return x * (1.0 - 0.11 * (1.0 - t * t)), y
    return [(x * GRID, y * GRID) for x, y in (waist(px, py) for px, py in norm)]


def contract(pts, inset, keep):
    """The shape's own outline pulled inward, then clipped to `keep`.

    A cutout shaped like an axis-aligned rectangle reads as damage; one that
    is the silhouette contracted reads as a marking on the form. An inset of
    zero keeps the marking flush with the edge, for a marking drawn in its
    own color rather than punched out of the field.
    """
    from shapely.geometry import Polygon

    inner = Polygon(pts).buffer(-inset, join_style=2)
    if inner.is_empty:
        return []
    hit = inner.intersection(keep)
    parts = list(hit.geoms) if hit.geom_type == "MultiPolygon" else [hit]
    return [list(part.exterior.coords) for part in parts if not part.is_empty]


def emit_many(name, groups):
    rows = []
    for pts in groups:
        flat = []
        for x, y in pts:
            flat += [f"{x / GRID:.4f}", f"{y / GRID:.4f}"]
        body = ", ".join(flat)
        rows.append(f"  [{body}]")
    joined = ",\n".join(rows)
    return f"export const {name}: number[][] = [\n{joined},\n];\n"


def emit(name, pts):
    flat = []
    for x, y in pts:
        flat += [f"{x / GRID:.4f}", f"{y / GRID:.4f}"]
    rows = [", ".join(flat[i:i + 8]) for i in range(0, len(flat), 8)]
    body = ",\n  ".join(rows)
    return f"export const {name}: number[] = [\n  {body},\n];\n"


if __name__ == "__main__":
    out = [HEADER]
    for name, fn in (("MAGNET", horseshoe), ("REDO", redo_arrow),
                     ("BRUSH", lambda: brush()[0])):
        pts = fn()
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        print(f"{name}: {len(pts)} points, "
              f"x {min(xs) / GRID:.2f}..{max(xs) / GRID:.2f} "
              f"y {min(ys) / GRID:.2f}..{max(ys) / GRID:.2f}")
        out.append(emit(name, pts))
    from shapely.geometry import Point, box as sbox

    magnet_pts = horseshoe()
    tip = -470.0
    cuts = contract(magnet_pts, 0.0, sbox(-GRID, -400.0, GRID, -400.0 + 145.0))
    out.append(emit_many("MAGNET_CUT", cuts))
    print(f"MAGNET_CUT: {len(cuts)} pieces")

    spark = redo_sparkle()
    out.append(emit_many("REDO_SPARK", spark))
    print(f"REDO_SPARK: {len(spark)} pieces")

    _, scale, cx, bottom = brush()
    cuts = paint(scale, cx, bottom)
    out.append(emit_many("BRUSH_CUT", cuts))
    print(f"BRUSH_CUT: {len(cuts)} pieces")

    dest = pathlib.Path(__file__).resolve().parent.parent / "lab/src/corpus/markPaths.ts"
    dest.write_text("\n".join(out))
    print(f"wrote {dest}")
