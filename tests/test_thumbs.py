"""Thumbnail baking: geometry, freshness, sheets."""
import json
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
    # ldview writes WebP, and resvg reads SVG only -- it fails on a raster with
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
