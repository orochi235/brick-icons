from pathlib import Path
import shutil
import numpy as np
import pytest
from PIL import Image
from brick_icons import cli


def _fake_render(monkeypatch, size=(400, 300)):
    def fake(cfg, part, out_png):
        out_png.parent.mkdir(parents=True, exist_ok=True)
        arr = np.zeros((size[1], size[0], 4), np.uint8)
        arr[40:-40, 40:-40, :3] = 90
        arr[40:-40, 40:-40, 3] = 255
        Image.fromarray(arr, "RGBA").save(out_png)
        return out_png
    monkeypatch.setattr(cli.render, "render_part", fake)


def test_png_both_writes_gray_and_mono(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    assert cli.main(["3001", "--mode", "both", "--out", str(tmp_path),
                     "--root", str(tmp_path)]) == 0
    assert (tmp_path / "3001.gray.png").exists()
    assert Image.open(tmp_path / "3001.mono.png").mode == "1"


def test_png_color_mode(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    cli.main(["3001", "--mode", "color", "--out", str(tmp_path), "--root", str(tmp_path)])
    assert Image.open(tmp_path / "3001.color.png").mode == "RGB"


def test_mono_size(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    cli.main(["3001", "--mode", "mono", "--width", "120", "--height", "80",
              "--out", str(tmp_path), "--root", str(tmp_path)])
    assert Image.open(tmp_path / "3001.mono.png").size == (120, 80)


def test_cel_mono_posterizes(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    cli.main(["3001", "--shading", "cel", "--mode", "gray",
              "--out", str(tmp_path), "--root", str(tmp_path)])
    # cel gray should have few distinct levels
    levels = len(set(np.unique(Image.open(tmp_path / "3001.gray.png")).tolist()))
    assert levels <= 6


@pytest.mark.skipif(shutil.which("potrace") is None, reason="potrace absent")
def test_svg_outline(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    cli.main(["3001", "--format", "svg", "--shading", "outline",
              "--out", str(tmp_path), "--root", str(tmp_path)])
    assert (tmp_path / "3001.svg").exists()
    assert "<path" in (tmp_path / "3001.svg").read_text()


def test_outline_silhouette_width_flag_thickens(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    cli.main(["3001", "--shading", "outline", "--mode", "mono", "--silhouette-width", "1",
              "--out", str(tmp_path), "--root", str(tmp_path)])
    thin = (np.asarray(Image.open(tmp_path / "3001.mono.png").convert("L")) == 0).sum()
    cli.main(["3001", "--shading", "outline", "--mode", "mono", "--silhouette-width", "9",
              "--out", str(tmp_path), "--root", str(tmp_path)])
    thick = (np.asarray(Image.open(tmp_path / "3001.mono.png").convert("L")) == 0).sum()
    assert thick > thin


def test_svg_requires_vector_shading(tmp_path, monkeypatch, capsys):
    _fake_render(monkeypatch)
    cli.main(["3001", "--format", "svg", "--shading", "normal",
              "--out", str(tmp_path), "--root", str(tmp_path)])
    assert not (tmp_path / "3001.svg").exists()
    assert "shading" in capsys.readouterr().out.lower()


def test_debug_dir_saves_stages(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    dbg = tmp_path / "dbg"
    cli.main(["3001", "--mode", "mono", "--out", str(tmp_path),
              "--root", str(tmp_path), "--debug-dir", str(dbg)])
    assert (dbg / "render" / "3001.png").exists()
    assert (dbg / "tone" / "3001.png").exists()
    assert (dbg / "mono" / "3001.png").exists()


def test_batch_list_file(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    lst = tmp_path / "p.txt"; lst.write_text("# bins\n3001\n3002\n\n")
    cli.main(["--list", str(lst), "--mode", "mono", "--out", str(tmp_path),
              "--root", str(tmp_path)])
    assert (tmp_path / "3001.mono.png").exists() and (tmp_path / "3002.mono.png").exists()


def test_batch_list_skips_indented_comments(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    lst = tmp_path / "p.txt"; lst.write_text("3001\n   # indented comment\n3002\n")
    cli.main(["--list", str(lst), "--mode", "mono", "--out", str(tmp_path), "--root", str(tmp_path)])
    assert (tmp_path / "3001.mono.png").exists() and (tmp_path / "3002.mono.png").exists()
    assert not any(p.name.startswith("#") for p in tmp_path.iterdir())


HAVE_LIB = (Path("vendor/ldraw")).exists()


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_outline_uses_hlr_not_ldview(tmp_path, monkeypatch):
    called = {"n": 0}
    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("LDView must not be called for outline shading")
    monkeypatch.setattr(cli.render, "render_part", boom)
    rc = cli.main(["3701", "--shading", "outline", "--format", "both",
                   "--mode", "both", "--out", str(tmp_path)])
    assert rc == 0 and called["n"] == 0
    assert (tmp_path / "3701.svg").read_text().count("<line") > 50
    assert Image.open(tmp_path / "3701.mono.png").mode == "1"
    assert (tmp_path / "3701.gray.png").exists()
