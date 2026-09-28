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
    "pose": True,            # turn a part the way its own !PREVIEW meta says
                             # to; 394 parts in the library declare one
    "shading": "normal",     # normal | cel | outline
    "engine": "occt",        # occt | naive | cadquery (each needs its extra);
                             # occt needs the `[occt]` extra to draw at all
    "cel_levels": 4,         # bands for cel shading
    "line_width": 1.4,       # outline edge stroke, output px
    "silhouette_width": 1.4, # smooth-silhouette stroke (cylinder limbs,
                             # folds), output px — match line_width so limb
                             # lines don't read heavier than the rim arcs
                             # and box edges they abut
    "stroke_ldu": 1.0,       # fit mode: no stroke wider than this many LDU of
                             # the part as drawn, so a part shrunk to fit keeps
                             # its detail (51542); 0 = fixed width
    "stroke_floor": 0.75,    # ...and none thinner than this, output px
    "stud_stroke": 0.5,      # a declared stud's strokes, as a fraction of the
                             # icon's line weight
    "stud_floor": 0.2,       # ...and none thinner than this, output px; at
                             # 0.4 a baseplate's stud walls close up (51542)
    "crumb_ldu": 1.0,        # fill cleanup never culls a piece wider than 2x
                             # this many LDU as drawn (51542's stud walls)
    "stud_instancing": "all",  # all | off -- draw each declared stud once and
                               # place it wherever it shows (all), or every
                               # stud through the engine (off)
    "contour": "on",         # on | off -- draw the silhouette contour
    "part_color": None,      # "0xRRGGBB" or None
    "scale": 1.0,            # part fill fraction of label (0-1)
    "scale_mode": "fit",     # fit | physical  (physical: SVG sized in mm)
    "line_mm": 0.2,          # physical edge stroke width (mm)
    "silhouette_mm": 0.2,    # physical smooth-silhouette stroke width (mm)
    "shade_style": "none",
    "light": None,           # "LAT,LONG" view-space light; None = style default
    "svg_bg": "none",        # SVG background paint; "none" = transparent
    "opacity": 1.0,          # face-fill opacity in SVG (translucent bricks)
    "solid_deco": False,     # under opacity < 1, paint printing and stickers
                             # at full opacity; the body stays see-through
    "wireframe": False,      # outline strokes only, occlusion culling off
    "use_ldview": False,     # draw with the vendored LDView, not our engine
    "ldview_look": "color",  # color | gray | lines -- what LDView draws: the
                             # part in its authored colors with edge lines,
                             # flat3's gray under flat3's light with no
                             # lines, or the edge lines alone
    "decal": False,          # lift the printed decoration off the part and
                             # lay it flat; no viewpoint, so the view, sizing
                             # and stroke settings do not apply
    "texture_px": 900,       # longer edge of a decal canvas, in px
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
    pose: bool
    shading: str
    engine: str
    cel_levels: int
    line_width: float
    silhouette_width: float
    stroke_ldu: float
    stroke_floor: float
    stud_stroke: float
    stud_floor: float
    crumb_ldu: float
    stud_instancing: str
    contour: str
    part_color: str | None
    scale: float
    scale_mode: str
    line_mm: float
    silhouette_mm: float
    shade_style: str
    light: str | None
    svg_bg: str
    opacity: float
    solid_deco: bool
    wireframe: bool
    use_ldview: bool
    ldview_look: str
    decal: bool
    texture_px: int
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
        pose=bool(data["pose"]),
        shading=str(data["shading"]),
        engine=str(data["engine"]),
        cel_levels=int(data["cel_levels"]),
        line_width=float(data["line_width"]),
        silhouette_width=float(data["silhouette_width"]),
        stroke_ldu=float(data["stroke_ldu"]),
        stroke_floor=float(data["stroke_floor"]),
        stud_stroke=float(data["stud_stroke"]),
        stud_floor=float(data["stud_floor"]),
        crumb_ldu=float(data["crumb_ldu"]),
        stud_instancing=str(data["stud_instancing"]),
        contour=str(data["contour"]),
        part_color=(str(data["part_color"]) if data["part_color"] else None),
        scale=float(data["scale"]),
        scale_mode=str(data["scale_mode"]),
        line_mm=float(data["line_mm"]),
        silhouette_mm=float(data["silhouette_mm"]),
        shade_style=str(data["shade_style"]),
        light=(str(data["light"]) if data["light"] else None),
        svg_bg=str(data["svg_bg"]),
        opacity=float(data["opacity"]),
        solid_deco=bool(data["solid_deco"]),
        wireframe=bool(data["wireframe"]),
        use_ldview=bool(data["use_ldview"]),
        ldview_look=str(data["ldview_look"]),
        decal=bool(data["decal"]),
        texture_px=int(data["texture_px"]),
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
