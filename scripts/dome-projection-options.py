#!/usr/bin/env python3
"""Draw a head's decal under each of the three dome-projection options.

    .venv/bin/python scripts/dome-projection-options.py 3626cp7e 3626bph6 3626bp63 \
        --out out/dome-options

A minifig head's print runs off the top of the r=13 wall cylinder and onto the
dome, which has no analytic primitive: LDraw builds it from four `t04o6250`
quarter-torus subfiles that arrive tessellated, so `unwrap.bind` returns None
and `bind_groups` drops the ink. The three options differ ONLY in what happens
to that dropped ink; the wall half of every panel is the same drawing.

Each option is a 1-D reparametrization of the meridian, so all three run through
the stock cylinder map with the dome vertices rewritten first. Nothing in the
tree is edited.

    leave     today. Dome ink is dropped.
    cylinder  project the dome radially onto the infinite wall cylinder.
              v = the point's own height.
    dome      fit the dome's profile and lay it out by arc length along it.
              v = wall height + distance travelled over the dome.

It writes three sheets: the options side by side, the recovered band blown up,
and a component-counted diff of the two working options. `--icons` adds the
pair that shows what `to_xyz` does with ink bound past the section, and
`--survey '3626*'` re-derives every corpus figure the handoff quotes.
"""
from __future__ import annotations

import argparse
import glob
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import hlr, unwrap  # noqa: E402

_radial_gap = unwrap._radial_gap

#: Canvas height in LDU per part, filled by `render`, so a slide measured in
#: LDU can also be quoted in pixels of the sheet the reader is looking at.
_CANVAS = {}
#: How far past its own section an extended carrier may claim geometry, as a
#: multiple of the section's height. The dome adds about a quarter of the
#: wall's 13 LDU; 1.5 covers it with room and still refuses the neck.
EXTEND = 1.5


def _extended_gap(pts, prim):
    """`_radial_gap` with the upper extent test relaxed. The radial test is
    untouched, so a point still has to lie ON the wall to bind -- which is
    exactly what the rewrite below puts it on."""
    p = unwrap._local(pts, prim)
    r = float(np.linalg.norm(prim.R[:, 0]))
    h = float(np.linalg.norm(prim.R[:, 1]))
    y = p[:, 1]
    if np.any(y < -unwrap.BIND_TOL / h) or np.any(y > EXTEND):
        return np.inf
    want = np.array([prim.radius_at(float(min(v, 1.0))) for v in y])
    return float(np.max(np.abs(np.hypot(p[:, 0], p[:, 2]) - want)) * r)


def _projecting_gap(pts, prim):
    """`_radial_gap` that PROJECTS above the section instead of measuring.

    Not the same rule as `_extended_gap`, and the difference is the finding:
    that one keeps the radial test, which is enough only because the flat
    panels hand it vertices already rewritten onto the wall. Real geometry on
    the jaw sits up to 5 LDU inside the wall -- ten times `BIND_TOL` -- so
    binding it means taking the point's azimuth and height and not asking how
    far off the wall it is. Bounded to the wall's own silhouette, or the wall
    claims every interior facet above it.
    """
    p = unwrap._local(pts, prim)
    r = float(np.linalg.norm(prim.R[:, 0]))
    h = float(np.linalg.norm(prim.R[:, 1]))
    y = p[:, 1]
    if np.any(y < -unwrap.BIND_TOL / h) or np.any(y > EXTEND):
        return np.inf
    rad = np.hypot(p[:, 0], p[:, 2])
    if np.any(y > 1.0):
        return float(max(0.0, (rad.max() - 1.0) * r))
    want = np.array([prim.radius_at(float(v)) for v in y])
    return float(np.max(np.abs(rad - want)) * r)


#: The jaw faces away from an iso camera, so the pair that shows what `to_xyz`
#: does with ink past the section has to be shot from below.
ICON_ANGLE = "-40,20"


def icons(parts, out_dir, angle=ICON_ANGLE, px=460, engine="occt"):
    """Each part rendered as it is today, and again with the bind extended.

    `to_xyz` is left alone, which is the point: a cylinder's `radius_at` is
    1.0 at every level, so ink binding past the section comes back at the WALL
    radius rather than on the jaw, and the depth clip cuts what is left.
    """
    from brick_icons import cli
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for i, part in enumerate(parts, 1):
        for tag, extended in (("today", False), ("extended", True)):
            argv = [part, "--engine", engine, "--angle", angle,
                    "--width", str(px), "--height", str(px),
                    "--format", "png", "--out", str(out_dir)]
            cfg = cli._config_from_args(cli.build_parser().parse_args(argv))
            if extended:
                unwrap._radial_gap = _projecting_gap
            try:
                cli.process_one(cfg, part, out_dir)
            finally:
                unwrap._radial_gap = _radial_gap
            for suf in ("gray", "mono"):
                src = out_dir / f"{part}.{suf}.png"
                if src.exists():
                    src.replace(out_dir / f"{part}.{tag}.{suf}.png")
            made.append(f"{part}.{tag}")
            print(f"[{len(made)}/{len(parts) * 2}] {part} {tag}", flush=True)
    return made


def icon_sheet(parts, out_dir, cell=440):
    pad, gut, head, cap = 24, 14, 78, 44
    tags = (("today", "ink past the wall is dropped"),
            ("extended", "bind extended, to_xyz unchanged"))
    W = pad * 2 + 2 * cell + gut
    H = head + len(parts) * (cell + cap + gut) + pad
    im = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(im)
    d.text((pad, 18), "looking up at the jaw: extending the bind is not "
           "enough on its own", font=_font(20), fill="#111111")
    d.text((pad, 46), "recovered ink is drawn back onto the INFINITE cylinder, "
           f"so it stands off the jaw it came from  (--angle {ICON_ANGLE})",
           font=_font(14), fill="#666666")
    y = head
    for part in parts:
        for i, (tag, sub) in enumerate(tags):
            x = pad + i * (cell + gut)
            d.text((x, y), f"{part}  -  {tag}", font=_font(16), fill="#111111")
            d.text((x, y + 21), sub, font=_font(13), fill="#777777")
            f = out_dir / f"{part}.{tag}.gray.png"
            if f.exists():
                g = Image.open(f).convert("RGBA")
                flat = Image.new("RGB", g.size, "#ffffff")
                flat.paste(g, mask=g.split()[3])
                im.paste(flat.resize((cell, cell), Image.LANCZOS), (x, y + cap))
                d.rectangle([x, y + cap, x + cell - 1, y + cap + cell - 1],
                            outline="#dddddd")
        y += cell + cap + gut
    path = out_dir / "sheet-dome-icons.png"
    im.save(path)
    return path


def wall(analytic):
    """The head's face carrier: the largest color-16 cylinder by wall area.

    None when a part authors every primitive in a real color rather than 16 --
    6 heads do, and `decal_groups` filters body primitives to 16, so they have
    no curved carrier today at all.
    """
    best = None
    for p in analytic:
        if getattr(p, "color", 16) != 16 or p.kind not in ("cyli", "con"):
            continue
        r = float(np.linalg.norm(p.R[:, 0]))
        h = float(np.linalg.norm(p.R[:, 1]))
        if best is None or r * h > best[0]:
            best = (r * h, p, r, h, float(p.t[1]))
    return best[1:] if best else None


def fit_profile(tris, tri_colors, y_top, r_wall):
    """(a, p, q) of the dome's profile ellipse, r = a + p cos t, y = y_top + q sin t.

    Fitted from the body tessellation rather than assumed, because the dome
    arrives as triangles and its declared torus is gone by the time geometry
    reaches here. Linear in (a, p) once q is fixed, so q is swept.
    """
    b = np.asarray(tris, float)[np.asarray(tri_colors) == 16].reshape(-1, 3)
    r = np.hypot(b[:, 0], b[:, 2])
    y = b[:, 1]
    keep = (y > y_top + 0.05) & (r > 0.15 * r_wall) & (r < r_wall + 0.5)
    r, y = r[keep], y[keep]
    if len(r) < 20:
        return None
    best = None
    for q in np.linspace(0.5, 3.0 * r_wall, 1500):
        c2 = 1.0 - ((y - y_top) / q) ** 2
        if np.any(c2 < -1e-9):
            continue
        A = np.column_stack([np.ones(len(r)), np.sqrt(np.clip(c2, 0, None))])
        sol, *_ = np.linalg.lstsq(A, r, rcond=None)
        res = np.abs(A @ sol - r)
        if best is None or res.max() < best[0]:
            best = (res.max(), float(sol[0]), float(sol[1]), float(q),
                    float(np.sqrt((res ** 2).mean())))
    return best


def arc_length(p, q, t):
    """Distance along the profile ellipse from t=0, by quadrature."""
    t = np.atleast_1d(np.asarray(t, float))
    n = 256
    u = np.linspace(0.0, 1.0, n)[None, :] * t[:, None]
    f = np.sqrt((p * np.sin(u)) ** 2 + (q * np.cos(u)) ** 2)
    return np.trapezoid(f, u, axis=1)


def rewrite(pts, mode, y_top, r_wall, prof):
    """Dome vertices moved onto the extended wall cylinder, per option.

    Below the junction this is the identity, so a triangle straddling it is
    not torn: both maps agree at t=0, and the dome map's ds/dy is 1 there.
    """
    pts = np.array(pts, float)
    hi = pts[:, 1] > y_top
    if not hi.any():
        return pts
    sub = pts[hi]
    th = np.arctan2(sub[:, 2], sub[:, 0])
    if mode == "cylinder":
        v = sub[:, 1]
    else:
        a, p, q = prof
        t = np.arcsin(np.clip((sub[:, 1] - y_top) / q, 0.0, 1.0))
        v = y_top + arc_length(p, q, t)
    pts[hi] = np.column_stack([r_wall * np.cos(th), v, r_wall * np.sin(th)])
    return pts


def stretch(mode, y_top, r_wall, prof, y):
    """(horizontal, vertical) scale the option applies to ink at height `y`.

    1.0 is true to the part. Horizontal is the same under both options -- the
    canvas keeps the wall's u scale, so a latitude of radius r is drawn
    r_wall/r too wide. Only the vertical differs, and that is the choice.
    """
    a, p, q = prof
    t = float(np.arcsin(np.clip((y - y_top) / q, 0.0, 1.0)))
    r = a + p * np.cos(t)
    horiz = r_wall / r
    if mode == "cylinder":
        ds = np.hypot(p * np.sin(t), q * np.cos(t))
        vert = (q * np.cos(t)) / ds if ds else 0.0
    else:
        vert = 1.0
    return horiz, float(vert)


def panels(part, mode, ldraw_dir):
    """The part's decal panels under one option, plus what the option cost.

    Panels, not a finished SVG: the three options grow the canvas by different
    amounts, so letting each size its own would draw the three at three scales
    and the sheet would compare nothing. The caller fixes one extent over all
    of them.
    """
    tri, tri_colors, analytic = hlr.part_geometry(part, ldraw_dir)
    tri = np.asarray(tri, float)
    _prim, r_wall, h_wall, y_base = wall(analytic)
    y_top = y_base + h_wall
    info = {"part": part, "mode": mode, "r_wall": r_wall, "y_top": y_top}

    if mode == "leave":
        return unwrap.decal_panels(tri, tri_colors, analytic), info

    fit = fit_profile(tri, tri_colors, y_top, r_wall)
    if fit is None:
        return [], info
    info["profile"] = {"a": fit[1], "p": fit[2], "q": fit[3],
                       "resid_max": fit[0], "resid_rms": fit[4]}
    prof = (fit[1], fit[2], fit[3])
    deco = np.asarray(tri_colors) != 16
    moved = tri.copy()
    moved[deco] = rewrite(tri[deco].reshape(-1, 3), mode, y_top,
                          r_wall, prof).reshape(-1, 3, 3)
    top = float(tri[deco].reshape(-1, 3)[:, 1].max())
    info["ink_top"] = top
    info["stretch_at_top"] = stretch(mode, y_top, r_wall, prof, top)
    unwrap._radial_gap = _extended_gap
    try:
        return unwrap.decal_panels(moved, tri_colors, analytic), info
    finally:
        unwrap._radial_gap = _radial_gap


def ink_bounds(regions):
    pts = [np.asarray(r, float) for _c, g in regions
           for r in unwrap._rings_of(g) if len(r)]
    if not pts:
        return None
    a = np.vstack(pts)
    return a.min(axis=0), a.max(axis=0)


def render(part, out_dir, px, ldraw_dir, pad=1.0):
    """One SVG per option, all three on ONE canvas cropped to the ink."""
    got = {}
    for mode in MODES:
        ps, info = panels(part, mode, ldraw_dir)
        got[mode] = (ps, info)
    lo = hi = None
    for ps, _info in got.values():
        if not ps:
            continue
        b = ink_bounds(ps[0][1])
        if b is None:
            continue
        lo = b[0] if lo is None else np.minimum(lo, b[0])
        hi = b[1] if hi is None else np.maximum(hi, b[1])
    if lo is None:
        return {}, {m: i for m, (_p, i) in got.items()}
    lo, hi = lo - pad, hi + pad
    ext = unwrap._corners(lo[0], lo[1], hi[0], hi[1])
    _CANVAS[part] = float(hi[1] - lo[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for mode, (ps, _info) in got.items():
        if not ps:
            continue
        _e, regions, face = ps[0]
        svg = unwrap.texture_svg(ext, regions, px=px, ldraw_dir=ldraw_dir,
                                 face=face, bg="#ffffff")
        path = out_dir / f"{part}.{mode}.svg"
        path.write_text(svg)
        paths[mode] = path
    return paths, {m: i for m, (_p, i) in got.items()}


MODES = ("leave", "cylinder", "dome")


def survey(pattern, ldraw_dir):
    """Every figure the handoff quotes about the head corpus, re-derived.

    Per part: how far its ink runs past the wall, what "extend the cylinder"
    does to the lowest of it, how far the two working options disagree, and
    how much of the dropped ink a pure extent bump would recover.
    """
    files = sorted(glob.glob(f"{ldraw_dir}/parts/{pattern}.dat"))
    rows, skipped = [], []
    for i, f in enumerate(files, 1):
        pid = Path(f).stem
        try:
            tri, tri_colors, analytic = hlr.part_geometry(pid, ldraw_dir)
            tri = np.asarray(tri, float)
            tri_colors = np.asarray(tri_colors)
            deco = tri[tri_colors != 16]
            if not len(deco):
                skipped.append((pid, "no decoration"))
                print(f"[{i}/{len(files)}] {pid}: no decoration", flush=True)
                continue
            found = wall(analytic)
            if found is None:
                skipped.append((pid, "no color-16 wall"))
                print(f"[{i}/{len(files)}] {pid}: no color-16 wall", flush=True)
                continue
            _prim, r_wall, h_wall, y_base = found
            y_top = y_base + h_wall
            fit = fit_profile(tri, tri_colors, y_top, r_wall)
            if fit is None:
                skipped.append((pid, "no dome fit"))
                print(f"[{i}/{len(files)}] {pid}: no dome fit", flush=True)
                continue
            _res, a, pp, q, _rms = fit
            top = float(deco.reshape(-1, 3)[:, 1].max())
            over = top - y_top
            _h, v = stretch("cylinder", y_top, r_wall, (a, pp, q), top)
            if over > 0:
                t = float(np.arcsin(np.clip(over / q, 0.0, 1.0)))
                sl = float(arc_length(pp, q, t)[0]) - over
            else:
                sl = 0.0
            body = [c for c in analytic if getattr(c, "color", 16) == 16
                    and c.kind in ("cyli", "con")]
            base = np.array([bind_is_none(t, body) for t in deco])
            unwrap._radial_gap = _extended_gap
            try:
                relaxed = np.array([bind_is_none(t, body) for t in deco])
            finally:
                unwrap._radial_gap = _radial_gap
            rows.append((pid, over, v, sl, int(base.sum()),
                         int((base & ~relaxed).sum())))
            print(f"[{i}/{len(files)}] {pid}: over {over:5.2f} LDU  "
                  f"cyl v={v:.2f}  slide {sl:.2f}  "
                  f"unbound {base.sum()}, extent bump recovers "
                  f"{(base & ~relaxed).sum()}", flush=True)
        except Exception as e:                       # noqa: BLE001
            skipped.append((pid, f"{type(e).__name__}: {e}"))
            print(f"[{i}/{len(files)}] {pid}: ERROR {type(e).__name__}",
                  flush=True)
    return rows, skipped


def bind_is_none(tri, carriers):
    return unwrap.bind(tri, carriers) is None


def report(rows, skipped):
    over = np.array([r[1] for r in rows])
    v = np.array([r[2] for r in rows])
    sl = np.array([r[3] for r in rows])
    unbound = np.array([r[4] for r in rows], float)
    rec = np.array([r[5] for r in rows], float)
    print(f"\n{len(rows)} heads with decoration and a dome; "
          f"{len(skipped)} skipped")
    print(f"  ink past the wall on {(over > 0).sum()} of them; "
          f"median {np.median(over[over > 0]):.2f} LDU, "
          f"max {over.max():.2f}")
    print("  extend-the-cylinder vertical scale at the lowest ink: "
          f"median {np.median(v):.2f}, p10 {np.percentile(v, 10):.2f}, "
          f"min {v.min():.2f}")
    print(f"  the two options disagree by: median {np.median(sl):.2f} LDU, "
          f"p90 {np.percentile(sl, 90):.2f}, max {sl.max():.2f}")
    for thr in (0.5, 1.0, 2.0):
        print(f"    over {thr:.1f} LDU: {(sl > thr).sum()} heads "
              f"({(sl > thr).mean() * 100:.0f}%)")
    has = unbound > 0
    print("  a pure extent bump recovers "
          f"{rec[has].sum() / unbound[has].sum() * 100:.0f}% of dropped ink "
          f"over the corpus; per part "
          f"{np.median(rec[has] / unbound[has]) * 100:.0f}% at the median")
    worst = sorted(rows, key=lambda r: -r[3])[:8]
    print("  biggest disagreement:",
          [(r[0], round(r[3], 2)) for r in worst])
    counts = {}
    for _pid, why in skipped:
        counts[why.split(":")[0]] = counts.get(why.split(":")[0], 0) + 1
    if counts:
        print("  skipped:", counts)


LABEL = {"leave": "leave it", "cylinder": "extend the cylinder",
         "dome": "recognize the dome"}
BLURB = {"leave": "dome ink dropped",
         "cylinder": "v = the point's own height",
         "dome": "v = arc length over the dome"}


def _font(size):
    for path in ("/System/Library/Fonts/SFNSMono.ttf",
                 "/System/Library/Fonts/Menlo.ttc"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def _raster(svg, width):
    png = svg.with_suffix(".png")
    subprocess.run(["resvg", "--width", str(width), str(svg), str(png)],
                   check=True, capture_output=True)
    return Image.open(png).convert("RGB")


def _reference(part, renders, height):
    """The shaded reference, flattened onto white and matched to the row.

    Sized by HEIGHT, not width: the references are square and the unwrapped
    panels are wide, so matching widths left the row half empty and the
    reference towering over the thing it is there to be compared with.
    """
    f = Path(renders) / f"{part}.webp"
    if not f.exists():
        return None
    im = Image.open(f).convert("RGBA")
    flat = Image.new("RGB", im.size, "#ffffff")
    flat.paste(im, mask=im.split()[3])
    return flat.resize((round(im.width * height / im.height), height),
                       Image.LANCZOS)


def sheet(parts, out_dir, renders, cell=520, band=None):
    """Rows of parts, columns of options, one PNG.

    Titled and per-column labelled, because the wall is shared and a sheet
    arrives with no conversation around it.
    """
    pad, gut, head, cap = 26, 14, 78, 46
    rows = []
    for part in parts:
        opts = []
        for mode in MODES:
            f = out_dir / f"{part}.{mode}.svg"
            opts.append(_raster(f, cell) if f.exists() else None)
        h = max((p.height for p in opts if p), default=cell)
        rows.append((part, [_reference(part, renders, h)] + opts))
    cols = 1 + len(MODES)
    row_h = [max((p.height for p in ps if p), default=cell) for _n, ps in rows]
    ref_w = max((ps[0].width for _n, ps in rows if ps[0]), default=cell)
    W = pad * 2 + ref_w + len(MODES) * cell + len(MODES) * gut
    H = head + sum(h + cap + gut for h in row_h) + pad
    im = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(im)
    d.text((pad, 20), "minifig head decals: what to do with ink that runs "
           "off the wall cylinder onto the jaw dome", font=_font(21),
           fill="#111111")
    d.text((pad, 48), "each row one part, at one scale across the row; "
           "columns vary only in how dome ink is mapped",
           font=_font(15), fill="#666666")
    y = head
    for (part, ps), h in zip(rows, row_h):
        for i, p in enumerate(ps):
            x = pad if i == 0 else pad + ref_w + gut + (i - 1) * (cell + gut)
            name = "reference render" if i == 0 else LABEL[MODES[i - 1]]
            sub = "ground truth" if i == 0 else BLURB[MODES[i - 1]]
            d.text((x, y), f"{part}  -  {name}", font=_font(16), fill="#111111")
            d.text((x, y + 21), sub, font=_font(13), fill="#777777")
            if p is not None:
                im.paste(p, (x, y + cap))
                d.rectangle([x, y + cap, x + p.width - 1, y + cap + p.height - 1],
                            outline="#dddddd")
        y += h + cap + gut
    path = out_dir / "sheet-dome-options.png"
    im.save(path)
    return path


#: Below this many pixels a diff component is antialias fringe along an edge
#: both options drew in the same place, not ink either one moved.
DIFF_MIN_PX = 25


def slide(part, infos, cell_h_ldu, px_h):
    """How far the two options disagree about where the lowest ink sits.

    The maps differ only in v, so this is exact rather than measured off the
    raster: cylinder puts ink at its own height, the dome at arc length.
    """
    i = infos.get("dome", {})
    pr = i.get("profile")
    if not pr or "ink_top" not in i:
        return None
    y_top, y_ink = i["y_top"], i["ink_top"]
    t = float(np.arcsin(np.clip((y_ink - y_top) / pr["q"], 0.0, 1.0)))
    v_dome = float(arc_length(pr["p"], pr["q"], t)[0])
    v_cyl = y_ink - y_top
    return v_dome - v_cyl, (v_dome - v_cyl) / cell_h_ldu * px_h


def diff_sheet(parts, out_dir, infos=None, cell=620):
    """cylinder, dome, and what actually moved between them.

    Component-counted, not eyeballed: the two agree exactly over the wall, so
    an unfiltered diff is mostly antialias fringe along edges neither option
    touched. Components under `DIFF_MIN_PX` are dropped and the rest counted.
    """
    pad, gut, head, cap = 26, 14, 82, 58
    rows = []
    for part in parts:
        f_cyl = out_dir / f"{part}.cylinder.svg"
        f_dome = out_dir / f"{part}.dome.svg"
        if not (f_cyl.exists() and f_dome.exists()):
            continue
        a = _raster(f_cyl, cell)
        b = _raster(f_dome, cell)
        A = np.asarray(a).astype(int)
        B = np.asarray(b).astype(int)
        mask = np.abs(A - B).max(axis=2) > 16
        lab, n = ndimage.label(mask)
        if n:
            sizes = np.bincount(lab.ravel())
            sizes[0] = 0
            keep = np.isin(lab, np.flatnonzero(sizes >= DIFF_MIN_PX))
        else:
            keep = np.zeros_like(mask)
        chunky = int(np.unique(lab[keep]).size)
        ink = (A.min(axis=2) < 230) | (B.min(axis=2) < 230)
        share = keep.sum() / max(int(ink.sum()), 1)

        # the union in pale gray, what moved in magenta over it
        panel = np.full(A.shape, 255, np.uint8)
        panel[ink] = (214, 214, 214)
        panel[keep] = (208, 24, 140)
        rows.append((part, a, b, Image.fromarray(panel), chunky, n, share))

    row_h = [r[1].height for r in rows]
    W = pad * 2 + 3 * cell + 2 * gut
    H = head + sum(h + cap + gut for h in row_h) + pad
    im = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(im)
    d.text((pad, 18), "what actually moves between the two working options",
           font=_font(21), fill="#111111")
    d.text((pad, 46), "magenta is every pixel the two draw differently; pale "
           "gray is ink they agree on. components under "
           f"{DIFF_MIN_PX}px dropped as antialias fringe",
           font=_font(14), fill="#666666")
    y = head
    for (part, a, b, dm, chunky, raw, share), h in zip(rows, row_h):
        ldu = px = None
        got = slide(part, (infos or {}).get(part, {}),
                    _CANVAS.get(part, 1.0), h)
        if got:
            ldu, px = got
        caps = [
            (f"{part}  -  extend the cylinder", BLURB["cylinder"]),
            (f"{part}  -  recognize the dome", BLURB["dome"]),
            (f"{part}  -  diff",
             f"{chunky} components over {DIFF_MIN_PX}px  ({raw} raw)   "
             f"{share * 100:.1f}% of the ink"),
        ]
        for i, (p_, (t1, t2)) in enumerate(zip((a, b, dm), caps)):
            x = pad + i * (cell + gut)
            d.text((x, y), t1, font=_font(16), fill="#111111")
            d.text((x, y + 21), t2, font=_font(13), fill="#777777")
            if i == 2 and ldu is not None:
                d.text((x, y + 38), f"lowest ink sits {ldu:.2f} LDU "
                       f"({px:.0f}px) further down under the dome",
                       font=_font(13), fill="#777777")
            im.paste(p_, (x, y + cap))
            d.rectangle([x, y + cap, x + p_.width - 1, y + cap + p_.height - 1],
                        outline="#dddddd")
        y += h + cap + gut
    path = out_dir / "sheet-dome-diff.png"
    im.save(path)
    return path


def band_sheet(parts, out_dir, infos=None, frac=0.34, cell=760):
    """The recovered band alone, cylinder against dome.

    The two options differ only below the wall's end, and at full-face size
    that difference is a few pixels of stubble. This is the bottom `frac` of
    the same canvas, blown up.
    """
    pad, gut, head, cap = 26, 14, 74, 44
    rows = []
    for part in parts:
        cut = []
        for mode in ("cylinder", "dome"):
            f = out_dir / f"{part}.{mode}.svg"
            if not f.exists():
                cut.append(None)
                continue
            im = _raster(f, cell)
            top = round(im.height * (1 - frac))
            cut.append(im.crop((0, top, im.width, im.height)))
        rows.append((part, cut))
    row_h = [max((p.height for p in ps if p), default=80) for _n, ps in rows]
    W = pad * 2 + 2 * cell + gut
    H = head + sum(h + cap + gut for h in row_h) + pad
    im = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(im)
    d.text((pad, 18), "the recovered band, blown up: extend the cylinder "
           "against recognize the dome", font=_font(21), fill="#111111")
    d.text((pad, 46), "bottom third of the same canvas. both restore the ink; "
           "they disagree about how far down it sits",
           font=_font(15), fill="#666666")
    y = head
    for (part, ps), h in zip(rows, row_h):
        for i, p in enumerate(ps):
            x = pad + i * (cell + gut)
            mode = ("cylinder", "dome")[i]
            st = ((infos or {}).get(part, {}).get(mode, {})
                  .get("stretch_at_top"))
            sub = BLURB[mode]
            if st:
                sub += f"   vertical scale at the lowest ink: {st[1]:.2f}"
            d.text((x, y), f"{part}  -  {LABEL[mode]}", font=_font(16),
                   fill="#111111")
            d.text((x, y + 21), sub, font=_font(13), fill="#777777")
            if p is not None:
                im.paste(p, (x, y + cap))
                d.rectangle([x, y + cap, x + p.width - 1, y + cap + p.height - 1],
                            outline="#dddddd")
        y += h + cap + gut
    path = out_dir / "sheet-dome-band.png"
    im.save(path)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--out", default="out/dome-options")
    ap.add_argument("--px", type=int, default=900)
    ap.add_argument("--ldraw-dir", default="vendor/ldraw")
    ap.add_argument("--renders", default="renders/reference")
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--icons", action="store_true",
                    help="also render each part as an icon, today against an "
                         "extended bind, and sheet the pair")
    ap.add_argument("--survey", metavar="GLOB",
                    help="skip the panels; measure this many parts "
                         "(e.g. '3626*') and report the corpus figures")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if args.survey:
        report(*survey(args.survey, args.ldraw_dir))
        return 0
    if not args.parts:
        ap.error("give some parts, or --survey")
    every = {}
    for i, part in enumerate(args.parts, 1):
        paths, infos = render(part, out, args.px, args.ldraw_dir)
        every[part] = infos
        pr = infos["dome"].get("profile")
        tail = ""
        if pr:
            tail = (f" profile r={pr['a']:.2f}+{pr['p']:.2f}cos t, "
                    f"y={infos['dome']['y_top']:.1f}+{pr['q']:.2f}sin t "
                    f"(resid max {pr['resid_max']:.3f})")
        print(f"[{i}/{len(args.parts)}] {part}: "
              f"{', '.join(sorted(paths)) or 'no decal'}{tail}", flush=True)
        for mode in MODES:
            st = infos[mode].get("stretch_at_top")
            if st:
                print(f"      {mode:<9} ink top y={infos[mode]['ink_top']:.2f} "
                      f"stretch h={st[0]:.2f} v={st[1]:.2f}", flush=True)
    if not args.no_sheet:
        print(f"sheet: {sheet(args.parts, out, args.renders)}", flush=True)
        print(f"sheet: {band_sheet(args.parts, out, every)}", flush=True)
        print(f"sheet: {diff_sheet(args.parts, out, every)}", flush=True)
    if args.icons:
        icons(args.parts, out / "icons")
        print(f"sheet: {icon_sheet(args.parts, out / 'icons')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
