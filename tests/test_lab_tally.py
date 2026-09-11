"""The failure tallies: what did not draw, corpus-wide and over time."""
import json
import subprocess

import pytest

from brick_icons import db
from brick_icons.lab import tally


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "corpus.db")
    yield c
    c.close()


def _part(conn, pid, title="Brick", category="Brick", printed=0):
    conn.execute("INSERT INTO parts (id, title, category, printed, obsolete, "
                 "status) VALUES (?, ?, ?, ?, 0, 'unreviewed')",
                 (pid, title, category, printed))


def _render(conn, pid, source, sha="a"):
    conn.execute("INSERT INTO renders (part_id, source, config_key, made_at, "
                 "path, sha256) VALUES (?, ?, 'k', '2026-09-05T10:00:00+00:00',"
                 " ?, ?)", (pid, source, f"r/{pid}.svg", sha))


_run = 0


def _measure(conn, pid, engine, source, error=None, build=None):
    global _run
    _run += 1
    conn.execute("INSERT INTO runs (id, kind, started, commit_sha, args) "
                 "VALUES (?, 'census', '2026-09-05T09:00:00+00:00', 'abc', '{}')",
                 (_run,))
    conn.execute("INSERT INTO measurements (run_id, part_id, engine, source, "
                 "error, build) VALUES (?, ?, ?, ?, ?, ?)",
                 (_run, pid, engine, source, error, build))


def _attempt(conn, pid, source, state):
    global _run
    _run += 1
    conn.execute("INSERT INTO runs (id, kind, started, commit_sha, args) "
                 "VALUES (?, 'store', '2026-09-05T09:00:00+00:00', 'abc', "
                 "'{\"dir\": \"out/store\"}')", (_run,))
    conn.execute("INSERT INTO attempts (run_id, part_id, source, state) "
                 "VALUES (?, ?, ?, ?)", (_run, pid, source, state))


# -- what counts as bad ----------------------------------------------------

def test_a_slot_that_ran_and_drew_nothing_is_a_failure_not_untried(conn):
    """The wall has always read it this way; the dashboard did not, and the
    disagreement was 2,480 decal parts reported as work still owed."""
    _part(conn, "3001", printed=1)
    _render(conn, "3002", "decal")
    _part(conn, "3002", printed=1)
    _attempt(conn, "3001", "decal", "none")
    conn.commit()
    decal = next(r for r in tally.count(conn) if r["source"] == "decal")
    assert decal["failed"] == 1
    assert decal["untried"] == 0


def test_a_defect_is_not_a_bad_piece(conn):
    """A defect drew something and is wrong about it. Folding the two together
    would report a fixed crash and a newly filed defect as no change."""
    _part(conn, "3001")
    _render(conn, "3001", "occt")
    conn.execute("INSERT INTO defects (id, part_id, engines, status, title, "
                 "filed) VALUES ('d1', '3001', ?, 'open', 't', '2026-09-05')",
                 (json.dumps(["occt"]),))
    conn.commit()
    row = next(r for r in tally.count(conn) if r["source"] == "occt")
    assert row["defect"] == 1
    assert row["failed"] == 0 and row["timeout"] == 0


def test_a_timeout_and_an_error_are_counted_apart(conn):
    _part(conn, "3001")
    _part(conn, "3002")
    _render(conn, "3001", "occt")
    _render(conn, "3002", "occt")
    _measure(conn, "3001", "occt", "occt", error="TimeoutError")
    _measure(conn, "3002", "occt", "occt", error="MemoryError")
    conn.commit()
    row = next(r for r in tally.count(conn) if r["source"] == "occt")
    assert (row["timeout"], row["failed"]) == (1, 1)


def test_out_of_scope_and_moved_parts_are_not_in_the_population(conn):
    _part(conn, "3001")
    _part(conn, "9001", category="|")
    _part(conn, "9002", title="~Moved to 3001")
    _render(conn, "3001", "occt")
    conn.commit()
    assert tally.in_scope(conn) == {"3001"}
    assert next(r for r in tally.count(conn))["size"] == 1


# -- the tiles -------------------------------------------------------------

def test_the_occt_tile_counts_a_part_once_across_every_facet(conn):
    """The tile answers "how many pieces are bad", not "how many slot-part
    pairs are" -- a part failing in three facets is one bad piece."""
    _part(conn, "3001")
    for source in ("occt", "white-occt", "silhouette-occt"):
        _render(conn, "3002", source)
        _measure(conn, "3001", "occt", source, error="MemoryError")
    _part(conn, "3002")
    conn.commit()
    tally.take(conn, at="2026-09-10T00:00:00+00:00")
    assert tally.totals(conn)["occt"]["bad"] == 1


def test_decal_and_occt_do_not_share_a_failure_mode(conn):
    _part(conn, "3001", printed=1)
    _part(conn, "3002")
    _render(conn, "3002", "occt")
    _render(conn, "9999", "decal")
    _part(conn, "9999", printed=1)
    _attempt(conn, "3001", "decal", "none")
    _measure(conn, "3002", "occt", "occt", error="TimeoutError")
    conn.commit()
    tally.take(conn, at="2026-09-10T00:00:00+00:00")
    out = tally.totals(conn)
    assert out["decal"] == {"bad": 1, "failed": 1, "timeout": 0}
    assert out["occt"]["timeout"] == 1


# -- the series ------------------------------------------------------------

def test_a_tally_that_has_not_moved_writes_nothing(conn):
    """A watch ingests every half hour. Without this the series is a flat
    line sampled 48 times a day instead of a step function."""
    _part(conn, "3001")
    _render(conn, "3001", "occt")
    conn.commit()
    assert tally.take(conn, at="2026-09-10T00:00:00+00:00") == 1
    assert tally.take(conn, at="2026-09-10T00:30:00+00:00") == 0
    assert len(tally.series(conn)) == 1


def test_a_slot_writes_a_new_row_when_its_count_moves(conn):
    _part(conn, "3001")
    _render(conn, "3001", "occt")
    conn.commit()
    tally.take(conn, at="2026-09-10T00:00:00+00:00")
    _measure(conn, "3001", "occt", "occt", error="MemoryError")
    conn.commit()
    assert tally.take(conn, at="2026-09-10T01:00:00+00:00") == 1
    rows = tally.series(conn)
    assert [r["bad"] for r in rows] == [0, 1]


def test_the_series_is_oldest_first_however_the_rows_went_in(conn):
    for at in ("2026-09-10T02:00:00+00:00", "2026-09-10T01:00:00+00:00"):
        conn.execute(
            "INSERT INTO tallies (taken, source, build, size, drawn, failed, "
            "timeout, defect, untried, not_applicable) "
            "VALUES (?, 'occt', NULL, 1, 0, 1, 0, 0, 0, 0)", (at,))
    conn.commit()
    assert [r["at"] for r in tally.series(conn)] == [
        "2026-09-10T01:00:00+00:00", "2026-09-10T02:00:00+00:00"]


def test_tracked_sources_leaves_naive_out_and_keeps_decal(conn):
    _part(conn, "3001")
    for source in ("occt", "white-occt", "silhouette-naive", "decal", "reference"):
        _render(conn, "3001", source)
    conn.commit()
    assert tally.tracked_sources(conn) == ["decal", "occt", "white-occt"]


# -- the build prefix ------------------------------------------------------

def test_by_build_dates_a_revision_from_git(conn):
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    _part(conn, "3001")
    _render(conn, "3001", "occt")
    _measure(conn, "3001", "occt", "occt", error="MemoryError",
             build=f"1214.{head}")
    conn.commit()
    rows = tally.by_build(conn)
    assert len(rows) == 1
    assert rows[0]["bad"] == 1 and rows[0]["at"].startswith("20")


def test_by_build_drops_a_revision_this_checkout_has_never_seen(conn):
    """A build drawn on a branch that was never merged has no place on a time
    axis, and guessing a date for it would put a real number in a wrong year."""
    _part(conn, "3001")
    _render(conn, "3001", "occt")
    _measure(conn, "3001", "occt", "occt", build="999.deadbee")
    conn.commit()
    assert tally.by_build(conn) == []


def test_by_build_drops_a_revision_that_barely_ran(conn):
    """A slot's bring-up run is not its failure rate. white-occt's first
    revision drew 277 parts of the 20,213 it draws now, 58% of them failed,
    and that one point set the chart's axis to 60%."""
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    for i in range(20):
        _part(conn, f"30{i:02d}")
        _render(conn, f"30{i:02d}", "occt")
        _measure(conn, f"30{i:02d}", "occt", "occt", build=f"200.{head}")
    _part(conn, "9999")
    _render(conn, "9999", "occt")
    _measure(conn, "9999", "occt", "occt", error="MemoryError",
             build=f"100.{head}")
    conn.commit()
    assert [r["build"] for r in tally.by_build(conn)] == [f"200.{head}"]


def test_a_dirty_build_is_dated_by_the_commit_it_sat_on(conn):
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    _part(conn, "3001")
    _render(conn, "3001", "occt")
    _measure(conn, "3001", "occt", "occt", build=f"1214.{head}+")
    conn.commit()
    assert len(tally.by_build(conn)) == 1


# -- surviving a rebuild ---------------------------------------------------

def test_tallies_are_carried_across_a_rebuild(tmp_path):
    """Nothing on disk re-derives these: the logs only say how it stands now."""
    path = tmp_path / "corpus.db"
    conn = db.connect(path)
    conn.execute(
        "INSERT INTO tallies (taken, source, build, size, drawn, failed, "
        "timeout, defect, untried, not_applicable) VALUES "
        "('2026-09-01T00:00:00+00:00', 'occt', '1.abc', 10, 7, 2, 1, 0, 0, 0)")
    conn.commit()
    conn.close()

    carried = db._stored_tallies(path)
    assert carried and carried[0][1] == "occt"
    assert carried[0][5] == 2


def test_each_facet_follows_its_own_failures_not_the_engines(conn):
    """Pooled per engine, all four occt facets report one number and draw as
    one line four times over. The point of a line per facet is to diverge."""
    _part(conn, "3001")
    _part(conn, "3002")
    for source in ("occt", "white-occt"):
        _render(conn, "3001", source)
        _render(conn, "3002", source)
    _measure(conn, "3001", "occt", "white-occt", error="MemoryError")
    _measure(conn, "3002", "occt", "occt", error="TimeoutError")
    conn.commit()
    tally.take(conn, at="2026-09-10T00:00:00+00:00")
    bad = {r["source"]: r["bad"] for r in tally.series(conn)}
    assert bad["white-occt"] == 1
    assert bad["occt"] == 1
    # The engine-pooled coverage columns see both failures in both facets;
    # the slot columns do not, which is the whole reason they exist.
    pooled = {r["source"]: r["failed"] + r["timeout"] for r in tally.count(conn)}
    assert pooled["occt"] == 2 and pooled["white-occt"] == 2


def test_the_tiles_read_the_last_tally_rather_than_recounting(conn):
    """Counting is a pass over every part in every slot; doing it per page
    load put ten seconds on the dashboard. It also keeps the tile and the
    chart's last point saying the same number."""
    _part(conn, "3001")
    _render(conn, "3001", "occt")
    _measure(conn, "3001", "occt", "occt", error="MemoryError")
    conn.commit()
    assert tally.totals(conn)["occt"]["bad"] == 0        # nothing tallied yet
    tally.take(conn, at="2026-09-10T00:00:00+00:00")
    out = tally.totals(conn)
    assert out["occt"]["bad"] == 1
    assert out["taken"] == "2026-09-10T00:00:00+00:00"


# -- the replayed history --------------------------------------------------

def test_history_carries_a_verdict_forward_over_the_ingests_after_it(conn):
    """The point of the replay: an ingest of one part moves the count by one
    and leaves everything else standing, where `by_build` would report that
    ingest as a rate over the single part it touched."""
    _part(conn, "3001")
    _part(conn, "3002")
    _render(conn, "3001", "occt")
    _render(conn, "3002", "occt")
    _measure(conn, "3001", "occt", "occt", error="ProcessDied")
    _measure(conn, "3002", "occt", "occt", error="ProcessDied")
    _measure(conn, "3001", "occt", "occt")
    steps = [r["bad"] for r in tally.history(conn, ["occt"])]
    assert steps == [1, 2, 1]


def test_history_ends_where_the_live_count_stands(conn):
    """The replay reads the runs in the order `count` picks its latest row
    from, so the two cannot drift -- a seam between them would read as a
    regression at whichever ingest the tallies started."""
    _part(conn, "3001", printed=1)
    _part(conn, "3002")
    _part(conn, "3003", printed=1)
    _render(conn, "3002", "occt")
    # `count` reads its slots off `renders`, so decal needs one to be a slot.
    _render(conn, "3003", "decal")
    _measure(conn, "3001", "occt", "occt", error="TimeoutError")
    _measure(conn, "3002", "occt", "occt", error="ProcessDied")
    _attempt(conn, "3001", "decal", "none")
    live = {r["source"]: r["slot_failed"] + r["slot_timeout"]
            for r in tally.count(conn)}
    last = {}
    for row in tally.history(conn):
        last[row["source"]] = row["bad"]
    assert last["occt"] == live["occt"] == 2
    assert last["decal"] == live["decal"] == 1


def test_history_reads_an_attempt_that_drew_nothing_as_a_failure(conn):
    # decal files no measurements at all, so without this its line is flat at
    # whatever handful of parts errored outright.
    _part(conn, "3001", printed=1)
    _attempt(conn, "3001", "decal", "none")
    assert [r["bad"] for r in tally.history(conn, ["decal"])] == [1]
    _attempt(conn, "3001", "decal", "stored")
    assert [r["bad"] for r in tally.history(conn, ["decal"])] == [1, 0]


def test_history_names_the_newest_revision_an_ingest_carried(conn):
    # Run 1 in the live corpus landed rows from six builds at once. The step
    # says which revision the slot ended that ingest holding, not the first
    # one the rows happened to name.
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    _part(conn, "3001")
    _part(conn, "3002")
    conn.execute("INSERT INTO runs (id, kind, started, commit_sha, args) "
                 "VALUES (900, 'census', '2026-09-05T09:00:00+00:00', 'abc', '{}')")
    for pid, build in (("3001", f"707.{head}"), ("3002", f"959.{head}")):
        conn.execute("INSERT INTO measurements (run_id, part_id, engine, "
                     "source, error, build) VALUES (900, ?, 'occt', 'occt', "
                     "NULL, ?)", (pid, build))
    rows = tally.history(conn, ["occt"])
    assert [r["build"] for r in rows] == [f"959.{head}"]
