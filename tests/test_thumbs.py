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
        with Image.open(out / str(level) / "3001.png") as img:
            assert img.size == (level, level)


def test_a_wide_render_is_padded_square_not_stretched(tmp_path):
    # Every stored render is 256x170. resvg cannot letterbox, so squaring is
    # this module's job -- and stretching would make every part the wrong shape.
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    thumbs.bake_part("3001", svg, out, sha="abc123")
    with Image.open(out / "128" / "3001.png") as img:
        assert img.size == (128, 128)
        assert img.getpixel((2, 2)) == (255, 255, 255, 255)


def test_a_baked_cell_is_opaque_so_the_ink_is_visible(tmp_path):
    # Renders are black ink on transparency and the lab's surface follows the
    # weasel theme, so a transparent thumbnail disappears in dark mode.
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    thumbs.bake_part("3001", svg, out, sha="abc123")
    with Image.open(out / "8" / "3001.png") as img:
        assert img.convert("RGBA").getextrema()[3] == (255, 255)


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
        with Image.open(out / f"sheet-{level}.png") as img:
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
    with Image.open(out / "sheet-32.png") as img:
        assert img.crop(g.cell_box(0)).getextrema()[3][1] > 0   # a is drawn
        assert img.crop(g.cell_box(1)).getextrema()[3][1] == 0  # b is empty


def test_the_gutter_replicates_the_cell_edge(tmp_path):
    out = _baked(tmp_path, ["a"])
    thumbs.compose(out, order=["a", "b"])
    with Image.open(out / "sheet-32.png") as img:
        x0, y0, _, _ = thumbs.geometry(2, 32).cell_box(0)
        assert img.getpixel((x0 - 1, y0)) == img.getpixel((x0, y0))


def test_the_wall_grounds_its_vector_cells_on_what_the_bake_used():
    """The two grounds are set in different languages and must not drift.

    The vector rung draws the SVG straight, so a cell zoomed past the loose
    PNG shows this ground where the bake showed its own -- any mismatch reads
    as the background changing color mid-zoom.
    """
    paint = (Path(__file__).resolve().parent.parent
             / "lab" / "src" / "corpus" / "paint.ts").read_text()
    def declared(name):
        m = re.search(name + r" = '(#[0-9a-fA-F]{6})'", paint)
        assert m, f"paint.ts no longer declares {name}"
        hexed = m.group(1)
        return tuple(int(hexed[i:i + 2], 16) for i in (1, 3, 5)) + (255,)

    assert declared("THUMB_GROUND") == thumbs.GROUND
    assert declared("RETIRED_GROUND") == thumbs.RETIRED_GROUND


def test_a_retired_part_bakes_onto_its_own_ground(tmp_path):
    svg = tmp_path / "3001.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
                   '<rect x="0" y="0" width="10" height="10"/></svg>')
    out = tmp_path / "slot"
    thumbs.bake_part("3001", svg, out, sha="abc", ground=thumbs.RETIRED_GROUND)
    with Image.open(out / "128" / "3001.png") as img:
        assert img.convert("RGBA").getpixel((2, 126)) == thumbs.RETIRED_GROUND


def test_changing_the_ground_rebakes_a_part_the_sha_says_is_fresh(tmp_path):
    svg = tmp_path / "3001.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
                   '<rect x="0" y="0" width="10" height="10"/></svg>')
    out = tmp_path / "slot"
    assert thumbs.bake_part("3001", svg, out, sha="abc")
    assert thumbs.bake_part("3001", svg, out, sha="abc") == []
    assert thumbs.bake_part("3001", svg, out, sha="abc",
                            ground=thumbs.RETIRED_GROUND)
    with Image.open(out / "128" / "3001.png") as img:
        assert img.convert("RGBA").getpixel((2, 126)) == thumbs.RETIRED_GROUND


def test_a_bake_from_before_grounds_were_recorded_stays_fresh(tmp_path):
    svg = tmp_path / "3001.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
                   '<rect x="0" y="0" width="10" height="10"/></svg>')
    out = tmp_path / "slot"
    thumbs.bake_part("3001", svg, out, sha="abc")
    (out / thumbs.GROUNDS).unlink()
    assert thumbs.bake_part("3001", svg, out, sha="abc") == []
