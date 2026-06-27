from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from . import render, process, trace
from .config import load_config, Config


def _parse_args(argv):
    p = argparse.ArgumentParser(prog="lego-bin-labels",
                                description="Render LEGO parts into bin-label assets.")
    p.add_argument("parts", nargs="*", help="part ids or .dat/.ldr paths")
    p.add_argument("--list", help="file with one part per line (overrides positional)")
    p.add_argument("--out", default="out")
    p.add_argument("--root", default=".")
    p.add_argument("--config", default=None)
    p.add_argument("--format", dest="fmt", choices=["png", "svg", "both"])
    p.add_argument("--mode", choices=["gray", "mono", "color", "both"])
    p.add_argument("--shading", choices=["normal", "cel", "outline"])
    p.add_argument("--cel-levels", type=int)
    p.add_argument("--outline-interior", dest="outline_interior", action="store_true", default=None)
    p.add_argument("--no-outline-interior", dest="outline_interior", action="store_false")
    p.add_argument("--dither", choices=["threshold", "floyd", "ordered", "atkinson"])
    p.add_argument("--angle")
    p.add_argument("--part-color")
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
    p.add_argument("--debug-dir", default=None)
    return p.parse_args(argv)


def _config_from_args(args) -> Config:
    toml = args.config or str(Path(args.root) / "labels.toml")
    overrides = {
        "fmt": args.fmt, "mode": args.mode, "shading": args.shading,
        "cel_levels": args.cel_levels, "outline_interior": args.outline_interior,
        "dither": args.dither, "angle": args.angle, "part_color": args.part_color,
        "curve_quality": args.curve_quality, "render_px": args.render_px,
        "scale": args.scale, "width": args.width, "height": args.height,
        "dpi": args.dpi, "label_mm": tuple(args.label_mm) if args.label_mm else None,
        "margin": args.margin, "threshold": args.threshold, "gamma": args.gamma,
        "levels": tuple(args.levels) if args.levels else None,
    }
    return load_config(toml_path=toml, overrides=overrides, root=args.root)


def _stage(debug_dir, stage, name) -> Path:
    d = Path(debug_dir) / stage
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{name}.png"


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


def process_one(cfg: Config, part: str, out_dir: Path, debug_dir=None) -> None:
    name = Path(part).stem if Path(part).suffix else part
    render_png = (_stage(debug_dir, "render", name) if debug_dir
                  else out_dir / f"{name}.render.png")
    render.render_part(cfg, part, render_png)
    rgba = Image.open(render_png).convert("RGBA")
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- SVG ---
    if cfg.fmt in ("svg", "both"):
        if cfg.shading == "outline":
            trace.outline_svg(rgba, out_dir / f"{name}.svg", interior=cfg.outline_interior)
        elif cfg.shading == "cel":
            trace.cel_svg(rgba, out_dir / f"{name}.svg", levels=cfg.cel_levels)
        else:
            print(f"skip svg for {name}: --shading must be outline or cel (got {cfg.shading})")

    # --- PNG ---
    if cfg.fmt in ("png", "both"):
        if cfg.shading == "outline":
            tone = process.make_outline(rgba, interior=cfg.outline_interior)
        else:
            tone = _tone(cfg, rgba)
        if debug_dir:
            tone.save(_stage(debug_dir, "tone", name))

        if cfg.mode == "color":
            process.flatten_rgb(rgba).save(out_dir / f"{name}.color.png")
        if cfg.mode in ("gray", "both"):
            tone.save(out_dir / f"{name}.gray.png")
        if cfg.mode in ("mono", "both"):
            fitted = process.fit_contain(tone, cfg.width, cfg.height, cfg.margin, cfg.scale)
            if cfg.shading == "outline":
                mono = process.dither(fitted, "threshold", 200)  # keep lines crisp
            else:
                mono = process.dither(fitted, cfg.dither, cfg.threshold)
            if debug_dir:
                mono.save(_stage(debug_dir, "mono", name))
            mono.save(out_dir / f"{name}.mono.png")

    if not debug_dir and render_png.exists():
        render_png.unlink()


def _gather_parts(args) -> list[str]:
    if args.list:
        return [s for ln in Path(args.list).read_text().splitlines()
                if (s := ln.strip()) and not s.startswith("#")]
    return args.parts


def main(argv=None) -> int:
    args = _parse_args(argv)
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
