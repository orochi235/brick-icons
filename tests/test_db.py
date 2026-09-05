import json

import pytest

from brick_icons import db, goldens


def test_connect_creates_the_schema(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meta", "parts", "runs", "renders",
            "measurements", "defects", "notes"} <= names


def test_connect_is_idempotent(tmp_path):
    path = tmp_path / "corpus.db"
    db.connect(path).close()
    conn = db.connect(path)
    assert conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == "1"


def test_a_newer_database_is_refused(tmp_path):
    path = tmp_path / "corpus.db"
    conn = db.connect(path)
    conn.execute("UPDATE meta SET value='99' WHERE key='schema_version'")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="schema version 99"):
        db.connect(path)


def _library(tmp_path):
    parts = tmp_path / "ldraw" / "parts"
    parts.mkdir(parents=True)
    (parts / "3001.dat").write_text("0 Brick  2 x  4\n")
    (parts / "3004p01.dat").write_text("0 Brick  1 x  2 with Cat Pattern\n")
    (parts / "3005.dat").write_text("0 ~Moved to 3005a\n")
    (parts / "u9236.dat").write_text("0 _Shortcut Something\n")
    return tmp_path / "ldraw"


def test_seeding_reads_the_description_not_the_id(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    assert db.seed_parts(conn, _library(tmp_path)) == 4
    rows = {r["id"]: r for r in conn.execute("SELECT * FROM parts")}
    assert rows["3001"]["title"] == "Brick  2 x  4"
    assert rows["3001"]["category"] == "Brick"
    assert rows["3001"]["printed"] == 0
    assert rows["3004p01"]["printed"] == 1
    assert rows["3005"]["obsolete"] == 1
    assert rows["u9236"]["obsolete"] == 1
    assert rows["3001"]["status"] == "unreviewed"


def test_reseeding_keeps_a_status_a_human_set(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    library = _library(tmp_path)
    db.seed_parts(conn, library)
    conn.execute("UPDATE parts SET status='broken' WHERE id='3001'")
    conn.commit()
    db.seed_parts(conn, library)
    assert conn.execute(
        "SELECT status FROM parts WHERE id='3001'").fetchone()[0] == "broken"


def test_a_run_records_its_arguments_and_closes(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    run_id = db.start_run(conn, "census", {"engine": "naive", "timeout": 120},
                          commit_sha="abc1234")
    row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    assert row["kind"] == "census"
    assert json.loads(row["args"])["engine"] == "naive"
    assert row["started"] and row["finished"] is None

    db.finish_run(conn, run_id, note="8235 parts")
    row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    assert row["finished"] and row["note"] == "8235 parts"


MEASURED = {
    "part": "93064", "engine": "naive", "angle": "iso",
    "extra_px": 17197, "missing_px": 2595,
    "extra_dist_px": {"50": 0.4, "90": 1.9, "99": 2.57, "100": 3.09},
    "missing": [{"px": 459, "x": [96.5, 102.2], "y": [153.2, 155.5]}],
    "extra": [], "secs": 49.0,
}
FAILED = {
    "part": "92738", "engine": "occt", "angle": "iso",
    "error": "ProcessDied", "detail": "killed mid-render; not retried",
    "secs": 0.0,
}


def test_importing_a_census_jsonl(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    run_id = db.start_run(conn, "census", {}, commit_sha="abc1234")
    path = tmp_path / "naive-s0.jsonl"
    path.write_text(json.dumps(MEASURED) + "\n" + json.dumps(FAILED) + "\n")

    assert db.import_census_jsonl(conn, run_id, path) == 2
    rows = {r["part_id"]: r for r in conn.execute("SELECT * FROM measurements")}
    assert rows["93064"]["missing_px"] == 2595
    assert rows["93064"]["missing_comps"] == 1
    assert rows["93064"]["extra_d99"] == 2.57
    assert rows["93064"]["error"] is None
    assert rows["92738"]["error"] == "ProcessDied"
    assert rows["92738"]["missing_px"] is None


def test_reimporting_the_same_run_replaces_rather_than_duplicates(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    run_id = db.start_run(conn, "census", {}, commit_sha="abc1234")
    path = tmp_path / "naive-s0.jsonl"
    path.write_text(json.dumps(MEASURED) + "\n")
    db.import_census_jsonl(conn, run_id, path)
    db.import_census_jsonl(conn, run_id, path)
    assert conn.execute("SELECT count(*) FROM measurements").fetchone()[0] == 1


SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 180">'
       '<path d="M 10 10 L 20 20" stroke="black"/></svg>')


def test_recording_a_render_stores_its_path_hash_and_size(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    svg = tmp_path / "renders" / "naive" / "3001.svg"
    svg.parent.mkdir(parents=True)
    svg.write_text(SVG)

    key = db.record_render(conn, "3001", "naive", svg, root=tmp_path)
    row = conn.execute("SELECT * FROM renders").fetchone()
    assert row["path"] == "renders/naive/3001.svg"
    assert row["config_key"] == key
    assert row["sha256"] == goldens.sha256(SVG)
    assert (row["width"], row["height"]) == (240.0, 180.0)


def test_a_second_render_of_the_same_config_replaces_the_row(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    svg = tmp_path / "renders" / "naive" / "3001.svg"
    svg.parent.mkdir(parents=True)
    svg.write_text(SVG)
    db.record_render(conn, "3001", "naive", svg, root=tmp_path)
    svg.write_text(SVG.replace("240", "300"))
    db.record_render(conn, "3001", "naive", svg, root=tmp_path)
    rows = conn.execute("SELECT * FROM renders").fetchall()
    assert len(rows) == 1 and rows[0]["width"] == 300.0


def test_an_unknown_source_is_refused(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    svg = tmp_path / "x.svg"
    svg.write_text(SVG)
    with pytest.raises(ValueError, match="source"):
        db.record_render(conn, "3001", "wireframe", svg, root=tmp_path)


DEFECT = {
    "id": "3941-occt-borehole",
    "part": "3941",
    "engines": ["occt"],
    "status": "open",
    "title": "borehole rim not drawn",
    "mark": {"x": 0.42, "y": 0.55, "w": 0.11, "h": 0.09},
    "filed": "2026-08-31",
    "notes": "occt draws nothing at all",
}


def test_defects_round_trip_through_the_database(tmp_path):
    from brick_icons.lab import defects as defects_toml

    conn = db.connect(tmp_path / "corpus.db")
    path = tmp_path / "defects.toml"
    defects_toml.save(path, [DEFECT])

    assert db.import_defects(conn, path) == 1
    row = conn.execute("SELECT * FROM defects").fetchone()
    assert row["part_id"] == "3941"
    assert json.loads(row["engines"]) == ["occt"]
    assert json.loads(row["mark"])["x"] == 0.42

    out = tmp_path / "again.toml"
    db.export_defects(conn, out)
    assert defects_toml.load(out) == [DEFECT]


def test_setting_a_status_and_adding_notes(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    db.seed_parts(conn, _library(tmp_path))

    db.set_status(conn, "3001", "suspect", note="stud row looks thin")
    row = conn.execute("SELECT * FROM parts WHERE id='3001'").fetchone()
    assert row["status"] == "suspect"
    assert row["status_note"] == "stud row looks thin"
    assert row["status_at"]

    db.add_note(conn, "measured 2595px missing", part_id="3001")
    assert [n["body"] for n in db.notes_for(conn, part_id="3001")] == [
        "measured 2595px missing"]


def test_an_unknown_status_is_refused(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    db.seed_parts(conn, _library(tmp_path))
    with pytest.raises(ValueError, match="status"):
        db.set_status(conn, "3001", "haunted")


def test_statuses_and_notes_round_trip_through_toml(tmp_path):
    library = _library(tmp_path)
    conn = db.connect(tmp_path / "corpus.db")
    db.seed_parts(conn, library)
    db.set_status(conn, "3001", "broken", note="no stud row at all")
    db.add_note(conn, "second look agrees", part_id="3001")
    path = tmp_path / "part-status.toml"
    db.export_statuses(conn, path)

    fresh = db.connect(tmp_path / "fresh.db")
    db.seed_parts(fresh, library)
    assert db.import_statuses(fresh, path) == 1
    row = fresh.execute("SELECT * FROM parts WHERE id='3001'").fetchone()
    assert (row["status"], row["status_note"]) == ("broken", "no stud row at all")
    assert [n["body"] for n in db.notes_for(fresh, part_id="3001")] == [
        "second look agrees"]


def test_a_part_left_unreviewed_is_not_written_out(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    db.seed_parts(conn, _library(tmp_path))
    path = tmp_path / "part-status.toml"
    assert db.export_statuses(conn, path) == 0
    assert "[[part]]" not in path.read_text()


def test_rebuild_walks_renders_and_toml_and_jsonl(tmp_path):
    library = _library(tmp_path)
    svg = tmp_path / "renders" / "naive" / "3001.svg"
    svg.parent.mkdir(parents=True)
    svg.write_text(SVG)
    (tmp_path / "census").mkdir()
    (tmp_path / "census" / "naive-s0.jsonl").write_text(json.dumps(MEASURED) + "\n")

    counts = db.rebuild(tmp_path / "corpus.db", ldraw_dir=library,
                        root=tmp_path, census_dir=tmp_path / "census",
                        commit_sha="abc1234")
    assert counts == {"parts": 4, "renders": 1, "measurements": 1,
                      "defects": 0, "statuses": 0}

    conn = db.connect(tmp_path / "corpus.db")
    assert conn.execute("SELECT path FROM renders").fetchone()[0] == \
        "renders/naive/3001.svg"


def test_rebuild_starts_from_empty_each_time(tmp_path):
    library = _library(tmp_path)
    (tmp_path / "census").mkdir()
    (tmp_path / "census" / "naive-s0.jsonl").write_text(json.dumps(MEASURED) + "\n")
    for _ in range(2):
        db.rebuild(tmp_path / "corpus.db", ldraw_dir=library, root=tmp_path,
                   census_dir=tmp_path / "census", commit_sha="abc1234")
    conn = db.connect(tmp_path / "corpus.db")
    assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM measurements").fetchone()[0] == 1


def test_storing_a_render_puts_it_under_source_and_part(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    conn.execute("INSERT INTO parts (id, title, printed, obsolete) "
                 "VALUES ('3001', 'Brick 2 x 4', 0, 0)")
    made = tmp_path / "work" / "3001.svg"
    made.parent.mkdir()
    made.write_text(SVG)

    path = db.store_render(conn, "3001", "naive", made, root=tmp_path)
    assert path == tmp_path / "renders" / "naive" / "3001.svg"
    assert path.read_text() == SVG
    row = conn.execute("SELECT path, sha256 FROM renders").fetchone()
    assert row["path"] == "renders/naive/3001.svg"
    assert row["sha256"] == goldens.sha256(SVG)


def test_a_second_source_does_not_overwrite_the_first(tmp_path):
    """Two sources of the same part are two rows AND two files. A source whose
    renders share a path would let the second silently replace the first."""
    conn = db.connect(tmp_path / "corpus.db")
    conn.execute("INSERT INTO parts (id, title, printed, obsolete) "
                 "VALUES ('3001', 'Brick 2 x 4', 0, 0)")
    made = tmp_path / "work" / "3001.svg"
    made.parent.mkdir()
    made.write_text(SVG)

    kept = [db.store_render(conn, "3001", s, made, root=tmp_path)
            for s in ("naive", "occt")]
    assert len(set(kept)) == 2
    assert all(p.exists() for p in kept)
    assert conn.execute("SELECT count(*) FROM renders").fetchone()[0] == 2


def test_every_svg_source_asks_the_cli_for_an_svg(tmp_path):
    """The store holds SVG. A canonical config that defaults to PNG renders
    fine and then has nothing to store, which the CLI reports as success."""
    for source in ("naive", "occt", "decal"):
        argv = db.canonical_argv("3001", source)
        assert argv[argv.index("--format") + 1] == "svg"
