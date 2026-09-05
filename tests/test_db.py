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
