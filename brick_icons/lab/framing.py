"""Where a raster render sits on the canvas the drawings are fitted to.

A drawing is fitted to a `width` x `height` canvas inside `margin` by
`hlr.fit_affine`. A raster slot frames itself -- LDView crops to the part, the
browser reference fits a 512 square -- so shown side by side the same part
comes out at a different scale in every pane. Fitting the raster's ink box by
the same rule puts it where a drawing of that part would be.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image

from ..hlr import fit_affine


@lru_cache(maxsize=1024)
def _ink(path: str, sha256: str) -> tuple[int, int, tuple] | None:
    """Image size and the bbox of its non-transparent pixels. `sha256` keys
    the cache, so a redraw at the same path is measured again."""
    with Image.open(path) as im:
        if "A" not in im.getbands():
            return None
        box = im.getchannel("A").getbbox()
        return (im.width, im.height, box) if box else None


def placement(path: Path | str, sha256: str, width: int, height: int,
              margin: int) -> dict | None:
    """The image's rectangle on the drawings' canvas, in canvas px, or None
    for one with no alpha to find the part by."""
    ink = _ink(str(path), sha256)
    if ink is None:
        return None
    iw, ih, box = ink
    f, ox, oy = fit_affine(box, width, height, margin)
    return {"canvas": [width, height],
            "x": ox, "y": oy, "w": iw * f, "h": ih * f}
