from pathlib import Path
import pytest
from PIL import Image
from brick_icons.config import load_config
from brick_icons import render


def test_resolve_part_id(tmp_path):
    (tmp_path / "vendor/ldraw/parts").mkdir(parents=True)
    (tmp_path / "vendor/ldraw/parts/3001.dat").write_text("0 brick")
    cfg = load_config(root=tmp_path)
    assert render.resolve_part(cfg, "3001") == tmp_path / "vendor/ldraw/parts/3001.dat"


def test_resolve_explicit_path(tmp_path):
    f = tmp_path / "c.ldr"; f.write_text("0")
    assert render.resolve_part(load_config(root=tmp_path), str(f)) == f


def test_resolve_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        render.resolve_part(load_config(root=tmp_path), "9999999")


def test_resolve_latlong_presets_and_explicit():
    assert render.resolve_latlong("iso") == (30.0, 45.0)
    assert render.resolve_latlong("top") == (90.0, 0.0)
    assert render.resolve_latlong("15,-60") == (15.0, -60.0)
    with pytest.raises(ValueError):
        render.resolve_latlong("sideways")


def test_build_argv_uses_launcher_prefix():
    direct = load_config(root=".", overrides={"ldview_launcher": []})
    argv = render.build_argv(direct, Path("/p/3001.dat"), Path("/o/3001.png"))
    assert argv[0] == str(direct.ldview)            # no prefix on Linux/direct
    rosetta = load_config(root=".", overrides={"ldview_launcher": ["arch", "-x86_64"]})
    argv2 = render.build_argv(rosetta, Path("/p/3001.dat"), Path("/o/3001.png"))
    assert argv2[:3] == ["arch", "-x86_64", str(rosetta.ldview)]


def test_build_argv_has_fidelity_lighting_angle():
    cfg = load_config(root=".")
    argv = render.build_argv(cfg, Path("/p/3001.dat"), Path("/o/3001.png"))
    assert str(cfg.ldview) in argv
    for flag in ["-SaveSnapshot=/o/3001.png", "-SaveWidth=2048", "-SaveHeight=2048",
                 "-AutoCrop=1", "-SaveAlpha=1", "-EdgeLines=1",
                 "-CurveQuality=12", "-HiResPrimitives=1", "-AllowPrimitiveSubstitution=1",
                 "-Lighting=1", "-UseQualityLighting=1", "-LightVector=-1,1,2",
                 "-DefaultLatLong=30.0,45.0", f"-LDrawDir={cfg.ldraw_dir.resolve()}"]:
        assert flag in argv


def test_build_argv_part_color_optional():
    base = load_config(root=".")
    assert not any(a.startswith("-DefaultColor3") for a in
                   render.build_argv(base, Path("/p/x.dat"), Path("/o/x.png")))
    # resolve() canonicalizes to lowercase 0xrrggbb; LDView hex is
    # case-insensitive, so this changes the flag text, not the render
    colored = load_config(root=".", overrides={"part_color": "0xCC0000"})
    assert "-DefaultColor3=0xcc0000" in render.build_argv(colored, Path("/p/x.dat"), Path("/o/x.png"))


LDVIEW = Path("vendor/LDView.app/Contents/MacOS/LDView")


@pytest.mark.skipif(not LDVIEW.exists(), reason="run scripts/setup-ldview.sh")
def test_render_part_live(tmp_path):
    cfg = load_config(root=Path.cwd())
    out = tmp_path / "3001.png"
    render.render_part(cfg, "3001", out)
    im = Image.open(out)
    assert im.mode == "RGBA" and im.width > 0


def test_build_argv_ldraw_dir_is_absolute(tmp_path, monkeypatch):
    """LDView resolves -LDrawDir against its own notion of cwd, not ours. Given
    a relative one it silently skips LDConfig.ldr and falls back to its built-in
    palette, which has no extended codes: 14769pt*'s Metallic_Silver (80) then
    renders in the same neutral gray as the black field it is printed on and the
    letterform disappears."""
    monkeypatch.chdir(tmp_path)
    cfg = load_config(root=".")
    argv = render.build_argv(cfg, Path("/p/3001.dat"), Path("/o/3001.png"))
    flag = next(a for a in argv if a.startswith("-LDrawDir="))
    assert Path(flag.split("=", 1)[1]).is_absolute(), flag
