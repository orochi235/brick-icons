from pathlib import Path

import pytest

from brick_icons.config import load_config


def test_defaults():
    cfg = load_config(root="/proj")
    assert cfg.dpi == 180 and cfg.mode == "both" and cfg.fmt == "png"
    assert cfg.dither == "atkinson" and cfg.shading == "normal"
    assert cfg.width == 256 and cfg.height == 170
    assert cfg.render_px == 2048 and cfg.curve_quality == 12
    assert cfg.angle == "iso" and cfg.cel_levels == 4
    assert cfg.part_color is None
    assert cfg.svg_bg == "none" and cfg.opacity == 1.0
    assert cfg.scale == 1.0
    assert cfg.ldraw_dir == Path("/proj/vendor/ldraw")
    assert cfg.ldview == Path("/proj/vendor/LDView.app/Contents/MacOS/LDView")
    # LDView 4.7 is a universal binary, so no argv prefix on any platform
    assert cfg.ldview_launcher == ()


def test_launcher_override():
    cfg = load_config(overrides={"ldview_launcher": []}, root="/p")
    assert cfg.ldview_launcher == ()


def test_overrides_win_and_none_ignored():
    cfg = load_config(overrides={"dpi": 360, "shading": "cel", "width": None}, root="/p")
    assert cfg.dpi == 360 and cfg.shading == "cel"
    assert cfg.width == 256  # None ignored


def test_label_mm_to_pixels():
    cfg = load_config(overrides={"label_mm": (24.0, 12.0), "dpi": 180}, root="/p")
    assert cfg.width == round(24.0 / 25.4 * 180)
    assert cfg.height == round(12.0 / 25.4 * 180)


def test_toml_used(tmp_path):
    t = tmp_path / "labels.toml"
    t.write_text('dpi = 360\nshading = "outline"\ncel_levels = 6\n')
    cfg = load_config(toml_path=str(t), root="/p")
    assert cfg.dpi == 360 and cfg.shading == "outline" and cfg.cel_levels == 6


def test_scale_mode_default_and_override(tmp_path):
    from brick_icons.config import load_config
    cfg = load_config(toml_path=None, overrides={}, root=".")
    assert cfg.scale_mode == "fit"
    assert cfg.line_mm == 0.2 and cfg.silhouette_mm == 0.2
    cfg2 = load_config(toml_path=None, overrides={"scale_mode": "physical"}, root=".")
    assert cfg2.scale_mode == "physical"


def test_part_color_code_resolves_to_hex():
    cfg = load_config(overrides={"part_color": "4"}, root=".")
    assert cfg.part_color == "0xb40000"


def test_part_color_name_resolves_to_hex():
    cfg = load_config(overrides={"part_color": "light bluish gray"}, root=".")
    assert cfg.part_color == "0x969696"


def test_part_color_hex_is_unchanged():
    cfg = load_config(overrides={"part_color": "0xc91a09"}, root=".")
    assert cfg.part_color == "0xc91a09"


def test_trans_code_sets_opacity():
    cfg = load_config(overrides={"part_color": "36"}, root=".")
    assert cfg.part_color == "0xc91a09"
    assert cfg.opacity == pytest.approx(128 / 255)


def test_explicit_opacity_beats_trans_alpha():
    cfg = load_config(overrides={"part_color": "36", "opacity": 0.9}, root=".")
    assert cfg.opacity == 0.9


def test_toml_opacity_beats_trans_alpha(tmp_path):
    t = tmp_path / "labels.toml"
    t.write_text('opacity = 0.8\n')
    cfg = load_config(toml_path=str(t), overrides={"part_color": "36"}, root=".")
    assert cfg.opacity == 0.8


def test_opaque_code_leaves_opacity_alone():
    cfg = load_config(overrides={"part_color": "4"}, root=".")
    assert cfg.opacity == 1.0


def test_unknown_color_raises():
    from brick_icons.colors import UnknownColorError
    with pytest.raises(UnknownColorError):
        load_config(overrides={"part_color": "chartreuse"}, root=".")


def test_engine_defaults_to_naive():
    assert load_config(root=".").engine == "naive"


def test_engine_override():
    assert load_config(root=".", overrides={"engine": "occt"}).engine == "occt"
