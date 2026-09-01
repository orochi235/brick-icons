"""Extracted decals, for the decal pane.

Extraction re-parses the part and unwraps every carrier, so it is slow enough
to cache. The lab calls the CLI's own `decal_one` rather than reassembling the
pipeline: a second answer to what a decal is would be exactly the divergence
the lab exists to catch.

A part with no decoration yields no SVG. That is the answer, not a failure --
and because it comes from running the extractor, it is more authoritative than
any guess from the part id.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..config import load_config

DEFAULT_PX = 900
DEFAULT_BG = "none"


def key(part: str, texture_px: int, svg_bg: str) -> str:
    blob = "\x00".join([part, str(texture_px), svg_bg])
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def extract(part: str, root: Path | str = ".",
            cache_root: Path | str = "out/lab/decal",
            texture_px: int = DEFAULT_PX,
            svg_bg: str = DEFAULT_BG) -> dict:
    cache_key = key(part, texture_px, svg_bg)
    out_dir = Path(cache_root) / cache_key
    stamp = out_dir / ".extracted"

    if stamp.exists():
        return {"ok": True, "cached": True, "key": cache_key,
                "names": sorted(p.name for p in out_dir.glob("*.svg")),
                "error": None}

    from .. import cli                          # imports OCP-free but heavy
    cfg = load_config(root=str(root))
    try:
        written = cli.decal_one(cfg, part, out_dir, texture_px, svg_bg)
    except Exception as e:                      # noqa: BLE001
        return {"ok": False, "cached": False, "key": cache_key, "names": [],
                "error": f"{type(e).__name__}: {e}"}

    # The stamp is what separates "extracted, found nothing" from "never run":
    # both leave the directory without SVGs, and only one should be re-run.
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp.write_text("")
    return {"ok": True, "cached": False, "key": cache_key,
            "names": sorted(p.name for p in written), "error": None}
