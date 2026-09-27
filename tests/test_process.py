import numpy as np
import pytest
from PIL import Image
from brick_icons import process


def test_to_grayscale_flattens_onto_white(half_transparent_rgba):
    g = process.to_grayscale(half_transparent_rgba)
    assert g.mode == "L"
    a = np.asarray(g)
    assert a[:, :10].mean() < 120     # gray part
    assert a[:, -10:].mean() > 245    # transparent -> white


def test_flatten_rgb_keeps_color():
    arr = np.zeros((10, 10, 4), np.uint8)
    arr[:, :, 0] = 200; arr[:, :, 3] = 255   # opaque red
    rgb = process.flatten_rgb(Image.fromarray(arr, "RGBA"))
    assert rgb.mode == "RGB"
    assert np.asarray(rgb)[..., 0].mean() > 150


def test_apply_levels_increases_contrast(gradient_rgba):
    g = process.to_grayscale(gradient_rgba)
    out = process.apply_levels(g, 64, 192, 1.0)
    a = np.asarray(out)
    assert a.min() == 0 and a.max() == 255


def test_posterize_reduces_unique_levels(gradient_rgba):
    g = process.to_grayscale(gradient_rgba)
    out = process.posterize(g, 4)
    assert len(set(np.unique(out).tolist())) <= 4


def test_posterize_rounds_odd_divisors():
    import numpy as np
    from PIL import Image
    g = Image.fromarray(np.full((4, 4), 128, np.uint8), "L")
    # levels=3 -> bands at 0, 127.5->128, 255; the 128 input maps to the 128 band
    out = np.asarray(process.posterize(g, 3))
    assert set(np.unique(out).tolist()) <= {0, 128, 255}
    assert (out == 128).all()


def test_fit_contain_centers_and_scales(half_transparent_rgba):
    g = process.to_grayscale(half_transparent_rgba)
    out = process.fit_contain(g, 100, 40, margin=5, scale=1.0)
    assert out.size == (100, 40)
    a = np.asarray(out)
    assert a[0, 0] == 255 and a[-1, -1] == 255
    small = process.fit_contain(g, 100, 100, margin=0, scale=0.5)
    assert (np.asarray(small) < 250).sum() < (np.asarray(process.fit_contain(g, 100, 100, margin=0, scale=1.0)) < 250).sum()


def _arr1(img):
    assert img.mode == "1"
    return np.asarray(img.convert("L"))


def test_threshold_pure_bw(gradient_rgba):
    g = process.to_grayscale(gradient_rgba)
    a = _arr1(process.dither(g, "threshold", 128))
    assert set(np.unique(a).tolist()) <= {0, 255}
    assert a[:, 0].mean() == 0 and a[:, -1].mean() == 255


@pytest.mark.parametrize("algo", ["floyd", "ordered", "atkinson"])
def test_dithers_preserve_mean(gradient_rgba, algo):
    g = process.to_grayscale(gradient_rgba)
    a = _arr1(process.dither(g, algo))
    assert set(np.unique(a).tolist()) <= {0, 255}
    assert abs(a.mean() / 255 - np.asarray(g).mean() / 255) < 0.08


def test_unknown_algo_raises(gradient_rgba):
    with pytest.raises(ValueError):
        process.dither(process.to_grayscale(gradient_rgba), "nope")


def test_draw_segments_black_on_white_sized():
    segs = [(10.0, 10.0, 90.0, 10.0, "edge"), (10.0, 10.0, 10.0, 90.0, "sil")]
    img = process.draw_segments(segs, 100, 100, line_px=2, sil_px=4)
    assert img.size == (100, 100) and img.mode == "L"
    a = np.asarray(img)
    assert (a == 0).any() and a.mean() > 200


def test_draw_segments_width_thickens():
    segs = [(10.0, 50.0, 90.0, 50.0, "edge")]
    thin = (np.asarray(process.draw_segments(segs, 100, 100, 1, 1)) < 128).sum()
    thick = (np.asarray(process.draw_segments(segs, 100, 100, 6, 1)) < 128).sum()
    assert thick > thin


def test_segments_mono_is_1bit():
    segs = [(10.0, 50.0, 90.0, 50.0, "edge")]
    m = process.segments_mono(segs, 100, 100, line_px=2, sil_px=3)
    assert m.mode == "1"


def test_draw_segments_renders_arc_nonblank():
    from brick_icons import process
    import numpy as np
    ops = [("arc", 50.0, 50.0, 40.0, 0.0, 0.0, 40.0, 0.0, 360.0, "edge")]
    img = process.draw_segments(ops, 100, 100)
    assert np.asarray(img).min() < 128


def test_draw_segments_contour_fills_corner_notch():
    # butt-capped strokes meeting at a corner leave the outer wedge unfilled;
    # the contour's band, filled, seals it
    from shapely.geometry import Polygon
    segs = [(50.0, 80.0, 10.0, 10.0, "sil"), (50.0, 80.0, 90.0, 10.0, "sil")]
    band = process.contour_band(Polygon([(10, 10), (90, 10), (50, 80)]),
                                6, 6)
    no = process.draw_segments(segs, 100, 100, sil_px=6)
    yes = process.draw_segments(segs, 100, 100, sil_px=6, contour_band=band)
    assert no.getpixel((50, 82)) > 200          # notch below the apex
    assert yes.getpixel((50, 82)) < 100         # sealed by the contour


def test_contour_band_sits_flush_with_the_stroke_inside():
    # inner edge at half the line weight in, all the rest outward
    from shapely.geometry import Point, box
    band = process.contour_band(box(0, 0, 100, 100), line_px=2, sil_px=4)
    assert band.area == pytest.approx(4 * 100 * 4, rel=0.03)
    assert band.contains(Point(50, 1.1)) is False    # past w/2 inside
    assert band.contains(Point(50, 0.9))
    assert band.contains(Point(50, -2.9))            # sil - w/2 outside
    assert not band.contains(Point(50, -3.1))


def test_contour_band_takes_the_stud_tier_along_a_stud():
    from shapely.geometry import Point, box
    studs = process.StudTier(box(40, -5, 60, 5), 1.0)
    band = process.contour_band(box(0, 0, 100, 100), 2, 4, studs)
    assert not band.contains(Point(50, 0.6))         # stud: 0.5 in
    assert band.contains(Point(50, -3.4))            # ...and 3.5 out
    assert band.contains(Point(20, 0.9))             # edge: 1 in
    assert not band.contains(Point(20, -3.2))        # ...and 3 out
    assert not band.contains(Point(38, -3.2))        # steps where it leaves
    assert process.contour_reach(2, 4, studs) == pytest.approx(3.5)


def test_a_stud_draws_at_the_stud_tier_in_the_png():
    # the gray and mono PNGs (the label) take the same stroke tiers as the
    # SVG, or 3811's 1024 studs at 1024 px draw as one black diamond
    from shapely.geometry import Point
    ring = lambda cx: [("arc", cx, 20.0, 6.0, 0.0, 0.0, 6.0, 0.0, 360.0, "line")]
    ink = lambda img: int((np.asarray(img) < 128).sum())
    studs = process.StudTier(Point(20, 20).buffer(7), 0.8)
    stud = ink(process.draw_segments(ring(20.0), 80, 40, line_px=3, studs=studs))
    other = ink(process.draw_segments(ring(60.0), 80, 40, line_px=3, studs=studs))
    assert stud < 0.5 * other, (stud, other)


def test_stud_ops_draw_at_their_own_width_after_the_segments():
    blank = np.asarray(process.draw_segments([], 20, 20))
    assert blank.min() == 255
    img = np.asarray(process.draw_segments(
        [], 20, 20, stud_ops=[("line", 2.0, 10.0, 18.0, 10.0, "edge")],
        stud_px=2))
    assert img[10, 10] < 128 and img[3, 10] == 255


def test_a_contour_band_with_a_hole_draws_it_open():
    from shapely.geometry import box
    band = box(2, 2, 28, 28).difference(box(6, 6, 24, 24))
    img = np.asarray(process.draw_segments([], 30, 30, contour_band=band))
    assert img[3, 15] < 128 and img[15, 3] < 128
    assert img[15, 15] == 255
