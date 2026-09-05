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
