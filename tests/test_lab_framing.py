from fastapi.testclient import TestClient
from PIL import Image

from brick_icons import db
from brick_icons.hlr import fit_affine
from brick_icons.lab import app as lab_app
from brick_icons.lab import framing


def _raster(path, size, ink):
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    im.paste((90, 90, 90, 255), ink)
    im.save(path)


def test_a_cropped_raster_is_fitted_like_a_drawing(tmp_path):
    """LDView crops to the part: its ink box is the whole image, and the
    image lands where fit_affine would put a drawing of that box."""
    png = tmp_path / "crop.png"
    _raster(png, (400, 300), (0, 0, 400, 300))
    got = framing.placement(png, "a", 256, 170, 6)
    f, ox, oy = fit_affine((0, 0, 400, 300), 256, 170, 6)
    assert got == {"canvas": [256, 170], "x": ox, "y": oy,
                   "w": 400 * f, "h": 300 * f}
    assert round(got["h"], 9) == 158             # height-limited: 170 - 2*6


def test_a_padded_raster_is_fitted_by_its_ink_not_its_frame(tmp_path):
    """The browser reference fits a 512 square with room around the part;
    the ink box decides the scale, so the frame spills past the canvas."""
    png = tmp_path / "pad.png"
    _raster(png, (512, 512), (6, 70, 506, 442))
    got = framing.placement(png, "b", 256, 170, 6)
    f = min(244 / 500, 158 / 372)
    assert abs(got["w"] - 512 * f) < 1e-9
    assert got["y"] < 0


def test_a_raster_with_no_alpha_has_no_placement(tmp_path):
    png = tmp_path / "rgb.png"
    Image.new("RGB", (10, 10), "white").save(png)
    assert framing.placement(png, "c", 256, 170, 6) is None


def test_part_route_places_raster_slots_and_leaves_svg_alone(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    conn.execute("INSERT INTO parts (id, title, category, printed, obsolete, "
                 "status) VALUES ('3001', 'Brick 2 x 4', 'Brick', 0, 0, 'good')")
    (tmp_path / "r").mkdir()
    _raster(tmp_path / "r" / "3001.png", (400, 300), (0, 0, 400, 300))
    (tmp_path / "r" / "3001.svg").write_text("<svg/>")
    for source, path in (("reference-gray", "r/3001.png"), ("occt", "r/3001.svg")):
        conn.execute("INSERT INTO renders (part_id, source, config_key, made_at, "
                     "path, sha256) VALUES ('3001', ?, 'k', 'now', ?, ?)",
                     (source, path, source))
    conn.commit()
    conn.close()
    client = TestClient(lab_app.create_app(
        root=tmp_path, cache_root=tmp_path / "cache",
        corpus_db=tmp_path / "corpus.db", defects_path=tmp_path / "defects.toml"))
    slots = {s["source"]: s for s in
             client.get("/api/corpus/part/3001").json()["slots"]}
    assert round(slots["reference-gray"]["placement"]["h"], 9) == 158
    assert "placement" not in slots["occt"]
    assert "path" not in slots["reference-gray"]
