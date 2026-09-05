"""The corpus wall's cell list."""
import pytest

from brick_icons import db
from brick_icons.lab import cells


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "corpus.db")
    yield c
    c.close()


def _part(conn, pid, title="Brick", category="Brick", status="unreviewed"):
    conn.execute("INSERT INTO parts (id, title, category, printed, obsolete, "
                 "status) VALUES (?, ?, ?, 0, 0, ?)",
                 (pid, title, category, status))


def _render(conn, pid, sha, made_at, source="census-naive"):
    conn.execute("INSERT INTO renders (part_id, source, config_key, made_at, "
                 "path, sha256) VALUES (?, ?, 'k', ?, ?, ?)",
                 (pid, source, made_at, f"renders/{source}/{pid}.svg", sha))


def test_every_part_is_a_cell_in_id_order(conn):
    for pid in ("3004", "3001", "3005"):
        _part(conn, pid)
    conn.commit()
    body = cells.cells(conn)
    assert [c["id"] for c in body["cells"]] == ["3001", "3004", "3005"]
    assert body["count"] == 3


def test_a_cell_index_is_its_position_in_that_order(conn):
    for pid in ("3004", "3001"):
        _part(conn, pid)
    conn.commit()
    assert [c["index"] for c in cells.cells(conn)["cells"]] == [0, 1]


def test_a_rendered_cell_carries_its_sha(conn):
    _part(conn, "3001")
    _render(conn, "3001", "deadbeef", "2026-09-05T10:00:00+00:00")
    conn.commit()
    cell = cells.cells(conn)["cells"][0]
    assert cell["sha"] == "deadbeef"
    assert cell["made_at"] == "2026-09-05T10:00:00+00:00"


def test_an_unrendered_cell_has_no_sha(conn):
    _part(conn, "3001")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["sha"] is None


def test_a_render_in_another_slot_is_not_this_slot_s(conn):
    _part(conn, "3001")
    _render(conn, "3001", "deadbeef", "2026-09-05T10:00:00+00:00", source="naive")
    conn.commit()
    assert cells.cells(conn, source="census-naive")["cells"][0]["sha"] is None
    assert cells.cells(conn, source="naive")["cells"][0]["sha"] == "deadbeef"


def test_the_version_is_the_newest_render(conn):
    _part(conn, "3001")
    _part(conn, "3004")
    _render(conn, "3001", "a", "2026-09-05T10:00:00+00:00")
    _render(conn, "3004", "b", "2026-09-05T11:00:00+00:00")
    conn.commit()
    assert cells.cells(conn)["version"] == "2026-09-05T11:00:00+00:00"


def test_the_version_is_empty_with_no_renders(conn):
    _part(conn, "3001")
    conn.commit()
    assert cells.cells(conn)["version"] == ""


def test_since_returns_only_what_was_rendered_after_it(conn):
    _part(conn, "3001")
    _part(conn, "3004")
    _render(conn, "3001", "a", "2026-09-05T10:00:00+00:00")
    _render(conn, "3004", "b", "2026-09-05T11:00:00+00:00")
    conn.commit()
    body = cells.cells(conn, since="2026-09-05T10:30:00+00:00")
    assert [c["id"] for c in body["cells"]] == ["3004"]
    assert body["count"] == 2  # the corpus size, not the delta's


def test_a_delta_cell_keeps_the_index_it_has_on_the_wall(conn):
    for pid in ("3001", "3004", "3005"):
        _part(conn, pid)
    _render(conn, "3005", "c", "2026-09-05T11:00:00+00:00")
    conn.commit()
    body = cells.cells(conn, since="2026-09-05T10:00:00+00:00")
    assert body["cells"][0]["index"] == 2


def test_a_delta_with_nothing_new_is_empty(conn):
    _part(conn, "3001")
    _render(conn, "3001", "a", "2026-09-05T10:00:00+00:00")
    conn.commit()
    body = cells.cells(conn, since="2026-09-05T12:00:00+00:00")
    assert body["cells"] == []
    assert body["count"] == 1
