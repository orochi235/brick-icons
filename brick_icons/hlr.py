from __future__ import annotations
import math
from collections import defaultdict, namedtuple
from pathlib import Path
import numpy as np

from . import arcfit
from . import primitives
from . import repair

# ellipses: projected circles (cx,cy,ux,uy,vx,vy) of the analytic
# primitives, px space — arc-recovery candidates for fill boundaries.
# proj: the render's Projection (fill_ops probes exact wall depths with it).
# refits: (old, new, bore) arc-op triples from the separator pinch refit —
# shade.refit_fill_boundaries moves fill seams onto the new curve.
# fold_ells: rounded (cx..vy) keys of the arcfit (fitted-round) ellipses —
# marks which drawn arcs are stylized fold arcs.
# loops: closed point loops of chained drawn fold-arc spans (op space) —
# stylized sub-region outlines for shade.fill_ops(loops=...).
VisResult = namedtuple("VisResult",
                       "segs bbox s faces analytic ellipses proj refits "
                       "fold_ells loops",
                       defaults=[(), None, (), (), ()])

_text_cache: dict[Path, list[str]] = {}


def default_roots(ldraw_dir: Path) -> list[Path]:
    ldraw_dir = Path(ldraw_dir)
    return [ldraw_dir / "p" / "48", ldraw_dir / "p",
            ldraw_dir / "parts", ldraw_dir / "parts" / "s", ldraw_dir / "models"]


def resolve(name: str, roots: list[Path]) -> Path | None:
    name = name.replace("\\", "/").strip()
    base = name.split("/")[-1]
    for root in roots:
        for cand in (root / name, root / base):
            if cand.exists():
                return cand
    return None


def _lines(path: Path) -> list[str]:
    if path not in _text_cache:
        _text_cache[path] = Path(path).read_text(errors="replace").splitlines()
    return _text_cache[path]


def _bfc_certified(ln: str) -> bool:
    """True if a line certifies BFC winding ('0 BFC CERTIFY ...' or a bare
    '0 BFC CW|CCW' orientation statement — either establishes trusted winding)."""
    tok = ln.split()
    if len(tok) >= 3 and tok[0] == "0" and tok[1] == "BFC":
        flags = tok[2:]
        if "NOCERTIFY" in flags:
            return False
        return "CERTIFY" in flags or "CW" in flags or "CCW" in flags
    return False


def flatten(path: Path, R: np.ndarray, t: np.ndarray, out: dict,
            roots: list[Path], depth: int = 0,
            inherited_invert: bool = False) -> None:
    if depth > 30:
        return
    out.setdefault("tri_meta", [])
    # `inherited_invert` fully encodes ancestor mirrors + INVERTNEXTs; each
    # reference below XORs in only its OWN matrix's reflection. Recomputing
    # reflection from the accumulated basis here would count every ancestor
    # mirror a second time and cancel it (lost the flip for geometry nested
    # two+ levels under a mirrored reference: 32062's axle end, 4019's gear
    # half). Only the root call's own basis is folded in here.
    base_invert = inherited_invert
    if depth == 0:
        base_invert ^= bool(np.linalg.det(R) < 0)
    lines = _lines(path)
    certified = any(_bfc_certified(ln) for ln in lines)
    local_cw = False            # CCW is the LDraw default winding
    invert_next = False
    for ln in lines:
        tok = ln.split()
        if not tok:
            continue
        typ = tok[0]
        if typ == "0":
            cmd = tok[1:]
            if len(cmd) >= 2 and cmd[0] == "BFC":
                flags = cmd[1:]
                if "CW" in flags:
                    local_cw = True
                if "CCW" in flags:
                    local_cw = False
                if "INVERTNEXT" in flags:
                    invert_next = True
            continue
        if typ == "1":
            if len(tok) >= 15:
                x, y, z = map(float, tok[2:5])
                a, b, c, d, e, f, g, h, i = map(float, tok[5:14])
                M = np.array([[a, b, c], [d, e, f], [g, h, i]], float)
                T = np.array([x, y, z], float)
                ref = " ".join(tok[14:])
                ref = primitives.ALIAS_REFS.get(
                    ref.replace("\\", "/").split("/")[-1].lower(), ref)
                Rsub, tsub = R @ M, R @ T + t
                prim = primitives.from_ref(ref, Rsub, tsub)
                if prim is not None and "analytic" in out:
                    out["analytic"].append(prim)
                else:
                    sub = resolve(ref, roots)
                    if sub is not None:
                        m_reflect = bool(np.linalg.det(M) < 0)
                        flatten(sub, Rsub, tsub, out, roots, depth + 1,
                                inherited_invert=base_invert ^ invert_next
                                ^ m_reflect)
            invert_next = False
        elif typ in ("2", "5") and len(tok) >= 8:
            pts = np.array(list(map(float, tok[2:])), float).reshape(-1, 3)
            out[typ].append(pts @ R.T + t)
        elif typ in ("3", "4"):
            n = 3 if typ == "3" else 4
            if len(tok) >= 2 + 3 * n:
                pts = np.array(list(map(float, tok[2:2 + 3 * n])), float).reshape(n, 3) @ R.T + t
                tri_invert = base_invert ^ local_cw
                meta = {"certified": certified, "invert": tri_invert}
                if n == 3:
                    out["tri"].append(pts)
                    out["tri_meta"].append(dict(meta))
                else:
                    out["tri"].append(pts[[0, 1, 2]])
                    out["tri_meta"].append(dict(meta))
                    out["tri"].append(pts[[0, 2, 3]])
                    out["tri_meta"].append(dict(meta))


SIGN_Z = -1.0          # tuned so parts face the camera (matches LDView iso)
MESH_CACHE_DIR = Path(".cache/mesh")


def view_basis(lat: float, long: float):
    la, lo = math.radians(lat), math.radians(long)
    up_world = np.array([0.0, -1.0, 0.0])          # LDraw Y is down
    d = np.array([math.cos(la) * math.sin(lo), -math.sin(la),
                  SIGN_Z * math.cos(la) * math.cos(lo)])
    forward = -d / np.linalg.norm(d)
    right = np.cross(forward, up_world); right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return right, up, forward


def project(P: np.ndarray, right, up, forward):
    return P @ right, -(P @ up), P @ forward       # sx, sy(image-down), depth


def same_side(p1, p2, c1, c2) -> bool:
    e = p2 - p1
    cr1 = e[0] * (c1[1] - p1[1]) - e[1] * (c1[0] - p1[0])
    cr2 = e[0] * (c2[1] - p1[1]) - e[1] * (c2[0] - p1[0])
    return bool(cr1 * cr2 > 0)


def rasterize_zbuffer(tri_s: np.ndarray, tri_z: np.ndarray, W: int, H: int) -> np.ndarray:
    zbuf = np.full((H, W), np.inf)
    for v, zz in zip(tri_s, tri_z):
        minx = max(int(np.floor(v[:, 0].min())), 0); maxx = min(int(np.ceil(v[:, 0].max())), W - 1)
        miny = max(int(np.floor(v[:, 1].min())), 0); maxy = min(int(np.ceil(v[:, 1].max())), H - 1)
        if maxx < minx or maxy < miny:
            continue
        gx, gy = np.meshgrid(np.arange(minx, maxx + 1), np.arange(miny, maxy + 1))
        x0, y0 = v[0]; x1, y1 = v[1]; x2, y2 = v[2]
        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denom) < 1e-9:
            continue
        a = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / denom
        b = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / denom
        cc = 1 - a - b
        inside = (a >= -1e-4) & (b >= -1e-4) & (cc >= -1e-4)
        z = a * zz[0] + b * zz[1] + cc * zz[2]
        sub = zbuf[miny:maxy + 1, minx:maxx + 1]
        m = inside & (z < sub)
        sub[m] = z[m]
    return zbuf


def dilate_zbuffer(zbuf: np.ndarray, r: int) -> np.ndarray:
    """Neighborhood-max of a z-buffer over a (2r+1) box: each cell becomes the
    farthest depth nearby. Used for edge occlusion so silhouette-tangent edges
    (with background on one side) survive while buried edges stay hidden."""
    if r <= 0:
        return zbuf
    d = zbuf.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx or dy:
                d = np.maximum(d, np.roll(np.roll(zbuf, dy, 0), dx, 1))
    return d


def clip_visible(seg, zbuf, W, H, depth, bias):
    """Return list of visible sub-segments. `depth` may be a scalar (uniform) or
    (z1, z2) for per-endpoint depth. Samples the z-buffer along the segment."""
    x1, y1, x2, y2, kind = seg
    z1, z2 = (depth, depth) if np.isscalar(depth) else depth
    n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 2))
    ts = np.linspace(0, 1, n)
    xs = x1 + (x2 - x1) * ts; ys = y1 + (y2 - y1) * ts; zs = z1 + (z2 - z1) * ts
    xi = np.clip(xs.astype(int), 0, W - 1); yi = np.clip(ys.astype(int), 0, H - 1)
    vis = zs <= zbuf[yi, xi] + bias
    runs, i = [], 0
    while i < n:
        if vis[i]:
            j = i
            while j + 1 < n and vis[j + 1]:
                j += 1
            runs.append((xs[i], ys[i], xs[j], ys[j], kind))
            i = j + 1
        else:
            i += 1
    return runs


EDGE_BIAS = 0.004      # fraction of depth range
SIL_BIAS = 0.03        # larger: silhouette lines sit on their own surface
EDGE_DILATE = 0.0024   # z-buffer dilation radius as a FRACTION of render_px:
                       # occlude edges against a neighborhood-max ("farthest nearby
                       # surface") buffer. Lets a silhouette-tangent edge (background
                       # just outside it, e.g. a cylinder's bottom-rim where body
                       # meets base) survive, while edges buried behind a surface on
                       # all sides stay hidden. A flat depth bias can't separate
                       # those two; see part 3941. Fraction (not px) so the effect is
                       # resolution-independent across render_px.


def _fit_params(allpts, right, up, fwd, render_px):
    """Pixel-fit (s, cx, cy) and depth range from a world point cloud."""
    a, b, z = project(allpts, right, up, fwd)
    minx, maxx, miny, maxy = a.min(), a.max(), b.min(), b.max()
    span = max(maxx - minx, maxy - miny) or 1.0
    s = (render_px - 20) / span
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    zrange = (z.max() - z.min()) or 1.0
    return s, cx, cy, zrange


def _ops_bbox(segs):
    xs, ys = [], []
    for op in segs:
        if op[0] == "line":
            xs += [op[1], op[3]]; ys += [op[2], op[4]]
        else:
            pts = primitives.arc_ellipse(op).points(
                np.radians(np.linspace(op[7], op[8], 12)))
            xs += list(pts[:, 0]); ys += list(pts[:, 1])
    xs = xs or [0, 1]; ys = ys or [0, 1]
    return (min(xs), min(ys), max(xs), max(ys))


def smooth_rim_skips(analytic, tris=None, cond=None):
    """Rim circles whose arcs are (partly) smooth joints, not edges:
    {(rim_key, side): True | bin mask} plus {("flat", key, side): True}.

    A wall's rim arc is a smooth joint wherever a wall of EQUAL slope
    continues on the OPPOSITE side of the circle plane (stacked
    cone/cylinder sections). Coverage accumulates per angular bin
    (primitives.rim_span_bins) so sectored tilings qualify too: 60474's
    side wall stacks a full upper ring on 1/12 sections with bite gaps —
    the seam vanishes where the lower wall continues and stays a real edge
    across the bites (emission splits the arc via rim_uncovered_spans).
    True means the whole circle is covered (4589's con3-on-con4 joint).
    Facet-authored wall stretches count as coverage too (`tris`, world
    coords): LDraw resumes a primitive-tiled wall as raw quads (60474's
    outer wall beside each bite, half its center-hole wall) and the seam
    is just as smooth there — see primitives.rim_facet_span_bins.

    Author-declared condlines (`cond`, type-5 world chords) on a rim circle
    count as opposite-side coverage UNCONDITIONALLY — the declaration says
    the joint is smooth whatever the slopes are (4740's dish stacks three
    cone bands of different pitches and condlines every junction; real
    creases are authored as type-2 edges) — see
    primitives.rim_cond_span_bins.

    Flat coplanar seams: a circle stretch with flat surface on BOTH radial
    sides (concentric ring tiling) is an interior seam, not an edge (see
    flat_rims). A side's arcs are suppressed only when the OPPOSITE side
    covers that side's whole angular span, so tilings that stop partway
    keep the real edge along the uncovered stretch (60474 tiles its top
    from 1/8 rings x 8 instances)."""
    wall_cov = defaultdict(lambda: np.zeros(primitives._RIM_BINS, bool))
    for prim in analytic:
        for key, side, slope in prim.wall_rims():
            wall_cov[(key, side, slope)] |= primitives.rim_span_bins(prim, key)
    skips = {}
    facet_cov = {}
    cond_cov = {}
    for prim in analytic:
        for key, side, slope in prim.wall_rims():
            if (key, side) in skips:
                continue
            fk = (key, -side, slope)
            if fk not in facet_cov:
                facet_cov[fk] = primitives.rim_facet_span_bins(
                    key, -side, slope, tris)
            if key not in cond_cov:
                cond_cov[key] = primitives.rim_cond_span_bins(key, cond)
            opp = wall_cov.get(fk)
            cov = facet_cov[fk] | cond_cov[key]
            opp = cov if opp is None else opp | cov
            if not opp.any():
                continue
            # one-bin dilation absorbs float jitter where rotated instances
            # abut; the tested side is NOT dilated
            m = opp | np.roll(opp, 1) | np.roll(opp, -1)
            skips[(key, side)] = True if m.all() else m
    flat_raw = defaultdict(lambda: np.zeros(primitives._RIM_BINS, bool))
    for prim in analytic:
        for key, side in prim.flat_rims():
            flat_raw[(key, side)] |= primitives.rim_span_bins(prim, key)
    for (key, side), mask in flat_raw.items():
        opp = flat_raw.get((key, -side))
        if opp is None:
            continue
        opp = opp | np.roll(opp, 1) | np.roll(opp, -1)
        if np.all(opp[mask]):
            skips[("flat", key, side)] = True
    return skips


def _visible_segments_faceted(out, right, up, fwd, render_px, cull=True):
    """Original z-buffer pipeline; used when no analytic primitives are present.
    cull=False skips occlusion clipping (translucent rendering: every edge is
    drawn); conditional-line silhouette detection still applies — it is view
    dependence, not occlusion."""
    tri = np.array(out["tri"]) if out["tri"] else np.zeros((0, 3, 3))
    fitpts = tri.reshape(-1, 3) if len(tri) else np.array(out["2"]).reshape(-1, 3)
    if len(fitpts) == 0:
        return VisResult([], (0.0, 0.0, 1.0, 1.0), 1.0, [], [])
    sx, sy, _ = project(fitpts, right, up, fwd)
    minx, maxx, miny, maxy = sx.min(), sx.max(), sy.min(), sy.max()
    span = max(maxx - minx, maxy - miny) or 1.0
    s = (render_px - 20) / span
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    proj = primitives.Projection(right, up, fwd, s, cx, cy, render_px / 2)

    if len(tri):
        tpx, tpy, tz = proj.to_px(tri.reshape(-1, 3))
        tri_s = np.stack([tpx, tpy], 1).reshape(-1, 3, 2)
        tri_z = tz.reshape(-1, 3)
        zbuf = rasterize_zbuffer(tri_s, tri_z, render_px, render_px)
        zrange = tri_z.max() - tri_z.min() or 1.0
    else:
        zbuf = np.full((render_px, render_px), np.inf); zrange = 1.0
    zedge = dilate_zbuffer(zbuf, max(2, round(render_px * EDGE_DILATE)))

    segs = []
    for e in out["2"]:
        ax, ay, az = proj.to_px(e[0:1]); bx, by, bz = proj.to_px(e[1:2])
        seg = (ax[0], ay[0], bx[0], by[0], "edge")
        if cull:
            segs += clip_visible(seg, zedge, render_px,
                                 render_px, (az[0], bz[0]), EDGE_BIAS * zrange)
        else:
            segs.append(seg)
    for q in out["5"]:
        px, py, pz = proj.to_px(q)
        p1 = np.array([px[0], py[0]]); p2 = np.array([px[1], py[1]])
        if math.hypot(*(p2 - p1)) < 0.5:
            continue
        if same_side(p1, p2, np.array([px[2], py[2]]), np.array([px[3], py[3]])):
            seg = (px[0], py[0], px[1], py[1], "sil")
            if cull:
                segs += clip_visible(seg, zbuf, render_px,
                                     render_px, (pz[0], pz[1]), SIL_BIAS * zrange)
            else:
                segs.append(seg)

    xs = [c for sg in segs for c in (sg[0], sg[2])] or [0, 1]
    ys = [c for sg in segs for c in (sg[1], sg[3])] or [0, 1]
    from . import shade
    faces = shade.faces_from_tris(tri, proj, cond_edges=out["5"]) if len(tri) else []
    faces = shade.order_faces(faces, eps=EDGE_BIAS * zrange)
    return VisResult(segs, (min(xs), min(ys), max(xs), max(ys)), s, faces, [],
                     (), proj)


def _visible_segments_analytic(out, right, up, fwd, render_px, cull=True):
    """Exact pipeline: analytic occlusion oracle + true arc/line drawn ops.
    cull=False emits every drawn op whole (translucent rendering)."""
    analytic = out["analytic"]
    fit_arcs = out.get("fit_arcs", [])
    half = render_px / 2.0

    cloud = []
    if out["tri"]:
        cloud.append(np.array(out["tri"]).reshape(-1, 3))
    if out["2"]:
        cloud.append(np.array(out["2"]).reshape(-1, 3))
    for prim in analytic:
        cloud.append(prim.fit_pts())
    for a in fit_arcs:
        cloud.append(np.array([arcfit.arc_point(a, t) for t in
                               np.linspace(a["t0"], a["t1"], 5)]))
    allpts = np.vstack(cloud)
    s, cx, cy, zrange = _fit_params(allpts, right, up, fwd, render_px)
    eps = 1e-3 * zrange
    proj = primitives.Projection(right, up, fwd, s, cx, cy, half)

    # occluders: analytic surfaces + flat triangles. Only ORIGINAL primitives
    # join the stroke-visibility list; walls merged later inside
    # faces_from_analytic build their own (cached) occluder lazily for
    # witness ordering, and must NOT be added here — their member surfaces
    # already cover the same geometry.
    occluders = [p.occluder() for p in analytic if p.occluder() is not None]
    if out["tri"]:
        occluders.append(primitives.TriangleOccluder(np.array(out["tri"])))

    # drawn ops: analytic curves (+ a cylinder excludes itself from its
    # silhouette). Wall-rim seams and coplanar flat seams are suppressed
    # (per angular bin) where a smooth surface continues across them — see
    # smooth_rim_skips.
    shared_rims = smooth_rim_skips(analytic,
                                   np.array(out["tri"]) if out["tri"] else None,
                                   cond=out["5"])
    specs = []
    for prim in analytic:
        own = prim.occluder()
        for op, dfn in prim.drawn_with_depth(proj, skip_rims=shared_rims):
            specs.append((op, dfn, own if op[-1] == "sil" else None))
    # fitted hand-faceted rounds: drawn as true arcs, but occlusion-tested
    # along their chord path (see arcfit) via the spec's proxy element
    fit_ells = []
    for a in fit_arcs:
        ell = primitives.project_circle_uv(a["C"], a["U"], a["V"], proj.to_AB,
                                           proj.s, proj.cx, proj.cy, half)
        cpx, cpy, cpz = proj.to_px(a["P"])
        tv = a["tv"]

        def chord_proxy(degs, cpx=cpx, cpy=cpy, cpz=cpz, tv=tv):
            d = np.asarray(degs, float)
            return (np.interp(d, tv, cpx), np.interp(d, tv, cpy),
                    np.interp(d, tv, cpz))
        specs.append((primitives._arc_op(ell, a["t0"], a["t1"], "edge"),
                      primitives._arc_depth_fn(ell), None, chord_proxy))
        # snap tolerance (8th element) = the fitted arc's measured radial
        # deviation from the authored chain vertices (+AA margin, capped):
        # fills densify/snap onto the DRAWN stylized curve instead of
        # scalloping past the stroke at facet corners (3941's X outline)
        Me = np.array([[ell.u[0], ell.v[0]], [ell.u[1], ell.v[1]]])
        mu = np.linalg.inv(Me) @ (np.stack([cpx, cpy], 0)
                                  - ell.center.reshape(2, 1))
        ru = np.hypot(mu[0], mu[1])
        pr = np.hypot(cpx - ell.center[0], cpy - ell.center[1])
        dev = float(np.max(np.abs(ru - 1.0) * pr / np.maximum(ru, 1e-9)))
        fit_ells.append((float(ell.center[0]), float(ell.center[1]),
                         float(ell.u[0]), float(ell.u[1]),
                         float(ell.v[0]), float(ell.v[1]),
                         a["step"] * 1.15 + 1.0,
                         min(dev * 1.25 + 0.5, 6.0)))
    # non-substituted straight edges (box edges, chords) and conditionals
    for e in out["2"]:
        px, py, z = proj.to_px(e)
        specs.append((("line", float(px[0]), float(py[0]),
                       float(px[1]), float(py[1]), "edge"),
                      primitives._line_depth_fn(float(z[0]), float(z[1]))))
    for q in out["5"]:
        px, py, z = proj.to_px(q)
        p1 = np.array([px[0], py[0]]); p2 = np.array([px[1], py[1]])
        if math.hypot(*(p2 - p1)) < 0.5:
            continue
        if same_side(p1, p2, np.array([px[2], py[2]]), np.array([px[3], py[3]])):
            specs.append((("line", float(px[0]), float(py[0]),
                           float(px[1]), float(py[1]), "sil"),
                          primitives._line_depth_fn(float(z[0]), float(z[1]))))

    if cull:
        segs = primitives.visible_subops(specs, occluders, proj.ray_origin, fwd,
                                         eps, n=64)
    else:
        segs = [spec[0] for spec in specs]
    from . import shade
    tri_faces = shade.faces_from_tris(np.array(out["tri"]), proj,
                                      cond_edges=out["5"]) if out["tri"] else []
    an_faces = shade.faces_from_analytic(analytic, proj)
    # facet-authored stretches of a primitive wall (60474's bite flanks)
    # join the abutting analytic band's gradient instead of flat-toning
    shade.absorb_wall_facets(tri_faces, an_faces)
    own_occ = {id(f): f["prim"].occluder() for f in an_faces
               if f["prim"].occluder() is not None}
    # Witness-depth ordering replaces both the mean-depth painter sort and the
    # occlusion cull: hidden faces paint first and get covered.
    faces = shade.order_faces(tri_faces + an_faces, proj, eps, own_occ=own_occ)

    # every drawn circle (no rim suppression) is an arc-recovery candidate
    # for the fill boundaries sampled from the same projected circles;
    # fitted-round ellipses join them carrying their own (coarse) max step.
    # Rim candidates carry step 25 deg: faceted faces ring holes/studs with
    # LDraw 16-gons (22.5 deg steps) whose vertices lie ON the rim circle —
    # under the default step their chords stay straight and the face fill
    # cuts across thin slivers (a counterbore crescent's tips).
    ells, seen = list(fit_ells), set()
    for prim in analytic:
        for op, *_ in prim.drawn_with_depth(proj):
            if op[0] == "arc":
                key = tuple(round(x, 6) for x in op[1:7])
                if key not in seen:
                    seen.add(key)
                    ells.append(op[1:7] + (25.0,))
    # NOTE: primitives.facet_snap_rims + the one-sided (negative) snap
    # tolerance in geom2d are wired for pulling truncation-ribbon
    # tessellation onto its true rim circle, but emitting those candidates
    # here is NOT yet safe: fills snap onto the circle while the drawn
    # chord strokes stay put, and the divergence opens paint slivers at
    # truncation zones (3941's front stud). Emit them only together with a
    # drawn-chord refit onto the same circles (arcfit-style, see
    # fit_edge_arcs) so strokes and fills move in lockstep.
    fold_keys = [tuple(round(v, 6) for v in e[:6]) for e in fit_ells]
    return VisResult(segs, _ops_bbox(segs), s, faces, analytic, ells, proj,
                     fold_ells=fold_keys)


def _snap_rim_crossings(segs, max_snap=4.0, vertex_tol=0.25):
    """Counterbore/rim stroke stylization, two passes over the final arcs.

    1) SNAP: a partial arc's endpoints move onto the nearest analytic
       junction with adjoining geometry when within max_snap degrees —
       sampled visibility stops up to a sample short of the true graze,
       leaving the end 'just next to' the adjoining stroke instead of ON it.
       Junction targets: crossings with any larger nearby circle, crossings
       with drawn lines (within the drawn span), and line endpoints lying on
       the carrier (within vertex_tol, op units) — the shared world vertex
       where a cut edge meets the round.
    2) PINCH REFIT: a counterbore's wall/annulus separator (partial arc M
       congruent to the full opening F, drawn where it occludes the bore B)
       is replaced by the circumcircle through (pinch1, pinch2, M's apex)
       fit in the BORE's unit space — an ellipse with the bore's aspect —
       so the separator reads concentric/parallel to the bore. The pinch
       points are B's visible endpoints. (Fitting a circle CONGRUENT to F
       through two of F's own points degenerates to F itself, hence the
       unit-space circumcircle instead.)

    Returns (segs, refits): refits records each replacement as an
    (old, new, bore) arc-op triple so fill seams can follow the new curve.
    """
    refits = []
    arcs = [(i, op) for i, op in enumerate(segs) if op[0] == "arc"]
    out = list(segs)

    def radius(op):
        return (math.hypot(op[3], op[4]) + math.hypot(op[5], op[6])) / 2.0

    def point(op, t):
        th = math.radians(t)
        return np.array([op[1] + math.cos(th) * op[3] + math.sin(th) * op[5],
                         op[2] + math.cos(th) * op[4] + math.sin(th) * op[6]])

    lines = [op for op in segs if op[0] == "line"]

    # pass 1: snap partial-arc ends onto analytic junctions with adjoining
    # geometry — crossings with larger circles, crossings with drawn lines,
    # and on-carrier line endpoints (vertices)
    for i, a in arcs:
        if abs(a[8] - a[7]) >= 359.9:
            continue
        ra = radius(a)
        ca = np.array(a[1:3])
        try:
            Mainv = np.linalg.inv(np.array([[a[3], a[5]], [a[4], a[6]]], float))
        except np.linalg.LinAlgError:
            continue
        cands = []  # junction angles in a's param, degrees
        for j, b in arcs:
            rb = radius(b)
            sep = math.hypot(a[1] - b[1], a[2] - b[2])
            if j == i or rb < ra - 1e-9 or not 1e-6 < sep < 0.6 * rb:
                continue
            try:
                Mbinv = np.linalg.inv(np.array([[b[3], b[5]], [b[4], b[6]]], float))
            except np.linalg.LinAlgError:
                continue
            # crossings in a's param: |d + rho (cos t, sin t)| = 1 in b's
            # unit space, d = Mb^-1 (ca - cb), rho = ra / rb
            rho = ra / rb
            d = Mbinv @ (ca - np.array(b[1:3]))
            hyp = 2.0 * rho * float(np.hypot(*d))
            C_ = 1.0 - rho * rho - float(d @ d)
            if hyp < 1e-12 or abs(C_) > hyp:
                continue
            phi = math.atan2(d[1], d[0])
            dth = math.acos(max(-1.0, min(1.0, C_ / hyp)))
            cands += [math.degrees(phi + dth), math.degrees(phi - dth)]
        for L in lines:
            # exact, in a's own unit space: the line maps to a line, the
            # carrier to the unit circle
            q1 = Mainv @ (np.array(L[1:3]) - ca)
            q2 = Mainv @ (np.array(L[3:5]) - ca)
            dq = q2 - q1
            qq = float(dq @ dq)
            if qq > 1e-18:
                half = float(q1 @ dq)
                c0 = float(q1 @ q1) - 1.0
                disc = half * half - qq * c0
                if disc >= 0.0:
                    sd = math.sqrt(disc)
                    for s in ((-half - sd) / qq, (-half + sd) / qq):
                        if -1e-9 <= s <= 1.0 + 1e-9:
                            q = q1 + s * dq
                            cands.append(math.degrees(math.atan2(q[1], q[0])))
            for q in (q1, q2):
                if abs(float(np.hypot(q[0], q[1])) - 1.0) * ra <= vertex_tol:
                    cands.append(math.degrees(math.atan2(q[1], q[0])))
        # each candidate claims the nearer endpoint; each endpoint takes its
        # nearest claimant within max_snap
        t0, t1 = a[7], a[8]
        best0 = best1 = None
        for cr in cands:
            d0 = ((cr - t0 + 180.0) % 360.0) - 180.0
            d1 = ((cr - t1 + 180.0) % 360.0) - 180.0
            if abs(d0) <= max_snap and abs(d0) <= abs(d1):
                if best0 is None or abs(d0) < abs(best0):
                    best0 = d0
            elif abs(d1) <= max_snap:
                if best1 is None or abs(d1) < abs(best1):
                    best1 = d1
        t0 += best0 or 0.0
        t1 += best1 or 0.0
        if (t0, t1) != (a[7], a[8]):
            out[i] = a[:7] + (t0, t1) + (a[9],)

    # pass 2: refit counterbore separators through the bore's pinch points
    arcs = [(i, op) for i, op in enumerate(out) if op[0] == "arc"]
    full = [(i, op) for i, op in arcs if abs(op[8] - op[7]) >= 359.9]
    part = [(i, op) for i, op in arcs if abs(op[8] - op[7]) < 359.9]
    for _, F in full:
        rF, cF = radius(F), np.array(F[1:3])

        def sep_from_F(op):
            return math.hypot(op[1] - cF[0], op[2] - cF[1])

        emms = [(i, op) for i, op in part
                if abs(radius(op) - rF) <= 0.01 * rF and 1e-6 < sep_from_F(op) < rF]
        bores = [(i, op) for i, op in part
                 if radius(op) < 0.9 * rF and sep_from_F(op) <= 0.35 * rF]
        if not emms or not bores:
            continue
        mi, M = min(emms, key=lambda t: sep_from_F(t[1]))
        _, B = min(bores, key=lambda t: sep_from_F(t[1]))
        try:
            Mb = np.array([[B[3], B[5]], [B[4], B[6]]], float)
            Mbinv = np.linalg.inv(Mb)
        except np.linalg.LinAlgError:
            continue
        cB = np.array(B[1:3])
        pts = [point(B, B[7]), point(B, B[8]), point(M, (M[7] + M[8]) / 2.0)]
        (ax_, ay_), (bx_, by_), (qx, qy) = [Mbinv @ (p - cB) for p in pts]
        d = 2.0 * (ax_ * (by_ - qy) + bx_ * (qy - ay_) + qx * (ay_ - by_))
        if abs(d) < 1e-9:
            continue  # collinear in unit space: no circumcircle
        na, nb, nq = ax_ * ax_ + ay_ * ay_, bx_ * bx_ + by_ * by_, qx * qx + qy * qy
        uc = np.array([(na * (by_ - qy) + nb * (qy - ay_) + nq * (ay_ - by_)) / d,
                       (na * (qx - bx_) + nb * (ax_ - qx) + nq * (bx_ - ax_)) / d])
        rho = math.hypot(ax_ - uc[0], ay_ - uc[1])
        if not 1e-6 < rho < 5.0:
            continue  # near-degenerate fit; keep the authored separator
        cN = cB + Mb @ uc
        Mn = rho * Mb
        Mninv = np.linalg.inv(Mn)

        def angle_on(p):
            v = Mninv @ (p - cN)
            return math.degrees(math.atan2(v[1], v[0]))

        t1a, t2a, ta = (angle_on(p) for p in pts)
        sweep = (t2a - t1a) % 360.0
        if (ta - t1a) % 360.0 <= sweep:
            t0n, t1n = t1a, t1a + sweep
        else:
            t0n, t1n = t2a, t2a + (360.0 - sweep)
        new = ("arc", float(cN[0]), float(cN[1]),
               float(Mn[0, 0]), float(Mn[1, 0]),
               float(Mn[0, 1]), float(Mn[1, 1]), t0n, t1n, M[9])
        refits.append((out[mi], new, B))
        out[mi] = new

    return out, refits


def _refit_candidates(refits):
    """Fill arc-candidates for refit separators: (cx,cy,ux,uy,vx,vy, step,
    snap_tol) 8-tuples. The snap tolerance is MEASURED (cf. fit_ells): the
    old (authored) curve's max radial deviation from the new one over the
    drawn span, +AA margin, capped — fill seams authored along the old
    curve snap onto the DRAWN curve (densify_on_arcs) instead of opening a
    tone lens beside the stroke (3941's boss/rim pinch wedge)."""
    cands = []
    for old, new, _bore in refits:
        ts = np.radians(np.linspace(old[7], old[8], 33))
        px = old[1] + np.cos(ts) * old[3] + np.sin(ts) * old[5]
        py = old[2] + np.cos(ts) * old[4] + np.sin(ts) * old[6]
        try:
            Mninv = np.linalg.inv(np.array([[new[3], new[5]],
                                            [new[4], new[6]]], float))
        except np.linalg.LinAlgError:
            cands.append(new[1:7] + (25.0,))
            continue
        mu = Mninv @ (np.stack([px, py], 0)
                      - np.array(new[1:3], float).reshape(2, 1))
        ru = np.hypot(mu[0], mu[1])
        pr = np.hypot(px - new[1], py - new[2])
        dev = float(np.max(np.abs(ru - 1.0) * pr / np.maximum(ru, 1e-9)))
        cands.append(new[1:7] + (25.0, min(dev * 1.25 + 0.5, 6.0)))
    return cands


def _fold_arc_loops(segs, fold_ells, bridge_frac=0.4, step=2.0):
    """Closed loops of drawn fitted-arc (arcfit) spans: the stylized outline
    of a sub-region, e.g. 3941's axle-cross post. Spans chain by coincident
    endpoints — authored junctions and pass-1 snaps land them exactly on one
    another — and chains left open by occluded sections (the front stud over
    the post outline's bottom) close by straight bridges. A loop only stands
    if its bridges total under bridge_frac of its perimeter: longer jumps
    mean unrelated fragments, not an outline. Returns sampled point loops
    (op space) for shade.fill_ops(loops=...)."""
    keys = {tuple(round(v, 6) for v in e[:6]) for e in fold_ells}
    chains = []          # [pts (N,2), drawn length, bridged length]
    for op in segs:
        if op[0] != "arc" or abs(op[8] - op[7]) >= 359.9:
            continue
        if tuple(round(v, 6) for v in op[1:7]) not in keys:
            continue
        n = max(3, int(abs(op[8] - op[7]) / step) + 1)
        t = np.radians(np.linspace(op[7], op[8], n))
        pts = np.stack([op[1] + np.cos(t) * op[3] + np.sin(t) * op[5],
                        op[2] + np.cos(t) * op[4] + np.sin(t) * op[6]],
                       axis=1)
        chains.append([pts, float(np.sum(np.linalg.norm(np.diff(pts, axis=0),
                                                        axis=1))), 0.0])
    loops = []
    while chains:
        # nearest end pair over all chains, self-pairs included: exact
        # junctions (d ~ 0) always join ahead of any bridge
        best = None                      # (dist, i, j, flip_i, flip_j)
        for i, ci in enumerate(chains):
            d = float(np.linalg.norm(ci[0][0] - ci[0][-1]))
            if best is None or d < best[0]:
                best = (d, i, i, False, False)
            for j in range(i + 1, len(chains)):
                cj = chains[j]
                for fi in (False, True):       # flip i so its tail joins
                    pi = ci[0][0] if fi else ci[0][-1]
                    for fj in (False, True):   # flip j so its head joins
                        pj = cj[0][-1] if fj else cj[0][0]
                        d = float(np.linalg.norm(pi - pj))
                        if d < best[0]:
                            best = (d, i, j, fi, fj)
        d, i, j, fi, fj = best
        if i == j:                       # close the chain into a loop
            pts, drawn, bridged = chains.pop(i)
            bridged += d
            perim = drawn + bridged
            if perim > 0 and bridged <= bridge_frac * perim:
                loops.append(pts)
            continue
        ci, cj = chains[i], chains[j]
        pi = ci[0][::-1] if fi else ci[0]
        pj = cj[0][::-1] if fj else cj[0]
        merged = [np.vstack([pi, pj]), ci[1] + cj[1], ci[2] + cj[2] + d]
        chains = [c for k, c in enumerate(chains) if k not in (i, j)]
        chains.append(merged)
    return loops


def cull_orphan_runs(segs, cap=None, tol=None, join_tol=0.75, protect=()):
    """Stylization-level orphan cull (2654a inner-rim fraying): drop short
    stroke runs with a free end. Every such run is CORRECT HLR of authored
    micro-geometry — a blend edge or trough-circle fragment whose 3D
    junction partner is sub-stroke and culled — so in the source it
    terminates at a tiny wedge, but in the icon it visibly floats.

    The stroke graph: ops are edges, coincident endpoints (post-snap
    junctions land exactly on one another) are junction nodes. Fray is a
    DANGLING BRANCH — peeled iteratively from any free tip, accumulating
    peeled length, and stopping when the accumulated branch would exceed
    `cap` or the branch reaches an anchored point. A tip is FREE when it
    lies on no other drawn op (neither a shared endpoint nor a
    T-junction). "Lies on" is visual, not geometric: the default anchor
    tolerance is ~1 output px (0.4% of the drawn extent) — a gap smaller
    than a stroke width is bridged by the ink itself, and tangent
    continuations or sampled occlusion cuts (visible_subops n=64 stops one
    sample short of the true graze) land within it. Silhouette-kind ops
    never peel (a broken outline is always worse than fray), though they
    still anchor and chain. `cap` is a safety ceiling, not the fray
    criterion (the
    stylization call was: drop free-ended runs regardless of length): it
    defaults to 25% of the part's drawn extent so an anchor-detection
    failure can never silently delete major geometry. 2654a's worst branch
    (blend dash + blend arc, ~13% of its width) must fit under it.

    Sub-stroke GHOST ops (the culled 3D junction partners themselves; they
    never render — trace culls anything under ~0.6 stroke widths) are
    invisible to the graph: they neither anchor a tip alive nor chain onto
    a dash to extend its branch. Full ellipses have no ends and never
    cull, but they do anchor strokes landing on them.

    `protect` is a set of rounded 6-tuple carrier keys (fold_ells): arcs on
    those carriers are fitted fold spans — stylized outline whose ends
    merge TANGENTIALLY into adjoining strokes (a graze, which fitting can
    leave slightly off) and whose removal exposes the fill seams that
    follow them (3941/4032a stud-flank hooks). They never peel and they
    stop a cascade."""
    if not segs:
        return segs
    ops = [("line",) + tuple(op) if len(op) == 5 else op for op in segs]
    x0, y0, x1, y1 = _ops_bbox(segs)
    dim = max(x1 - x0, y1 - y0)
    if cap is None:
        cap = 0.25 * dim
    if tol is None:
        tol = 0.004 * dim            # ~1 output px at a 256 icon
    ghost_len = 0.002 * dim          # ~0.5 output px at a 256 icon

    # per-op polylines (anchor targets), endpoints, and lengths
    polys, ends, lens = [], [], []
    for op in ops:
        if op[0] == "line":
            pts = np.array([[op[1], op[2]], [op[3], op[4]]], float)
        else:
            _, cx, cy, ux, uy, vx, vy, t0, t1, _ = op
            n = max(3, int(abs(t1 - t0) / 2.0) + 2)
            t = np.radians(np.linspace(t0, t1, n))
            pts = np.stack([cx + np.cos(t) * ux + np.sin(t) * vx,
                            cy + np.cos(t) * uy + np.sin(t) * vy], axis=1)
        polys.append(pts)
        lens.append(float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1))))
        full = op[0] == "arc" and abs(op[8] - op[7]) >= 359.9
        ends.append(None if full else (pts[0].copy(), pts[-1].copy()))

    real = [i for i in range(len(ops)) if lens[i] >= ghost_len]

    # junction nodes: cluster coincident endpoints of real ops
    node_of = {}                       # (op, slot) -> node id
    node_pts = []
    for i in real:
        if ends[i] is None:
            continue
        for slot, p in enumerate(ends[i]):
            for nid, q in enumerate(node_pts):
                if abs(p[0] - q[0]) <= join_tol and abs(p[1] - q[1]) <= join_tol \
                        and float(np.hypot(*(p - q))) <= join_tol:
                    node_of[(i, slot)] = nid
                    break
            else:
                node_of[(i, slot)] = len(node_pts)
                node_pts.append(p)

    # flat arrays of every real op's polyline segments, for T-anchor tests
    A = np.vstack([polys[i][:-1] for i in real])
    B = np.vstack([polys[i][1:] for i in real])
    owner = np.concatenate([np.full(len(polys[i]) - 1, i) for i in real])
    D = B - A
    dd = np.maximum(np.einsum("ij,ij->i", D, D), 1e-18)

    alive = set(real)

    def anchored(i, P):
        u = np.clip(np.einsum("ij,ij->i", P - A, D) / dd, 0.0, 1.0)
        dist = np.linalg.norm(P - (A + u[:, None] * D), axis=1)
        dist[(owner == i) | ~np.isin(owner, list(alive))] = np.inf
        return float(dist.min()) <= max(tol, lens[i] / 63.0)

    # peel dangling branches: a leaf op whose tip node holds no other
    # living op and whose tip is unanchored is fray — remove it and carry
    # the removed length to the ops at its far node, so a chain is only
    # eaten back until the branch total hits the cap
    carry = defaultdict(float)
    changed = True
    while changed:
        changed = False
        degree = defaultdict(int)
        for i in alive:
            if ends[i] is not None:
                degree[node_of[(i, 0)]] += 1
                degree[node_of[(i, 1)]] += 1
        for i in sorted(alive, key=lambda k: lens[k]):
            if ends[i] is None or carry[i] + lens[i] > cap \
                    or ops[i][-1] == "sil":
                continue
            if ops[i][0] == "arc" and \
                    tuple(round(v, 6) for v in ops[i][1:7]) in protect:
                continue
            for slot in (0, 1):
                nid = node_of[(i, slot)]
                if degree[nid] > 1 or anchored(i, ends[i][slot]):
                    continue
                alive.discard(i)
                far = node_of[(i, 1 - slot)]
                for j in alive:
                    if ends[j] is not None and far in (node_of[(j, 0)],
                                                       node_of[(j, 1)]):
                        carry[j] = max(carry[j], carry[i] + lens[i])
                changed = True
                break

    return [orig for i, orig in enumerate(segs)
            if ends[i] is None or lens[i] < ghost_len or i in alive]


def _resolve_input(part: str, roots: list[Path]) -> Path:
    """Resolve a part id or .dat/.ldr/.mpd path to a file, or raise a clear error."""
    s = str(part)
    if s.lower().endswith((".dat", ".ldr", ".mpd")):
        p = Path(s)
        if not p.exists():
            raise FileNotFoundError(f"part file not found: {s}")
        return p
    path = resolve(s + ".dat", roots)
    if path is None:
        raise FileNotFoundError(f"could not resolve part {part!r} under {[str(r) for r in roots]}")
    return path


def visible_segments(part: str, ldraw_dir, lat=30.0, long=45.0, render_px=900,
                     cull=True):
    roots = default_roots(ldraw_dir)
    path = _resolve_input(part, roots)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    flatten(path, np.eye(3), np.zeros(3), out, roots)
    if out["tri"]:
        # Repair returns outward-oriented tris as float32 (cache dtype); the
        # ~7 sig-fig precision is ample at icon scale. Keep out["tri"] a LIST
        # of (3,3) rows — _visible_segments_* test it with `if out["tri"]:`.
        fixed = repair.repaired_tris(np.array(out["tri"]), out["tri_meta"],
                                     MESH_CACHE_DIR)
        out["tri"] = list(fixed)
    # hand-faceted rounds (condline-marked type-2 chains) become true arcs;
    # any part that gains one needs the analytic pipeline to draw it
    out["fit_arcs"], out["2"] = arcfit.fit_edge_arcs(out["2"], out["5"])
    right, up, fwd = view_basis(lat, long)
    if out["analytic"] or out["fit_arcs"]:
        res = _visible_segments_analytic(out, right, up, fwd, render_px, cull=cull)
    else:
        res = _visible_segments_faceted(out, right, up, fwd, render_px, cull=cull)
    segs, refits = _snap_rim_crossings(dedupe_segments(res.segs))
    if cull:
        segs = cull_orphan_runs(segs, protect=set(res.fold_ells or ()))
    if refits:
        # refit separators are arc-recovery candidates too, so the moved
        # fill seam emits as a true arc (25 deg step, like the rim ones)
        # and carries a measured snap tolerance for the old-curve seams
        res = res._replace(ellipses=list(res.ellipses)
                           + _refit_candidates(refits))
    loops = _fold_arc_loops(segs, res.fold_ells) if res.fold_ells else []
    return res._replace(segs=segs, refits=refits, loops=loops)


def _merge_intervals(iv, eps):
    """Union of 1-D intervals; only overlapping/touching (gap <= eps) merge,
    so occlusion gaps survive."""
    iv = sorted(iv)
    out = [list(iv[0])]
    for a, b in iv[1:]:
        if a <= out[-1][1] + eps:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def dedupe_segments(segs, eps=0.05):
    """Cull redundant drawn ops: collinear line spans on the same carrier
    line and arc spans on the same carrier ellipse are unioned per kind.
    LDraw subparts re-draw shared edges and rim circles many times over;
    after occlusion culling those survive as duplicate or overlapping
    elements. Exact duplicates collapse and abutting/overlapping spans merge
    into one op; gaps (real occlusion breaks) are never bridged."""
    lines, arcs, out = defaultdict(list), defaultdict(list), []
    for op in segs:
        if len(op) == 5:
            op = ("line",) + tuple(op)
        if op[0] == "line":
            _, x1, y1, x2, y2, kind = op
            dx, dy = x2 - x1, y2 - y1
            L = math.hypot(dx, dy)
            if L < 1e-9:
                continue
            dxh, dyh = dx / L, dy / L
            if (dxh, dyh) < (-dxh, -dyh):        # fold direction mod 180
                dxh, dyh = -dxh, -dyh
            c = -dyh * x1 + dxh * y1             # signed offset from origin
            # carrier-key quanta are float-noise scale (duplicates of one
            # world edge agree to ~1e-6 px), far tighter than the merge eps:
            # distinct nearly-parallel lines must never share a key
            key = (kind, round(dxh * 1e3), round(dyh * 1e3), round(c * 1e3))
            t1, t2 = dxh * x1 + dyh * y1, dxh * x2 + dyh * y2
            lines[key].append((min(t1, t2), max(t1, t2), dxh, dyh, c))
        elif op[0] == "arc":
            _, cx, cy, ux, uy, vx, vy, t0, t1, kind = op
            M = np.array([[ux, vx], [uy, vy]])
            det = M[0, 0] * M[1, 1] - M[0, 1] * M[1, 0]
            if abs(det) < 1e-9:
                out.append(op)
                continue
            # carrier key: center + quadratic form (M M^T)^-1, invariant to
            # the (u, v) parametrization the drawing primitive happened to use
            Q = np.linalg.inv(M @ M.T)
            key = (kind, round(cx * 1e3), round(cy * 1e3),
                   round(Q[0, 0] * 1e6), round(Q[0, 1] * 1e6), round(Q[1, 1] * 1e6))
            # polar angles around the center are monotonic in t and frame-free
            def polar(t_deg):
                t = math.radians(t_deg)
                d = math.cos(t) * np.array([ux, uy]) + math.sin(t) * np.array([vx, vy])
                return math.degrees(math.atan2(d[1], d[0]))
            span = abs(t1 - t0)
            if span >= 359.9:
                arcs[key].append((0.0, 360.0, op))
                continue
            p0, p1 = polar(t0), polar(t1)
            if det * (1 if t1 >= t0 else -1) < 0:  # normalize to CCW polar
                p0, p1 = p1, p0
            if p1 <= p0:
                p1 += 360.0
            arcs[key].append((p0, p1, op))
        else:
            out.append(op)
    for key, spans in lines.items():
        kind = key[0]
        _, _, dxh, dyh, c = spans[0]
        for a, b in _merge_intervals([s[:2] for s in spans], eps):
            out.append(("line", dxh * a - dyh * c, dyh * a + dxh * c,
                        dxh * b - dyh * c, dyh * b + dxh * c, kind))
    for key, spans in arcs.items():
        kind = key[0]
        ref = spans[0][2]
        _, cx, cy, ux, uy, vx, vy, _, _, _ = ref
        Minv = np.linalg.inv(np.array([[ux, vx], [uy, vy]]))

        def param(polar_deg):
            d = np.array([math.cos(math.radians(polar_deg)),
                          math.sin(math.radians(polar_deg))])
            m = Minv @ d
            return math.degrees(math.atan2(m[1], m[0]))
        # circular union: shift every span into [base, base+720) where base
        # is a gap edge, then merge linearly
        if any(b - a >= 360.0 for a, b in ((s[0], s[1]) for s in spans)):
            out.append(("arc", cx, cy, ux, uy, vx, vy, 0.0, 360.0, kind))
            continue
        ivs = [(a % 360.0, a % 360.0 + (b - a)) for a, b, _ in spans]
        merged = _merge_intervals(ivs, eps)
        # rejoin a run that wraps past 360 onto the first run
        if len(merged) > 1 and merged[0][0] <= (merged[-1][1] - 360.0) + eps:
            merged[0][0] = merged[-1][0] - 360.0
            merged.pop()
        for a, b in merged:
            if b - a >= 359.9:
                out.append(("arc", cx, cy, ux, uy, vx, vy, 0.0, 360.0, kind))
                continue
            ta, tb = param(a), param(b)
            det = ux * vy - uy * vx
            if det > 0:                    # param order matching CCW polar
                while tb <= ta:
                    tb += 360.0
            else:
                while tb >= ta:
                    tb -= 360.0
            out.append(("arc", cx, cy, ux, uy, vx, vy, ta, tb, kind))
    return out


def fit_ellipses(ells, f, ox, oy):
    """Remap projected-circle params through the fit affine (uniform f).
    A trailing per-candidate max-step element (fitted rounds) passes through
    unchanged — it is angular, not spatial. The optional 8th element (snap
    tolerance, px) IS spatial and scales with f."""
    return [(e[0] * f + ox, e[1] * f + oy, e[2] * f, e[3] * f,
             e[4] * f, e[5] * f, *e[6:7], *(x * f for x in e[7:8]))
            for e in ells]


def fit_affine(bbox, W, H, margin=6, scale=1.0):
    """Uniform scale+offset mapping the segment bbox into a W x H canvas."""
    scale = max(0.01, min(1.0, scale))
    bx0, by0, bx1, by1 = bbox
    bw, bh = (bx1 - bx0) or 1.0, (by1 - by0) or 1.0
    iw = max(1.0, (W - 2 * margin) * scale); ih = max(1.0, (H - 2 * margin) * scale)
    f = min(iw / bw, ih / bh)
    ox = (W - bw * f) / 2 - bx0 * f
    oy = (H - bh * f) / 2 - by0 * f
    return f, ox, oy


def fit_segments(segs, bbox, W, H, margin=6, scale=1.0):
    f, ox, oy = fit_affine(bbox, W, H, margin, scale)
    out = []
    for op in segs:
        if len(op) == 5:                               # legacy line tuple
            op = ("line",) + tuple(op)
        if op[0] == "line":
            _, x1, y1, x2, y2, k = op
            out.append(("line", x1 * f + ox, y1 * f + oy, x2 * f + ox, y2 * f + oy, k))
        else:
            _, cx, cy, ux, uy, vx, vy, t0, t1, k = op
            out.append(("arc", cx * f + ox, cy * f + oy,
                        ux * f, uy * f, vx * f, vy * f, t0, t1, k))
    return out
