"""The findings view: which parts to look at, and why, without rendering."""
import pytest

from brick_icons import db
from brick_icons.lab import findings


def _part(conn, pid, title="Brick", status="unreviewed", printed=0):
    conn.execute("INSERT INTO parts (id, title, printed, obsolete, status) "
                 "VALUES (?, ?, ?, 0, ?)", (pid, title, printed, status))


def _measure(conn, run_id, pid, engine="naive", **kw):
    row = {"missing_px": 0, "extra_px": 0, "missing_comps": 0,
           "extra_d99": 0.0, "extra_d100": 0.0, "secs": 1.0,
           "error": None, "detail": None} | kw
    conn.execute(
        "INSERT INTO measurements (run_id, part_id, engine, missing_px, "
        "extra_px, missing_comps, extra_d99, extra_d100, secs, error, detail) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, pid, engine, row["missing_px"], row["extra_px"],
         row["missing_comps"], row["extra_d99"], row["extra_d100"],
         row["secs"], row["error"], row["detail"]))


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "corpus.db")
    yield c
    c.close()


def test_the_worst_parts_come_first(conn):
    run = db.start_run(conn, "census", {}, "abc")
    for pid, d99 in (("clean", 0.2), ("bad", 7.1), ("middling", 1.9)):
        _part(conn, pid)
        _measure(conn, run, pid, extra_d99=d99)
    conn.commit()
    rows = findings.findings(conn)["rows"]
    assert [r["part_id"] for r in rows] == ["bad", "middling", "clean"]
    assert rows[0]["extra_d99"] == 7.1


def test_only_the_latest_run_counts(conn):
    """A part measured twice is one finding -- the newer number. Showing both
    makes a fixed part look broken forever."""
    _part(conn, "3001")
    old = db.start_run(conn, "census", {}, "old")
    new = db.start_run(conn, "census", {}, "new")
    _measure(conn, old, "3001", extra_d99=9.0)
    _measure(conn, new, "3001", extra_d99=0.1)
    conn.commit()
    result = findings.findings(conn)
    assert result["total"] == 1
    assert result["rows"][0]["extra_d99"] == 0.1


def test_each_engine_is_its_own_finding(conn):
    """A part can be clean under naive and broken under occt; that is two
    things to look at, not one."""
    _part(conn, "18742")
    run = db.start_run(conn, "census", {}, "abc")
    _measure(conn, run, "18742", engine="naive", extra_d99=0.52)
    _measure(conn, run, "18742", engine="occt", extra_d99=7.12)
    conn.commit()
    assert findings.findings(conn)["total"] == 2
    only = findings.findings(conn, engine="occt")
    assert only["total"] == 1 and only["rows"][0]["extra_d99"] == 7.12


def test_a_row_says_whether_its_render_is_already_stored(conn, tmp_path):
    """This is the point of the store: the view serves what is there and asks
    for the rest, instead of re-rendering a corpus list every time."""
    for pid in ("stored", "not-stored"):
        _part(conn, pid)
    run = db.start_run(conn, "census", {}, "abc")
    _measure(conn, run, "stored", extra_d99=2.0)
    _measure(conn, run, "not-stored", extra_d99=1.0)
    svg = tmp_path / "renders" / "naive" / "stored.svg"
    svg.parent.mkdir(parents=True)
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>')
    db.record_render(conn, "stored", "naive", svg, root=tmp_path, run_id=run)
    conn.commit()
    by_id = {r["part_id"]: r for r in findings.findings(conn)["rows"]}
    assert by_id["stored"]["render"] == "renders/naive/stored.svg"
    assert by_id["not-stored"]["render"] is None


def test_an_errored_part_is_a_finding_even_with_no_numbers(conn):
    _part(conn, "92738")
    run = db.start_run(conn, "census", {}, "abc")
    _measure(conn, run, "92738", engine="occt", extra_d99=None,
             error="ProcessDied", detail="killed mid-render")
    conn.commit()
    row = findings.findings(conn)["rows"][0]
    assert row["error"] == "ProcessDied"
    assert row["part_id"] == "92738"


def test_filters_narrow_without_changing_the_order(conn):
    run = db.start_run(conn, "census", {}, "abc")
    for pid, status, d99 in (("a", "broken", 5.0), ("b", "wontfix", 9.0),
                             ("c", "broken", 1.0)):
        _part(conn, pid, status=status)
        _measure(conn, run, pid, extra_d99=d99)
    conn.commit()
    rows = findings.findings(conn, status="broken")["rows"]
    assert [r["part_id"] for r in rows] == ["a", "c"]


def test_paging_reports_the_whole_count(conn):
    run = db.start_run(conn, "census", {}, "abc")
    for i in range(10):
        _part(conn, f"p{i}")
        _measure(conn, run, f"p{i}", extra_d99=float(i))
    conn.commit()
    page = findings.findings(conn, limit=3, offset=0)
    assert page["total"] == 10 and len(page["rows"]) == 3
    assert page["rows"][0]["part_id"] == "p9"
    assert findings.findings(conn, limit=3, offset=3)["rows"][0]["part_id"] == "p6"
