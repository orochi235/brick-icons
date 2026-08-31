"""LDView renders, for the reference pane.

LDView writes a snapshot per invocation, so every frame is a subprocess. That
is why this caches on everything that changes the picture, and why the pane
asks for a frame only when an orbit settles rather than while it moves.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .. import render
from ..config import load_config


def key(part: str, angle: str, render_px: int, part_color: str | None) -> str:
    blob = "\x00".join([part, angle, str(render_px), part_color or ""])
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def available(root: Path | str = ".") -> bool:
    """Whether the vendored LDView is actually present."""
    return Path(load_config(root=str(root)).ldview).exists()


def render_reference(part: str, angle: str, root: Path | str = ".",
                     cache_root: Path | str = "out/lab/reference",
                     render_px: int | None = None,
                     part_color: str | None = None) -> dict:
    cfg = load_config(root=str(root))
    px = render_px or cfg.render_px
    cache_key = key(part, angle, px, part_color)
    name = f"{part}.png"
    out = Path(cache_root) / cache_key / name

    def failed(message: str) -> dict:
        return {"ok": False, "cached": False, "key": cache_key, "name": name,
                "error": message}

    try:
        render.resolve_latlong(angle)
    except ValueError as e:
        return failed(str(e))

    if out.exists():
        return {"ok": True, "cached": True, "key": cache_key, "name": name,
                "error": None}
    if not available(root):
        return failed("LDView is not installed — run scripts/setup-ldview.sh")

    overrides = {"angle": angle, "render_px": px}
    if part_color:
        overrides["part_color"] = part_color
    cfg = load_config(root=str(root), overrides=overrides)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        render.render_part(cfg, part, out)
    except Exception as e:                          # noqa: BLE001
        return failed(f"{type(e).__name__}: {e}")
    return {"ok": True, "cached": False, "key": cache_key, "name": name,
            "error": None}
