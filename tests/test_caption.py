import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from brick_icons import caption

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _sheet  # noqa: E402


def test_numbers_are_fixed_width_with_one_decimal():
    assert caption.size_text(18842) == "  18.4 KB"
    assert caption.size_text(512) == "   0.5 KB"
    assert caption.size_text(2_500_000) == "   2.4 MB"
    assert caption.secs_text(3.24) == "  3.2 s"
    assert caption.secs_text(123.45) == "123.5 s"
    widths = {len(caption.size_text(n)) for n in (0, 512, 18842, 2_500_000, None)}
    assert len(widths) == 1
    assert {len(caption.secs_text(s)) for s in (0.04, 3.2, 99.9, None)} == {7}


def test_the_decimal_points_line_up_down_a_column():
    lines = [caption.line("3001", 18842, 3.24), caption.line("3001", 900_000, 41.0),
             caption.line("3001", 700, 0.3)]
    points = {tuple(m.start() for m in re.finditer(r"\.", s)) for s in lines}
    assert len(points) == 1


def test_an_unmeasured_time_is_a_dash_never_a_number():
    text = caption.line("3001", None, None)
    assert text.count(caption.DASH) == 2
    assert not re.search(r"\d\.\d", text)


def test_pad_grows_the_canvas_and_leaves_the_drawing_alone():
    img = Image.new("RGB", (400, 300), "white")
    img.paste((200, 0, 0), (100, 100, 300, 200))
    out = caption.pad(img, caption.line("3001", 18842, 3.2))
    assert out.width == 400 and out.height > 300
    a = np.asarray(out)
    assert (a[:300] == np.asarray(img)).all()
    assert (a[300:].min(axis=2) < 128).any()


def test_pad_widens_for_a_caption_longer_than_the_drawing():
    out = caption.pad(Image.new("1", (40, 30), 1), caption.line("3001", 1, 1.0))
    assert out.width > 40 and out.mode == "1"


def test_pad_svg_adds_a_preserved_caption_strip():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 180" '
           'preserveAspectRatio="xMidYMid meet"><path d="M0 0L1 1"/></svg>')
    out = caption.pad_svg(svg, caption.line("3001", 18842, 3.2))
    vb = re.search(r'viewBox="([^"]+)"', out).group(1).split()
    assert float(vb[2]) == 256 and float(vb[3]) > 180
    assert 'xml:space="preserve"' in out
    assert ">3001 ·   18.4 KB ·   3.2 s</text></svg>" in out


def test_pad_svg_scales_a_sized_root():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"></svg>'
    out = caption.pad_svg(svg, "x")
    h = float(re.search(r'height="([\d.]+)"', out).group(1))
    vb = re.search(r'viewBox="([^"]+)"', out).group(1).split()
    assert h > 50 and abs(h - float(vb[3])) < 0.01


def test_a_captioned_sheet_panel_carries_its_caption():
    before = Image.new("RGB", (200, 150), "white")
    after = before.copy()
    after.paste((0, 0, 0), (50, 50, 150, 100))
    shot = caption.Shot(after, "3001", 18842, 3.2)
    img = _sheet.sheet("t", [("3001", caption.Shot(before, "3001", 18000, 3.0),
                              shot)])
    want = np.asarray(caption.pad(after, shot.text))
    a = np.asarray(img)
    # the `after` column: left 130 + gutter 12, then one panel and gutter
    x, y = 130 + 12 + 200 + 12, 56
    assert (a[y:y + want.shape[0], x:x + want.shape[1]] == want).all()


def test_an_uncaptioned_sheet_is_unchanged():
    before = Image.new("RGB", (200, 150), "white")
    img = _sheet.sheet("t", [("3001", before, before.copy())])
    assert img.height == 56 + 150 + 12


def _db(path, secs_run):
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE renders (part_id, source, run_id, path);"
        "CREATE TABLE measurements (run_id, part_id, source, secs);"
        "CREATE TABLE attempts (run_id, part_id, source, secs);")
    conn.execute("INSERT INTO renders VALUES ('3001', 'occt', 7, 'r/3001.svg')")
    conn.execute("INSERT INTO measurements VALUES (?, '3001', 'occt', 4.5)",
                 (secs_run,))
    conn.execute("INSERT INTO measurements VALUES (9, '3001', 'occt', 1.0)")
    conn.commit()
    conn.close()


def test_stored_secs_is_the_run_that_made_the_stored_drawing(tmp_path):
    _db(tmp_path / "c.db", 7)
    (tmp_path / "r").mkdir()
    (tmp_path / "r" / "3001.svg").write_text("<svg/>")
    db = tmp_path / "c.db"
    assert caption.stored_secs("3001", "occt", db_path=db) == 4.5
    assert caption.stored_secs("3001", "occt", tmp_path / "r" / "3001.svg",
                               db_path=db) == 4.5
    assert caption.stored_secs("3001", "occt", tmp_path / "other.svg",
                               db_path=db) is None
    assert caption.stored_secs("3001", "naive", db_path=db) is None


def test_stored_secs_never_borrows_another_run(tmp_path):
    _db(tmp_path / "c.db", 8)          # only runs 8 and 9 were timed
    assert caption.stored_secs("3001", "occt", db_path=tmp_path / "c.db") is None
