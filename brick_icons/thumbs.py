"""Thumbnails for the corpus wall: per-part rasters and the sheets holding them.

A cell's index is its position in part-id order over every part, so a render
landing later writes one cell rather than renumbering the sheet.
"""
from __future__ import annotations

import fcntl
import json
import math
import os
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import trace

SHEET_LEVELS = (8, 32)
LOOSE_LEVEL = 128
# The mip chain stops at the coarsest level, so it cannot bleed and needs no
# padding. Every finer sheet does.
GUTTER = 2
LEVELS = (*SHEET_LEVELS, LOOSE_LEVEL)
BAKED = "baked.json"
#: The decoration masks, beside the drawings with the same layout, so a
#: mask tile and sheet line up with the drawing's cell for cell.
MASK_DIR = "mask"

#: Transparent: a bake carries ink and nothing else, and the wall paints the
#: ground under it. Baking a ground made the three zoom rungs disagree about
#: who owned the cell background -- the sheet had white in its pixels, the
#: loose PNG hid the ground drawn under it, and only the vector rung showed
#: one -- so a cell jumped from #ffffff to the ground color on one wheel notch.
GROUND = (0, 0, 0, 0)



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



def _write_baked(out: Path, shas: dict[str, str]) -> None:
    _write_json(out / BAKED, shas)


def _rasterized(part_id: str, svg: Path, out: Path) -> Image.Image:
    wide = out / f".{part_id}.wide.png"
    proc = subprocess.run(
        ["resvg", "--width", str(LOOSE_LEVEL), str(svg), str(wide)],
        capture_output=True, text=True)
    if proc.returncode != 0 or not wide.is_file():
        raise RuntimeError(f"resvg failed on {part_id}: "
                           f"{(proc.stderr or proc.stdout).strip()[:200]}")
    try:
        with Image.open(wide) as img:
            return img.convert("RGBA")
    finally:
        wide.unlink(missing_ok=True)


def _mask_text(render: Path) -> str | None:
    if render.suffix.lower() != ".svg":
        return None
    return trace.deco_mask_svg(render.read_text())


def _drawn(part_id: str, render: Path, out: Path) -> Image.Image:
    """The render at `LOOSE_LEVEL` wide, as RGBA.

    A vector slot goes through resvg -- the project's antialias reference, the
    same rasterizer the census, the contact sheet and the differ use. It has no
    letterbox flag (`-w`, `-h`, `-z` only) and passing both -w and -h stretches
    a 256x170 render, so it is asked for a width and squared by `_square`.

    A raster slot has no SVG to rasterize; `reference` writes WebP. Feeding one to
    resvg fails with "provided data has not an UTF-8 encoding", which reads
    like a corrupt file rather than the wrong kind of one.
    """
    if render.suffix.lower() != ".svg":
        with Image.open(render) as img:
            return img.convert("RGBA")
    return _rasterized(part_id, render, out)


#: Thumbnails and sheets are WebP q90, as the raster render slots are: sheet-32
#: is 24 MB as PNG against 12 MB here, and the wall fetches it on every open.
THUMB_EXT = "webp"
THUMB_SAVE = {"format": "WEBP", "quality": 90, "method": 4}

#: The lossless copy of each sheet that a patch edits. Re-encoding the WebP
#: itself is generational: one pass over the occt slot's sheet-32 changed 8.7M
#: of its 32M pixels. One per sheet, overwritten in place.
MASTER = "sheet-{level}.master.png"
MASTER_SAVE = {"format": "PNG", "compress_level": 1}
_LOCK = ".sheets.lock"


def bake_part(part_id: str, svg: Path | str, out: Path | str,
              sha: str) -> list[int]:
    """Rasterize one part at every level. Returns the levels written.

    An unchanged sha writes nothing: this runs after every batch of renders,
    and the corpus it has already baked is the overwhelming majority of it.
    """
    out, svg = Path(out), Path(svg)
    shas = baked_shas(out)
    mask_text = _mask_text(svg)
    masks = out / MASK_DIR
    # The sha covers the render, not the encoding, so the tiles have to be
    # there in the format being written now -- otherwise changing THUMB_EXT
    # skips every part and composes a sheet out of tiles that do not exist.
    if shas.get(part_id) == sha and _tiles_exist(out, part_id) and (
            mask_text is None or baked_shas(masks).get(part_id) == sha
            and _tiles_exist(masks, part_id)):
        return []
    out.mkdir(parents=True, exist_ok=True)
    _write_tiles(out, part_id, _drawn(part_id, svg, out))
    mask_shas = baked_shas(masks)
    if mask_text is not None:
        masks.mkdir(parents=True, exist_ok=True)
        tmp = masks / f".{part_id}.mask.svg"
        tmp.write_text(mask_text)
        try:
            _write_tiles(masks, part_id, _rasterized(part_id, tmp, masks))
        finally:
            tmp.unlink(missing_ok=True)
    elif part_id in mask_shas:
        # Redrawn without marks: its old mask would describe another drawing.
        for level in LEVELS:
            (masks / str(level) / f"{part_id}.{THUMB_EXT}").unlink(missing_ok=True)
    # A lab redraw and bake-thumbs.py's watcher can land on the same slot at
    # once: baked.json is the only state two bakes of different parts share,
    # so its read-modify-write is locked and re-read fresh here rather than
    # merged into the snapshot taken before this part's tiles were written.
    with _sheets_locked(out):
        _write_baked(out, {**baked_shas(out), part_id: sha})
    if mask_text is not None:
        with _sheets_locked(masks):
            _write_baked(masks, {**baked_shas(masks), part_id: sha})
    elif part_id in mask_shas:
        with _sheets_locked(masks):
            _write_baked(masks, {k: v for k, v in baked_shas(masks).items()
                                 if k != part_id})
    return list(LEVELS)


def _tiles_exist(out: Path, part_id: str) -> bool:
    return all((out / str(level) / f"{part_id}.{THUMB_EXT}").is_file()
               for level in LEVELS)


def _write_tiles(out: Path, part_id: str, drawn: Image.Image) -> None:
    for level in LEVELS:
        path = out / str(level) / f"{part_id}.{THUMB_EXT}"
        path.parent.mkdir(parents=True, exist_ok=True)
        _square(drawn, level).save(path, **THUMB_SAVE)


@contextmanager
def _sheets_locked(out: Path):
    """One writer of a slot's sheets at a time: a bake composing while a
    redraw patches would otherwise publish a sheet without the patch."""
    out.mkdir(parents=True, exist_ok=True)
    with open(out / _LOCK, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _save_atomic(img: Image.Image, path: Path, **save) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    img.save(tmp, **save)
    os.replace(tmp, path)


def _next_version(previous) -> str:
    """Later than the last one, and never a number a browser may have cached
    from a slot since wiped: seconds since the epoch, or one past the last."""
    try:
        last = int(previous)
    except (TypeError, ValueError):
        last = 0
    return str(max(last + 1, int(time.time())))


def _tile(out: Path, level: int, part_id: str) -> Image.Image | None:
    path = out / str(level) / f"{part_id}.{THUMB_EXT}"
    if not path.is_file():
        return None
    with Image.open(path) as img:
        return img.convert("RGBA")


def _paste_cell(sheet: Image.Image, g: Geometry, index: int,
                cell: Image.Image | None) -> None:
    """The cell and its gutter, drawn from `cell`, or cleared without one."""
    x0, y0, x1, y1 = g.cell_box(index)
    if cell is None:
        sheet.paste((0, 0, 0, 0), (x0 - g.gutter, y0 - g.gutter,
                                   x1 + g.gutter, y1 + g.gutter))
        return
    sheet.paste(cell, (x0, y0))
    if g.gutter:
        _replicate_edges(sheet, cell, x0, y0, g.gutter)


def _publish(out: Path, level: int, sheet: Image.Image, manifest: dict) -> str:
    """Master, WebP, then manifest, each whole or not at all. The manifest
    goes last: it names the version a reader fetches the image under."""
    path = out / f"sheet-{level}.json"
    version = _next_version(_read_json(path).get("version"))
    _save_atomic(sheet, out / MASTER.format(level=level), **MASTER_SAVE)
    _save_atomic(sheet, out / f"sheet-{level}.{THUMB_EXT}", **THUMB_SAVE)
    _write_json(path, {**manifest, "version": version})
    return version


def has_sheets(out: Path | str) -> bool:
    return all((Path(out) / f"sheet-{level}.json").is_file()
               for level in SHEET_LEVELS)


def compose(out: Path | str, order: list[str]) -> list[Path]:
    """Paste every baked thumbnail onto its sheet, in `order`'s index order.

    `order` is every part, not only the drawn ones: an index is a position in
    the corpus, so a part gaining a render later fills the cell it already had.
    """
    out = Path(out)
    written = []
    with _sheets_locked(out):
        shas = baked_shas(out)
        for level in SHEET_LEVELS:
            g = geometry(len(order), level)
            sheet = Image.new("RGBA", (g.size, g.size), (0, 0, 0, 0))
            for index, part_id in enumerate(order):
                cell = _tile(out, level, part_id)
                if cell is not None:
                    _paste_cell(sheet, g, index, cell)
            _publish(out, level, sheet, {
                "level": level, "gutter": g.gutter, "pitch": g.pitch,
                "cols": g.cols, "rows": g.rows, "count": len(order),
                "size": g.size, "baked": shas})
            written.append(out / f"sheet-{level}.{THUMB_EXT}")
    return written


def patch_cell(out: Path | str, part_id: str, index: int,
               count: int) -> dict[int, str]:
    """Redraw one part's cell on every sheet from its baked tiles, as
    `compose` would draw it, and nothing else. Returns each level's new
    version.

    `count` is the corpus size now. A sheet baked for another count has every
    index after the change shifted, so it is refused rather than patched.
    """
    out = Path(out)
    versions = {}
    with _sheets_locked(out):
        # Every level is checked before any is touched: catching a mismatch
        # on a later level after an earlier one has already published would
        # leave "refused" meaning some levels changed and some didn't.
        manifests = {}
        for level in SHEET_LEVELS:
            manifest = _read_json(out / f"sheet-{level}.json")
            if manifest.get("count") != count:
                raise ValueError(
                    f"{out}/sheet-{level} holds {manifest.get('count')} cells "
                    f"and the corpus {count}; rebake the slot")
            master = out / MASTER.format(level=level)
            if not master.is_file():
                raise FileNotFoundError(f"{master} is missing; rebake the slot")
            manifests[level] = manifest
        shas = baked_shas(out)
        for level in SHEET_LEVELS:
            manifest = manifests[level]
            with Image.open(out / MASTER.format(level=level)) as img:
                sheet = img.convert("RGBA")
            _paste_cell(sheet, geometry(count, level), index,
                        _tile(out, level, part_id))
            baked = {k: v for k, v in manifest.get("baked", {}).items()
                     if k != part_id}
            if part_id in shas:
                baked[part_id] = shas[part_id]
            versions[level] = _publish(out, level, sheet,
                                       {**manifest, "baked": baked})
    return versions


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


def _square(drawn: Image.Image, level: int) -> Image.Image:
    """Fit a render inside a `GROUND` square of `level` px.

    A never-baked cell is told apart by the manifest's `baked` map, not by
    alpha -- `isStale` in lab/src/corpus/sheet.ts compares shas, and a cell
    missing from that map never reaches the blit.
    """
    scale = level / max(drawn.size)
    size = (max(1, round(drawn.width * scale)), max(1, round(drawn.height * scale)))
    cell = Image.new("RGBA", (level, level), GROUND)
    fitted = drawn.resize(size, Image.LANCZOS)
    cell.paste(fitted, ((level - size[0]) // 2, (level - size[1]) // 2), fitted)
    return cell
