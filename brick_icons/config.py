from __future__ import annotations

import platform as _platform
import tomllib
from dataclasses import dataclass
from pathlib import Path

MM_PER_INCH = 25.4


def default_ldview_launcher(system: str | None = None, machine: str | None = None) -> list[str]:
    """Prefix args to launch LDView. macOS ships only an x86_64 build, so run it
    under Rosetta on Apple Silicon; everywhere else, run the binary directly."""
    system = system or _platform.system()
    machine = machine or _platform.machine()
    if system == "Darwin" and machine == "arm64":
        return ["arch", "-x86_64"]
    return []


DEFAULTS = {
    "ldview": "vendor/LDView.app/Contents/MacOS/LDView",
    "ldview_launcher": None,   # None -> default_ldview_launcher(); [] to force direct
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
    "cel_levels": 4,         # bands for cel shading
    "outline_interior": True,# include interior edges in outline
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
    cel_levels: int
    outline_interior: bool
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
    fmt: str
    mode: str
    dither: str
    threshold: int
    gamma: float
    levels: tuple | None


def load_config(toml_path=None, overrides=None, root="."):
    data = dict(DEFAULTS)
    if toml_path and Path(toml_path).exists():
        with open(toml_path, "rb") as f:
            data.update(tomllib.load(f))
    if overrides:
        data.update({k: v for k, v in overrides.items() if v is not None})

    root = Path(root)
    if data.get("label_mm"):
        w_mm, h_mm = data["label_mm"]
        data["width"] = round(w_mm / MM_PER_INCH * data["dpi"])
        data["height"] = round(h_mm / MM_PER_INCH * data["dpi"])

    launcher = data["ldview_launcher"]
    if launcher is None:
        launcher = default_ldview_launcher()

    return Config(
        ldview=root / data["ldview"],
        ldview_launcher=tuple(launcher),
        ldraw_dir=root / data["ldraw_dir"],
        dpi=int(data["dpi"]),
        width=int(data["width"]),
        height=int(data["height"]),
        margin=int(data["margin"]),
        render_px=int(data["render_px"]),
        curve_quality=int(data["curve_quality"]),
        angle=str(data["angle"]),
        shading=str(data["shading"]),
        cel_levels=int(data["cel_levels"]),
        outline_interior=bool(data["outline_interior"]),
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
        fmt=str(data["fmt"]),
        mode=str(data["mode"]),
        dither=str(data["dither"]),
        threshold=int(data["threshold"]),
        gamma=float(data["gamma"]),
        levels=tuple(data["levels"]) if data["levels"] else None,
    )
