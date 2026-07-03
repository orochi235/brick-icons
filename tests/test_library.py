import json

from brick_icons import library


def test_parse_header_and_accept():
    hdr = "0 Brick  2 x  4\n0 !LDRAW_ORG Part UPDATE 2004-03\n"
    info = library.parse_header(hdr.splitlines())
    assert info.title == "Brick  2 x  4"
    assert info.category == "Brick"
    assert info.org == "Part"
    assert library.is_sortable(info) is True


def test_reject_sticker_shortcut_moved_pattern():
    def info(t, org="Part"):
        return library.parse_header([f"0 {t}", f"0 !LDRAW_ORG {org} UPDATE x"])
    assert library.is_sortable(info("Sticker 1 x 1")) is False
    assert library.is_sortable(info("Brick 2 x 4", org="Shortcut")) is False
    assert library.is_sortable(info("Moved to 3001")) is False
    assert library.is_sortable(info("Tile 2 x 2 with Pattern")) is False
    assert library.is_sortable(info("~Brick 2 x 4")) is False
    assert library.is_sortable(info("Minifig Head")) is False


def test_select_parts_finds_known_ids():
    from brick_icons import library
    ids = set(library.select_parts("vendor/ldraw", limit=None))
    assert "3001" in ids and "3020" in ids and "3040b" in ids
    assert all(not i.endswith(".dat") for i in ids)
    assert len(ids) > 200


def test_render_library_small(tmp_path):
    from brick_icons import library
    manifest = library.render_library(
        out_dir=str(tmp_path), ldraw_dir="vendor/ldraw",
        limit=3, workers=1, shade_style="flat3")
    assert (tmp_path / "manifest.json").exists()
    data = json.loads((tmp_path / "manifest.json").read_text())
    assert len(data) == 3
    ok = [r for r in data if r["status"] == "ok"]
    assert ok, "expected at least one successful render"
    r = ok[0]
    assert r["width_mm"] > 0 and r["height_mm"] > 0 and r["category"]
    svg = tmp_path / r["category"] / f'{r["id"]}.svg'
    assert svg.exists() and svg.read_text().startswith("<svg")
