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
    assert 'stroke-width="4"' in txt and 'stroke-width="2"' in txt



def test_segments_to_svg_emits_arc_path(tmp_path):
    ops = [("arc", 50.0, 50.0, 40.0, 30.0, 0.0, 0.0, 90.0, "edge")]
    out = _trace.segments_to_svg(ops, 100, 100, tmp_path / "a.svg")
    txt = out.read_text()
    assert "<path" in txt and " A " in txt          # elliptical-arc command


def test_segments_to_svg_mixed_line_and_legacy(tmp_path):
    ops = [("line", 0.0, 0.0, 10.0, 10.0, "edge"), (1.0, 1.0, 2.0, 2.0, "sil")]
    out = _trace.segments_to_svg(ops, 20, 20, tmp_path / "b.svg")
    assert out.read_text().count("<line") == 2
