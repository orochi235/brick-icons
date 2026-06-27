from __future__ import annotations

import subprocess
from pathlib import Path

from .config import Config

ANGLE_PRESETS = {
    "iso": (30.0, 45.0), "front": (0.0, 0.0), "back": (0.0, 180.0),
    "left": (0.0, -90.0), "right": (0.0, 90.0), "top": (90.0, 0.0),
    "bottom": (-90.0, 0.0),
}


def resolve_latlong(angle: str) -> tuple[float, float]:
    if angle in ANGLE_PRESETS:
        return ANGLE_PRESETS[angle]
    try:
        lat, long = (float(x) for x in angle.split(","))
        return lat, long
    except (ValueError, TypeError):
        raise ValueError(f"bad angle {angle!r}: preset {list(ANGLE_PRESETS)} or 'LAT,LONG'")


def resolve_part(cfg: Config, part: str) -> Path:
    p = Path(part)
    if p.suffix.lower() in (".dat", ".ldr", ".mpd") and p.exists():
        return p
    candidate = cfg.ldraw_dir / "parts" / f"{part}.dat"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"could not resolve part {part!r} (looked for {candidate})")


def build_argv(cfg: Config, part_file: Path, out_png: Path) -> list[str]:
    lat, long = resolve_latlong(cfg.angle)
    argv = [
        *cfg.ldview_launcher, str(cfg.ldview), str(part_file),
        f"-LDrawDir={cfg.ldraw_dir}",
        f"-SaveSnapshot={out_png}",
        f"-SaveWidth={cfg.render_px}", f"-SaveHeight={cfg.render_px}",
        "-AutoCrop=1", "-SaveAlpha=1", "-EdgeLines=1",
        f"-CurveQuality={cfg.curve_quality}",
        "-HiResPrimitives=1", "-AllowPrimitiveSubstitution=1",
        "-Lighting=1", "-UseQualityLighting=1", "-LightVector=-1,1,2",
        f"-DefaultLatLong={lat},{long}",
    ]
    if cfg.part_color:
        argv.append(f"-DefaultColor3={cfg.part_color}")
    return argv


def render_part(cfg: Config, part: str, out_png: Path) -> Path:
    part_file = resolve_part(cfg, part)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(build_argv(cfg, part_file, out_png), check=True, capture_output=True)
    if not out_png.exists():
        raise RuntimeError(f"LDView did not write {out_png}")
    return out_png
