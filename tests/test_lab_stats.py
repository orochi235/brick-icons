"""The corpus dashboard's tallies."""
import json

import pytest

from brick_icons import db
from brick_icons.lab import stats, tally


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
             extra_d99=None, finished="2026-09-05T09:30:00+00:00", phases=None,
             build=None):
    global _run
    _run += 1
    conn.execute("INSERT INTO runs (id, kind, started, finished, commit_sha, "
                 "args) VALUES (?, 'census', '2026-09-05T09:00:00+00:00', ?, "
                 "'abc1234', '{}')", (_run, finished))
    conn.execute("INSERT INTO measurements (run_id, part_id, engine, source, "
                 "error, secs, extra_d99, phases, build) VALUES "
                 "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (_run, pid, engine, source or f"silhouette-{engine}", error, secs,
                  extra_d99, json.dumps(phases) if phases else None, build))


def _attempt(conn, pid, source, secs, commit_sha="f5e2883"):
    """A slot that draws but never scores records what it cost here."""
    global _run
    _run += 1
    conn.execute("INSERT INTO runs (id, kind, started, finished, commit_sha, "
                 "args) VALUES (?, 'store', '2026-09-05T09:00:00+00:00', "
                 "'2026-09-05T09:30:00+00:00', ?, '{}')", (_run, commit_sha))
    conn.execute("INSERT INTO attempts (run_id, part_id, source, state, secs) "
                 "VALUES (?, ?, ?, 'stored', ?)", (_run, pid, source, secs))


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
    _part(conn, "s1", category="|")
    conn.commit()
    assert stats.stats(conn)["set"]["size"] == 2
    assert stats.stats(conn, out_of_scope=False)["set"]["size"] == 1


def test_obsolete_parts_can_be_dropped_without_narrowing_to_them(conn):
    # `kind="obsolete"` looks at nothing else; the flag says whether the class
    # is in the set at all, which is the sidebar's question.
    _part(conn, "3001")
    _part(conn, "3002", obsolete=1)
    conn.commit()
    assert stats.stats(conn)["set"]["size"] == 2
    assert stats.stats(conn, obsolete=False)["set"]["size"] == 1
    assert stats.stats(conn, kind="obsolete")["set"]["size"] == 1


def test_a_part_ldraw_gives_a_preview_turn_can_be_dropped(conn):
    _part(conn, "3001")
    _part(conn, "87544dq0")
    conn.execute("UPDATE parts SET preview = '16 0 0 0 -1 0 0 0 1 0 0 0 -1' "
                 "WHERE id = '87544dq0'")
    conn.commit()
    assert stats.stats(conn)["set"]["size"] == 2
    assert stats.stats(conn, posed=False)["set"]["size"] == 1


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


def test_two_badges_on_one_axis_are_alternatives_and_two_axes_narrow(conn):
    # The wall's legend groups the badges into axes and this has to agree with
    # it: no part is both technic and duplo, so reading the pair as "carries
    # both" answered every such pick with an empty wall.
    _part(conn, "t1", category="=Technic")
    _part(conn, "d1", category="Duplo")
    _part(conn, "t2", category="=Technic", printed=1)
    conn.commit()
    size = lambda **kw: stats.stats(conn, **kw)["set"]["size"]
    assert size(badges=["technic"]) == 2
    assert size(badges=["technic", "duplo"]) == 3
    assert size(badges=["technic", "printed"]) == 1


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
    _render(conn, "3001", "silhouette-naive")
    _measure(conn, "3002", "naive", error="TimeoutError")
    conn.commit()
    rows = {r["source"]: r for r in stats.stats(conn)["coverage"]}
    assert rows["silhouette-naive"]["counts"]["drawn"] == 1
    assert rows["silhouette-naive"]["counts"]["timeout"] == 1
    assert rows["silhouette-naive"]["size"] == 2


def test_the_decal_slot_does_not_count_plain_parts_as_never_attempted(conn):
    """The chart read as mostly undone for decal because every unprinted part
    landed in `untried`, when the slot was never going to draw them."""
    _part(conn, "3001")
    _part(conn, "3001p01", printed=1)
    _render(conn, "3001p01", "decal")
    conn.commit()
    counts = {r["source"]: r["counts"] for r in stats.stats(conn)["coverage"]}
    assert counts["decal"]["notApplicable"] == 1
    assert counts["decal"]["untried"] == 0
    assert counts["decal"]["drawn"] == 1


def test_a_slot_that_draws_everything_marks_nothing_inapplicable(conn):
    _part(conn, "3001")
    _render(conn, "3001", "silhouette-naive")
    _part(conn, "3002")
    conn.commit()
    counts = stats.stats(conn)["coverage"][0]["counts"]
    assert counts["notApplicable"] == 0
    assert counts["untried"] == 1


def test_a_slot_reports_every_label_even_at_zero(conn):
    _part(conn, "3001")
    _render(conn, "3001", "silhouette-naive")
    conn.commit()
    counts = stats.stats(conn)["coverage"][0]["counts"]
    assert set(counts) == set(stats.COVERAGE_ORDER)
    assert counts["failed"] == 0


def test_coverage_counts_only_the_working_set(conn):
    _part(conn, "3001")
    _part(conn, "s1", category="|")
    _render(conn, "3001", "silhouette-naive")
    _render(conn, "s1", "silhouette-naive")
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
        _measure(conn, f"300{i}", "occt", secs=secs)
    conn.commit()
    row = {r["engine"]: r for r in stats.stats(conn)["speed"]}["occt"]
    assert row["n"] == 4
    assert row["total"] == 106.0
    assert row["median"] == 2.5
    assert row["max"] == 100.0
    assert sum(b["n"] for b in row["bins"]) == 4


def test_speed_buckets_seconds_evenly(conn):
    for i, secs in enumerate([0.5, 2.0, 3.9, 61.0, 4000.0]):
        _part(conn, f"300{i}")
        _measure(conn, f"300{i}", "occt", secs=secs)
    conn.commit()
    bins = {r["engine"]: r for r in stats.stats(conn)["speed"]}["occt"]["bins"]
    widths = {round(b["to"] - b["from"], 3) for b in bins if b["to"] is not None}
    assert widths == {stats.SECS_BUCKET}
    assert bins[-1] == {"from": stats.SECS_TOP, "to": None, "n": 2}
    assert [b["n"] for b in bins[:3]] == [1, 2, 0]


def test_speed_ignores_a_part_outside_the_set(conn):
    _part(conn, "3001")
    _part(conn, "s1", category="|")
    _measure(conn, "3001", "occt", secs=1.0)
    _measure(conn, "s1", "occt", secs=50.0)
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


# -- running and shape ----------------------------------------------------

def test_an_unfinished_run_makes_the_payload_say_so(conn):
    _part(conn, "3001")
    _measure(conn, "3001", "naive", secs=1.0, finished=None)
    conn.commit()
    assert stats.stats(conn)["running"] is True


def test_a_corpus_with_every_run_finished_is_not_running(conn):
    _part(conn, "3001")
    _measure(conn, "3001", "naive", secs=1.0)
    conn.commit()
    assert stats.stats(conn)["running"] is False


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


# -- where the seconds went -----------------------------------------------

def test_phases_are_totalled_per_engine_over_the_set(conn):
    _part(conn, "3001")
    _part(conn, "3002")
    _measure(conn, "3001", "occt", secs=2.0, phases={
        "render": 1.0, "rasterize": 0.4, "truth_mask": 0.3, "compare": 0.3})
    _measure(conn, "3002", "occt", secs=1.0, phases={
        "render": 0.5, "rasterize": 0.2, "truth_mask": 0.2, "compare": 0.1})
    conn.commit()
    row = stats.stats(conn)["phases"][0]
    assert row["engine"] == "occt"
    assert row["n"] == 2
    assert row["totals"]["render"] == pytest.approx(1.5)
    assert row["totals"]["rasterize"] == pytest.approx(0.6)
    assert row["total"] == pytest.approx(sum(row["totals"].values()))


def test_a_measurement_without_phases_is_not_counted(conn):
    _part(conn, "3001")
    _part(conn, "3002")
    _measure(conn, "3001", "occt", secs=2.0, phases={"render": 1.0})
    _measure(conn, "3002", "occt", secs=9.0)
    conn.commit()
    row = stats.stats(conn)["phases"][0]
    assert row["n"] == 1
    assert row["totals"]["render"] == pytest.approx(1.0)


def test_phases_count_only_the_working_set(conn):
    _part(conn, "3001")
    _part(conn, "3002", category="Sticker")
    _measure(conn, "3001", "occt", secs=1.0, phases={"render": 0.5})
    _measure(conn, "3002", "occt", secs=1.0, phases={"render": 0.9})
    conn.commit()
    row = stats.stats(conn, excluded=("Sticker",))["phases"][0]
    assert row["n"] == 1
    assert row["totals"]["render"] == pytest.approx(0.5)


def test_an_engine_with_no_phases_at_all_is_not_a_row(conn):
    _part(conn, "3001")
    _measure(conn, "3001", "naive", secs=1.0)
    conn.commit()
    assert stats.stats(conn)["phases"] == []


# -- the render's own split, which most rows predate ----------------------

def _at(nodes, path):
    """The node at `path` in a phase tree, or None."""
    for node in nodes or ():
        if node["path"] == path:
            return node
        found = _at(node["children"], path)
        if found:
            return found
    return None


def test_the_split_reports_its_own_smaller_n(conn):
    _part(conn, "3001")
    _part(conn, "3002")
    _measure(conn, "3001", "occt", secs=1.0, phases={
        "render": 1.0, "geometry": 0.4, "decoration": 0.1, "fill": 0.2})
    _measure(conn, "3002", "occt", secs=1.0, phases={"render": 2.0})
    conn.commit()
    row = stats.stats(conn)["phases"][0]
    assert row["n"] == 2
    assert row["split"]["n"] == 1
    assert _at(row["split"]["nodes"], "render/geometry")["secs"] \
        == pytest.approx(0.4)
    # The row that never named a split contributes nothing to it -- its 2.0s
    # of render would otherwise land in `rest` and swamp the band.
    assert _at(row["split"]["nodes"], "render/rest")["secs"] == pytest.approx(0.3)
    assert row["split"]["total"] == pytest.approx(1.0)


def test_rest_is_the_part_of_render_the_split_does_not_name(conn):
    _part(conn, "3001")
    _measure(conn, "3001", "occt", secs=1.0, phases={
        "render": 1.0, "geometry": 0.4, "fill": 0.2})
    conn.commit()
    nodes = stats.stats(conn)["phases"][0]["split"]["nodes"]
    assert _at(nodes, "render/rest")["secs"] == pytest.approx(0.4)


def test_rounding_noise_does_not_invent_a_rest(conn):
    _part(conn, "3001")
    # Each phase is rounded independently, so the children can out-total the
    # parent by a millisecond. That is noise, not an unnamed stage.
    _measure(conn, "3001", "occt", secs=1.0, phases={
        "render": 0.5, "geometry": 0.31, "fill": 0.2})
    conn.commit()
    nodes = stats.stats(conn)["phases"][0]["split"]["nodes"]
    assert _at(nodes, "render/rest") is None


def test_an_engine_whose_rows_all_predate_the_split_has_none(conn):
    _part(conn, "3001")
    _measure(conn, "3001", "occt", secs=1.0, phases={"render": 1.0, "compare": 0.2})
    conn.commit()
    assert stats.stats(conn)["phases"][0]["split"] is None


# -- naive is the reference, not a candidate -------------------------------

def test_naive_is_left_out_of_timing_phases_and_accuracy(conn):
    """Comparing the two engines here measured a race nobody is running."""
    _part(conn, "3001")
    _measure(conn, "3001", "naive", secs=1.0, extra_d99=9.0,
             phases={"render": 1.0})
    _measure(conn, "3001", "occt", secs=2.0, extra_d99=1.0,
             phases={"render": 2.0})
    conn.commit()
    out = stats.stats(conn)
    assert [r["engine"] for r in out["speed"]] == ["occt"]
    assert [r["engine"] for r in out["error"]] == ["occt"]
    assert [r["engine"] for r in out["phases"]] == ["occt"]


def test_naive_keeps_its_coverage_rows(conn):
    """Coverage says how much of the library each slot has drawn, which is
    still worth seeing for the reference."""
    _part(conn, "3001")
    _render(conn, "3001", "white-naive")
    _render(conn, "3001", "occt")
    conn.commit()
    sources = {r["source"] for r in stats.stats(conn)["coverage"]}
    assert sources == {"white-naive", "occt"}


def test_the_failure_tiles_ignore_the_working_set(conn):
    """The tiles answer "how much of the library is broken", which is not a
    question the Controls should be able to make a smaller number of."""
    _part(conn, "3001")
    _part(conn, "3002", printed=1)
    _render(conn, "3001", "occt")
    _render(conn, "3002", "occt")
    _measure(conn, "3002", "occt", source="occt", error="MemoryError")
    conn.commit()
    tally.take(conn, at="2026-09-10T00:00:00+00:00")
    wide = stats.stats(conn)["failures"]["totals"]
    narrow = stats.stats(conn, kind="base")["failures"]["totals"]
    assert wide["occt"]["bad"] == 1
    assert narrow == wide


# -- what a pass costs, slot by slot --------------------------------------

def _cost(conn, **kw):
    ids, _ = stats.members(conn, **kw)
    return stats._cost(stats._cost_rows(conn), ids)


def test_cost_is_each_slot_s_share_of_running_them_all(conn):
    _part(conn, "3001")
    _part(conn, "3002")
    for pid, occt, white in (("3001", 10.0, 5.0), ("3002", 30.0, 5.0)):
        _measure(conn, pid, "occt", source="occt", secs=occt, build="b1")
        _measure(conn, pid, "occt", source="white-occt", secs=white, build="b1")
    cost = _cost(conn)
    assert cost["n"] == 2
    assert [r["source"] for r in cost["slots"]] == ["occt", "white-occt"]
    assert cost["slots"][0]["share"] == pytest.approx(0.8)
    assert cost["slots"][1]["share"] == pytest.approx(0.2)


def test_cost_ratios_are_taken_against_the_plain_slot(conn):
    """Not against the biggest, which flips the two on a half-percent."""
    _part(conn, "3001")
    _measure(conn, "3001", "occt", source="occt", secs=10.0, build="b1")
    _measure(conn, "3001", "occt", source="white-occt", secs=12.0, build="b1")
    cost = _cost(conn)
    assert cost["base"] == "occt"
    ratios = {r["source"]: r["ratio"] for r in cost["slots"]}
    assert ratios == {"occt": pytest.approx(1.0), "white-occt": pytest.approx(1.2)}


def test_cost_compares_one_build_over_the_parts_it_drew_in_every_slot(conn):
    """A slot's stored seconds span every revision that drew it, and the old
    ones are slow enough to reverse which slot reads as expensive."""
    for pid in ("3001", "3002", "3003"):
        _part(conn, pid)
    # b2 drew both slots over two parts; b1 drew one slot over three, slowly.
    for pid in ("3001", "3002", "3003"):
        _measure(conn, pid, "occt", source="silhouette-occt", secs=90.0, build="b1")
    for pid in ("3001", "3002"):
        _measure(conn, pid, "occt", source="occt", secs=10.0, build="b2")
        _measure(conn, pid, "occt", source="silhouette-occt", secs=5.0, build="b2")
    cost = _cost(conn)
    assert cost["build"] == "b2"
    assert cost["n"] == 2
    assert {r["source"]: round(r["ratio"], 3) for r in cost["slots"]} == {
        "occt": 1.0, "silhouette-occt": 0.5}


def test_a_build_only_one_slot_drew_cannot_be_the_comparison(conn):
    """There is nothing for it to be proportional to."""
    _part(conn, "3001")
    _measure(conn, "3001", "occt", source="occt", secs=10.0, build="b1")
    assert _cost(conn) is None


def test_a_thin_slot_does_not_shrink_the_others(conn):
    """Every slot cut to the parts they ALL share took a 17,611-part
    comparison down to 1,592 the moment a slot that had barely run joined."""
    _part(conn, "3001")
    _part(conn, "3002")
    for pid in ("3001", "3002"):
        _measure(conn, pid, "occt", source="occt", secs=10.0, build="b1")
        _measure(conn, pid, "occt", source="white-occt", secs=4.0, build="b1")
    _measure(conn, "3001", "naive", source="white-naive", secs=99.0, build="b1")
    rows = {r["source"]: r for r in _cost(conn)["slots"]}
    assert rows["white-occt"]["n"] == 2
    assert rows["white-naive"]["n"] == 1
    assert rows["white-naive"]["ratio"] == pytest.approx(9.9)


def test_a_slot_missing_from_the_base_revision_says_where_it_came_from(conn):
    _part(conn, "3001")
    _part(conn, "3002")
    for pid in ("3001", "3002"):
        _measure(conn, pid, "occt", source="occt", secs=10.0, build="b1")
        _measure(conn, pid, "occt", source="white-occt", secs=4.0, build="b0")
    cost = _cost(conn)
    rows = {r["source"]: r for r in cost["slots"]}
    assert cost["build"] == "b1"
    assert rows["occt"]["build"] == "b1"
    assert rows["white-occt"]["build"] == "b0"


def test_a_slot_that_only_ever_attempted_still_costs_something(conn):
    """`decal` draws and never scores, so its seconds are in `attempts`."""
    _part(conn, "3001")
    _part(conn, "3002")
    for pid in ("3001", "3002"):
        _measure(conn, pid, "occt", source="occt", secs=10.0, build="b1")
        _measure(conn, pid, "occt", source="white-occt", secs=4.0, build="b1")
        _render(conn, pid, "decal")
        _attempt(conn, pid, "decal", 2.0)
    rows = {r["source"]: r for r in _cost(conn)["slots"]}
    assert rows["decal"]["n"] == 2
    assert rows["decal"]["ratio"] == pytest.approx(0.2)
    assert rows["decal"]["build"] == "f5e2883"


def test_a_slot_already_measured_is_not_counted_twice_from_attempts(conn):
    _part(conn, "3001")
    _measure(conn, "3001", "occt", source="occt", secs=10.0, build="b1")
    _measure(conn, "3001", "occt", source="white-occt", secs=4.0, build="b1")
    _render(conn, "3001", "white-occt")
    _attempt(conn, "3001", "white-occt", 99.0)
    rows = {r["source"]: r for r in _cost(conn)["slots"]}
    assert rows["white-occt"]["ratio"] == pytest.approx(0.4)


def test_cost_counts_only_the_working_set(conn):
    _part(conn, "3001")
    _part(conn, "3002", obsolete=1)
    for pid in ("3001", "3002"):
        _measure(conn, pid, "occt", source="occt", secs=10.0, build="b1")
        _measure(conn, pid, "occt", source="white-occt", secs=5.0, build="b1")
    assert _cost(conn)["n"] == 2
    assert _cost(conn, kind="base")["n"] == 1


def test_a_measurement_with_no_build_cannot_be_placed_on_a_revision(conn):
    _part(conn, "3001")
    _measure(conn, "3001", "occt", source="occt", secs=10.0)
    _measure(conn, "3001", "occt", source="white-occt", secs=5.0)
    assert _cost(conn) is None
