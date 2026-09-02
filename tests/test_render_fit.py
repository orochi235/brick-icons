"""The fit sidecar the lab's 3D pane frames itself with.

Its whole value is that it is the engine's own projection rather than a second
derivation of it, so what these check is the composition: a world point mapped
through the sidecar lands where the render drew it.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from brick_icons import cli, hlr


def _fit(tmp_path, part, *args):
    assert cli.main([part, "--shading", "outline", "--format", "svg",
                     "--out", str(tmp_path), *args]) == 0
    return json.loads((tmp_path / f"{part}.fit.json").read_text())


def _to_canvas(fit, points):
    """The map a consumer of the sidecar writes: A/B, then scale and offset."""
    p = np.asarray(points, float)
    a = p @ np.array(fit["right"])
    b = -(p @ np.array(fit["up"]))
    return np.column_stack([a * fit["k"] + fit["kx"], b * fit["k"] + fit["ky"]])


@pytest.fixture
def ldraw_parts():
    if not Path("vendor/ldraw/parts").exists():
        pytest.skip("LDraw library absent")


def test_sidecar_is_written_beside_the_svg(tmp_path, ldraw_parts):
    fit = _fit(tmp_path, "3005")
    assert (tmp_path / "3005.svg").exists()
    assert set(fit) == {"right", "up", "fwd", "k", "kx", "ky", "width", "height"}


def test_viewbox_size_is_the_canvas(tmp_path, ldraw_parts):
    fit = _fit(tmp_path, "3005", "--width", "300", "--height", "200")
    assert (fit["width"], fit["height"]) == (300, 200)


def test_it_maps_world_where_the_render_drew_it(tmp_path, ldraw_parts):
    """The composition, against the pipeline's own two-step map."""
    res = hlr.visible_segments("3005", Path("vendor/ldraw"), lat=30.0, long=45.0,
                               render_px=512, cull=True, engine="naive")
    f, ox, oy = hlr.fit_affine(res.bbox, 512, 512, 6, 1.0)
    k, kx, ky = hlr.canvas_affine(res, f, ox, oy)

    points = np.array(res.tri, float).reshape(-1, 3)[:200]
    px_x, px_y, _ = res.proj.to_px(points)
    a, b, _ = res.proj.to_AB(points)

    assert np.allclose(px_x * f + ox, a * k + kx)
    assert np.allclose(px_y * f + oy, b * k + ky)


def test_the_part_lands_inside_the_canvas(tmp_path, ldraw_parts):
    """Sign and basis errors survive an algebra check but not this one: a
    flipped axis puts the part off the viewBox entirely."""
    fit = _fit(tmp_path, "3005", "--width", "512", "--height", "512")
    res = hlr.visible_segments("3005", Path("vendor/ldraw"), lat=30.0, long=45.0,
                               render_px=512, cull=True, engine="naive")
    drawn = _to_canvas(fit, np.array(res.tri, float).reshape(-1, 3))

    assert drawn[:, 0].min() >= -1 and drawn[:, 0].max() <= 513
    assert drawn[:, 1].min() >= -1 and drawn[:, 1].max() <= 513
    # Fills the canvas rather than sitting in a corner of it.
    assert max(np.ptp(drawn[:, 0]), np.ptp(drawn[:, 1])) > 400


def test_an_engine_without_a_pixel_fit_uses_the_canvas_fit_alone(tmp_path):
    """occt and cadquery draw in projected units and carry no `proj`."""
    res = hlr.VisResult((), (0.0, 0.0, 1.0, 1.0), 1.0, faces=(), analytic=(),
                        ellipses=())
    assert res.proj is None
    assert hlr.canvas_affine(res, 3.0, 5.0, 7.0) == (3.0, 5.0, 7.0)


def test_it_reports_the_style_s_own_light_and_colour(tmp_path, ldraw_parts):
    """The pane lights itself from this, so it must be the render's own vector
    rather than one the frontend derived a second time."""
    from brick_icons import shade
    fit = _fit(tmp_path, "3005", "--shade-style", "flat3", "--part-color", "0xC91A09")
    style = shade.make_style("flat3", part_color=shade.parse_hex_color("0xC91A09"))
    assert fit["part_color"] == [201, 26, 9]
    assert np.allclose(fit["light"], style.light)


def test_a_render_with_no_style_reports_no_light(tmp_path, ldraw_parts):
    """`--shade-style none` draws no faces, so there is no light to report and
    the pane keeps its own rather than being handed an invented one."""
    fit = _fit(tmp_path, "3005", "--shade-style", "none")
    assert "light" not in fit and "part_color" not in fit
