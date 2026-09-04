from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import colors

MM_PER_INCH = 25.4


DEFAULTS = {
    "ldview": "vendor/LDView.app/Contents/MacOS/LDView",
    "ldview_launcher": [],     # argv prefix for LDView; a platform that needs
                               # one (an emulator, a wrapper) sets it in the config
    "ldraw_dir": "vendor/ldraw",
    "dpi": 180,
    "label_mm": None,        # (w_mm, h_mm) or None
    "width": 256,            # px (ignored if label_mm)
    "height": 170,
    "margin": 6,
    "render_px": 2048,       # LDView supersample square
    "curve_quality": 12,     # LDView curve subdivision (max)
    "angle": "iso",          # preset or "LAT,LONG"
    "shading": "normal",     # normal | cel | outline
    "engine": "naive",       # naive | occt | cadquery (each needs its extra)
    "cel_levels": 4,         # bands for cel shading
    "line_width": 2,         # outline edge stroke, output px
    "silhouette_width": 2,   # smooth-silhouette stroke (cylinder limbs,
                             # folds), output px — match line_width so limb
                             # lines don't read heavier than the rim arcs
                             # and box edges they abut
    "part_color": None,      # "0xRRGGBB" or None
    "scale": 1.0,            # part fill fraction of label (0-1)
    "scale_mode": "fit",     # fit | physical  (physical: SVG sized in mm)
    "line_mm": 0.2,          # physical edge stroke width (mm)
    "silhouette_mm": 0.2,    # physical smooth-silhouette stroke width (mm)
    "shade_style": "none",
    "light": None,           # "LAT,LONG" view-space light; None = style default
    "svg_bg": "none",        # SVG background paint; "none" = transparent
    "opacity": 1.0,          # face-fill opacity in SVG (translucent bricks)
    "wireframe": False,      # outline strokes only, occlusion culling off
    "weld_corners": False,   # broad junction weld: ink the notch at EVERY
                             # stroke T-graze, not just stub-bridged
                             # junctions (restyles stud/limb corners)
    "part_label": False,     # stamp the part id in small print (test renders)
    "debug_colors": False,   # False | "cycle" | "ramp" | "ramp=N" -- one
                             # color per drawn element, in emission order
    "fmt": "png",            # png | svg | both
    "mode": "both",          # gray | mono | color | both  (png only)
    "dither": "atkinson",    # threshold | floyd | ordered | atkinson
    "threshold": 128,
    "gamma": 1.0,
    "levels": None,          # (black_in, white_in) or None
}


@dataclass(frozen=True)
class Config:
    ldview: Path
    ldview_launcher: tuple
    ldraw_dir: Path
    dpi: int
    width: int
    height: int
    margin: int
    render_px: int
    curve_quality: int
    angle: str
    shading: str
    engine: str
    cel_levels: int
    line_width: int
    silhouette_width: int
    part_color: str | None
    scale: float
    scale_mode: str
    line_mm: float
    silhouette_mm: float
    shade_style: str
    light: str | None
    svg_bg: str
    opacity: float
    wireframe: bool
    weld_corners: bool
    part_label: bool
    debug_colors: bool | str
    fmt: str
    mode: str
    dither: str
    threshold: int
    gamma: float
    levels: tuple | None


def load_config(toml_path=None, overrides=None, root="."):
    data = dict(DEFAULTS)
    explicit = set()            # keys the caller actually set: a translucent
                                # color supplies opacity only if they did not
    if toml_path and Path(toml_path).exists():
        with open(toml_path, "rb") as f:
            from_toml = tomllib.load(f)
        data.update(from_toml)
        explicit |= set(from_toml)
    if overrides:
        given = {k: v for k, v in overrides.items() if v is not None}
        data.update(given)
        explicit |= set(given)

    root = Path(root)
    if data.get("label_mm"):
        w_mm, h_mm = data["label_mm"]
        data["width"] = round(w_mm / MM_PER_INCH * data["dpi"])
        data["height"] = round(h_mm / MM_PER_INCH * data["dpi"])

    ldraw_dir = root / data["ldraw_dir"]
    if data["part_color"]:
        hex_str, alpha = colors.resolve(data["part_color"], ldraw_dir)
        data["part_color"] = hex_str
        if alpha is not None and "opacity" not in explicit:
            data["opacity"] = alpha / 255.0

    launcher = data["ldview_launcher"] or []

    return Config(
        ldview=root / data["ldview"],
        ldview_launcher=tuple(launcher),
        ldraw_dir=ldraw_dir,
        dpi=int(data["dpi"]),
        width=int(data["width"]),
        height=int(data["height"]),
        margin=int(data["margin"]),
        render_px=int(data["render_px"]),
        curve_quality=int(data["curve_quality"]),
        angle=str(data["angle"]),
        shading=str(data["shading"]),
        engine=str(data["engine"]),
        cel_levels=int(data["cel_levels"]),
        line_width=int(data["line_width"]),
        silhouette_width=int(data["silhouette_width"]),
        part_color=(str(data["part_color"]) if data["part_color"] else None),
        scale=float(data["scale"]),
        scale_mode=str(data["scale_mode"]),
        line_mm=float(data["line_mm"]),
        silhouette_mm=float(data["silhouette_mm"]),
        shade_style=str(data["shade_style"]),
        light=(str(data["light"]) if data["light"] else None),
        svg_bg=str(data["svg_bg"]),
        opacity=float(data["opacity"]),
        wireframe=bool(data["wireframe"]),
        weld_corners=bool(data["weld_corners"]),
        part_label=bool(data["part_label"]),
        debug_colors=(data["debug_colors"]
                      if isinstance(data["debug_colors"], str)
                      else bool(data["debug_colors"])),
        fmt=str(data["fmt"]),
        mode=str(data["mode"]),
        dither=str(data["dither"]),
        threshold=int(data["threshold"]),
        gamma=float(data["gamma"]),
        levels=tuple(data["levels"]) if data["levels"] else None,
    )
