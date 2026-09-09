"""The corpus wall's cell list."""
import json

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


def _render(conn, pid, sha, made_at, source="silhouette-naive"):
    conn.execute("INSERT INTO renders (part_id, source, config_key, made_at, "
                 "path, sha256) VALUES (?, ?, 'k', ?, ?, ?)",
                 (pid, source, made_at, f"renders/{source}/{pid}.svg", sha))


def _defect(conn, defect_id, pid, engines, status="open", checked=None):
    conn.execute("INSERT INTO defects (id, part_id, engines, status, title, "
                 "checked, filed) "
                 "VALUES (?, ?, ?, ?, 't', ?, '2026-09-05T00:00:00+00:00')",
                 (defect_id, pid, json.dumps(engines), status,
                  json.dumps(checked) if checked else None))


_run_id = 0


def _measure(conn, pid, engine, error=None, source=None):
    global _run_id
    _run_id += 1
    conn.execute("INSERT INTO runs (id, kind, started, commit_sha, args) "
                 "VALUES (?, 'census', '2026-09-05T09:00:00+00:00', 'abc', '{}')",
                 (_run_id,))
    conn.execute("INSERT INTO measurements (run_id, part_id, engine, source, "
                 "error) VALUES (?, ?, ?, ?, ?)",
                 (_run_id, pid, engine, source or f"silhouette-{engine}", error))


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
    assert cells.cells(conn, source="silhouette-naive")["cells"][0]["sha"] is None
    assert cells.cells(conn, source="naive")["cells"][0]["sha"] == "deadbeef"


def test_the_version_is_the_newest_render(conn):
    _part(conn, "3001")
    _part(conn, "3004")
    _render(conn, "3001", "a", "2026-09-05T10:00:00+00:00")
    _render(conn, "3004", "b", "2026-09-05T11:00:00+00:00")
    conn.commit()
    # Two halves: the newest render, then a stamp over what has been judged.
    drawn, _, stamp = cells.cells(conn)["version"].partition("|")
    assert drawn == "2026-09-05T11:00:00+00:00"
    assert stamp


def test_the_version_is_empty_with_no_renders(conn):
    _part(conn, "3001")
    conn.commit()
    assert cells.cells(conn)["version"].startswith("|")


def test_a_defect_moves_the_version_and_comes_back_in_the_delta(conn):
    _part(conn, "3001")
    _render(conn, "3001", "a", "2026-09-05T10:00:00+00:00")
    conn.commit()
    before = cells.cells(conn)["version"]
    assert cells.cells(conn, since=before)["cells"] == []
    # Nothing was drawn, so the render half cannot carry this -- which is why
    # filing a defect used to leave the cell stale until a reload.
    conn.execute(
        "INSERT INTO defects (id, part_id, engines, status, title, filed) "
        "VALUES ('3001-x', '3001', '[\"naive\"]', 'open', 'x', '2026-09-09')")
    conn.commit()
    after = cells.cells(conn)
    assert after["version"] != before
    assert [c["id"] for c in cells.cells(conn, since=before)["cells"]] == ["3001"]


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


def test_a_census_slot_reads_its_engine_s_measurements(conn):
    # renders.source is a slot; measurements.engine is an engine. Without the
    # mapping every metric joins to nothing and the wall sorts on all-None.
    assert cells.engine_for("silhouette-naive") == "naive"
    assert cells.engine_for("silhouette-occt") == "occt"
    assert cells.engine_for("naive") == "naive"


def test_a_cell_carries_the_metric_from_its_slot_s_engine(conn):
    _part(conn, "3001")
    _render(conn, "3001", "a", "2026-09-05T10:00:00+00:00")
    conn.execute("INSERT INTO runs (id, kind, started, commit_sha, args) "
                 "VALUES (1, 'census', '2026-09-05T09:00:00+00:00', 'abc', '{}')")
    conn.execute("INSERT INTO measurements (run_id, part_id, engine, source, "
                 "extra_d99, secs) "
                 "VALUES (1, '3001', 'naive', 'silhouette-naive', 4.5, 12.0)")
    conn.commit()
    cell = cells.cells(conn, source="silhouette-naive")["cells"][0]
    assert cell["extra_d99"] == 4.5
    assert cell["secs"] == 12.0


def test_a_delta_with_nothing_new_is_empty(conn):
    _part(conn, "3001")
    _render(conn, "3001", "a", "2026-09-05T10:00:00+00:00")
    conn.commit()
    body = cells.cells(conn, since="2026-09-05T12:00:00+00:00")
    assert body["cells"] == []
    assert body["count"] == 1


def test_a_part_with_no_defects_reports_none_open(conn):
    _part(conn, "3001")
    conn.commit()
    cell = cells.cells(conn, source="silhouette-naive")["cells"][0]
    assert cell["open_defects"] == 0
    assert cell["elsewhere"] == []


def test_a_defect_naming_this_engine_counts_here_only(conn):
    _part(conn, "3001")
    _defect(conn, "d1", "3001", ["naive"])
    conn.commit()
    cell = cells.cells(conn, source="silhouette-naive")["cells"][0]
    assert cell["open_defects"] == 1
    assert cell["elsewhere"] == []


def test_a_defect_naming_another_engine_counts_elsewhere_only(conn):
    _part(conn, "3001")
    _defect(conn, "d1", "3001", ["occt"])
    conn.commit()
    cell = cells.cells(conn, source="silhouette-naive")["cells"][0]
    assert cell["open_defects"] == 0
    assert cell["elsewhere"] == ["defect"]


def test_a_fixed_defect_counts_in_neither(conn):
    _part(conn, "3001")
    _defect(conn, "d1", "3001", ["naive"], status="fixed")
    conn.commit()
    cell = cells.cells(conn, source="silhouette-naive")["cells"][0]
    assert cell["open_defects"] == 0
    assert cell["elsewhere"] == []


def _years(conn, pid, year_from, year_to, sets, matched):
    conn.execute("INSERT INTO part_years (part_id, year_from, year_to, sets, "
                 "colors, matched) VALUES (?, ?, ?, ?, 0, ?)",
                 (pid, year_from, year_to, sets, matched))


def test_a_counted_part_reports_the_sets_it_is_in(conn):
    _part(conn, "3001")
    _years(conn, "3001", 1979, 2026, 320, "exact")
    row = cells.cells(conn)["cells"][0]
    assert row["sets"] == 320
    assert "popular" in row["tags"]


def test_an_estimated_year_reports_no_set_count(conn):
    # `keywords` reads the sets off LDraw's own !KEYWORDS line, so there is no
    # inventory behind the row and its 0 is an absence, not a count. Reported
    # as one it would tag every such part `obscure`, which is how 6,586 parts
    # came to look rare.
    _part(conn, "003238a", title="Sticker Shield", category="Sticker")
    _years(conn, "003238a", 1978, 1981, 0, "keywords")
    row = cells.cells(conn)["cells"][0]
    assert row["year_from"] == 1978
    assert row["sets"] is None
    assert "obscure" not in row["tags"]
    assert "retired" in row["tags"]


def test_a_mould_dated_by_its_prints_reports_no_set_count(conn):
    # 11778 is only ever sold with feathers on it, so its years come from
    # 11778p01 and 11778p02 and there is no inventory behind the row at all.
    # Its 0 is the same absence `keywords` writes, read the other way round:
    # reported as a count it would tag an eagle wing `obscure`.
    _part(conn, "11778", title="Animal Eagle Wing Left")
    _years(conn, "11778", 2013, 2018, 0, "prints")
    row = cells.cells(conn)["cells"][0]
    assert (row["year_from"], row["year_to"]) == (2013, 2018)
    assert row["sets"] is None
    assert "obscure" not in row["tags"]


def test_a_print_does_not_inherit_its_base_part_s_popularity(conn):
    # 3069bp1f is one silver-arched-window print. Its years come from the
    # plain 1 x 2 tile it is struck on, which is fair -- the mould is that
    # old -- but that tile's 5,766 sets are not the print's, and reporting
    # them made a one-set print `popular`.
    _part(conn, "3069bp1f", title="Tile 1 x 2 with Silver Arched Window")
    _years(conn, "3069bp1f", 1977, 2027, 5766, "base")
    row = cells.cells(conn)["cells"][0]
    assert row["year_from"] == 1977
    assert row["sets"] is None
    assert row["colors"] is None
    assert "popular" not in row["tags"]


def test_a_plain_part_is_base(conn):
    _part(conn, "3001")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["base"] is True


def test_a_printed_part_is_not_base(conn):
    conn.execute("INSERT INTO parts (id, title, category, printed, obsolete, "
                 "status) VALUES ('3001p01', 'Brick, Printed', 'Brick', 1, 0, "
                 "'unreviewed')")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["base"] is False


def test_an_obsolete_part_is_not_base(conn):
    conn.execute("INSERT INTO parts (id, title, category, printed, obsolete, "
                 "status) VALUES ('3001', '~Brick', 'Brick', 0, 1, "
                 "'unreviewed')")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["base"] is False


def test_a_composite_part_is_not_base(conn):
    _part(conn, "1234c01")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["base"] is False


def test_a_sticker_part_is_not_base(conn):
    _part(conn, "1234d01")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["base"] is False


def test_an_unofficial_part_is_not_base(conn):
    _part(conn, "u9123")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["base"] is False


def test_a_mould_variant_is_base(conn):
    _part(conn, "3068b")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["base"] is True


def test_a_part_erroring_elsewhere_is_clean_here(conn):
    _part(conn, "3001")
    _measure(conn, "3001", "naive")
    _measure(conn, "3001", "occt", error="TimeoutError")
    conn.commit()
    cell = cells.cells(conn, source="silhouette-naive")["cells"][0]
    assert cell["error"] is None
    assert "timeout" in cell["elsewhere"]


def test_a_sticker_is_in_scope(conn):
    # occt draws 2,695 of the 2,701; the exclusion outlived the fix.
    _part(conn, "003238a", title="Sticker Minifig Shield", category="Sticker")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["out_of_scope"] is False


def test_a_part_nobody_at_lego_made_is_out_of_scope(conn):
    _part(conn, "t1008", title="Brickstuff Pico LED", category="|")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["out_of_scope"] is True


def test_a_brick_is_in_scope(conn):
    _part(conn, "3001")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["out_of_scope"] is False


def _years(conn, pid, year_from, year_to, sets, matched="exact", colors=0):
    conn.execute("INSERT INTO part_years (part_id, year_from, year_to, sets, "
                 "colors, matched) VALUES (?, ?, ?, ?, ?, ?)",
                 (pid, year_from, year_to, sets, colors, matched))


def test_a_cell_carries_its_years_and_tags(conn):
    _part(conn, "3001")
    _years(conn, "3001", 1979, 2026, 4252, colors=57)
    conn.commit()
    cell = cells.cells(conn)["cells"][0]
    assert (cell["year_from"], cell["year_to"], cell["sets"]) == (1979, 2026, 4252)
    assert cell["colors"] == 57
    assert "popular" in cell["tags"]


def test_a_cell_with_no_catalog_entry_says_so(conn):
    _part(conn, "3001")
    conn.commit()
    cell = cells.cells(conn)["cells"][0]
    assert cell["year_from"] is None and cell["sets"] is None
    assert cell["colors"] is None


def test_a_facet_slot_still_names_its_engine():
    assert cells.engine_for("white-naive") == "naive"
    assert cells.engine_for("silhouette-occt") == "occt"
    assert cells.engine_for("naive") == "naive"


def test_a_facet_slot_does_not_borrow_the_oracle_s_numbers(conn):
    """Both file under engine "naive", and white-* sorts last so it
    always won MAX(run_id) -- every oracle cell quietly showed white figures,
    which are ~1px larger on every part because the strokes are drawn."""
    _part(conn, "3001")
    _measure(conn, "3001", "naive", source="silhouette-naive")
    conn.execute("UPDATE measurements SET extra_d99 = 0.45 "
                 "WHERE source = 'silhouette-naive'")
    _measure(conn, "3001", "naive", source="white-naive")
    conn.execute("UPDATE measurements SET extra_d99 = 1.01 "
                 "WHERE source = 'white-naive'")
    conn.commit()
    assert cells.cells(conn, source="silhouette-naive")["cells"][0]["extra_d99"] == 0.45
    assert cells.cells(conn, source="white-naive")["cells"][0]["extra_d99"] == 1.01


def test_a_slot_with_no_measurements_of_its_own_shows_none(conn):
    _part(conn, "3001")
    _measure(conn, "3001", "naive", source="silhouette-naive")
    conn.commit()
    assert cells.cells(conn, source="white-naive")["cells"][0]["extra_d99"] is None


def test_erroring_in_any_other_slot_marks_the_cell(conn):
    """Every slot counts, not just the facet's other engine: a part that falls
    over anywhere is a part worth looking at, and narrowing the relation to a
    family left the wall silent about it."""
    _part(conn, "3001")
    _measure(conn, "3001", "naive", source="white-naive")
    _measure(conn, "3001", "occt", error="TimeoutError", source="silhouette-occt")
    conn.commit()
    assert "timeout" in cells.cells(conn, source="white-naive")["cells"][0][
        "elsewhere"]


def test_a_slot_with_no_measurements_of_its_own_carries_its_engine_s_error(conn):
    """`occt` records no measurements at all -- every failure of the occt
    engine is filed under `silhouette-occt` or `white-occt`. Read per slot,
    that painted a clean wall over 2,432 parts that do not draw."""
    _part(conn, "3001")
    _measure(conn, "3001", "occt", error="TimeoutError", source="white-occt")
    conn.commit()
    cell = cells.cells(conn, source="occt")["cells"][0]
    assert cell["error"] == "TimeoutError"
    # Its own, not a weaker report of somebody else's.
    assert cell["elsewhere"] == []


def test_a_slot_s_own_error_is_not_elsewhere(conn):
    _part(conn, "3001")
    _measure(conn, "3001", "occt", error="TimeoutError", source="occt")
    conn.commit()
    assert cells.cells(conn, source="occt")["cells"][0]["elsewhere"] == []


def test_a_third_party_part_is_out_of_scope(conn):
    _part(conn, "t1008", title="| Brickstuff Pico LED", category="|")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["out_of_scope"] is True


# `coverage` is the label the wall groups on and the dashboard tallies. It
# lives here rather than in the browser so the two cannot disagree about what
# `drawn` means.
def test_a_part_nobody_drew_is_untried(conn):
    _part(conn, "3001")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["coverage"] == "untried"


def test_a_drawn_part_with_nothing_against_it_is_drawn(conn):
    _part(conn, "3001")
    _render(conn, "3001", "a", "2026-09-05T10:00:00+00:00")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["coverage"] == "drawn"


def test_a_timeout_is_its_own_label_not_a_failure(conn):
    _part(conn, "3001")
    _measure(conn, "3001", "naive", error="TimeoutError")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["coverage"] == "timeout"


def test_any_other_error_is_a_failure(conn):
    _part(conn, "3001")
    _measure(conn, "3001", "naive", error="BRepCheck")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["coverage"] == "failed"


def test_an_open_defect_outranks_a_clean_render(conn):
    _part(conn, "3001")
    _render(conn, "3001", "a", "2026-09-05T10:00:00+00:00")
    _defect(conn, "d1", "3001", ["naive"])
    conn.commit()
    assert cells.cells(conn)["cells"][0]["coverage"] == "defect"


def test_a_qualified_slot_files_its_measurements_under_the_last_segment():
    """The qualifier leads and can be several words; the engine trails. A rule
    keyed on `census-` left every later slot naming itself as its own engine,
    which joins to nothing in measurements and sorts without erroring."""
    assert cells.engine_for("translucent-naive") == "naive"
    assert cells.engine_for("translucent-occt") == "occt"
    assert cells.engine_for("white-naive") == "naive"
    assert cells.engine_for("naive") == "naive"
    assert cells.engine_for("ldview") == "ldview"


def test_slot_states_gives_every_facet_of_an_engine_that_engine_s_error(conn):
    """Failing to draw is a property of the engine, not of which facet was
    asked for, so both occt slots report it."""
    _part(conn, "3001")
    _render(conn, "3001", "a", "2026-09-05T00:00:00+00:00", "silhouette-occt")
    _render(conn, "3001", "b", "2026-09-05T00:00:00+00:00", "white-occt")
    _measure(conn, "3001", "occt", error="TimeoutError", source="silhouette-occt")
    _measure(conn, "3001", "occt", source="white-occt")
    conn.commit()
    states = cells.slot_states(conn, "3001", ["silhouette-occt", "white-occt"])
    assert states["silhouette-occt"]["error"] == "TimeoutError"
    assert states["white-occt"]["error"] == "TimeoutError"


def test_slot_states_counts_a_defect_here_and_elsewhere(conn):
    _part(conn, "3001")
    _defect(conn, "d1", "3001", ["occt"])
    conn.commit()
    states = cells.slot_states(conn, "3001",
                               ["silhouette-occt", "silhouette-naive"])
    assert states["silhouette-occt"]["open_defects"] == 1
    assert states["silhouette-occt"]["elsewhere"] == []
    assert states["silhouette-naive"]["open_defects"] == 0
    assert states["silhouette-naive"]["elsewhere"] == ["defect"]


def test_slot_states_marks_a_wontfix_as_accepted_only_on_its_own_engine(conn):
    _part(conn, "3001")
    _defect(conn, "d1", "3001", ["occt"], status="wontfix")
    conn.commit()
    states = cells.slot_states(conn, "3001",
                               ["silhouette-occt", "silhouette-naive"])
    assert states["silhouette-occt"]["accepted_defects"] == 1
    assert states["silhouette-naive"]["accepted_defects"] == 0


def test_slot_states_reads_error_elsewhere_across_every_slot(conn):
    """One slot failing marks every other slot's view of the part."""
    _part(conn, "3001")
    _measure(conn, "3001", "naive", error="MemoryError", source="white-naive")
    conn.commit()
    states = cells.slot_states(conn, "3001", ["white-occt", "silhouette-occt"])
    assert "failed" in states["white-occt"]["elsewhere"]
    assert "failed" in states["silhouette-occt"]["elsewhere"]


# --- looking for review: an open defect whose slot has been redrawn ---------


def test_a_defect_judged_against_the_render_on_screen_asks_for_nothing(conn):
    _part(conn, "3001")
    _render(conn, "3001", "sha-a", "2026-09-05T00:00:00+00:00")
    _defect(conn, "d1", "3001", ["naive"],
            checked={"silhouette-naive": "sha-a"})
    conn.commit()
    cell = cells.cells(conn, source="silhouette-naive")["cells"][0]
    assert cell["open_defects"] == 1
    assert cell["review_defects"] == 0


def test_a_defect_whose_slot_has_been_redrawn_asks_for_review(conn):
    _part(conn, "3001")
    _render(conn, "3001", "sha-b", "2026-09-06T00:00:00+00:00")
    _defect(conn, "d1", "3001", ["naive"],
            checked={"silhouette-naive": "sha-a"})
    conn.commit()
    cell = cells.cells(conn, source="silhouette-naive")["cells"][0]
    # Disjoint: it left `open` when it entered `review`, so it cannot hide
    # behind the part's untouched faults.
    assert cell["open_defects"] == 0
    assert cell["review_defects"] == 1


def test_a_defect_nobody_has_judged_never_asks_for_review(conn):
    """The whole corpus predates `checked`. Without a baseline a record has
    nothing to compare against, and must stay quiet rather than flag."""
    _part(conn, "3001")
    _render(conn, "3001", "sha-b", "2026-09-06T00:00:00+00:00")
    _defect(conn, "d1", "3001", ["naive"])
    conn.commit()
    cell = cells.cells(conn, source="silhouette-naive")["cells"][0]
    assert cell["open_defects"] == 1
    assert cell["review_defects"] == 0


def test_a_closed_defect_asks_for_review_however_much_the_render_moves(conn):
    _part(conn, "3001")
    _render(conn, "3001", "sha-b", "2026-09-06T00:00:00+00:00")
    _defect(conn, "d1", "3001", ["naive"], status="fixed",
            checked={"silhouette-naive": "sha-a"})
    conn.commit()
    cell = cells.cells(conn, source="silhouette-naive")["cells"][0]
    assert cell["review_defects"] == 0
    assert cell["open_defects"] == 0


def test_a_redraw_in_another_engine_reads_as_review_elsewhere(conn):
    _part(conn, "3001")
    _render(conn, "3001", "sha-b", "2026-09-06T00:00:00+00:00",
            source="silhouette-occt")
    _defect(conn, "d1", "3001", ["occt"],
            checked={"silhouette-occt": "sha-a"})
    conn.commit()
    cell = cells.cells(conn, source="silhouette-naive")["cells"][0]
    assert cell["elsewhere"] == ["review"]


# --- errors belong to a slot, defects to an engine -------------------------


def test_a_real_error_outranks_a_timeout_when_an_engine_s_facets_disagree(conn):
    """One facet giving up on the clock must not mask another failing
    outright, so the engine reports the worse of the two."""
    _part(conn, "3001")
    _measure(conn, "3001", "occt", error="TimeoutError", source="silhouette-occt")
    _measure(conn, "3001", "occt", error="GEOSException", source="white-occt")
    conn.commit()
    assert cells.cells(conn, source="occt")["cells"][0]["error"] == "GEOSException"


def test_a_timeout_elsewhere_is_told_apart_from_an_error_elsewhere(conn):
    """One `error_elsewhere` bool could not say which, so the wall drew a
    render error in the color of a timeout."""
    _part(conn, "3001")
    _part(conn, "3002")
    _measure(conn, "3001", "occt", error="TimeoutError", source="silhouette-occt")
    _measure(conn, "3002", "occt", error="GEOSException", source="silhouette-occt")
    conn.commit()
    rows = {c["id"]: c for c in cells.cells(conn, source="silhouette-naive")["cells"]}
    assert rows["3001"]["elsewhere"] == ["timeout"]
    assert rows["3002"]["elsewhere"] == ["failed"]


def test_a_defect_against_an_engine_that_never_drew_the_part_still_counts(conn):
    """A defect belongs to an engine, not to a render. Reading it off the
    slots that have drawn the part hid every fault in an engine that has
    not got to it yet."""
    _part(conn, "3001")
    _defect(conn, "d1", "3001", ["occt"])
    conn.commit()
    cell = cells.cells(conn, source="silhouette-naive")["cells"][0]
    assert cell["elsewhere"] == ["defect"]


def test_a_sibling_slot_of_the_same_engine_is_not_elsewhere(conn):
    """`occt` and `silhouette-occt` are one engine. A defect against occt is
    this cell's own, and reporting it as elsewhere too draws it twice."""
    _part(conn, "3001")
    _render(conn, "3001", "sha-a", "2026-09-05T00:00:00+00:00",
            source="silhouette-occt")
    _defect(conn, "d1", "3001", ["occt"])
    conn.commit()
    cell = cells.cells(conn, source="occt")["cells"][0]
    assert cell["open_defects"] == 1
    assert cell["elsewhere"] == []


def test_a_wontfix_in_another_slot_asks_nothing_of_this_one(conn):
    _part(conn, "3001")
    _defect(conn, "d1", "3001", ["occt"], status="wontfix")
    conn.commit()
    cell = cells.cells(conn, source="silhouette-naive")["cells"][0]
    assert cell["accepted_defects"] == 0
    assert cell["elsewhere"] == []


def _attempt(conn, pid, source, state=None, secs=None, error=None):
    global _run_id
    _run_id += 1
    conn.execute("INSERT INTO runs (id, kind, started, commit_sha, args) "
                 "VALUES (?, 'store', '2026-09-05T09:00:00+00:00', 'abc', '{}')",
                 (_run_id,))
    conn.execute("INSERT INTO attempts (run_id, part_id, source, state, secs, "
                 "error) VALUES (?, ?, ?, ?, ?, ?)",
                 (_run_id, pid, source, state, secs, error))


def test_a_slot_nothing_has_ever_used_is_not_live(conn):
    """The detail view lays out one tile per live slot. `decal` and
    `translucent-naive` have never drawn, been tried or been measured, and a
    column of empties for them is eight slots of noise on every part."""
    _part(conn, "3001")
    _render(conn, "3001", "sha", "2026-09-05T00:00:00+00:00", source="occt")
    conn.commit()
    assert cells.live_sources(conn) == ["occt"]


def test_a_slot_that_only_ever_failed_is_live(conn):
    """`naive` holds no render at all and has been run: a slot is live because
    someone pointed the renderer at it, not because it succeeded."""
    _part(conn, "3001")
    _attempt(conn, "3001", "naive", error="TimeoutError", secs=120.0)
    _measure(conn, "3001", "occt", error="ProcessDied")
    conn.commit()
    assert cells.live_sources(conn) == ["naive", "silhouette-occt"]


def test_live_sources_are_in_the_module_s_own_order(conn):
    _part(conn, "3001")
    for source in ("white-occt", "occt", "ldview"):
        _render(conn, "3001", "sha", "2026-09-05T00:00:00+00:00", source=source)
    conn.commit()
    assert cells.live_sources(conn) == ["occt", "ldview", "white-occt"]


def test_an_attempt_says_how_long_a_slot_ran_before_it_gave_up(conn):
    _part(conn, "3001")
    _attempt(conn, "3001", "occt", error="TimeoutError", secs=120.5)
    conn.commit()
    assert cells.slot_attempts(conn, "3001")["occt"] == {
        "state": None, "secs": 120.5, "error": "TimeoutError"}


def test_the_latest_attempt_per_slot_is_the_one_that_counts(conn):
    _part(conn, "3001")
    _attempt(conn, "3001", "occt", error="TimeoutError", secs=120.0)
    _attempt(conn, "3001", "occt", state="stored", secs=204.0)
    conn.commit()
    got = cells.slot_attempts(conn, "3001")["occt"]
    assert (got["state"], got["error"]) == ("stored", None)


def test_a_plain_part_is_not_applicable_to_the_decal_slot(conn):
    _part(conn, "3001")
    rows = cells.cells(conn, source="decal")["cells"]
    assert [r["not_applicable"] for r in rows] == [True]


def test_a_decorated_part_the_decal_slot_missed_is_still_owed(conn):
    conn.execute("INSERT INTO parts (id, title, category, printed, obsolete, "
                 "status) VALUES ('3001p01', 'Brick with Pattern', 'Brick', "
                 "1, 0, 'unreviewed')")
    rows = cells.cells(conn, source="decal")["cells"]
    assert [r["not_applicable"] for r in rows] == [False]


def test_a_plain_part_with_a_decal_against_its_name_keeps_its_render(conn):
    _part(conn, "3001")
    _render(conn, "3001", "sha", "2026-09-08T00:00:00+00:00", source="decal")
    rows = cells.cells(conn, source="decal")["cells"]
    assert [r["not_applicable"] for r in rows] == [False]


def test_no_part_is_inapplicable_to_a_slot_that_draws_the_whole_library(conn):
    _part(conn, "3001")
    rows = cells.cells(conn, source="silhouette-naive")["cells"]
    assert [r["not_applicable"] for r in rows] == [False]


def test_a_plain_part_is_not_owed_by_the_decal_slot(conn):
    """The coverage chart counted every unprinted part as never attempted, so
    the decal slot read as mostly undone when most of it was never its work."""
    _part(conn, "3001")
    rows = cells.cells(conn, source="decal")["cells"]
    assert [r["coverage"] for r in rows] == ["notApplicable"]


def test_a_decorated_part_the_decal_slot_missed_is_still_untried(conn):
    conn.execute("INSERT INTO parts (id, title, category, printed, obsolete, "
                 "status) VALUES ('3001p01', 'Brick with Pattern', 'Brick', "
                 "1, 0, 'unreviewed')")
    rows = cells.cells(conn, source="decal")["cells"]
    assert [r["coverage"] for r in rows] == ["untried"]


def test_a_slot_erroring_on_a_part_it_does_not_cover_still_says_so(conn):
    """`notApplicable` displaces `untried` and nothing else -- burying a real
    failure under "nothing to draw" would hide the contradiction."""
    assert cells.coverage_of(sha=None, error="ValueError", open_defects=0,
                             inapplicable=True) == "failed"
    assert cells.coverage_of(sha="abc", error=None, open_defects=0,
                             inapplicable=True) == "drawn"
    assert cells.coverage_of(sha=None, error=None, open_defects=1,
                             inapplicable=True) == "defect"


def test_a_cell_says_ldraw_poses_the_part(conn):
    _part(conn, "3001")
    conn.execute("INSERT INTO parts (id, title, category, printed, obsolete, "
                 "preview, status) VALUES ('87544dq0', 'Panel Sticker', "
                 "'Sticker', 0, 0, '16 0 0 0 -1 0 0 0 1 0 0 0 -1', "
                 "'unreviewed')")
    conn.commit()
    by_id = {c["id"]: c for c in cells.cells(conn)["cells"]}
    assert "posed" in by_id["87544dq0"]["tags"]
    assert "posed" not in by_id["3001"]["tags"]
