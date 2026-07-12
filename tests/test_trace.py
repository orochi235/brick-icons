import re
import shutil
import numpy as np
import pytest
from PIL import Image
from brick_icons import trace, process

HAVE_POTRACE = shutil.which("potrace") is not None
pytestmark = pytest.mark.skipif(not HAVE_POTRACE, reason="potrace not installed")


def _disc():
    yy, xx = np.mgrid[0:120, 0:120]
    m = (xx - 60) ** 2 + (yy - 60) ** 2 <= 50 ** 2
    a = np.zeros((120, 120, 4), np.uint8)
    a[m, :3] = 110; a[m, 3] = 255
    return Image.fromarray(a, "RGBA")


def test_cel_svg_layers_match_bands(tmp_path):
    out = tmp_path / "c.svg"
    # gradient disc so multiple bands exist
    yy, xx = np.mgrid[0:120, 0:120]
    m = (xx - 60) ** 2 + (yy - 60) ** 2 <= 50 ** 2
    a = np.zeros((120, 120, 4), np.uint8)
    a[..., 0] = a[..., 1] = a[..., 2] = np.clip(xx * 2, 0, 255)
    a[m, 3] = 255; a[~m, 3] = 0
    trace.cel_svg(Image.fromarray(a, "RGBA"), out, levels=4)
    txt = out.read_text()
    fills = set(re.findall(r'fill="(#[0-9a-f]{6})"', txt))
    assert len(fills) >= 2          # multiple tonal bands
    assert "<path" in txt


from brick_icons import trace as _trace


def test_segments_to_svg_writes_lines(tmp_path):
    segs = [(10.0, 10.0, 90.0, 10.0, "edge"), (10.0, 10.0, 10.0, 90.0, "sil")]
    out = tmp_path / "s.svg"
    _trace.segments_to_svg(segs, 100, 100, out, line_px=2, sil_px=4)
    txt = out.read_text()
    assert 'viewBox="0 0 100 100"' in txt
    assert txt.count("<line") == 2
    assert 'stroke-width="4.00"' in txt and 'stroke-width="2.00"' in txt



def test_segments_to_svg_part_label(tmp_path):
    # label: fixed small print in the corner — absolute size, NOT scaled to
    # the part; absent entirely unless requested
    segs = [(10.0, 10.0, 90.0, 10.0, "edge")]
    out = _trace.segments_to_svg(segs, 100, 100, tmp_path / "l.svg", label="30136")
    txt = out.read_text()
    assert "<text" in txt and ">30136</text>" in txt
    bare = _trace.segments_to_svg(segs, 100, 100, tmp_path / "b.svg")
    assert "<text" not in bare.read_text()


def test_segments_to_svg_emits_arc_path(tmp_path):
    # parametric arc: center (50,50), u=(40,0), v=(0,30), params 0..90 deg
    ops = [("arc", 50.0, 50.0, 40.0, 0.0, 0.0, 30.0, 0.0, 90.0, "edge")]
    out = _trace.segments_to_svg(ops, 100, 100, tmp_path / "a.svg")
    txt = out.read_text()
    assert "<path" in txt and " A " in txt          # elliptical-arc command


def test_full_ellipse_arc_splits_into_quarter_segments(tmp_path):
    # A 0..360 sweep (e.g. a fully-visible stud top rim). A single SVG arc
    # whose endpoints coincide renders as nothing — and any span near 180 has
    # near-antipodal endpoints, which amplify the 0.01 px coordinate rounding
    # into an O(sqrt(r*eps)) center shift when the renderer re-derives the
    # ellipse center. So full sweeps emit as four <=90 deg sub-arcs.
    ops = [("arc", 50.0, 50.0, 40.0, 0.0, 0.0, 30.0, 0.0, 360.0, "edge")]
    out = _trace.segments_to_svg(ops, 100, 100, tmp_path / "e.svg")
    d = re.search(r'<path d="([^"]+)"', out.read_text()).group(1)
    assert d.count(" A ") == 4                      # quarter sub-arcs
    assert d.count("M ") == 1                        # single subpath
    # every sub-arc spans <= 90, so the large-arc flag is 0 on each
    flags = re.findall(r'A [\d.]+ [\d.]+ [\d.-]+ (\d) \d', d)
    assert flags == ["0", "0", "0", "0"]
    # consecutive arc endpoints differ (a degenerate arc renders nothing)
    pts = re.findall(r'(-?[\d.]+ -?[\d.]+)(?= A|$)', d)
    assert len(set(pts)) >= 4


def test_segments_to_svg_mixed_line_and_legacy(tmp_path):
    ops = [("line", 0.0, 0.0, 10.0, 10.0, "edge"), (1.0, 1.0, 2.0, 2.0, "sil")]
    out = _trace.segments_to_svg(ops, 20, 20, tmp_path / "b.svg")
    assert out.read_text().count("<line") == 2


def test_segments_to_svg_writes_fill_layer(tmp_path):
    segs = [("line", 0.0, 0.0, 10.0, 0.0, "edge")]
    fills = [{"d": "M 0 0 L 10 0 L 0 10 Z", "fill": "#cccccc", "depth": 1.0}]
    out = _trace.segments_to_svg(segs, 20, 20, tmp_path / "f.svg", fills=fills)
    txt = out.read_text()
    # fill layer precedes the stroke group (painter: fills under strokes)
    assert txt.index('fill="#cccccc"') < txt.index('<g stroke="black"')
    # each fill is stroked in its own color to hide antialiasing seams
    assert 'stroke="#cccccc"' in txt


def test_fill_paths_use_evenodd(tmp_path):
    fills = [{"d": "M 0 0 L 10 0 L 10 10 L 0 10 Z M 2 2 L 8 2 L 8 8 L 2 8 Z",
              "fill": "#888888", "depth": 0.0}]
    out = _trace.segments_to_svg([], 20, 20, tmp_path / "eo.svg", fills=fills)
    assert 'fill-rule="evenodd"' in out.read_text()


def test_segments_to_svg_writes_gradient_fill(tmp_path):
    segs = [("line", 0.0, 0.0, 10.0, 0.0, "edge")]
    fills = [{"d": "M 0 0 L 10 0 L 10 10 Z", "depth": 1.0,
              "gradient": {"x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 0.0,
                           "stops": [(0.0, "#333333"), (1.0, "#cccccc")]}}]
    out = _trace.segments_to_svg(segs, 20, 20, tmp_path / "g.svg", fills=fills)
    txt = out.read_text()
    assert "linearGradient" in txt and 'stop-color="#333333"' in txt
    assert "url(#g0)" in txt


def test_segments_to_svg_writes_radial_gradient(tmp_path):
    fills = [{"d": "M 0 0 L 10 0 L 10 10 Z", "depth": 1.0,
              "gradient": {"type": "radial", "cx": 5.0, "cy": 5.0, "r": 4.0,
                           "ratio": 0.8, "fx": -0.2, "fy": -0.25,
                           "stops": [(0.0, "#cccccc"), (1.0, "#333333")]}}]
    out = _trace.segments_to_svg([], 20, 20, tmp_path / "r.svg", fills=fills)
    txt = out.read_text()
    assert "<radialGradient" in txt and "gradientTransform" in txt
    assert 'fx="-0.200"' in txt and "url(#g0)" in txt


def test_svg_background_defaults_transparent(tmp_path):
    segs = [("line", 0.0, 0.0, 10.0, 0.0, "edge")]
    out = _trace.segments_to_svg(segs, 20, 20, tmp_path / "t.svg")
    assert "<rect" not in out.read_text()


def test_svg_background_paint(tmp_path):
    segs = [("line", 0.0, 0.0, 10.0, 0.0, "edge")]
    out = _trace.segments_to_svg(segs, 20, 20, tmp_path / "w.svg", bg="white")
    assert '<rect width="100%" height="100%" fill="white"/>' in out.read_text()


def test_fill_opacity_per_face(tmp_path):
    fills = [{"d": "M 0 0 L 10 0 L 0 10 Z", "fill": "#cccccc", "depth": 1.0},
             {"d": "M 0 0 L 10 0 L 10 10 Z", "fill": "#888888", "depth": 0.5}]
    out = _trace.segments_to_svg([], 20, 20, tmp_path / "o.svg",
                                 fills=fills, opacity=0.5)
    txt = out.read_text()
    # per-path opacity (unculled faces overlap and must blend individually),
    # not group-level; line strokes stay opaque
    assert txt.count('opacity="0.5"') == 2
    assert 'opacity' not in txt.split('<g stroke="black"')[1]


def test_fill_opacity_one_emits_no_attr(tmp_path):
    fills = [{"d": "M 0 0 L 10 0 L 0 10 Z", "fill": "#cccccc", "depth": 1.0}]
    out = _trace.segments_to_svg([], 20, 20, tmp_path / "o1.svg",
                                 fills=fills, opacity=1.0)
    assert "opacity" not in out.read_text()


def test_segments_to_svg_physical_mm(tmp_path):
    segs = [("line", 10.0, 10.0, 90.0, 10.0, "edge")]
    out = _trace.segments_to_svg(
        segs, 100, 100, tmp_path / "p.svg",
        physical=(12.8, 9.6), s=5.0, line_mm=0.2, sil_mm=0.3)
    txt = out.read_text()
    assert 'width="12.80mm"' in txt and 'height="9.60mm"' in txt
    assert 'viewBox="0 0 100 100"' in txt
    # line stroke: 0.2mm / 0.4 * 5.0 = 2.5 px
    assert 'stroke-width="2.50"' in txt


def test_stroke_clip_from_geom(tmp_path):
    # clip_geom: strokes are clipped to the silhouette buffered outward by
    # half the widest stroke, with mitered corners — end caps can no longer
    # poke past outline corners into the background
    from brick_icons import geom2d
    sil = geom2d.to_geom(np.array([(10, 10), (90, 10), (90, 90), (10, 90)], float))
    segs = [(10.0, 10.0, 90.0, 10.0, "edge"), (90.0, 10.0, 90.0, 90.0, "sil")]
    out = tmp_path / "c.svg"
    _trace.segments_to_svg(segs, 100, 100, out, line_px=2, sil_px=4,
                           clip_geom=sil)
    txt = out.read_text()
    assert "<clipPath" in txt and 'clip-path="url(#' in txt
    assert "8.00 8.00" in txt                       # buffered by max(2,4)/2
    # the clip applies to the stroke group, not the fills
    assert re.search(r'<g stroke="black"[^>]*clip-path=', txt)


def test_no_clip_without_geom(tmp_path):
    segs = [(10.0, 10.0, 90.0, 10.0, "edge")]
    out = tmp_path / "n.svg"
    _trace.segments_to_svg(segs, 100, 100, out)
    assert "<clipPath" not in out.read_text()


def test_stroke_clip_covers_arc_bulge(tmp_path):
    # a drawn arc legitimately bulges past the sampled fill polygon (fitted
    # hand-faceted rounds); the clip must grow to cover it, not flatten it
    from brick_icons import geom2d
    sil = geom2d.to_geom(np.array([(10, 10), (90, 10), (90, 90), (10, 90)], float))
    arc = ("arc", 10.0, 50.0, -15.0, 0.0, 0.0, 15.0, -90.0, 90.0, "edge")
    out = tmp_path / "a.svg"
    _trace.segments_to_svg([arc], 100, 100, out, line_px=2, sil_px=2,
                           clip_geom=sil)
    txt = out.read_text()
    clip_d = re.search(r'<clipPath[^>]*><path d="([^"]+)"', txt).group(1)
    xs = [float(v) for v in re.findall(r"[ML] ([-\d.]+)", clip_d)]
    assert min(xs) <= -5.0                 # clip reaches the arc apex (-5,50)


def test_contour_path_drawn_with_miter(tmp_path):
    # the closed silhouette contour draws under the strokes with mitered
    # joins: corners become sharp (a closed path has joins, never caps)
    segs = [(10.0, 10.0, 90.0, 10.0, "sil")]
    out = tmp_path / "m.svg"
    _trace.segments_to_svg(segs, 100, 100, out, line_px=2, sil_px=4,
                           contour_d="M 10 10 L 90 10 L 50 80 Z")
    txt = out.read_text()
    m = re.search(r'<g stroke="black"[^>]*>\s*<path d="M 10 10 L 90 10 L 50 80 Z"[^>]*/>', txt)
    assert m and 'stroke-linejoin="miter"' in m.group(0)
    assert 'stroke-width="4.00"' in m.group(0)


def test_no_contour_by_default(tmp_path):
    out = tmp_path / "p.svg"
    _trace.segments_to_svg([(10.0, 10.0, 90.0, 10.0, "sil")], 100, 100, out)
    assert "miter" not in out.read_text()


def test_substroke_fragments_culled(tmp_path):
    # a visible fragment much shorter than its stroke width renders as a
    # bare round-cap dot (warts at technic-hole crescent tips) — drop it
    segs = [(10.0, 10.0, 10.07, 10.03, "sil"),          # 0.08 px: dot
            (20.0, 20.0, 80.0, 20.0, "edge"),           # real line
            ("arc", 50.0, 50.0, 9.0, 0.0, 0.0, 9.0, 0.0, 2.0, "edge")]  # 0.3 px arc
    out = tmp_path / "t.svg"
    _trace.segments_to_svg(segs, 100, 100, out, line_px=2, sil_px=4)
    txt = out.read_text()
    assert txt.count("<line") == 1 and "10.07" not in txt
    assert " A " not in txt
