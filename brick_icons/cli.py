from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from . import render, process, trace, hlr, shade, geom2d, unwrap
from .config import load_config, Config


def _parse_args(argv):
    p = argparse.ArgumentParser(prog="brick-icons",
                                description="Render LEGO parts into bin-label assets.")
    p.add_argument("parts", nargs="*", help="part ids or .dat/.ldr paths")
    p.add_argument("--list", help="file with one part per line (overrides positional)")
    p.add_argument("--out", default="out")
    p.add_argument("--root", default=".")
    p.add_argument("--config", default=None)
    p.add_argument("--format", dest="fmt", choices=["png", "svg", "both"])
    p.add_argument("--mode", choices=["gray", "mono", "color", "both"])
    p.add_argument("--shading", choices=["normal", "cel", "outline"])
    p.add_argument("--engine", choices=["naive", "occt"], default=None,
                   help="geometry engine for outline/wireframe renders")
    p.add_argument("--cel-levels", type=int)
    p.add_argument("--line-width", type=int, help="outline interior stroke (output px)")
    p.add_argument("--silhouette-width", type=int, help="outline contour stroke (output px)")
    p.add_argument("--scale-mode", dest="scale_mode", choices=["fit", "physical"])
    p.add_argument("--line-mm", dest="line_mm", type=float)
    p.add_argument("--silhouette-mm", dest="silhouette_mm", type=float)
    p.add_argument("--dither", choices=["threshold", "floyd", "ordered", "atkinson"])
    p.add_argument("--angle")
    p.add_argument("--part-color")
    p.add_argument("--list-colors", dest="list_colors", action="store_true",
                   default=False,
                   help="print the LDraw palette (code, name, hex) and exit")
    p.add_argument("--curve-quality", type=int)
    p.add_argument("--render-px", type=int)
    p.add_argument("--scale", type=float)
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--dpi", type=int)
    p.add_argument("--label-mm", type=float, nargs=2, metavar=("W", "H"))
    p.add_argument("--margin", type=int)
    p.add_argument("--threshold", type=int)
    p.add_argument("--gamma", type=float)
    p.add_argument("--levels", type=int, nargs=2, metavar=("BLACK", "WHITE"))
    p.add_argument("--shade-style", dest="shade_style",
                   choices=["none"] + sorted(shade.STYLES))
    p.add_argument("--weld-corners", dest="weld_corners", action="store_true",
                   default=None,
                   help="ink the notch at EVERY stroke T-graze junction "
                        "(broad weld), not just stub-bridged ones")
    p.add_argument("--wireframe", action="store_true", default=None,
                   help="outline strokes only with occlusion culling off "
                        "(every edge drawn, hidden or not; no fills)")
    p.add_argument("--opacity", type=float,
                   help="face-fill opacity 0-1 for SVG output "
                        "(translucent bricks; default 1)")
    p.add_argument("--part-label", dest="part_label", action="store_true",
                   default=None,
                   help="stamp the part id in fixed small print in the "
                        "bottom-left corner (contact sheets / test renders)")
    p.add_argument("--svg-bg", dest="svg_bg", metavar="PAINT",
                   help='SVG background: a color ("white", "#rrggbb") or '
                        '"none" for transparent (default none)')
    p.add_argument("--light", type=str, metavar="LAT,LONG",
                   help="view-space light: elevation, azimuth in degrees "
                        "(0,0 = frontal; positive azimuth = from the left; "
                        "default ~37,39 upper-left)")
    p.add_argument("--debug-dir", default=None)
    return p.parse_args(argv)


def _config_from_args(args) -> Config:
    toml = args.config or str(Path(args.root) / "labels.toml")
    overrides = {
        "fmt": args.fmt, "mode": args.mode, "shading": args.shading,
        "engine": args.engine,
        "cel_levels": args.cel_levels,
        "line_width": args.line_width, "silhouette_width": args.silhouette_width,
        "dither": args.dither, "angle": args.angle, "part_color": args.part_color,
        "curve_quality": args.curve_quality, "render_px": args.render_px,
        "scale": args.scale, "scale_mode": args.scale_mode,
        "line_mm": args.line_mm, "silhouette_mm": args.silhouette_mm,
        "width": args.width, "height": args.height,
        "dpi": args.dpi, "label_mm": tuple(args.label_mm) if args.label_mm else None,
        "margin": args.margin, "threshold": args.threshold, "gamma": args.gamma,
        "levels": tuple(args.levels) if args.levels else None,
        "shade_style": args.shade_style, "light": args.light,
        "svg_bg": args.svg_bg, "opacity": args.opacity,
        "wireframe": args.wireframe, "weld_corners": args.weld_corners,
        "part_label": args.part_label,
    }
    return load_config(toml_path=toml, overrides=overrides, root=args.root)


def _stage(debug_dir, stage, name) -> Path:
    d = Path(debug_dir) / stage
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{name}.png"


def _emit_unwrap(debug_dir, name, res, cfg) -> None:
    """The decal laid flat on its carrier — the only way to see whether a
    carrier bound correctly without reading projected output. Same extraction
    the `decal` subcommand runs, on a white ground because this one is read
    against a render rather than composited."""
    svgs = unwrap.decal_svgs(res.tri, res.tri_colors, res.analytic,
                             ldraw_dir=cfg.ldraw_dir, bg="#ffffff")
    d = Path(debug_dir)
    d.mkdir(parents=True, exist_ok=True)
    for i, svg in enumerate(svgs):
        tag = "" if len(svgs) == 1 else f".{i}"
        (d / f"{name}.unwrap{tag}.svg").write_text(svg)


def _tone(cfg: Config, rgba: Image.Image) -> Image.Image:
    """The styled grayscale ('L') image per shading (normal/cel). Not for outline."""
    g = process.to_grayscale(rgba)
    if cfg.levels:
        g = process.apply_levels(g, cfg.levels[0], cfg.levels[1], cfg.gamma)
    elif cfg.gamma != 1.0:
        g = process.apply_levels(g, 0, 255, cfg.gamma)
    if cfg.shading == "cel":
        g = process.posterize(g, cfg.cel_levels)
    return g



def _sil_faces(res, f, ox, oy):
    """Silhouette-only stand-in for `res.faces`, from an engine that projects
    its faces but does not yet shade them (occt). It reaches `silhouette_geom`
    and nothing else, so fills and spur trimming stay off."""
    return shade.apply_affine_faces(
        [{"poly": np.asarray(q, float)} for q in (res.sil_polys or ())],
        f, ox, oy)

def process_one(cfg: Config, part: str, out_dir: Path, debug_dir=None) -> None:
    name = Path(part).stem if Path(part).suffix else part
    out_dir.mkdir(parents=True, exist_ok=True)
    label = name if cfg.part_label else None

    if cfg.shading == "outline" or cfg.wireframe:
        lat, long = render.resolve_latlong(cfg.angle)
        # translucent or wireframe: draw hidden geometry too
        cull = cfg.opacity >= 1.0 and not cfg.wireframe
        res = hlr.visible_segments(part, cfg.ldraw_dir, lat=lat, long=long,
                                   render_px=cfg.render_px, cull=cull, engine=cfg.engine)
        segs, bbox, s = res.segs, res.bbox, res.s
        if debug_dir:
            _emit_unwrap(debug_dir, name, res, cfg)
        style = None
        if cfg.shade_style != "none" and not cfg.wireframe:
            style = shade.make_style(cfg.shade_style,
                                     part_color=shade.parse_hex_color(cfg.part_color),
                                     light=cfg.light)
        if cfg.fmt in ("svg", "both"):
            if cfg.scale_mode == "physical":
                bx0, by0, bx1, by1 = bbox
                pad = cfg.margin / cfg.render_px * 100 * s   # small margin in px-space
                vb_w = (bx1 - bx0) + 2 * pad
                vb_h = (by1 - by0) + 2 * pad
                pbbox = (bx0 - pad, by0 - pad, bx1 + pad, by1 + pad)
                shifted = hlr.fit_segments(segs, pbbox, round(vb_w), round(vb_h),
                                           margin=0, scale=1.0)
                f, ox, oy = hlr.fit_affine(pbbox, round(vb_w), round(vb_h), margin=0, scale=1.0)
                faces = shade.apply_affine_faces(res.faces, f, ox, oy)
                ells = hlr.fit_ellipses(res.ellipses, f, ox, oy)
                spurs = shade.silhouette_spur_trim(
                    faces, ells, cfg.silhouette_mm / 0.4 * s,
                    strokes=shifted) if faces else None
                fills = shade.fill_ops(faces, style, clip=cull, ellipses=ells,
                                       proj=res.proj, fit=(f, ox, oy),
                                       refits=res.refits, loops=res.loops,
                                       strokes=shifted,
                                       line_px=cfg.line_mm / 0.4 * s,
                                       sil_px=cfg.silhouette_mm / 0.4 * s,
                                       drop=spurs,
                                       weld_corners=cfg.weld_corners,
                                       ldraw_dir=cfg.ldraw_dir) \
                    if style is not None else None
                sil_geom = shade.silhouette_geom(
                    faces or _sil_faces(res, f, ox, oy)) or None
                if sil_geom is not None and spurs is not None:
                    sil_geom = geom2d.difference(sil_geom, spurs)
                contour = geom2d.contour_d(
                    geom2d.union_all([sil_geom] + geom2d.arc_regions(shifted)),
                    geom2d.arc_candidates(ells)) \
                    if sil_geom is not None else None
                w_mm = vb_w / s * 0.4
                h_mm = vb_h / s * 0.4
                trace.segments_to_svg(
                    shifted, round(vb_w), round(vb_h), out_dir / f"{name}.svg",
                    physical=(w_mm, h_mm), s=s,
                    line_mm=cfg.line_mm, sil_mm=cfg.silhouette_mm, fills=fills,
                    bg=cfg.svg_bg, opacity=cfg.opacity,
                    clip_geom=sil_geom, contour_d=contour, label=label)
            else:
                fit = hlr.fit_segments(segs, bbox, cfg.width, cfg.height, cfg.margin, cfg.scale)
                f, ox, oy = hlr.fit_affine(bbox, cfg.width, cfg.height, cfg.margin, cfg.scale)
                faces = shade.apply_affine_faces(res.faces, f, ox, oy)
                ells = hlr.fit_ellipses(res.ellipses, f, ox, oy)
                spurs = shade.silhouette_spur_trim(
                    faces, ells, cfg.silhouette_width,
                    strokes=fit) if faces else None
                fills = shade.fill_ops(faces, style, clip=cull, ellipses=ells,
                                       proj=res.proj, fit=(f, ox, oy),
                                       refits=res.refits, loops=res.loops,
                                       strokes=fit, line_px=cfg.line_width,
                                       sil_px=cfg.silhouette_width,
                                       drop=spurs,
                                       weld_corners=cfg.weld_corners,
                                       ldraw_dir=cfg.ldraw_dir) \
                    if style is not None else None
                sil_geom = shade.silhouette_geom(
                    faces or _sil_faces(res, f, ox, oy)) or None
                if sil_geom is not None and spurs is not None:
                    sil_geom = geom2d.difference(sil_geom, spurs)
                contour = geom2d.contour_d(
                    geom2d.union_all([sil_geom] + geom2d.arc_regions(fit)),
                    geom2d.arc_candidates(ells)) \
                    if sil_geom is not None else None
                trace.segments_to_svg(fit, cfg.width, cfg.height, out_dir / f"{name}.svg",
                                      line_px=cfg.line_width, sil_px=cfg.silhouette_width,
                                      fills=fills, bg=cfg.svg_bg,
                                      opacity=cfg.opacity,
                                      clip_geom=sil_geom, contour_d=contour,
                                      label=label)
        if cfg.fmt in ("png", "both"):
            def sil_rings(W, H, fit_segs):
                f, ox, oy = hlr.fit_affine(bbox, W, H, cfg.margin, cfg.scale)
                faces = (shade.apply_affine_faces(res.faces, f, ox, oy)
                         or _sil_faces(res, f, ox, oy))
                if not faces:
                    return None
                g = geom2d.close_slivers(
                    geom2d.union_all([shade.silhouette_geom(faces)]
                                     + geom2d.arc_regions(fit_segs)))
                return geom2d.rings(g, min_area=0.5)
            if cfg.mode in ("gray", "both"):
                gpx = max(cfg.width, cfg.height, cfg.render_px // 2)
                gfit = hlr.fit_segments(segs, bbox, gpx, gpx, cfg.margin, cfg.scale)
                ratio = gpx / max(cfg.width, cfg.height)
                g = process.draw_segments(gfit, gpx, gpx,
                                          line_px=cfg.line_width * ratio,
                                          sil_px=cfg.silhouette_width * ratio,
                                          contour_rings=sil_rings(gpx, gpx, gfit))
                if label:
                    process.stamp_label(g, label)
                g.save(out_dir / f"{name}.gray.png")
            if cfg.mode in ("mono", "both"):
                mfit = hlr.fit_segments(segs, bbox, cfg.width, cfg.height, cfg.margin, cfg.scale)
                m = process.segments_mono(mfit, cfg.width, cfg.height,
                                          line_px=cfg.line_width,
                                          sil_px=cfg.silhouette_width,
                                          contour_rings=sil_rings(cfg.width, cfg.height, mfit))
                if label:
                    process.stamp_label(m, label)
                m.save(out_dir / f"{name}.mono.png")
        return

    # --- LDView path (cel / normal / color) ---
    render_png = (_stage(debug_dir, "render", name) if debug_dir
                  else out_dir / f"{name}.render.png")
    render.render_part(cfg, part, render_png)
    rgba = Image.open(render_png).convert("RGBA")

    if cfg.fmt in ("svg", "both"):
        if cfg.shading == "cel":
            trace.cel_svg(rgba, out_dir / f"{name}.svg", levels=cfg.cel_levels,
                          bg=cfg.svg_bg, opacity=cfg.opacity)
        else:
            print(f"skip svg for {name}: --shading must be outline or cel (got {cfg.shading})")

    if cfg.fmt in ("png", "both"):
        tone = _tone(cfg, rgba)
        if debug_dir:
            tone.save(_stage(debug_dir, "tone", name))
        if cfg.mode == "color":
            color = process.flatten_rgb(rgba)
            if label:
                process.stamp_label(color, label)
            color.save(out_dir / f"{name}.color.png")
        if cfg.mode in ("gray", "both"):
            if label:
                tone = process.stamp_label(tone.copy(), label)
            tone.save(out_dir / f"{name}.gray.png")
        if cfg.mode in ("mono", "both"):
            fitted = process.fit_contain(tone, cfg.width, cfg.height, cfg.margin, cfg.scale)
            mono = process.dither(fitted, cfg.dither, cfg.threshold)
            if debug_dir:
                mono.save(_stage(debug_dir, "mono", name))
            if label:
                process.stamp_label(mono, label)
            mono.save(out_dir / f"{name}.mono.png")

    if not debug_dir and render_png.exists():
        render_png.unlink()


def _gather_parts(args) -> list[str]:
    if args.list:
        return [s for ln in Path(args.list).read_text().splitlines()
                if (s := ln.split("#")[0].strip())]
    return args.parts


def _parse_decal_args(argv):
    p = argparse.ArgumentParser(
        prog="brick-icons decal",
        description="Extract a part's printed decoration as a flat SVG "
                    "texture, laid out on the face it is printed on.")
    p.add_argument("parts", nargs="*", help="part ids or .dat/.ldr paths")
    p.add_argument("--list", help="file with one part per line (overrides positional)")
    p.add_argument("--out", default="out")
    p.add_argument("--root", default=".")
    p.add_argument("--config", default=None)
    p.add_argument("--texture-px", dest="texture_px", type=int, default=900,
                   help="longer edge of the texture canvas (default 900)")
    p.add_argument("--svg-bg", dest="svg_bg", metavar="PAINT", default="none",
                   help='background: a color ("white", "#rrggbb") or "none" '
                        'for transparent (default none)')
    return p.parse_args(argv)


def decal_one(cfg, part: str, out_dir: Path, px: int, bg: str) -> list[Path]:
    """Write one SVG per carrier the part carries a decal on."""
    name = Path(part).stem if Path(part).suffix else part
    tri, tri_colors, analytic = hlr.part_geometry(part, cfg.ldraw_dir)
    svgs = unwrap.decal_svgs(tri, tri_colors, analytic, px=px,
                             ldraw_dir=cfg.ldraw_dir, bg=bg)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for i, svg in enumerate(svgs):
        tag = "" if len(svgs) == 1 else f".{i}"
        path = out_dir / f"{name}.decal{tag}.svg"
        path.write_text(svg)
        written.append(path)
    return written


def _decal_main(argv) -> int:
    args = _parse_decal_args(argv)
    toml = args.config or str(Path(args.root) / "labels.toml")
    cfg = load_config(toml_path=toml, overrides={}, root=args.root)
    parts = _gather_parts(args)
    if not parts:
        print("no parts given")
        return 2
    out_dir = Path(args.out)
    missing = []
    for i, part in enumerate(parts, 1):
        try:
            written = decal_one(cfg, part, out_dir, args.texture_px, args.svg_bg)
        except Exception as e:                  # long lists: never abort
            missing.append(part)
            print(f"[{i}/{len(parts)}] {part}: {type(e).__name__}: {e}",
                  flush=True)
            continue
        if not written:
            missing.append(part)
            print(f"[{i}/{len(parts)}] {part}: no decal", flush=True)
        else:
            head = written[0].name
            more = ("" if len(written) == 1
                    else f" (+{len(written) - 1} more surfaces)")
            print(f"[{i}/{len(parts)}] {part} -> {head}{more}", flush=True)
    if missing:
        print(f"{len(missing)}/{len(parts)} yielded no decal")
        return 1
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "decal":
        return _decal_main(argv[1:])
    args = _parse_args(argv)
    if args.list_colors:
        from . import colors
        args.part_color = None      # the listing is how you look up a name;
                                    # a bad spec must not block it
        pal = colors.load_palette(_config_from_args(args).ldraw_dir)
        for code in sorted(pal.by_code):
            c = pal.by_code[code]
            tail = "" if c.alpha == 255 else f"  alpha {c.alpha}"
            print(f"{c.code:<4} {c.name:<34} {c.hex}{tail}")
        return 0
    cfg = _config_from_args(args)
    parts = _gather_parts(args)
    if not parts:
        print("no parts given")
        return 2
    out_dir = Path(args.out)
    for part in parts:
        process_one(cfg, part, out_dir, debug_dir=args.debug_dir)
        print(f"done: {part}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
