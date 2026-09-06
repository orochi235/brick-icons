"""The corpus dashboard's tallies."""
import json

import pytest

from brick_icons import db
from brick_icons.lab import stats


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "corpus.db")
    yield c
    c.close()


def _part(conn, pid, title="Brick", category="Brick", printed=0, obsolete=0):
    conn.execute("INSERT INTO parts (id, title, category, printed, obsolete, "
                 "status) VALUES (?, ?, ?, ?, ?, 'unreviewed')",
                 (pid, title, category, printed, obsolete))


def _render(conn, pid, source, sha="a"):
    conn.execute("INSERT INTO renders (part_id, source, config_key, made_at, "
                 "path, sha256) VALUES (?, ?, 'k', '2026-09-05T10:00:00+00:00',"
                 " ?, ?)", (pid, source, f"r/{pid}.svg", sha))


_run = 0


def _measure(conn, pid, engine, source=None, error=None, secs=None,
             extra_d99=None, finished="2026-09-05T09:30:00+00:00"):
    global _run
    _run += 1
    conn.execute("INSERT INTO runs (id, kind, started, finished, commit_sha, "
                 "args) VALUES (?, 'census', '2026-09-05T09:00:00+00:00', ?, "
                 "'abc1234', '{}')", (_run, finished))
    conn.execute("INSERT INTO measurements (run_id, part_id, engine, source, "
                 "error, secs, extra_d99) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (_run, pid, engine, source or f"census-{engine}", error, secs,
                  extra_d99))


def _defect(conn, did, pid, engines):
    conn.execute("INSERT INTO defects (id, part_id, engines, status, title, "
                 "filed) VALUES (?, ?, ?, 'open', 't', '2026-09-05')",
                 (did, pid, json.dumps(engines)))


# -- the working set ------------------------------------------------------

def test_the_set_is_every_part_by_default_but_redirects(conn):
    _part(conn, "3001")
    _part(conn, "3002", title="~Moved to 3001")
    conn.commit()
    out = stats.stats(conn)
    assert out["set"]["size"] == 1
    assert out["set"]["total"] == 2


def test_redirects_come_back_when_asked_for(conn):
    _part(conn, "3001")
    _part(conn, "3002", title="~Moved to 3001")
    conn.commit()
    assert stats.stats(conn, moved=True)["set"]["size"] == 2


def test_out_of_scope_parts_can_be_dropped(conn):
    _part(conn, "3001")
    _part(conn, "s1", category="Sticker")
    conn.commit()
    assert stats.stats(conn)["set"]["size"] == 2
    assert stats.stats(conn, out_of_scope=False)["set"]["size"] == 1


def test_a_category_can_be_excluded_by_its_clean_name(conn):
    _part(conn, "3001", category="Brick")
    _part(conn, "t1", category="=Technic")
    conn.commit()
    assert stats.stats(conn, excluded=["Technic"])["set"]["size"] == 1


def test_a_badge_narrows_to_parts_carrying_it(conn):
    _part(conn, "3001", category="Brick")
    _part(conn, "t1", category="=Technic")
    conn.commit()
    assert stats.stats(conn, badges=["technic"])["set"]["size"] == 1


def test_every_badge_asked_for_has_to_be_present(conn):
    _part(conn, "t1", category="=Technic")
    conn.commit()
    assert stats.stats(conn, badges=["technic"])["set"]["size"] == 1
    assert stats.stats(conn, badges=["technic", "duplo"])["set"]["size"] == 0


def test_the_kind_filters_pick_one_class_of_part(conn):
    _part(conn, "3001")
    _part(conn, "3001p01", printed=1)
    conn.commit()
    assert stats.stats(conn, kind="printed")["set"]["size"] == 1
    assert stats.stats(conn, kind="base")["set"]["size"] == 1
    assert stats.stats(conn, kind="all")["set"]["size"] == 2


# -- coverage -------------------------------------------------------------

def test_coverage_is_counted_per_slot_over_the_set(conn):
    _part(conn, "3001")
    _part(conn, "3002")
    _render(conn, "3001", "census-naive")
    _measure(conn, "3002", "naive", error="TimeoutError")
    conn.commit()
    rows = {r["source"]: r for r in stats.stats(conn)["coverage"]}
    assert rows["census-naive"]["counts"]["drawn"] == 1
    assert rows["census-naive"]["counts"]["timeout"] == 1
    assert rows["census-naive"]["size"] == 2


def test_a_slot_reports_every_label_even_at_zero(conn):
    _part(conn, "3001")
    _render(conn, "3001", "census-naive")
    conn.commit()
    counts = stats.stats(conn)["coverage"][0]["counts"]
    assert set(counts) == set(stats.COVERAGE_ORDER)
    assert counts["failed"] == 0


def test_coverage_counts_only_the_working_set(conn):
    _part(conn, "3001")
    _part(conn, "s1", category="Sticker")
    _render(conn, "3001", "census-naive")
    _render(conn, "s1", "census-naive")
    conn.commit()
    rows = stats.stats(conn, out_of_scope=False)["coverage"]
    assert rows[0]["counts"]["drawn"] == 1


def test_a_slot_with_no_renders_is_not_a_slot(conn):
    _part(conn, "3001")
    conn.commit()
    assert stats.stats(conn)["coverage"] == []


# -- speed and error ------------------------------------------------------

def test_speed_reports_the_spread_per_engine(conn):
    for i, secs in enumerate([1.0, 2.0, 3.0, 100.0]):
        _part(conn, f"300{i}")
        _measure(conn, f"300{i}", "naive", secs=secs)
    conn.commit()
    row = {r["engine"]: r for r in stats.stats(conn)["speed"]}["naive"]
    assert row["n"] == 4
    assert row["total"] == 106.0
    assert row["median"] == 2.5
    assert row["max"] == 100.0
    assert sum(b["n"] for b in row["bins"]) == 4


def test_speed_ignores_a_part_outside_the_set(conn):
    _part(conn, "3001")
    _part(conn, "s1", category="Sticker")
    _measure(conn, "3001", "naive", secs=1.0)
    _measure(conn, "s1", "naive", secs=50.0)
    conn.commit()
    row = stats.stats(conn, out_of_scope=False)["speed"][0]
    assert row["n"] == 1
    assert row["total"] == 1.0


def test_an_engine_reports_how_far_off_its_renders_were(conn):
    _part(conn, "3001")
    _part(conn, "3002")
    _measure(conn, "3001", "occt", extra_d99=1.0)
    _measure(conn, "3002", "occt", extra_d99=3.0)
    conn.commit()
    row = stats.stats(conn)["error"][0]
    assert row["engine"] == "occt"
    assert row["d99"]["median"] == 2.0


# -- runs and shape -------------------------------------------------------

def test_a_run_says_what_it_measured_and_whether_it_is_open(conn):
    _part(conn, "3001")
    _measure(conn, "3001", "naive", secs=1.0, finished=None)
    conn.commit()
    run = stats.stats(conn)["runs"][0]
    assert run["parts"] == 1
    assert run["open"] is True
    assert run["commit_sha"] == "abc1234"


def test_shape_counts_the_set_by_category_and_kind(conn):
    _part(conn, "3001", category="Brick")
    _part(conn, "t1", category="=Technic")
    _part(conn, "3001p01", category="Brick", printed=1)
    conn.commit()
    shape = stats.stats(conn)["shape"]
    assert dict(shape["categories"])["Brick"] == 2
    assert shape["kinds"]["printed"] == 1


def test_shape_says_how_many_parts_carry_outside_facts(conn):
    _part(conn, "3001")
    _part(conn, "3002")
    conn.execute("INSERT INTO part_years (part_id, year_from, year_to, sets, "
                 "colors, matched) VALUES ('3001', 1974, 1990, 12, 3, 'x')")
    conn.commit()
    assert stats.stats(conn)["shape"]["dated"] == 1


def test_the_tallies_say_when_they_were_read(conn):
    _part(conn, "3001")
    conn.commit()
    assert stats.stats(conn)["as_of"].endswith("+00:00")
