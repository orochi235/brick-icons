import numpy as np
from PIL import Image

from brick_icons.lab import diff


def _img(fill=255, boxes=()):
    a = np.full((64, 64), fill, np.uint8)
    for x0, y0, x1, y1 in boxes:
        a[y0:y1, x0:x1] = 0
    return Image.fromarray(a, "L")


def test_identical_images_have_no_components():
    r = diff.compare(_img(), _img())
    assert r["components"] == 0
    assert r["pixels"] == 0


def test_one_block_is_one_component():
    r = diff.compare(_img(), _img(boxes=[(10, 10, 20, 20)]))
    assert r["components"] == 1
    assert r["pixels"] == 100


def test_two_separated_blocks_are_two_components():
    r = diff.compare(_img(), _img(boxes=[(2, 2, 8, 8), (40, 40, 48, 48)]))
    assert r["components"] == 2


def test_component_sizes_are_reported_largest_first():
    r = diff.compare(_img(), _img(boxes=[(2, 2, 6, 6), (30, 30, 42, 42)]))
    assert r["sizes"] == [144, 16]


def test_speckle_below_the_floor_is_not_counted():
    """One stray pixel is antialias, not a defect."""
    r = diff.compare(_img(), _img(boxes=[(5, 5, 6, 6)]), min_size=4)
    assert r["components"] == 0


def test_sizes_are_capped_so_a_fringe_cannot_flood_the_response():
    boxes = [(2 * i, 2 * i, 2 * i + 1, 2 * i + 1) for i in range(30)]
    r = diff.compare(_img(), _img(boxes=boxes), min_size=1, max_listed=10)
    assert len(r["sizes"]) == 10
    assert r["components"] == 30


def test_mismatched_sizes_are_an_error():
    import pytest
    small = Image.fromarray(np.full((8, 8), 255, np.uint8), "L")
    with pytest.raises(ValueError):
        diff.compare(_img(), small)


def test_writes_a_visualisation(tmp_path):
    out = tmp_path / "d.png"
    diff.compare(_img(), _img(boxes=[(10, 10, 20, 20)]), out_png=out)
    assert out.exists()


def test_rasterize_writes_a_png(tmp_path):
    svg = tmp_path / "a.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
                   '<rect x="2" y="2" width="6" height="6" fill="black"/></svg>')
    out = tmp_path / "a.png"
    assert diff.rasterize(svg, out, width=64) == out
    assert out.exists()
    assert Image.open(out).size[0] == 64


def test_rasterize_is_skipped_when_the_png_is_current(tmp_path):
    svg = tmp_path / "a.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"/>')
    out = tmp_path / "a.png"
    diff.rasterize(svg, out, width=32)
    first = out.stat().st_mtime_ns
    diff.rasterize(svg, out, width=32)
    assert out.stat().st_mtime_ns == first


def test_rasterize_reports_a_bad_svg(tmp_path):
    import pytest
    bad = tmp_path / "bad.svg"
    bad.write_text("not an svg at all")
    with pytest.raises(RuntimeError):
        diff.rasterize(bad, tmp_path / "bad.png", width=32)


def test_as_raster_passes_a_png_through(tmp_path):
    png = tmp_path / "a.png"
    Image.new("L", (8, 8), 255).save(png)
    assert diff.as_raster(png, tmp_path, width=64) == png


def test_as_raster_rasterizes_an_svg_beside_it(tmp_path):
    svg = tmp_path / "a.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
                   '<rect width="10" height="10" fill="black"/></svg>')
    got = diff.as_raster(svg, tmp_path, width=48)
    assert got.suffix == ".png"
    assert got.exists()
