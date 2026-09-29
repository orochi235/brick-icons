"""Thumbnail baking: geometry, freshness, sheets."""
import json
import os
import re
from pathlib import Path

import pytest
from PIL import Image

from brick_icons import thumbs


def test_levels_are_the_two_sheets_and_the_loose_one():
    assert thumbs.SHEET_LEVELS == (8, 32)
    assert thumbs.LOOSE_LEVEL == 128


def test_the_grid_is_square_enough_to_hold_every_part():
    g = thumbs.geometry(24591, level=32)
    assert g.cols == 157
    assert g.rows == 157
    assert g.cols * g.rows >= 24591


def test_the_coarsest_level_has_no_gutter():
    assert thumbs.geometry(100, level=8).gutter == 0
    assert thumbs.geometry(100, level=32).gutter == 2


def test_pitch_is_the_cell_plus_both_gutters():
    g = thumbs.geometry(100, level=32)
    assert g.pitch == 36
    assert g.size == g.cols * 36


def test_a_cell_lands_row_major_inside_its_gutter():
    g = thumbs.geometry(100, level=32)  # cols == 10
    assert g.cell_box(0) == (2, 2, 34, 34)
    assert g.cell_box(1) == (38, 2, 70, 34)
    assert g.cell_box(10) == (2, 38, 34, 70)


def test_an_index_past_the_grid_is_an_error():
    g = thumbs.geometry(4, level=8)
    with pytest.raises(IndexError):
        g.cell_box(g.cols * g.rows)


def test_the_loose_level_is_not_a_sheet():
    # 128 px is served as loose files. Sheeting it would silently produce a
    # 12800px page nothing asks for.
    with pytest.raises(ValueError):
        thumbs.geometry(100, level=thumbs.LOOSE_LEVEL)


def test_a_square_sheet_never_crops_an_uneven_grid():
    g = thumbs.geometry(82, level=32)   # cols 10, rows 9
    assert (g.cols, g.rows) == (10, 9)
    assert g.size >= g.rows * g.pitch
    assert g.cell_box(81)[3] <= g.size


def test_a_tiny_corpus_still_has_a_grid():
    for count in (0, 1):
        g = thumbs.geometry(count, level=8)
        assert g.cols == 1 and g.rows == 1


SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
       '<rect x="0" y="0" width="256" height="170" fill="black"/></svg>')


def test_it_rasterizes_every_level_for_one_part(tmp_path):
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    made = thumbs.bake_part("3001", svg, out, sha="abc123")
    assert sorted(made) == [8, 32, 128]
    for level in (8, 32, 128):
        with Image.open(out / str(level) / f"3001.{thumbs.THUMB_EXT}") as img:
            assert img.size == (level, level)


def test_a_wide_render_is_padded_square_not_stretched(tmp_path):
    # Every stored render is 256x170. resvg cannot letterbox, so squaring is
    # this module's job -- and stretching would make every part the wrong shape.
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    thumbs.bake_part("3001", svg, out, sha="abc123")
    with Image.open(out / "128" / f"3001.{thumbs.THUMB_EXT}") as img:
        assert img.size == (128, 128)
        assert img.getpixel((2, 2)) == (0, 0, 0, 0)  # letterbox, not ink


def test_a_baked_cell_carries_ink_and_no_ground(tmp_path):
    # The wall paints the ground under every rung. Baking one made the sheet,
    # the loose PNG and the live SVG disagree, and a cell changed shade on the
    # wheel notch that crossed between them.
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    thumbs.bake_part("3001", svg, out, sha="abc123")
    with Image.open(out / "128" / f"3001.{thumbs.THUMB_EXT}") as img:
        rgba = img.convert("RGBA")
        assert rgba.getpixel((2, 2))[3] == 0        # letterbox is clear
        assert rgba.getpixel((64, 64))[3] == 255    # ink is not


def test_it_bakes_a_raster_slot_without_going_near_resvg(tmp_path):
    # the reference slot writes WebP, and resvg reads SVG only -- it fails on a raster with
    # "provided data has not an UTF-8 encoding", which reads like a corrupt
    # file rather than the wrong kind of one.
    src = tmp_path / "3001.webp"
    Image.new("RGBA", (256, 170), (0, 0, 0, 255)).save(src, "WEBP")
    out = tmp_path / "thumbs"
    assert sorted(thumbs.bake_part("3001", src, out, sha="abc123")) == [8, 32, 128]
    with Image.open(out / "128" / f"3001.{thumbs.THUMB_EXT}") as img:
        assert img.size == (128, 128)
        assert img.convert("RGBA").getpixel((2, 2))[3] == 0     # letterboxed
        assert img.convert("RGBA").getpixel((64, 64))[3] == 255  # ink


def test_it_skips_a_part_whose_sha_is_unchanged(tmp_path):
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    thumbs.bake_part("3001", svg, out, sha="abc123")
    assert thumbs.bake_part("3001", svg, out, sha="abc123") == []
    assert thumbs.bake_part("3001", svg, out, sha="different") != []


def test_the_baked_sha_is_readable_back(tmp_path):
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    thumbs.bake_part("3001", svg, out, sha="abc123")
    assert thumbs.baked_shas(out) == {"3001": "abc123"}


def _baked(tmp_path, ids):
    svg = tmp_path / "src.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    for pid in ids:
        thumbs.bake_part(pid, svg, out, sha=f"sha-{pid}")
    return out


def test_the_sheet_is_one_page_sized_from_the_part_count(tmp_path):
    out = _baked(tmp_path, ["a", "b", "c"])
    thumbs.compose(out, order=["a", "b", "c", "d"])
    for level in (8, 32):
        g = thumbs.geometry(4, level)
        with Image.open(out / f"sheet-{level}.{thumbs.THUMB_EXT}") as img:
            assert img.size == (g.size, g.size)


def test_the_manifest_names_the_geometry_and_what_is_baked(tmp_path):
    out = _baked(tmp_path, ["a", "c"])
    thumbs.compose(out, order=["a", "b", "c", "d"])
    m = json.loads((out / "sheet-32.json").read_text())
    assert m["level"] == 32 and m["gutter"] == 2 and m["pitch"] == 36
    assert m["cols"] == 2 and m["count"] == 4
    assert m["baked"] == {"a": "sha-a", "c": "sha-c"}


def test_a_part_with_no_thumbnail_leaves_its_cell_empty(tmp_path):
    out = _baked(tmp_path, ["a"])
    thumbs.compose(out, order=["a", "b"])
    g = thumbs.geometry(2, 32)
    with Image.open(out / f"sheet-32.{thumbs.THUMB_EXT}") as img:
        assert img.crop(g.cell_box(0)).getextrema()[3][1] > 0   # a is drawn
        assert img.crop(g.cell_box(1)).getextrema()[3][1] == 0  # b is empty


def test_the_gutter_replicates_the_cell_edge(tmp_path):
    out = _baked(tmp_path, ["a"])
    thumbs.compose(out, order=["a", "b"])
    with Image.open(out / f"sheet-32.{thumbs.THUMB_EXT}") as img:
        x0, y0, _, _ = thumbs.geometry(2, 32).cell_box(0)
        assert img.getpixel((x0 - 1, y0)) == img.getpixel((x0, y0))


def test_no_ground_is_baked_in_either_language():
    """The wall owns the ground; the bake owns the ink.

    Reintroducing a baked ground on one side only is what made a cell change
    shade mid-zoom, and the two sides are set in different languages, so
    neither is free to grow one back alone.
    """
    assert thumbs.GROUND == (0, 0, 0, 0)
    paint = (Path(__file__).resolve().parent.parent
             / "lab" / "src" / "corpus" / "paint.ts").read_text()
    assert "THUMB_GROUND" not in paint, "paint.ts grew a baked-ground constant back"
    assert re.search(r"export function thumbGround\(\)", paint), \
        "paint.ts no longer declares thumbGround()"


def test_a_truncated_sidecar_is_a_cache_miss_not_a_crash(tmp_path):
    """Two bakes overlapping leaves a reader an empty baked.json, and every
    later bake died on it -- the sheets stop updating while the database
    keeps saying they are current."""
    (tmp_path / thumbs.BAKED).write_text("")
    assert thumbs.baked_shas(tmp_path) == {}
    (tmp_path / thumbs.BAKED).write_text("{oh no")
    assert thumbs.baked_shas(tmp_path) == {}


def test_a_sidecar_is_written_whole_or_not_at_all(tmp_path):
    thumbs._write_json(tmp_path / "x.json", {"a": "1"})
    assert json.loads((tmp_path / "x.json").read_text()) == {"a": "1"}
    # nothing left behind to be mistaken for a slot's own file
    assert not list(tmp_path.glob("*.tmp"))


def test_a_tile_write_goes_through_a_temp_file_then_replace(tmp_path, monkeypatch):
    """A background patch_cell can read a tile while bake_part writes it; the
    write must land as temp-file-then-replace, like every other sheet write
    in this module, or that reader can see a half-written file."""
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"

    replaced = []
    real_replace = os.replace

    def spy(src, dst):
        assert Path(src).name.endswith(".tmp"), src
        assert Path(src).is_file()
        replaced.append(Path(dst))
        real_replace(src, dst)

    monkeypatch.setattr(thumbs.os, "replace", spy)
    thumbs.bake_part("3001", svg, out, sha="abc123")

    tile_paths = {out / str(level) / f"3001.{thumbs.THUMB_EXT}"
                  for level in thumbs.LEVELS}
    assert tile_paths <= set(replaced)
    for level in thumbs.LEVELS:
        assert not list((out / str(level)).glob(".*.tmp")), level
    with Image.open(out / "128" / f"3001.{thumbs.THUMB_EXT}") as img:
        assert img.size == (128, 128)
        assert img.convert("RGBA").getpixel((64, 64))[3] == 255  # ink survives


def test_a_format_change_rebakes_rather_than_composing_missing_tiles(tmp_path,
                                                                    monkeypatch):
    """An unchanged sha must not skip a part whose tiles are in the old format.

    `baked.json` records the render's sha and says nothing about how the tile
    was encoded, so without this the first run after a THUMB_EXT change skips
    everything and `compose` builds an empty sheet.
    """
    out = tmp_path / "slot"
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    assert thumbs.bake_part("3001", svg, out, sha="abc") == list(thumbs.LEVELS)
    assert thumbs.bake_part("3001", svg, out, sha="abc") == []

    monkeypatch.setattr(thumbs, "THUMB_EXT", "png")
    monkeypatch.setattr(thumbs, "THUMB_SAVE", {"format": "PNG"})
    assert thumbs.bake_part("3001", svg, out, sha="abc") == list(thumbs.LEVELS)
    for level in thumbs.LEVELS:
        assert (out / str(level) / "3001.png").is_file()


MARKED = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170" '
          'data-marks="deco"><g stroke-linejoin="round">'
          '<path d="M0 0H128V170H0Z" fill="#858585"/>'
          '<path d="M128 0H256V170H128Z" class="deco" fill="#b40000"/></g></svg>')


def test_a_marked_render_bakes_a_mask_beside_its_drawing(tmp_path):
    svg = tmp_path / "3001p01.svg"
    svg.write_text(MARKED)
    out = tmp_path / "thumbs"
    thumbs.bake_part("3001p01", svg, out, sha="s1")
    masks = out / thumbs.MASK_DIR
    assert thumbs.baked_shas(masks) == {"3001p01": "s1"}
    with Image.open(masks / "128" / f"3001p01.{thumbs.THUMB_EXT}") as img:
        rgba = img.convert("RGBA")
    # the 256x170 render sits centered in the 128 square: left half body, right half print
    y = 64
    assert rgba.getpixel((20, y))[:3] < (30, 30, 30)
    assert rgba.getpixel((108, y))[:3] > (225, 225, 225)


def test_an_unmarked_render_bakes_no_mask(tmp_path):
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    thumbs.bake_part("3001", svg, out, sha="s1")
    assert thumbs.baked_shas(out / thumbs.MASK_DIR) == {}


def test_a_marked_part_missing_its_mask_is_rebaked(tmp_path):
    svg = tmp_path / "3001p01.svg"
    svg.write_text(MARKED)
    out = tmp_path / "thumbs"
    thumbs.bake_part("3001p01", svg, out, sha="s1")
    (out / thumbs.MASK_DIR / "32" / f"3001p01.{thumbs.THUMB_EXT}").unlink()
    assert thumbs.bake_part("3001p01", svg, out, sha="s1") == [8, 32, 128]


def test_a_redraw_without_marks_drops_the_old_mask(tmp_path):
    svg = tmp_path / "3001p01.svg"
    svg.write_text(MARKED)
    out = tmp_path / "thumbs"
    thumbs.bake_part("3001p01", svg, out, sha="s1")
    svg.write_text(SVG)
    thumbs.bake_part("3001p01", svg, out, sha="s2")
    masks = out / thumbs.MASK_DIR
    assert thumbs.baked_shas(masks) == {}
    assert not (masks / "128" / f"3001p01.{thumbs.THUMB_EXT}").exists()


import shutil
import threading
import time

import numpy as np

DISC = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
        '<circle cx="128" cy="85" r="60" fill="black"/></svg>')
ORDER = ["a", "b", "c", "d", "e"]


def _baked_slot(tmp_path):
    out = tmp_path / "slot"
    svg = tmp_path / "rect.svg"
    svg.write_text(SVG)
    for pid in ORDER:
        thumbs.bake_part(pid, svg, out, sha=f"old-{pid}")
    thumbs.compose(out, ORDER)
    return out


def _master(out, level):
    with Image.open(out / f"sheet-{level}.master.png") as img:
        return np.asarray(img.convert("RGBA"))


def _redraw_c(tmp_path, out):
    disc = tmp_path / "disc.svg"
    disc.write_text(DISC)
    thumbs.bake_part("c", disc, out, sha="new-c")


def test_a_patched_cell_is_what_a_full_compose_would_draw(tmp_path):
    out = _baked_slot(tmp_path)
    before = {lvl: _master(out, lvl) for lvl in thumbs.SHEET_LEVELS}
    _redraw_c(tmp_path, out)

    thumbs.patch_cell(out, "c", ORDER.index("c"), len(ORDER))

    oracle = tmp_path / "oracle"
    shutil.copytree(out, oracle)
    thumbs.compose(oracle, ORDER)
    for lvl in thumbs.SHEET_LEVELS:
        after = _master(out, lvl)
        assert np.array_equal(after, _master(oracle, lvl)), lvl
        g = thumbs.geometry(len(ORDER), lvl)
        x0, y0, x1, y1 = g.cell_box(ORDER.index("c"))
        ys, xs = np.nonzero((after != before[lvl]).any(axis=2))
        assert len(xs) > 0, lvl
        assert xs.min() >= x0 - g.gutter and xs.max() < x1 + g.gutter, lvl
        assert ys.min() >= y0 - g.gutter and ys.max() < y1 + g.gutter, lvl


def test_a_patch_records_the_new_sha_and_a_new_version(tmp_path):
    out = _baked_slot(tmp_path)
    was = json.loads((out / "sheet-32.json").read_text())
    _redraw_c(tmp_path, out)
    versions = thumbs.patch_cell(out, "c", 2, len(ORDER))
    now = json.loads((out / "sheet-32.json").read_text())
    assert now["baked"]["c"] == "new-c"
    assert now["baked"]["a"] == "old-a"
    assert int(now["version"]) > int(was["version"])
    assert versions == {8: json.loads((out / "sheet-8.json").read_text())["version"],
                        32: now["version"]}


def test_two_writes_in_one_second_get_two_versions(tmp_path):
    out = _baked_slot(tmp_path)
    first = json.loads((out / "sheet-8.json").read_text())["version"]
    thumbs.compose(out, ORDER)
    second = json.loads((out / "sheet-8.json").read_text())["version"]
    assert int(second) > int(first)


def test_a_fresh_slot_starts_its_version_at_the_clock(tmp_path):
    before = int(time.time())
    out = _baked_slot(tmp_path)
    assert int(json.loads((out / "sheet-8.json").read_text())["version"]) >= before


def test_a_patch_refuses_a_sheet_baked_for_another_part_count(tmp_path):
    out = _baked_slot(tmp_path)
    with pytest.raises(ValueError, match="rebake"):
        thumbs.patch_cell(out, "c", 2, len(ORDER) + 1)


def test_a_patch_refuses_a_slot_with_no_master(tmp_path):
    out = _baked_slot(tmp_path)
    (out / "sheet-32.master.png").unlink()
    with pytest.raises(FileNotFoundError, match="rebake"):
        thumbs.patch_cell(out, "c", 2, len(ORDER))


def test_a_patch_checks_every_level_before_patching_any(tmp_path):
    out = _baked_slot(tmp_path)
    manifest = json.loads((out / "sheet-32.json").read_text())
    manifest["count"] = manifest["count"] + 1
    (out / "sheet-32.json").write_text(json.dumps(manifest))
    before_master = (out / "sheet-8.master.png").read_bytes()
    before_webp = (out / f"sheet-8.{thumbs.THUMB_EXT}").read_bytes()
    before_version = json.loads((out / "sheet-8.json").read_text())["version"]
    _redraw_c(tmp_path, out)

    with pytest.raises(ValueError, match="rebake"):
        thumbs.patch_cell(out, "c", 2, len(ORDER))

    assert (out / "sheet-8.master.png").read_bytes() == before_master
    assert (out / f"sheet-8.{thumbs.THUMB_EXT}").read_bytes() == before_webp
    assert json.loads((out / "sheet-8.json").read_text())["version"] == before_version


def test_a_cell_with_no_tile_is_cleared(tmp_path):
    out = _baked_slot(tmp_path)
    for lvl in thumbs.LEVELS:
        (out / str(lvl) / f"c.{thumbs.THUMB_EXT}").unlink()
    thumbs.patch_cell(out, "c", 2, len(ORDER))
    g = thumbs.geometry(len(ORDER), 32)
    x0, y0, x1, y1 = g.cell_box(2)
    assert not _master(out, 32)[y0:y1, x0:x1].any()


def test_has_sheets_says_whether_a_slot_was_composed(tmp_path):
    assert not thumbs.has_sheets(tmp_path / "slot")
    assert thumbs.has_sheets(_baked_slot(tmp_path))


def test_two_interleaved_bakes_keep_both_entries(tmp_path, slow_counted):
    # A lab redraw and the watcher's bake-thumbs.py are separate processes on
    # the same slot; slowing tile-writing forces both to read baked.json
    # before either has written its own entry.
    svg = tmp_path / "rect.svg"
    svg.write_text(SVG)
    out = tmp_path / "slot"
    slow_counted(thumbs, "_write_tiles")
    gate = threading.Barrier(2)

    def one(part_id):
        gate.wait()
        thumbs.bake_part(part_id, svg, out, sha=f"sha-{part_id}")
    threads = [threading.Thread(target=one, args=(p,)) for p in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert thumbs.baked_shas(out) == {"a": "sha-a", "b": "sha-b"}
