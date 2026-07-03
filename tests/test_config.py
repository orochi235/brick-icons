from pathlib import Path
from brick_icons.config import load_config


def test_defaults():
    cfg = load_config(root="/proj")
    assert cfg.dpi == 180 and cfg.mode == "both" and cfg.fmt == "png"
    assert cfg.dither == "atkinson" and cfg.shading == "normal"
    assert cfg.width == 256 and cfg.height == 170
    assert cfg.render_px == 2048 and cfg.curve_quality == 12
    assert cfg.angle == "iso" and cfg.cel_levels == 4
    assert cfg.outline_interior is True and cfg.part_color is None
    assert cfg.scale == 1.0
    assert cfg.ldraw_dir == Path("/proj/vendor/ldraw")
    assert cfg.ldview == Path("/proj/vendor/LDView.app/Contents/MacOS/LDView")
    assert isinstance(cfg.ldview_launcher, tuple)   # platform-detected prefix


def test_default_launcher_by_platform():
    from brick_icons.config import default_ldview_launcher
    assert default_ldview_launcher("Darwin", "arm64") == ["arch", "-x86_64"]
    assert default_ldview_launcher("Darwin", "x86_64") == []
    assert default_ldview_launcher("Linux", "x86_64") == []


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
    assert cfg.line_mm == 0.2 and cfg.silhouette_mm == 0.3
    cfg2 = load_config(toml_path=None, overrides={"scale_mode": "physical"}, root=".")
    assert cfg2.scale_mode == "physical"
