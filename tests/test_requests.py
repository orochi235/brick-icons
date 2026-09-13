"""The redraw queue: what counts as waiting, and what it is expected to cost."""
import pytest

from brick_icons import db, requests


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "corpus.db")
    c.execute("INSERT INTO parts (id, title, printed, obsolete) "
              "VALUES ('3001', 'Brick', 0, 0)")
    c.commit()
    yield c
    c.close()


def _render(conn, made_at, part="3001", source="occt"):
    conn.execute("INSERT OR REPLACE INTO renders (part_id, source, config_key, "
                 "made_at, path, sha256) VALUES (?, ?, 'k', ?, 'p.svg', 'x')",
                 (part, source, made_at))
    conn.commit()


def test_a_request_waits_until_a_newer_render_lands(conn, tmp_path):
    log = tmp_path / "requests.jsonl"
    _render(conn, "2026-09-01T00:00:00+00:00")
    requests.add(log, "3001", "occt", at="2026-09-10T00:00:00+00:00")
    assert requests.pending(conn, "occt", log) == ["3001"]
    _render(conn, "2026-09-11T00:00:00+00:00")
    assert requests.pending(conn, "occt", log) == []


def test_asking_again_after_a_redraw_waits_again(conn, tmp_path):
    log = tmp_path / "requests.jsonl"
    requests.add(log, "3001", "occt", at="2026-09-10T00:00:00+00:00")
    _render(conn, "2026-09-11T00:00:00+00:00")
    requests.add(log, "3001", "occt", at="2026-09-12T00:00:00+00:00")
    assert requests.pending_for(conn, "3001", log) == {
        "occt": "2026-09-12T00:00:00+00:00"}


def test_a_request_is_per_slot(conn, tmp_path):
    log = tmp_path / "requests.jsonl"
    requests.add(log, "3001", "occt")
    assert requests.pending(conn, "naive", log) == []


def test_a_torn_line_does_not_break_the_log(conn, tmp_path):
    log = tmp_path / "requests.jsonl"
    requests.add(log, "3001", "occt")
    with log.open("a") as fh:
        fh.write('{"part": "3004", "sour')
    assert requests.pending(conn, "occt", log) == ["3001"]


def test_cost_prefers_the_part_over_the_slot(conn):
    conn.execute("INSERT INTO measurements (run_id, part_id, engine, source, "
                 "secs) VALUES (1, 'other', 'occt', 'occt', 90.0)")
    assert requests.cost(conn, "3001", "occt") == 90.0
    conn.execute("INSERT INTO measurements (run_id, part_id, engine, source, "
                 "secs) VALUES (2, '3001', 'occt', 'occt', 40.0)")
    assert requests.cost(conn, "3001", "occt") == 40.0
    conn.execute("INSERT INTO attempts (run_id, part_id, source, state, secs) "
                 "VALUES (3, '3001', 'occt', 'stored', 3.0)")
    assert requests.cost(conn, "3001", "occt") == 3.0


def test_an_untimed_slot_has_no_cost(conn):
    assert requests.cost(conn, "3001", "occt") is None


def test_a_cheap_or_decal_redraw_draws_here():
    assert requests.draws_here("decal", None)
    assert requests.draws_here("occt", 2.0)
    assert not requests.draws_here("occt", 300.0)
    assert not requests.draws_here("occt", None)


def test_requested_parts_go_first_and_only_once():
    lines = ["a,b,c", "d,e"]
    assert requests.front_load(lines, ["d", "x"], per_batch=3) == [
        "d,x", "a,b,c", "e"]
