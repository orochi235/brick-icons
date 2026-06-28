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


def test_outline_svg_has_paths(tmp_path):
    out = tmp_path / "d.svg"
    trace.outline_svg(_disc(), out, interior=False)
    txt = out.read_text()
    assert "<svg" in txt and "<path" in txt
    assert 'transform="translate(' in txt   # potrace transform preserved


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


@pytest.mark.skipif(shutil.which("magick") is None, reason="ImageMagick absent")
def test_outline_svg_rasterizes_nonblank(tmp_path):
    svg = tmp_path / "d.svg"; png = tmp_path / "d.png"
    trace.outline_svg(_disc(), svg, interior=True)
    import subprocess
    subprocess.run(["magick", "-density", "150", str(svg), "-background", "white",
                    "-flatten", str(png)], check=True, capture_output=True)
    assert (np.asarray(Image.open(png).convert("L")) < 250).sum() > 0
