"""Thumbnails for the corpus wall: per-part rasters and the sheets holding them.

A cell's index is its position in part-id order over every part, so a render
landing later writes one cell rather than renumbering the sheet.
"""
from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

SHEET_LEVELS = (8, 32)
LOOSE_LEVEL = 128
# The mip chain stops at the coarsest level, so it cannot bleed and needs no
# padding. Every finer sheet does.
GUTTER = 2
LEVELS = (*SHEET_LEVELS, LOOSE_LEVEL)
BAKED = "baked.json"


@dataclass(frozen=True)
class Geometry:
    count: int
    level: int
    cols: int
    rows: int
    gutter: int

    @property
    def pitch(self) -> int:
        return self.level + 2 * self.gutter

    @property
    def size(self) -> int:
        return self.cols * self.pitch

    def cell_box(self, index: int) -> tuple[int, int, int, int]:
        """The cell's (left, top, right, bottom) on the sheet, gutters excluded."""
        if not 0 <= index < self.cols * self.rows:
            raise IndexError(f"cell {index} is outside a {self.cols}x{self.rows} grid")
        col, row = index % self.cols, index // self.cols
        x = col * self.pitch + self.gutter
        y = row * self.pitch + self.gutter
        return (x, y, x + self.level, y + self.level)


def geometry(count: int, level: int) -> Geometry:
    if level not in SHEET_LEVELS:
        raise ValueError(f"{level} is not a sheet level; sheets are {SHEET_LEVELS}")
    cols = max(1, math.ceil(math.sqrt(count)))
    # cols >= sqrt(count) makes cols*cols >= count, so rows <= cols always and
    # a square `size` is never a crop -- only ever some dead rows at the bottom.
    rows = max(1, math.ceil(count / cols))
    gutter = 0 if level == min(SHEET_LEVELS) else GUTTER
    return Geometry(count=count, level=level, cols=cols, rows=rows, gutter=gutter)


def baked_shas(out: Path | str) -> dict[str, str]:
    path = Path(out) / BAKED
    return json.loads(path.read_text()) if path.is_file() else {}


def _write_baked(out: Path, shas: dict[str, str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / BAKED).write_text(json.dumps(shas, sort_keys=True))


def bake_part(part_id: str, svg: Path | str, out: Path | str,
              sha: str) -> list[int]:
    """Rasterize one part at every level. Returns the levels written.

    An unchanged sha writes nothing: this runs after every batch of renders,
    and the corpus it has already baked is the overwhelming majority of it.
    """
    out = Path(out)
    shas = baked_shas(out)
    if shas.get(part_id) == sha:
        return []
    # resvg is the project's antialias reference -- the same rasterizer the
    # census, the contact sheet and the differ use. It has no letterbox flag
    # (`-w`, `-h`, `-z` only) and passing both -w and -h stretches a 256x170
    # render, so it is asked for a width and squared here.
    out.mkdir(parents=True, exist_ok=True)
    wide = out / f".{part_id}.wide.png"
    proc = subprocess.run(
        ["resvg", "--width", str(LOOSE_LEVEL), str(svg), str(wide)],
        capture_output=True, text=True)
    if proc.returncode != 0 or not wide.is_file():
        raise RuntimeError(f"resvg failed on {part_id}: "
                           f"{(proc.stderr or proc.stdout).strip()[:200]}")
    try:
        with Image.open(wide) as img:
            drawn = img.convert("RGBA")
        for level in LEVELS:
            path = out / str(level) / f"{part_id}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            _square(drawn, level).save(path)
    finally:
        wide.unlink(missing_ok=True)
    _write_baked(out, {**shas, part_id: sha})
    return list(LEVELS)


def _square(drawn: Image.Image, level: int) -> Image.Image:
    """Fit a render inside an opaque white square of `level` px.

    Opaque, because a render is black ink on transparency and the wall's
    background follows the weasel theme -- a transparent thumbnail is invisible
    in dark mode. A cell that was never baked stays fully transparent on the
    sheet, so alpha still separates "drawn" from "not drawn".
    """
    scale = level / max(drawn.size)
    size = (max(1, round(drawn.width * scale)), max(1, round(drawn.height * scale)))
    cell = Image.new("RGBA", (level, level), (255, 255, 255, 255))
    fitted = drawn.resize(size, Image.LANCZOS)
    cell.paste(fitted, ((level - size[0]) // 2, (level - size[1]) // 2), fitted)
    return cell
