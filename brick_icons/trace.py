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


def segments_to_svg(segs, w, h, out_path, line_px=2, sil_px=2,
                    physical=None, s=None, line_mm=0.2, sil_mm=0.2,
                    fills=None, bg: str = "none", opacity: float = 1.0,
                    clip_geom=None, contour_d: str | None = None,
                    label: str | None = None) -> Path:
    if physical is not None:
        w_mm, h_mm = physical
        root = (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{w_mm:.2f}mm" height="{h_mm:.2f}mm" '
                f'viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet">')
        line_px = line_mm / 0.4 * s
        sil_px = sil_mm / 0.4 * s
    else:
        root = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
                f'preserveAspectRatio="xMidYMid meet">')
    parts = [root]
    if bg != "none":
        parts.append(f'<rect width="100%" height="100%" fill="{bg}"/>')
    if fills:
        # Each fill is stroked in its own paint (~0.8px) so antialiasing seams
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
        for i, fo in enumerate(fills):
            if "gradient" in fo:
                g = fo["gradient"]
                stops = "".join(
                    f'<stop offset="{o * 100:.1f}%" stop-color="{c}"/>' for o, c in g["stops"])
                if g.get("type") == "radial":
                    # unit-circle gradient space mapped onto the group's
                    # bounding ellipse; fx/fy shift the bright spot lightward
                    tf = (f'matrix({g["r"]:.2f} 0 0 {g["r"] * g["ratio"]:.2f} '
                          f'{g["cx"]:.2f} {g["cy"]:.2f})')
                    key = ("radial", tf, f'{g["fx"]:.3f},{g["fy"]:.3f}', stops)
                    gid = def_ids.get(key)
                    if gid is None:
                        gid = f"g{i}"
                        def_ids[key] = gid
                        defs.append(
                            f'<radialGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                            f'cx="0" cy="0" r="1" fx="{g["fx"]:.3f}" fy="{g["fy"]:.3f}" '
                            f'gradientTransform="{tf}">{stops}</radialGradient>')
                else:
                    key = (f'{g["x1"]:.2f},{g["y1"]:.2f},{g["x2"]:.2f},{g["y2"]:.2f}', stops)
                    gid = def_ids.get(key)
                    if gid is None:
                        gid = f"g{i}"
                        def_ids[key] = gid
                        defs.append(
                            f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                            f'x1="{g["x1"]:.2f}" y1="{g["y1"]:.2f}" '
                            f'x2="{g["x2"]:.2f}" y2="{g["y2"]:.2f}">{stops}</linearGradient>')
                paint = f"url(#{gid})"
            else:
                paint = fo["fill"]
            # translucent fills paint fill-only: the self-stroke that closes
            # AA seams between abutting opaque fills double-paints its 0.4px
            # overhang onto neighbors when composited at opacity < 1 —
            # concentric ghost rings on a dish's stacked bands (4740)
            seam = (f' stroke="{paint}" stroke-width="0.8"'
                    if opacity >= 1.0 else "")
            body.append(f'<path d="{fo["d"]}" fill="{paint}" '
                        f'fill-rule="evenodd"{seam}{face_op}/>')
        body.append("</g>")
        if defs:
            parts.append("<defs>" + "".join(defs) + "</defs>")
        parts += body
    # Clip the stroke layer to the silhouette buffered outward by half the
    # widest stroke (mitered): round end caps otherwise poke half a width
    # past outline corners into the background ("frayed" corners).
    clip_attr = ""
    if clip_geom is not None:
        from . import geom2d
        # grow by drawn-arc bulge regions so the clip never flattens an arc
        clip = geom2d.union_all([clip_geom] + geom2d.arc_regions(segs))
        cd = geom2d.buffer_d(clip, max(line_px, sil_px) / 2.0)
        if cd:
            parts.append(f'<defs><clipPath id="sclip">'
                         f'<path d="{cd}" clip-rule="evenodd"/></clipPath></defs>')
            clip_attr = ' clip-path="url(#sclip)"'
    parts.append(f'<g stroke="black" fill="none" stroke-linecap="round"{clip_attr}>')
    if contour_d:
        # closed silhouette contour under the per-edge strokes: a closed path
        # has JOINS everywhere and no caps, so mitering it renders outline
        # corners sharp — the per-edge strokes' round vertex caps alone leave
        # them blunted
        parts.append(f'<path d="{contour_d}" stroke-width="{sil_px:.2f}" '
                     f'stroke-linejoin="miter" stroke-miterlimit="5"/>')
    line_groups = {}                                  # sw -> [(x1,y1,x2,y2)]
    for op in segs:
        if len(op) == 5:                              # legacy line tuple
            op = ("line",) + tuple(op)
        sw = sil_px if op[-1] == "sil" else line_px
        # a fragment much shorter than its stroke renders as a bare cap dot
        # (e.g. a near-end-on cylinder-wall silhouette sliver): pure noise
        if op[0] == "line":
            _, x1, y1, x2, y2, kind = op
            if math.hypot(x2 - x1, y2 - y1) < 0.6 * sw:
                continue
            line_groups.setdefault(round(sw, 2), []).append(
                (round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)))
        else:
            r = (math.hypot(op[3], op[4]) + math.hypot(op[5], op[6])) / 2.0
            if r * math.radians(abs(op[8] - op[7])) < 0.6 * sw:
                continue
            parts.append(f'<path d="{_arc_to_svg(op)}" stroke-width="{sw:.2f}"/>')
    # straight strokes sharing endpoints chain into mitered polylines, with
    # elbow-join paths over the leftover corner wedges — separate
    # round-capped strokes pinch every 3D corner (see _chain_line_ops)
    joinery = ' stroke-linejoin="miter" stroke-miterlimit="5"'
    for sw in sorted(line_groups):
        ops = line_groups[sw]
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
    parts.append("</g>")
    if label:
        # part id in fixed small print, bottom-left corner: absolute size
        # (2 mm physical, 8 canvas px otherwise), deliberately NOT scaled to
        # the part — identification aid for contact sheets and test renders
        fs = 2.0 / 0.4 * s if physical is not None else 8.0
        pad = fs * 0.25
        parts.append(f'<text x="{pad:.2f}" y="{h - pad:.2f}" '
                     f'font-family="monospace" font-size="{fs:.2f}" '
                     f'fill="black">{label}</text>')
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
