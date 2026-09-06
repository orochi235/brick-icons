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


def _render(conn, pid, sha, made_at, source="census-naive"):
    conn.execute("INSERT INTO renders (part_id, source, config_key, made_at, "
                 "path, sha256) VALUES (?, ?, 'k', ?, ?, ?)",
                 (pid, source, made_at, f"renders/{source}/{pid}.svg", sha))


def _defect(conn, defect_id, pid, engines, status="open"):
    conn.execute("INSERT INTO defects (id, part_id, engines, status, title, "
                 "filed) VALUES (?, ?, ?, ?, 't', '2026-09-05T00:00:00+00:00')",
                 (defect_id, pid, json.dumps(engines), status))


_run_id = 0


def _measure(conn, pid, engine, error=None, source=None):
    global _run_id
    _run_id += 1
    conn.execute("INSERT INTO runs (id, kind, started, commit_sha, args) "
                 "VALUES (?, 'census', '2026-09-05T09:00:00+00:00', 'abc', '{}')",
                 (_run_id,))
    conn.execute("INSERT INTO measurements (run_id, part_id, engine, source, "
                 "error) VALUES (?, ?, ?, ?, ?)",
                 (_run_id, pid, engine, source or f"census-{engine}", error))


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


def test_a_census_slot_reads_its_engine_s_measurements(conn):
    # renders.source is a slot; measurements.engine is an engine. Without the
    # mapping every metric joins to nothing and the wall sorts on all-None.
    assert cells.engine_for("census-naive") == "naive"
    assert cells.engine_for("census-occt") == "occt"
    assert cells.engine_for("naive") == "naive"


def test_a_cell_carries_the_metric_from_its_slot_s_engine(conn):
    _part(conn, "3001")
    _render(conn, "3001", "a", "2026-09-05T10:00:00+00:00")
    conn.execute("INSERT INTO runs (id, kind, started, commit_sha, args) "
                 "VALUES (1, 'census', '2026-09-05T09:00:00+00:00', 'abc', '{}')")
    conn.execute("INSERT INTO measurements (run_id, part_id, engine, source, "
                 "extra_d99, secs) "
                 "VALUES (1, '3001', 'naive', 'census-naive', 4.5, 12.0)")
    conn.commit()
    cell = cells.cells(conn, source="census-naive")["cells"][0]
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
    cell = cells.cells(conn, source="census-naive")["cells"][0]
    assert cell["open_defects"] == 0
    assert cell["open_defects_elsewhere"] == 0


def test_a_defect_naming_this_engine_counts_here_only(conn):
    _part(conn, "3001")
    _defect(conn, "d1", "3001", ["naive"])
    conn.commit()
    cell = cells.cells(conn, source="census-naive")["cells"][0]
    assert cell["open_defects"] == 1
    assert cell["open_defects_elsewhere"] == 0


def test_a_defect_naming_another_engine_counts_elsewhere_only(conn):
    _part(conn, "3001")
    _defect(conn, "d1", "3001", ["occt"])
    conn.commit()
    cell = cells.cells(conn, source="census-naive")["cells"][0]
    assert cell["open_defects"] == 0
    assert cell["open_defects_elsewhere"] == 1


def test_a_fixed_defect_counts_in_neither(conn):
    _part(conn, "3001")
    _defect(conn, "d1", "3001", ["naive"], status="fixed")
    conn.commit()
    cell = cells.cells(conn, source="census-naive")["cells"][0]
    assert cell["open_defects"] == 0
    assert cell["open_defects_elsewhere"] == 0


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
    cell = cells.cells(conn, source="census-naive")["cells"][0]
    assert cell["error"] is None
    assert cell["error_elsewhere"] is True


def test_a_sticker_is_out_of_scope(conn):
    _part(conn, "003238a", title="Sticker Minifig Shield", category="Sticker")
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
    assert cells.engine_for("census-white-naive") == "naive"
    assert cells.engine_for("census-occt") == "occt"
    assert cells.engine_for("naive") == "naive"


def test_a_facet_slot_does_not_borrow_the_oracle_s_numbers(conn):
    """Both file under engine "naive", and census-white-* sorts last so it
    always won MAX(run_id) -- every oracle cell quietly showed white figures,
    which are ~1px larger on every part because the strokes are drawn."""
    _part(conn, "3001")
    _measure(conn, "3001", "naive", source="census-naive")
    conn.execute("UPDATE measurements SET extra_d99 = 0.45 "
                 "WHERE source = 'census-naive'")
    _measure(conn, "3001", "naive", source="census-white-naive")
    conn.execute("UPDATE measurements SET extra_d99 = 1.01 "
                 "WHERE source = 'census-white-naive'")
    conn.commit()
    assert cells.cells(conn, source="census-naive")["cells"][0]["extra_d99"] == 0.45
    assert cells.cells(conn, source="census-white-naive")["cells"][0]["extra_d99"] == 1.01


def test_a_slot_with_no_measurements_of_its_own_shows_none(conn):
    _part(conn, "3001")
    _measure(conn, "3001", "naive", source="census-naive")
    conn.commit()
    assert cells.cells(conn, source="census-white-naive")["cells"][0]["extra_d99"] is None


def test_erroring_elsewhere_means_this_facet_s_other_engine(conn):
    """An oracle timeout says nothing about whether the white facet drew the
    part, so it must not mark a white cell."""
    _part(conn, "3001")
    _measure(conn, "3001", "naive", source="census-white-naive")
    _measure(conn, "3001", "occt", error="TimeoutError", source="census-occt")
    conn.commit()
    assert cells.cells(conn, source="census-white-naive")["cells"][0][
        "error_elsewhere"] is False
    _measure(conn, "3001", "occt", error="TimeoutError",
             source="census-white-occt")
    conn.commit()
    assert cells.cells(conn, source="census-white-naive")["cells"][0][
        "error_elsewhere"] is True


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
