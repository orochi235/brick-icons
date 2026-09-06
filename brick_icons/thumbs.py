"""Thumbnails for the corpus wall: per-part rasters and the sheets holding them.

A cell's index is its position in part-id order over every part, so a render
landing later writes one cell rather than renumbering the sheet.
"""
from __future__ import annotations

import json
import math
import os
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
GROUNDS = "grounds.json"

#: The ground a thumbnail is fitted onto, mirrored by `THUMB_GROUND` in
#: lab/src/corpus/paint.ts -- the wall's vector rung rasterizes the SVG itself
#: and has no bake to inherit this from.
GROUND = (255, 255, 255, 255)

#: What a retired part sits on instead, mirrored by `RETIRED_GROUND` there.
RETIRED_GROUND = (233, 233, 233, 255)


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


def _read_json(path: Path) -> dict:
    """A sidecar that cannot be read is a cache miss, not a crash: every value
    in it is recoverable by baking the part again."""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    """Written whole or not at all. `write_text` truncates first, so a reader
    that arrives mid-write gets an empty file and every later bake dies on it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, sort_keys=True))
    os.replace(tmp, path)


def baked_shas(out: Path | str) -> dict[str, str]:
    return _read_json(Path(out) / BAKED)


def baked_grounds(out: Path | str) -> dict[str, list[int]]:
    """What ground each part was last baked on.

    Its own sidecar because `baked.json` is copied into the sheet manifest and
    the wall compares those values to a render sha -- anything else in there
    would read as a stale cell.
    """
    return _read_json(Path(out) / GROUNDS)


def _write_baked(out: Path, shas: dict[str, str]) -> None:
    _write_json(out / BAKED, shas)


def bake_part(part_id: str, svg: Path | str, out: Path | str,
              sha: str, ground: tuple[int, int, int, int] = GROUND) -> list[int]:
    """Rasterize one part at every level. Returns the levels written.

    An unchanged sha on an unchanged ground writes nothing: this runs after
    every batch of renders, and the corpus it has already baked is the
    overwhelming majority of it.
    """
    out = Path(out)
    shas = baked_shas(out)
    grounds = baked_grounds(out)
    # A part baked before grounds were recorded was baked on `GROUND`, so a
    # missing entry is not a reason to redo the whole corpus once.
    if (shas.get(part_id) == sha
            and grounds.get(part_id, list(GROUND)) == list(ground)):
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
            _square(drawn, level, ground).save(path)
    finally:
        wide.unlink(missing_ok=True)
    _write_baked(out, {**shas, part_id: sha})
    _write_json(out / GROUNDS, {**grounds, part_id: list(ground)})
    return list(LEVELS)


def compose(out: Path | str, order: list[str]) -> list[Path]:
    """Paste every baked thumbnail onto its sheet, in `order`'s index order.

    `order` is every part, not only the drawn ones: an index is a position in
    the corpus, so a part gaining a render later fills the cell it already had.
    """
    out = Path(out)
    shas = baked_shas(out)
    written = []
    for level in SHEET_LEVELS:
        g = geometry(len(order), level)
        sheet = Image.new("RGBA", (g.size, g.size), (0, 0, 0, 0))
        for index, part_id in enumerate(order):
            tile = out / str(level) / f"{part_id}.png"
            if not tile.is_file():
                continue
            with Image.open(tile) as img:
                cell = img.convert("RGBA")
            x0, y0, _, _ = g.cell_box(index)
            sheet.paste(cell, (x0, y0))
            if g.gutter:
                _replicate_edges(sheet, cell, x0, y0, g.gutter)
        path = out / f"sheet-{level}.png"
        sheet.save(path)
        (out / f"sheet-{level}.json").write_text(json.dumps({
            "level": level, "gutter": g.gutter, "pitch": g.pitch,
            "cols": g.cols, "rows": g.rows, "count": len(order),
            "size": g.size, "baked": shas,
        }, sort_keys=True))
        written.append(path)
    return written


def _replicate_edges(sheet: Image.Image, cell: Image.Image,
                     x0: int, y0: int, gutter: int) -> None:
    """Pad a cell with its own edge pixels.

    Without this each mip reduction averages a cell against its neighbour and
    the wall reads as halos -- a rendering fault that looks like a data fault.
    """
    w, h = cell.size
    for d in range(1, gutter + 1):
        sheet.paste(cell.crop((0, 0, w, 1)), (x0, y0 - d))
        sheet.paste(cell.crop((0, h - 1, w, h)), (x0, y0 + h + d - 1))
        sheet.paste(cell.crop((0, 0, 1, h)), (x0 - d, y0))
        sheet.paste(cell.crop((w - 1, 0, w, h)), (x0 + w + d - 1, y0))


def _square(drawn: Image.Image, level: int,
            ground: tuple[int, int, int, int] = GROUND) -> Image.Image:
    """Fit a render inside an opaque `ground` square of `level` px.

    Opaque, because a render is black ink on transparency and the wall's
    background follows the weasel theme -- a transparent thumbnail is invisible
    in dark mode. A cell that was never baked stays fully transparent on the
    sheet, so alpha still separates "drawn" from "not drawn".
    """
    scale = level / max(drawn.size)
    size = (max(1, round(drawn.width * scale)), max(1, round(drawn.height * scale)))
    cell = Image.new("RGBA", (level, level), ground)
    fitted = drawn.resize(size, Image.LANCZOS)
    cell.paste(fitted, ((level - size[0]) // 2, (level - size[1]) // 2), fitted)
    return cell
