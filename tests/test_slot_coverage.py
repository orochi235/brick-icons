"""Which parts a fill round spends its hours on.

`never` and `errored` are not the dashboard's `untried` and `failed`, and the
gap between them is the point: a part that ran clean and emitted no drawing
has a measurement row, so this counts it as tried while `coverage_of` falls
through to `untried` for want of anything saying otherwise.
"""
import importlib.util
from pathlib import Path

import pytest

from brick_icons import db

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "slot_coverage", ROOT / "scripts" / "slot-coverage.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "corpus.db")
    yield c
    c.close()


def _part(conn, pid):
    conn.execute("INSERT INTO parts (id, title, category, printed, obsolete, "
                 "status) VALUES (?, 'Brick', 'Brick', 0, 0, 'unreviewed')",
                 (pid,))


_run = 0


def _measure(conn, pid, source, error=None, secs=10.0):
    global _run
    _run += 1
    conn.execute("INSERT INTO runs (id, kind, started, commit_sha, args) VALUES "
                 "(?, 'census', '2026-09-05T09:00:00+00:00', 'abc', '{}')", (_run,))
    conn.execute("INSERT INTO measurements (run_id, part_id, engine, source, "
                 "error, secs) VALUES (?, ?, 'occt', ?, ?, ?)",
                 (_run, pid, source, error, secs))


def _render(conn, pid, source):
    conn.execute("INSERT INTO renders (part_id, source, config_key, made_at, "
                 "path, sha256) VALUES (?, ?, 'k', '2026-09-05T10:00:00+00:00',"
                 " ?, 'a')", (pid, source, f"r/{pid}.svg"))


SLOT = "silhouette-occt"


def _owed(conn):
    return sc.owed(conn, SLOT, sc.corpus(conn, SLOT))


def test_a_part_with_no_row_for_this_slot_is_never_tried(conn):
    _part(conn, "3001")
    conn.commit()
    assert _owed(conn)["never"] == ["3001"]


def test_a_row_under_another_facet_does_not_count_as_tried(conn):
    """Each slot draws its own picture. occt succeeding says nothing about
    whether the silhouette variant was ever asked."""
    _part(conn, "3001")
    _measure(conn, "3001", "occt")
    conn.commit()
    assert _owed(conn)["never"] == ["3001"]


def test_a_part_that_ran_clean_and_drew_nothing_is_not_never_tried(conn):
    """The case the two tools disagree about, and the reason `--only never`
    came up empty on a slot the dashboard showed 69 untried parts for. It was
    asked and it answered; there is nothing for a fill round to try."""
    _part(conn, "3001")
    _measure(conn, "3001", SLOT, error=None, secs=54.9)
    conn.commit()
    o = _owed(conn)
    assert o["never"] == []
    assert o["errored"] == ["3001"]


def test_only_never_takes_nothing_that_has_been_tried(conn):
    _part(conn, "3001")
    _part(conn, "3002")
    _measure(conn, "3002", SLOT, error="ProcessDied")
    conn.commit()
    o = _owed(conn)
    budget = 10 * 3600.0
    assert sc.batch(o, budget, "never") == ["3001"]
    assert sc.batch(o, budget, "errored") == ["3002"]
    # The default spends never-first, then repeats.
    assert sc.batch(o, budget, "all") == ["3001", "3002"]


def test_only_never_is_empty_where_the_whole_gap_is_repeats(conn):
    """silhouette-occt's real state: 95% drawn, and every part of the gap
    already answered. A retry round is worth launching against an engine
    change and not otherwise."""
    _part(conn, "3001")
    _part(conn, "3002")
    _render(conn, "3001", SLOT)
    _measure(conn, "3002", SLOT, error="ProcessDied")
    conn.commit()
    o = _owed(conn)
    assert o["drawn"] == ["3001"]
    assert o["never"] == []
    assert sc.batch(o, 10 * 3600.0, "never") == []


def test_a_drawn_part_is_owed_nothing_however_it_was_measured(conn):
    _part(conn, "3001")
    _render(conn, "3001", SLOT)
    _measure(conn, "3001", SLOT, error="TimeoutError")
    conn.commit()
    o = _owed(conn)
    assert o["drawn"] == ["3001"]
    assert o["never"] == [] and o["errored"] == []
