"""The ingestion log: which ingests have happened, and what each one took in."""
import pytest

from brick_icons import db
from brick_icons.lab import ingest


def _attempt(conn, run_id, pid, source="decal", state="stored", **kw):
    row = {"secs": 1.0, "error": None, "detail": None} | kw
    conn.execute(
        "INSERT INTO attempts (run_id, part_id, source, state, secs, error, "
        "detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (run_id, pid, source, state, row["secs"], row["error"], row["detail"]))


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "corpus.db")
    yield c
    c.close()


def test_newest_run_first(conn):
    for kind in ("census", "store", "render"):
        db.start_run(conn, kind, {}, "abc")
    conn.commit()
    assert [r["kind"] for r in ingest.runs(conn)] == ["render", "store", "census"]


def test_a_run_carries_its_own_tally(conn):
    run = db.start_run(conn, "store", {"dir": "out/store"}, "abc")
    for pid in ("a", "b", "c"):
        _attempt(conn, run, pid)
    _attempt(conn, run, "d", state=None, error="TimeoutError")
    _attempt(conn, run, "e", state="none")
    conn.commit()
    row = ingest.runs(conn)[0]
    assert row["counts"] == {"stored": 3, "none": 1, "error": 1}
    assert row["total"] == 5
    assert row["args"] == {"dir": "out/store"}


def test_a_run_with_no_attempts_tallies_to_nothing(conn):
    """A census rebuild writes measurements, not attempts. It still belongs on
    the log -- a run that ingested nothing is exactly what someone is looking
    for when they ask why the wall did not move."""
    db.start_run(conn, "census", {}, "abc")
    conn.commit()
    row = ingest.runs(conn)[0]
    assert row["counts"] == {}
    assert row["total"] == 0


def test_duration_comes_from_the_two_timestamps(conn):
    run = db.start_run(conn, "store", {}, "abc")
    conn.execute("UPDATE runs SET started=?, finished=? WHERE id=?",
                 ("2026-09-08T17:09:12+00:00", "2026-09-08T17:14:42+00:00", run))
    conn.commit()
    assert ingest.runs(conn)[0]["secs"] == 330.0


def test_an_unfinished_run_has_no_duration(conn):
    db.start_run(conn, "store", {}, "abc")
    conn.commit()
    row = ingest.runs(conn)[0]
    assert row["finished"] is None
    assert row["secs"] is None


def test_attempts_come_back_for_one_run_only(conn):
    mine = db.start_run(conn, "store", {}, "abc")
    other = db.start_run(conn, "store", {}, "abc")
    _attempt(conn, mine, "a")
    _attempt(conn, other, "b")
    conn.commit()
    rows = ingest.attempts(conn, mine)["rows"]
    assert [r["part_id"] for r in rows] == ["a"]


def test_errors_are_rolled_up_rather_than_listed_one_by_one(conn):
    """400 parts killed by the same crash is one line to read, not 400."""
    run = db.start_run(conn, "store", {}, "abc")
    for i in range(400):
        _attempt(conn, run, f"p{i}", state=None, error="ProcessDied")
    _attempt(conn, run, "slow", state=None, error="TimeoutError")
    conn.commit()
    out = ingest.attempts(conn, run)
    assert out["errors"] == [{"error": "ProcessDied", "n": 400},
                             {"error": "TimeoutError", "n": 1}]


def test_the_attempt_rows_are_capped(conn):
    """A store run holds thousands. The rollup is the summary; the rows are a
    sample, and the count says how big the thing they were drawn from is."""
    run = db.start_run(conn, "store", {}, "abc")
    for i in range(300):
        _attempt(conn, run, f"p{i:03d}")
    conn.commit()
    out = ingest.attempts(conn, run, limit=50)
    assert len(out["rows"]) == 50
    assert out["total"] == 300


def test_attempts_can_be_narrowed_to_the_failures(conn):
    run = db.start_run(conn, "store", {}, "abc")
    _attempt(conn, run, "ok")
    _attempt(conn, run, "bad", state=None, error="TimeoutError")
    conn.commit()
    rows = ingest.attempts(conn, run, failed_only=True)["rows"]
    assert [r["part_id"] for r in rows] == ["bad"]
