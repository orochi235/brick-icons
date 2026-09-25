"""Does occt put a flat tile's print where the flat decal sheet says it is?

    .venv/bin/python scripts/decal-projection-oracle.py 3069bp49 3068bp00 --out out/decal-oracle

A print on a flat carrier has no sagitta to close, so its occt projection must
be the affine image of the `--decal` sheet: sheet px -> UV (the sheet's own
layout, inverted) -> world (the carrier's plane basis, `unwrap.to_xyz`) ->
canvas px (the `.fit.json` camera, as `edge_truth._to_px` reads it). The sheet's
own `<path>` elements go through that one matrix, so its arcs, splines and
2-decimal rounding all come along; the occt drawing is reduced to the paths in
the print's colors with the seam-hiding stroke removed. Both rasterize at the
same size and the diff is counted by component (`brick_icons.lab.diff`).

Two rows per part: `smooth` is the sheet as the CLI writes it; `chords` disarms
`unwrap._smooth_d` in-process (the recipe of decal-smooth-sheet.py), so the
freeform-ring spline is measured on its own against occt, which draws chords.

Everything lands under --out/<part>/ (the two drawings, the mapped and filtered
SVGs, their rasters) and --out/<part>.oracle.png, overwritten on each run.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from unittest import mock

import numpy as np
import shapely
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brick_icons import cli, colors, config, geom2d, hlr, unwrap  # noqa: E402
from brick_icons.lab import diff  # noqa: E402
from _sheet import diff_panel, sheet  # noqa: E402

DECAL_ARGS = ["--decal", "--angle", "iso", "--format", "svg"]
OCCT_ARGS = ["--engine", "occt", "--shading", "outline", "--shade-style",
             "flat3", "--angle", "iso", "--format", "svg"]
INK = diff.PANEL_THRESHOLD      # a channel this far off white is ink
SHIFT_SEARCH = 6                # px each way when fitting an offset


def draw(part: str, out_dir: Path) -> tuple[Path, Path, dict]:
    """The two CLI drawings, in-process, and the occt one's camera."""
    cli.main([part, *DECAL_ARGS, "--out", str(out_dir)])
    cli.main([part, *OCCT_ARGS, "--out", str(out_dir)])
    fit = json.loads((out_dir / f"{part}.fit.json").read_text())
    return out_dir / f"{part}.decal.svg", out_dir / f"{part}.svg", fit


def sheet_panels(part: str, ldraw_dir: str, px: int):
    """[(carrier, ext, regions, s, dx, dy)]: what `decal_sheet` drew, with the
    carrier each panel was laid out on and the sheet transform it used.

    `decal_panels` hands back extents without their carriers, so the carrier
    is captured off its one `carrier_extent` call. The scale and panel
    offsets restate `decal_sheet`'s layout; `check_sheet` proves they match.
    """
    tri, tri_colors, analytic = hlr.part_geometry(part, ldraw_dir)
    got = []
    orig = unwrap.carrier_extent

    def record(carrier, uv=None):
        ext = orig(carrier, uv)
        got.append(carrier)
        return ext

    with mock.patch.object(unwrap, "carrier_extent", record):
        panels = unwrap.decal_panels(tri, tri_colors, analytic)
    if len(got) != len(panels):
        raise RuntimeError(f"{part}: {len(panels)} panels, {len(got)} carriers")
    sizes = [unwrap._extent_size(ext) for ext, _r, _f in panels]
    if len(panels) == 1:
        s = px / max(*sizes[0], 1e-9)
        offs = [(0.0, 0.0)]
    else:
        cols, _rows = unwrap.sheet_grid(len(panels))
        cell_w, cell_h = max(w for w, _h in sizes), max(h for _w, h in sizes)
        gutter = unwrap.SHEET_GUTTER * max(cell_w, cell_h)
        sheet_w = cols * cell_w + (cols + 1) * gutter
        sheet_h = -(-len(panels) // cols) * cell_h + (-(-len(panels) // cols) + 1) * gutter
        s = px / max(sheet_w, sheet_h, 1e-9)
        offs = [((gutter + (i % cols) * (cell_w + gutter) + (cell_w - w) / 2) * s,
                 (gutter + (i // cols) * (cell_h + gutter) + (cell_h - h) / 2) * s)
                for i, (w, h) in enumerate(sizes)]
    codes = sorted({int(c) for c in tri_colors if c != 16}
                   | {int(getattr(p, "color", 16)) for p in analytic
                      if getattr(p, "color", 16) != 16})
    return [(c, ext, regions, s, dx, dy)
            for c, (ext, regions, _face), (dx, dy) in zip(got, panels, offs)], codes


def to_canvas(carrier, ext, s, dx, dy, fit):
    """Sheet px -> canvas px, as a function and as its SVG matrix."""
    if not isinstance(carrier, unwrap.Plane):
        raise ValueError("only a flat carrier projects affinely")
    cu = np.asarray(ext, float)
    x0, _ = cu.min(axis=0)
    _, y1 = cu.max(axis=0)
    right, up = np.asarray(fit["right"], float), np.asarray(fit["up"], float)

    def f(xy):
        xy = np.asarray(xy, float).reshape(-1, 2)
        u = (xy[:, 0] - dx) / s + x0
        v = y1 - (xy[:, 1] - dy) / s
        P = unwrap.to_xyz(np.column_stack([u, v]), carrier)
        return np.column_stack([(P @ right) * fit["k"] + fit["kx"],
                                -(P @ up) * fit["k"] + fit["ky"]])

    o, ex, ey = f([[0, 0], [1, 0], [0, 1]])
    a, b = ex - o
    c, d = ey - o
    return f, (a, b, c, d, o[0], o[1])


def mapped_svg(panels, fit, ldraw_dir, smooth=True) -> str:
    """The sheet's own panel paths, under their matrices, on the occt canvas."""
    saved = unwrap._smooth_d
    if not smooth:
        unwrap._smooth_d = lambda pts, arcs=None: geom2d.path_d(
            shapely.Polygon(pts), arcs=arcs)
    try:
        body = []
        for carrier, ext, regions, s, dx, dy in panels:
            _f, m = to_canvas(carrier, ext, s, dx, dy, fit)
            paths = unwrap._panel_paths(ext, regions, s, ldraw_dir, face=None)
            body.append('<g transform="matrix(%s)">%s</g>'
                        % (" ".join(f"{v:.6f}" for v in m), "".join(paths)))
    finally:
        unwrap._smooth_d = saved
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d">%s</svg>'
            % (fit["width"], fit["height"], "".join(body)))


def check_sheet(panels, sheet_svg: str, ldraw_dir) -> bool:
    """Do the regenerated panel paths match the ones the CLI wrote?"""
    mine = {re.search(r'd="([^"]*)"', p).group(1)
            for c, ext, regions, s, _dx, _dy in panels
            for p in unwrap._panel_paths(ext, regions, s, ldraw_dir, face=None)}
    theirs = set(re.findall(r'<path d="([^"]*)"', sheet_svg))
    return mine <= theirs


_PATH = re.compile(r"<path\b[^>]*/>")
_FILL = re.compile(r'fill="(#[0-9a-fA-F]{6})"')
_STROKE = re.compile(r'\s+stroke(?:-width)?="[^"]*"')


def occt_print_svg(svg: str, hexes: set[str], fit, keep_stroke=False) -> str:
    """Only the occt paths filled in a print color, stroke stripped: the fill
    outlines itself in its own color to hide antialias seams, which fattens
    every region by half a stroke and is not a statement about geometry."""
    keep = []
    for m in _PATH.finditer(svg):
        fill = _FILL.search(m.group(0))
        if fill and fill.group(1).lower() in hexes:
            keep.append(m.group(0) if keep_stroke else _STROKE.sub("", m.group(0)))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d">'
            '<g stroke-linejoin="round">%s</g></svg>'
            % (fit["width"], fit["height"], "".join(keep)))


def ink(im: Image.Image) -> np.ndarray:
    return (255 - np.asarray(im.convert("RGB"), int)).max(axis=2) > INK


def best_shift(a: np.ndarray, b: np.ndarray, reach=SHIFT_SEARCH):
    """(dx, dy, xor) moving `a` onto `b` by whole pixels."""
    best = (0, 0, int((a ^ b).sum()))
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            moved = np.roll(np.roll(a, dy, axis=0), dx, axis=1)
            n = int((moved ^ b).sum())
            if n < best[2]:
                best = (dx, dy, n)
    return best


def geometry(a: np.ndarray, b: np.ndarray, px_per_ldu: float) -> dict:
    """Offset and scale of ink mask `b` (occt) relative to `a` (decal)."""
    out = {"decal_px": int(a.sum()), "occt_px": int(b.sum()),
           "iou": float((a & b).sum() / max((a | b).sum(), 1))}
    if a.any() and b.any():
        ca = np.array(np.nonzero(a), float).mean(axis=1)[::-1]
        cb = np.array(np.nonzero(b), float).mean(axis=1)[::-1]
        out["centroid_dxy_px"] = tuple(float(v) for v in cb - ca)
        out["centroid_dxy_ldu"] = tuple(float(v) / px_per_ldu for v in cb - ca)
        ea = np.ptp(np.nonzero(a)[1]) + 1, np.ptp(np.nonzero(a)[0]) + 1
        eb = np.ptp(np.nonzero(b)[1]) + 1, np.ptp(np.nonzero(b)[0]) + 1
        out["bbox_scale_xy"] = (eb[0] / ea[0], eb[1] / ea[1])
        dx, dy, n = best_shift(a, b)
        out["shift_px"] = (dx, dy)
        out["xor_px"] = int((a ^ b).sum())
        out["xor_after_shift_px"] = n
    return out


def raster(svg_text: str, path: Path, width: int) -> Image.Image:
    path.write_text(svg_text)
    return Image.open(diff.rasterize(path, path.with_suffix(".png"), width)).convert("RGB")


def run_part(part: str, out: Path, cfg, zoom: int, i: int, n: int) -> Path:
    d = out / part
    d.mkdir(parents=True, exist_ok=True)
    sheet_path, occt_path, fit = draw(part, d)
    panels, codes = sheet_panels(part, cfg.ldraw_dir, cfg.texture_px or 900)
    hexes = {"#" + colors.resolve(str(c), cfg.ldraw_dir)[0][2:].lower()
             for c in codes}
    width = fit["width"] * zoom
    px_per_ldu = fit["k"] * zoom
    ok = check_sheet(panels, sheet_path.read_text(), cfg.ldraw_dir)
    c0, ext0, _r0, s0, dx0, dy0 = panels[0]
    corners = to_canvas(c0, ext0, s0, dx0, dy0, fit)[0](
        [[dx0, dy0], [dx0 + s0 * unwrap._extent_size(ext0)[0], dy0]])

    occt_svg = occt_path.read_text()
    occt = raster(occt_print_svg(occt_svg, hexes, fit), d / f"{part}.occt-print.svg", width)
    stroked = raster(occt_print_svg(occt_svg, hexes, fit, keep_stroke=True),
                     d / f"{part}.occt-print-stroked.svg", width)
    smooth = raster(mapped_svg(panels, fit, cfg.ldraw_dir), d / f"{part}.mapped.svg", width)
    chords = raster(mapped_svg(panels, fit, cfg.ldraw_dir, smooth=False),
                    d / f"{part}.mapped-chords.svg", width)

    print(f"[{i}/{n}] {part}: {len(panels)} panel(s), print colors "
          f"{sorted(hexes)}, sheet paths {'match' if ok else 'DIFFER FROM'} the CLI's, "
          f"canvas {fit['width']}x{fit['height']} @ zoom {zoom} "
          f"({px_per_ldu:.2f} px/LDU); panel x-axis lands {corners[0].round(2).tolist()}"
          f" -> {corners[1].round(2).tolist()}")
    rows = []
    for label, im in (("smooth", smooth), ("chords", chords)):
        _panel, comps, pixels = diff_panel(im, occt)
        g = geometry(ink(im), ink(occt), px_per_ldu)
        print(f"    {label:7s} vs occt: {comps:4d} comp, {pixels:6d} px | "
              f"ink decal {g['decal_px']} occt {g['occt_px']} iou {g['iou']:.3f}"
              + (f" | centroid d=({g['centroid_dxy_px'][0]:+.2f},{g['centroid_dxy_px'][1]:+.2f}) px"
                 f" =({g['centroid_dxy_ldu'][0]:+.3f},{g['centroid_dxy_ldu'][1]:+.3f}) LDU"
                 f" | bbox scale ({g['bbox_scale_xy'][0]:.4f},{g['bbox_scale_xy'][1]:.4f})"
                 f" | best shift {g['shift_px']} xor {g['xor_px']} -> {g['xor_after_shift_px']}"
                 if "shift_px" in g else ""))
        rows.append((f"{part}\n{label}", im, occt))
    _p, comps, pixels = diff_panel(occt, stroked)
    print(f"    stroke alone (occt stripped vs as drawn): {comps} comp, {pixels} px")
    sheet_png = out / f"{part}.oracle.png"
    sheet(f"{part}: decal sheet mapped through carrier + fit camera vs occt "
          f"projection (iso, flat3, zoom {zoom})", rows,
          columns=("decal mapped", "occt projection"), out=sheet_png)
    return sheet_png


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", default="out/decal-oracle")
    ap.add_argument("--zoom", type=int, default=4,
                    help="raster px per occt canvas px (default 4)")
    args = ap.parse_args(argv)
    cfg = config.load_config()
    out = Path(args.out)
    for i, part in enumerate(args.parts, 1):
        png = run_part(part, out, cfg, args.zoom, i, len(args.parts))
        print(f"    sheet: {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
