from __future__ import annotations

import math
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from . import process

_VIEWBOX = re.compile(r'viewBox="([^"]+)"')
_TRANSFORM = re.compile(r'<g transform="([^"]+)"')
_PATH_D = re.compile(r'<path[^>]*\sd="([^"]+)"')


def _potrace(mask_L: Image.Image) -> tuple[list[str], str, str]:
    """Trace a 1-bit mask; return (path_d_list, viewbox, g_transform)."""
    with tempfile.TemporaryDirectory() as td:
        pbm = Path(td) / "m.pbm"
        svg = Path(td) / "m.svg"
        mask_L.convert("1").save(pbm)
        subprocess.run(["potrace", "-s", "-o", str(svg), str(pbm),
                        "--turdsize", "2", "--alphamax", "1.0", "--opttolerance", "0.2"],
                       check=True, capture_output=True)
        txt = svg.read_text()
    vb = _VIEWBOX.search(txt).group(1)
    tf_match = _TRANSFORM.search(txt)
    if not tf_match:
        return [], vb, ""          # empty mask -> no paths
    return _PATH_D.findall(txt), vb, tf_match.group(1)


def _write_svg(out_path: Path, viewbox: str, transform: str,
               layers: list[tuple[list[str], str]], bg: str = "none",
               opacity: float = 1.0) -> None:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" '
             f'preserveAspectRatio="xMidYMid meet">']
    if bg != "none":
        parts.append(f'<rect width="100%" height="100%" fill="{bg}"/>')
    if transform:
        # group-level opacity: cel layers overlap by design (cumulative
        # dark-on-light), so the stack must composite first, then blend once
        op = f' opacity="{opacity:g}"' if opacity < 1.0 else ""
        parts.append(f'<g transform="{transform}" stroke="none"{op}>')
        for ds, fill in layers:
            for d in ds:
                parts.append(f'<path d="{d}" fill="{fill}"/>')
        parts.append("</g>")
    parts.append("</svg>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts))


def _arc_to_svg(op):
    """Convert a parametric arc op ('arc', cx, cy, ux, uy, vx, vy, t0, t1, kind)
    to an SVG elliptical-arc path 'd'. The point at param t is
    center + cos t*u + sin t*v; semi-axes/rotation come from the SVD of [u v]."""
    _, cx, cy, ux, uy, vx, vy, t0, t1, _ = op
    u = np.array([ux, uy]); v = np.array([vx, vy])
    M = np.column_stack([u, v])
    U_, S_, _ = np.linalg.svd(M)
    rx, ry = float(S_[0]), float(S_[1])
    phi = math.degrees(math.atan2(U_[1, 0], U_[0, 0]))

    def pt(t_deg):
        a = math.radians(t_deg)
        p = np.array([cx, cy]) + math.cos(a) * u + math.sin(a) * v
        return p[0], p[1]
    # increasing param sweeps u->v; sign of cross(u,v) gives screen orientation
    sweep = 1 if (ux * vy - uy * vx) * (1 if t1 >= t0 else -1) > 0 else 0

    # Emit in sub-arcs of <= 90 deg. Besides the degenerate coincident-endpoint
    # case (a full ellipse renders as nothing), spans near 180 are numerically
    # treacherous: the renderer re-derives the center from the endpoints, and
    # near-antipodal endpoints amplify the 0.01 px coordinate rounding into an
    # O(sqrt(r*eps)) center shift — ~2 px on a hole rim at 1024 px output.
    n = max(1, math.ceil(abs(t1 - t0) / 90.0))
    x0, y0 = pt(t0)
    cmds = [f'M {x0:.2f} {y0:.2f}']
    for k in range(1, n + 1):
        xk, yk = pt(t0 + (t1 - t0) * k / n)
        cmds.append(f'A {rx:.2f} {ry:.2f} {phi:.2f} 0 {sweep} {xk:.2f} {yk:.2f}')
    return " ".join(cmds)


def _polyline_mid(P):
    """The point half way along polyline P by length."""
    total = sum(math.dist(a, b) for a, b in zip(P, P[1:]))
    walked = 0.0
    for a, b in zip(P, P[1:]):
        step = math.dist(a, b)
        if walked + step >= total / 2.0 and step > 0:
            t = (total / 2.0 - walked) / step
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        walked += step
    return P[-1]


def _polyline_gap(P, Q):
    """The farthest any point of polyline P sits from polyline Q."""
    worst = 0.0
    for x, y in P:
        best = float("inf")
        for (ax, ay), (bx, by) in zip(Q, Q[1:]):
            dx, dy = bx - ax, by - ay
            dd = dx * dx + dy * dy
            t = 0.0 if dd < 1e-18 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / dd))
            best = min(best, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
        worst = max(worst, best)
    return worst


def _drop_sliver_loops(segs, width, max_len):
    """Two strokes that close a loop no wider than `width` are dropped.

    They outline a face too thin to draw: 38583's recess meets the quarter
    disc that closes its arch 0.13 LDU from the arch wall, and the declared
    edge and the disc's rim, both correctly visible, came out as a 6 px tick
    hanging off the arch. Under a stroke wider than the loop the two only
    ever paint one blob. Silhouette strokes never go (an outline gap is
    always worse), and a loop longer than `max_len` is a slot, not a sliver.
    """
    ops = [("line",) + tuple(op) if len(op) == 5 else op for op in segs]
    cand = []
    for i, op in enumerate(ops):
        if op[-1] == "sil":
            continue
        pts = process.op_points(op)
        L = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
        # a side shorter than the loop is wide is a chord link, not a side:
        # two of a discretized curve's 0.3 px chords have ends this close
        if width < L <= max_len:
            cand.append((i, pts))
    drop = set()
    for a in range(len(cand)):
        i, P = cand[a]
        for b in range(a + 1, len(cand)):
            j, Q = cand[b]
            if i in drop or j in drop:
                continue
            ends = (math.dist(P[0], Q[0]) <= width and math.dist(P[-1], Q[-1]) <= width) \
                or (math.dist(P[0], Q[-1]) <= width and math.dist(P[-1], Q[0]) <= width)
            if ends and math.dist(_polyline_mid(P), _polyline_mid(Q)) <= width \
                    and _polyline_gap(P, Q) <= width and _polyline_gap(Q, P) <= width:
                drop.update((i, j))
    if not drop:
        return segs
    return [op for k, op in enumerate(segs) if k not in drop]


def _drop_sliver_noise(ops, min_len, run=3):
    """Ops with the fragments shorter than `min_len` dropped -- one renders as
    a bare round-cap dot (the warts at 6589's crescent tips).

    A fragment joined end to end with at least `run - 1` others that short is
    kept: that is one link of a discretized curve, not a dot. cadquery's
    exporter emits nothing but such links, at ~0.3 px against a 1.2 px
    threshold, so culling on length alone erased every curve it drew.

    ops: [(x1, y1, x2, y2)], already rounded. Order is preserved and no
    iteration is hash-ordered (census byte-diff gate).
    """
    short = [i for i, (x1, y1, x2, y2) in enumerate(ops)
             if math.hypot(x2 - x1, y2 - y1) < min_len]
    if not short:
        return ops
    at = {}
    for i in short:
        x1, y1, x2, y2 = ops[i]
        at.setdefault((x1, y1), []).append(i)
        at.setdefault((x2, y2), []).append(i)
    parent = {i: i for i in short}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for point in sorted(at):
        members = at[point]
        for j in members[1:]:
            a, b = find(members[0]), find(j)
            if a != b:
                parent[max(a, b)] = min(a, b)
    size = {}
    for i in short:
        size[find(i)] = size.get(find(i), 0) + 1
    keep = {i for i in short if size[find(i)] >= run}
    drop = set(short) - keep
    return [op for i, op in enumerate(ops) if i not in drop]


def _chain_line_ops(ops, stub_len=0.0):
    """Chain straight strokes sharing endpoints into polyline paths so SVG
    linejoins render the corners, plus elbow-join stubs for the wedges a
    single chain cannot cover.

    Separate round-capped strokes under-cover every corner wedge: the face
    color pokes past the shared cap disc to within cap-radius of the vertex,
    where a true join fills the wedge to the miter point (Quick Look zoom
    made these pinch notches obvious at every 3-stroke 3D corner). Ops must
    share a stroke width (a path has one) and are keyed on their EMITTED
    2-dp coordinates so joins are watertight in the output.

    At each vertex, cyclically adjacent stroke pairs are paired sharpest
    wedge first (the pinch depth grows as the wedge closes); each pairing
    becomes a join inside one chained path. Wedges left over at 3+-degree
    vertices get a short 2-segment elbow path over the strokes' own
    geometry — a real join, not an ink pocket. Elbow arms are trimmed to
    `stub_len` (~1.5 stroke widths): a full-length arm would redraw the
    whole stroke and double-composite its antialiased fringe, visibly
    thickening exactly the strokes that happen to end at junctions. Closed
    chains emit `Z` so the seam corner joins too. Everything is sorted; no
    hash-order iteration (census byte-diff gate).

    ops: [(x1, y1, x2, y2)] (already culled + rounded). Returns
    (chains, elbows, singles): chains as [[(x, y), ...], closed?],
    elbows as [((x, y), vertex, (x, y))], singles as op indices."""
    n = len(ops)
    node_of = {}                                   # coord -> node id
    incid = []                                     # node -> [(op, end)]
    ends = []                                      # op -> (node0, node1)
    for i, (x1, y1, x2, y2) in enumerate(ops):
        ids = []
        for p in ((x1, y1), (x2, y2)):
            j = node_of.setdefault(p, len(incid))
            if j == len(incid):
                incid.append([])
            ids.append(j)
        incid[ids[0]].append((i, 0))
        incid[ids[1]].append((i, 1))
        ends.append(tuple(ids))
    coords = [None] * len(incid)
    for p, j in node_of.items():
        coords[j] = p
    partner = [[None, None] for _ in range(n)]     # per op end: paired op
    elbows = []
    for v in range(len(incid)):
        inc = incid[v]
        if len(inc) < 2:
            continue
        vx, vy = coords[v]
        dirs = []
        for i, e in inc:
            ox, oy = coords[ends[i][1 - e]]
            a = math.atan2(oy - vy, ox - vx)
            dirs.append((a, i, e))
        dirs.sort()
        m = len(dirs)
        # cyclically adjacent pairs, sharpest wedge first
        wedges = []
        for k in range(m):
            a0, i0, e0 = dirs[k]
            a1, i1, e1 = dirs[(k + 1) % m]
            if m == 2 and k == 1:
                break                              # one wedge pair only
            span = (a1 - a0) % (2 * math.pi)
            wedges.append((span, k, (i0, e0), (i1, e1)))
        wedges.sort()
        used = set()
        for span, _, (i0, e0), (i1, e1) in wedges:
            if i0 in used or i1 in used or i0 == i1:
                joined = False
            elif partner[i0][e0] is None and partner[i1][e1] is None:
                # skip a 2-cycle (duplicate strokes between the same nodes)
                two_cycle = (ends[i0] in (ends[i1], ends[i1][::-1])
                             and partner[i0][1 - e0] == i1)
                joined = not two_cycle
                if joined:
                    partner[i0][e0] = i1
                    partner[i1][e1] = i0
                    used.add(i0)
                    used.add(i1)
            else:
                joined = False
            if not joined and span < math.radians(170.0):
                arms = []
                for i, e in ((i0, e0), (i1, e1)):
                    ox, oy = coords[ends[i][1 - e]]
                    ln = math.hypot(ox - vx, oy - vy)
                    f = min(1.0, stub_len / ln) if ln else 1.0
                    arms.append((round(vx + f * (ox - vx), 2),
                                 round(vy + f * (oy - vy), 2)))
                elbows.append((arms[0], (vx, vy), arms[1]))
    # walk chains
    visited = [False] * n
    chains, singles = [], []
    for i in range(n):
        if visited[i]:
            continue
        if partner[i][0] is None and partner[i][1] is None:
            visited[i] = True
            singles.append(i)
            continue
        # find a terminal end (or accept a cycle)
        cur, ent = i, 0
        seen = {i}
        while partner[cur][ent] is not None:
            nxt = partner[cur][ent]
            if nxt in seen:
                break                              # cycle
            seen.add(nxt)
            ent = 1 - (0 if partner[nxt][0] == cur else 1)
            cur = nxt
        closed = partner[cur][ent] is not None
        pts = [coords[ends[cur][ent]]]
        op, out_end = cur, 1 - ent
        while True:
            visited[op] = True
            pts.append(coords[ends[op][out_end]])
            nxt = partner[op][out_end]
            if nxt is None or visited[nxt]:
                break
            out_end = 1 - (0 if partner[nxt][0] == op else 1)
            op = nxt
        if closed:
            pts = pts[:-1]                         # Z re-closes the loop
        chains.append((pts, closed))
    return chains, elbows, singles


# --debug-colors cycle: the 48 most separated colors the page allows, so two
# elements anywhere in one render never read alike. Hand-picked hues capped at
# a dozen because hue is one axis; this packs CIELAB, which has lightness and
# chroma too -- min dE 26.7 between ANY pair and 29.8 between neighbors, against
# the old palette's 29.3 between neighbors and 0 past the twelfth element.
# scripts/gen-debug-palette.py regenerates it and re-derives both numbers.
DEBUG_PALETTE = (
    "#0000fc", "#00f600", "#ea00fc", "#7ed800", "#664efc", "#d2de00",
    "#720c9c", "#42f06c", "#cc06ba", "#129600", "#fc009c", "#30f0ae",
    "#fc0018", "#0072f6", "#fccc30", "#c078fc", "#84a206", "#1e429c",
    "#f69606", "#006cae", "#c64200", "#2ac6f6", "#cc0c30", "#4ea866",
    "#fc006c", "#005a12", "#fc6cd2", "#ae9006", "#8a54a2", "#c0d884",
    "#900654", "#96decc", "#8a2418", "#ccb4fc", "#666600", "#ea7e9c",
    "#007260", "#fc8460", "#004e60", "#f6c06c", "#5a425a", "#a26006",
    "#7e96b4", "#424e2a", "#fcc6b4", "#964854", "#8a9c78", "#966c4e",
)


RAMP_LEN = 6           # elements per light-to-dark ramp
RAMP_HUE_STEP = 41.0   # degrees between ramps; coprime-ish with 360 so the
                       # first repeat is far away, not one ramp later


def _hsl_hex(h, s, ll):
    def ch(n):
        k = (n + h / 30.0) % 12.0
        a = s * min(ll, 1.0 - ll)
        return round(255 * (ll - a * max(-1.0, min(k - 3.0, 9.0 - k, 1.0))))
    return f"#{ch(0):02x}{ch(8):02x}{ch(4):02x}"


def ramp_color(n, ramp_len=RAMP_LEN):
    """Emission-order color that reads as BOTH position and group: `n` runs
    light to dark inside one hue for `ramp_len` elements, then the hue steps.

    The flat cycle answers "which element owns this vertex" but not "how far
    along is it" -- past a dozen elements every color has been used already.
    Here the lightness gives the position within a run and the hue gives the
    run. A short run (the default 6) reads adjacent elements apart; a long one
    (ramp=100) trades that for coarse structure -- which hundred a segment
    falls in, and where the run boundaries land.
    """
    ramp_len = max(1, int(ramp_len))
    ramp, i = divmod(n, ramp_len)
    h = (ramp * RAMP_HUE_STEP) % 360.0
    ll = 0.80 - 0.66 * (i / max(1, ramp_len - 1))
    return _hsl_hex(h, 0.78, ll)


def parse_debug_mode(mode):
    """Validate a --debug-colors value; return ("cycle"|"ramp", ramp_len)."""
    mode = (mode or "cycle").strip()
    if mode == "cycle":
        return "cycle", 0
    if mode == "ramp":
        return "ramp", RAMP_LEN
    if mode.startswith("ramp="):
        n = mode.split("=", 1)[1]
        if not n.isdigit() or int(n) < 1:
            raise ValueError(f"ramp length must be a positive integer: {mode!r}")
        return "ramp", int(n)
    raise ValueError(f"expected 'cycle', 'ramp' or 'ramp=N', got {mode!r}")


def debug_color(n, mode):
    kind, ramp_len = parse_debug_mode(mode)
    if kind == "ramp":
        return ramp_color(n, ramp_len)
    return DEBUG_PALETTE[n % len(DEBUG_PALETTE)]


def _colorize(parts, start, mode="cycle", n=0, stop=None):
    """Give every drawn element in parts[start + 1:stop] its own color, in
    emission order, counting on from `n`. Answers "which element owns this
    vertex", which one black outline cannot. `mode` is "cycle" (12 distinct
    hues), "ramp", or "ramp=N" for a run of N elements per hue (see
    ramp_color)."""
    for i in range(start + 1, len(parts) if stop is None else stop):
        el = parts[i]
        if not (el.startswith("<path") or el.startswith("<line")):
            continue
        color = debug_color(n, mode)
        parts[i] = el.replace("/>", f' stroke="{color}"/>', 1)
        n += 1
    return n


_STUD_STROKES = re.compile(r'(<g id="sd\d+s"[^>]*>)(.*?)(</g>)', re.S)
_ELEMENT = re.compile(r"<(?:path|line)\b[^>]*/>")


def _colorize_studs(parts, lo, hi, mode, n):
    """_colorize for the stroke definitions a placed stud draws from
    (instancing.Instancer.svg_parts), which sit inside one `<defs>`: each
    element is one color at every stud that uses it."""
    def element(m):
        nonlocal n
        el = [m.group(0)]
        n = _colorize(el, -1, mode, n)
        return el[0]

    def group(m):
        return m.group(1) + _ELEMENT.sub(element, m.group(2)) + m.group(3)
    for i in range(lo, hi):
        parts[i] = _STUD_STROKES.sub(group, parts[i])
    return n



#: On the root of every SVG whose decoration carries `class="deco"`. Without
#: it a file with no marks could be a plain part or a render from before the
#: marks existed, and only the first says "none of this is printing".
DECO_MARKED = 'data-marks="deco"'
_MASK_STYLE = ('<style>path[fill]{fill:#000;stroke:#000}'
               'path.deco{fill:#fff;stroke:#fff}</style>')
_SVG_OPEN = re.compile(r"<svg\b[^>]*>")


def deco_mask_svg(text: str) -> str | None:
    """The render with decoration white and every other fill black, strokes
    untouched, or None for a render that does not mark its decoration.
    Rasterized like the drawing, it lines up with it pixel for pixel."""
    m = _SVG_OPEN.search(text)
    if m is None or DECO_MARKED not in m.group(0):
        return None
    return text[:m.end()] + _MASK_STYLE + text[m.end():]


def fill_elements(fills, opacity=1.0, gid_prefix="g", solid_deco=False):
    """(defs, body) for fill ops: the gradients they paint with, and the
    self-stroked paths inside one round-joined group. `gid_prefix` names the
    gradients; a second drawing in the same file (a stud definition, see
    instancing.Instancer) takes its own so the ids cannot collide.
    `solid_deco` paints decoration as an opaque fill whatever `opacity` is:
    in painter's order it then hides everything behind it, and a nearer
    translucent face still blends over it."""
    # Each fill is stroked in its own paint (its "seam", process.seam_px;
    # SEAM_PX when the op carries none) so antialiasing seams
    # between abutting coplanar faces don't show; gradient fills (cylinder
    # walls) carry a <linearGradient> def instead of a flat color.
    # Opacity is per-face: translucent renders skip occlusion clipping,
    # so faces overlap and each must blend individually (nearer over
    # deeper). The `opacity` attribute composites a path's own fill +
    # seam stroke together first, so a face never double-paints itself.
    face_op = f' opacity="{opacity:g}"' if opacity < 1.0 else ""
    defs, body = [], ['<g stroke-linejoin="round">']
    # Smooth-group facets share one gradient object; dedupe defs by
    # content so a 50-facet curve emits one <linearGradient>, not 50.
    def_ids = {}

    def gradient(g, gid):
        """The id of the def painting gradient `g`, emitting it under `gid`
        unless an identical one exists."""
        stops = "".join(f'<stop offset="{o * 100:.1f}%" {_stop_paint(c)}/>'
                        for o, c in g["stops"])
        if g.get("type") == "radial":
            # unit-circle gradient space mapped onto the group's
            # bounding ellipse; fx/fy shift the bright spot lightward
            tf = (f'matrix({g["r"]:.2f} 0 0 {g["r"] * g["ratio"]:.2f} '
                  f'{g["cx"]:.2f} {g["cy"]:.2f})')
            key = ("radial", tf, f'{g["fx"]:.3f},{g["fy"]:.3f}', stops)
            el = (f'<radialGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                  f'cx="0" cy="0" r="1" fx="{g["fx"]:.3f}" fy="{g["fy"]:.3f}" '
                  f'gradientTransform="{tf}">{stops}</radialGradient>')
        else:
            key = (f'{g["x1"]:.2f},{g["y1"]:.2f},{g["x2"]:.2f},{g["y2"]:.2f}', stops)
            el = (f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                  f'x1="{g["x1"]:.2f}" y1="{g["y1"]:.2f}" '
                  f'x2="{g["x2"]:.2f}" y2="{g["y2"]:.2f}">{stops}</linearGradient>')
        if key not in def_ids:
            def_ids[key] = gid
            defs.append(el)
        return def_ids[key]

    for i, fo in enumerate(fills):
        if "gradient" in fo:
            paint = f'url(#{gradient(fo["gradient"], f"{gid_prefix}{i}")})'
        else:
            paint = fo["fill"]
        # translucent fills paint fill-only: the self-stroke that closes
        # AA seams between abutting opaque fills double-paints its 0.4px
        # overhang onto neighbors when composited at opacity < 1 —
        # concentric ghost rings on a dish's stacked bands (4740)
        solid = opacity >= 1.0 or (solid_deco and fo.get("deco"))
        sw = round(fo.get("seam", process.SEAM_PX), 2)
        seam = f' stroke="{paint}" stroke-width="{sw:g}"' if solid else ""
        # class="deco" marks paint that is not the part's own color, so a
        # viewer can recolor the part without touching its printing
        deco = ' class="deco"' if fo.get("deco") else ""
        sh = fo.get("shade")
        if sh is None:
            body.append(f'<path d="{fo["d"]}"{deco} fill="{paint}" '
                        f'fill-rule="evenodd"{seam}{"" if solid else face_op}/>')
            continue
        # the print's shading: the same region again in translucent black
        # (shade._deco_shade), grown to cover the print's seam stroke where it
        # has one. Unstroked -- a stroke would lay a second coat of alpha over
        # its own fill -- and still class "deco", so a recolor or a
        # decoration mask treats it as the print it shades. A translucent
        # print composites with its shade first, as one layer.
        if "gradient" in sh:
            shade_paint = f'fill="url(#{gradient(sh["gradient"], f"{gid_prefix}s{i}")})"'
        else:
            shade_paint = f'fill="#000000" fill-opacity="{sh["alpha"]:g}"'
        shade_d = sh.get("d_seamed", fo["d"]) if solid else fo["d"]
        pair = [f'<path d="{fo["d"]}"{deco} fill="{paint}" '
                f'fill-rule="evenodd"{seam}/>',
                f'<path d="{shade_d}" class="deco shade" {shade_paint} '
                f'fill-rule="evenodd"/>']
        body += pair if solid else [f"<g{face_op}>", *pair, "</g>"]
    body.append("</g>")
    return defs, body


def _stop_paint(c):
    """A gradient stop's paint: a color, or a shade layer's alpha over
    black (shade._deco_shade)."""
    if isinstance(c, str):
        return f'stop-color="{c}"'
    return f'stop-color="#000000" stop-opacity="{c:g}"'


def stroke_elements(segs, line_px, sil_px, studs=None):
    """SVG elements for stroke ops at their widths (process.stroke_width):
    arcs as paths, straight strokes chained into mitered polylines with
    elbow joins. The caller wraps them in the stroke group."""
    parts = []
    line_groups = {}                                  # sw -> [(x1,y1,x2,y2)]
    segs = _drop_sliver_loops(segs, 0.6 * line_px, 4.0 * line_px)
    for op in segs:
        if len(op) == 5:                              # legacy line tuple
            op = ("line",) + tuple(op)
        sw = process.stroke_width(op, line_px, sil_px, studs)
        if op[0] == "line":
            _, x1, y1, x2, y2, kind = op
            line_groups.setdefault(round(sw, 2), []).append(
                (round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)))
        else:
            r = (math.hypot(op[3], op[4]) + math.hypot(op[5], op[6])) / 2.0
            if r * math.radians(abs(op[8] - op[7])) < 0.6 * sw:
                continue
            parts.append(f'<path d="{_arc_to_svg(op)}" stroke-width="{sw:.2f}"/>')
    # straight strokes sharing endpoints chain into mitered polylines, with
    # elbow-join paths over the leftover corner wedges — separate
    # round-capped strokes pinch every 3D corner (see _chain_line_ops).
    # miterlimit 1.5 bevels joins sharper than ~84°: a longer miter tip is a
    # barb poking past the fill at interior corners (98283 ledge, 32062 notch
    # chevrons); outline corners stay sharp via contour_d, which keeps 5
    joinery = ' stroke-linejoin="miter" stroke-miterlimit="1.5"'
    for sw in sorted(line_groups):
        ops = _drop_sliver_noise(line_groups[sw], 0.6 * sw)
        chains, elbows, singles = _chain_line_ops(ops, stub_len=1.5 * sw)
        for pts, closed in chains:
            d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts) \
                + (" Z" if closed else "")
            parts.append(f'<path d="{d}" stroke-width="{sw:.2f}"{joinery}/>')
        for i in singles:
            x1, y1, x2, y2 = ops[i]
            parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                         f'stroke-width="{sw:.2f}"/>')
        for (ax, ay), (vx, vy), (bx, by) in elbows:
            parts.append(f'<path d="M {ax:.2f} {ay:.2f} L {vx:.2f} {vy:.2f} '
                         f'L {bx:.2f} {by:.2f}" stroke-width="{sw:.2f}"{joinery}/>')
    return parts


def segments_to_svg(segs, w, h, out_path, line_px=2, sil_px=2,
                    physical=None, s=None, line_mm=0.2, sil_mm=0.2,
                    fills=None, bg: str = "none", opacity: float = 1.0,
                    solid_deco: bool = False, clip_geom=None, contour=None, contour_arcs=None,
                    debug_colors: bool = False, studs=None,
                    between=None, hide=None, spare=None) -> Path:
    """The SVG drawing: fills, then `between` (instancing's placed studs),
    then the silhouette contour, then the strokes. `contour` is the region
    the contour outlines (geom2d.contour_region), drawn as a path with arcs
    recovered from `contour_arcs` and clipped to process.contour_band.
    `hide` (instancing.hide_region) is where neither the contour nor the
    strokes draw, save the ops `spare` claims (instancing.unplaced_hide),
    drawn in a group of their own."""
    if physical is not None:
        w_mm, h_mm = physical
        root = (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{w_mm:.2f}mm" height="{h_mm:.2f}mm" '
                f'viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" '
                f'{DECO_MARKED}>')
        line_px = line_mm / 0.4 * s
        sil_px = sil_mm / 0.4 * s
    else:
        root = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
                f'preserveAspectRatio="xMidYMid meet" {DECO_MARKED}>')
    parts = [root]
    if bg != "none":
        parts.append(f'<rect width="100%" height="100%" fill="{bg}"/>')
    if fills:
        defs, body = fill_elements(fills, opacity, solid_deco=solid_deco)
        if defs:
            parts.append("<defs>" + "".join(defs) + "</defs>")
        parts += body
    placed = (len(parts), len(parts) + len(between or ()))
    if between:
        # placed drawings (instancing's studs): over the part's fills,
        # under its strokes
        parts += between
    from . import geom2d
    from shapely.geometry import box
    hidden = hide is not None and not hide.is_empty
    # Clip the stroke layer to the silhouette buffered outward by half the
    # widest stroke (mitered): round end caps otherwise poke half a width
    # past outline corners into the background ("frayed" corners).
    keep = None
    if clip_geom is not None:
        # grow by drawn-arc bulge regions so the clip never flattens an arc
        keep = geom2d.grow(geom2d.union_all([clip_geom]
                                            + geom2d.arc_regions(segs, clip_geom)),
                           max(line_px, sil_px) / 2.0)
    # what `spare` claims -- a stud the engine drew, its own strokes lying on
    # and inside its footprint, which `hide` may be -- draws whole
    own = [op for op in segs if spare(op)] \
        if hidden and spare is not None else []
    if own:
        segs = [op for op in segs if not spare(op)]
    own_attr = ""
    od = geom2d.path_d(keep) if own and keep is not None else ""
    if od:
        parts.append(f'<defs><clipPath id="oclip">'
                     f'<path d="{od}" clip-rule="evenodd"/></clipPath></defs>')
        own_attr = ' clip-path="url(#oclip)"'
    if hidden:
        keep = geom2d.difference(box(-1, -1, w + 1, h + 1)
                                 if keep is None else keep, hide)
    clip_attr = ""
    cd = geom2d.path_d(keep) if keep is not None else ""
    if cd:
        parts.append(f'<defs><clipPath id="sclip">'
                     f'<path d="{cd}" clip-rule="evenodd"/></clipPath></defs>')
        clip_attr = ' clip-path="url(#sclip)"'
    stroke_g = len(parts)
    contour_d = geom2d.path_d(contour, contour_arcs, wide=True) \
        if contour is not None else ""
    if contour_d:
        # One side of a path cannot be stroked, so the contour strokes wide
        # enough to reach its band on both sides and the band clips it (see
        # process.contour_band). A closed path has JOINS everywhere and no
        # caps, so mitering it renders outline corners sharp -- the per-edge
        # strokes' round vertex caps alone leave them blunted.
        band = process.contour_band(contour, line_px, sil_px, studs)
        if hidden:
            band = geom2d.difference(band, hide)
        bd = geom2d.path_d(band)
        if bd:
            reach = process.contour_reach(line_px, sil_px, studs)
            parts.append(f'<defs><clipPath id="cclip"><path d="{bd}" '
                         f'clip-rule="evenodd"/></clipPath></defs>')
            parts.append('<g stroke="black" fill="none" '
                         'clip-path="url(#cclip)">')
            parts.append(f'<path d="{contour_d}" stroke-width="{2 * reach:.2f}" '
                         f'stroke-linejoin="miter" stroke-miterlimit="5"/>')
            parts.append("</g>")
    parts.append(f'<g stroke="black" fill="none" stroke-linecap="round"{clip_attr}>')
    parts += stroke_elements(segs, line_px, sil_px, studs)
    if own:
        parts.append("</g>")
        parts.append(f'<g stroke="black" fill="none" stroke-linecap="round"'
                     f'{own_attr}>')
        parts += stroke_elements(own, line_px, sil_px, studs)
    if debug_colors:
        mode = debug_colors if isinstance(debug_colors, str) else "cycle"
        _colorize_studs(parts, *placed, mode,
                        _colorize(parts, stroke_g, mode))
    parts.append("</g>")
    parts.append("</svg>")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts))
    return out_path


def cel_svg(rgba: Image.Image, out_path: Path, levels: int = 4,
            bg: str = "none", opacity: float = 1.0) -> Path:
    rgba = rgba.convert("RGBA")
    g = process.posterize(process.to_grayscale(rgba), levels)
    arr = np.asarray(g)
    sil = np.asarray(process._silhouette_mask(rgba), int) > 16
    layers: list[tuple[list[str], str]] = []
    vb = tf = None
    for v in sorted(set(np.unique(arr).tolist())):
        if v >= 255:
            continue
        mask = (arr <= v) & sil          # cumulative: this dark or darker
        if mask.sum() == 0:
            continue
        mL = Image.fromarray(np.where(mask, 0, 255).astype(np.uint8), "L")
        ds, vbb, tff = _potrace(mL)
        if not ds:
            continue
        vb = vb or vbb
        tf = tf or tff
        layers.append((ds, f"#{v:02x}{v:02x}{v:02x}"))
    layers.reverse()                     # lightest/largest first, darker on top
    _write_svg(Path(out_path), vb or "0 0 1 1", tf or "", layers, bg=bg,
               opacity=opacity)
    return Path(out_path)
