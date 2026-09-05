# Corpus database Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `brick_icons/db.py` — the SQLite store for part status, defects, render pointers and census measurement history — and the script that rebuilds it from files on disk.

**Architecture:** One module holding the schema and every accessor. The database is derived: `renders/<source>/<part>.svg` and the git-tracked TOML are the artifacts, and `scripts/build-corpus-db.py` reconstructs `corpus.db` from them plus the census JSONL. Nothing writes SQLite concurrently — the census shards keep writing their own append-only JSONL and one importer loads a finished run.

**Tech Stack:** Python 3.14, `sqlite3` from the standard library, `tomllib` for reading and `brick_icons.lab.defects`' own writer for TOML output. Tests are pytest, under `tests/test_db.py`.

Spec: `docs/superpowers/specs/2026-09-04-corpus-database-design.md`.

---

## File structure

- **Create `brick_icons/db.py`** — schema, `connect()`, and the accessors. Everything that knows SQL lives here and nothing else does.
- **Create `tests/test_db.py`** — every task's tests. Uses `tmp_path`; never touches the real `corpus.db`.
- **Create `scripts/build-corpus-db.py`** — the rebuild, with one progress line per source file.
- **Modify `.gitignore`** — add `corpus.db`.
- **Reuse, do not reimplement:** `brick_icons.lab.partindex.build` walks the library and reads descriptions; `brick_icons.lab.cache.key` canonicalizes an argv into a config key; `brick_icons.goldens.sha256` and `summarize_svg` hash and parse an SVG; `brick_icons.lab.defects.load`/`save` read and write the defect TOML in its fixed field order.

---

### Task 1: Schema and connect

**Files:**
- Create: `brick_icons/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

```python
import sqlite3

import pytest

from brick_icons import db


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'brick_icons.db'`

- [ ] **Step 3: Write minimal implementation**

```python
"""The corpus database: part status, defects, renders and measurement history.

Derived, never authoritative. The artifacts are `renders/<source>/<part>.svg`
and the git-tracked TOML; `scripts/build-corpus-db.py` rebuilds this file from
them.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path("corpus.db")
SCHEMA_VERSION = 1
PART_STATUSES = ("unreviewed", "good", "suspect", "broken", "wontfix")
SOURCES = ("naive", "occt", "decal", "ldview")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS parts (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  category TEXT,
  printed INTEGER NOT NULL,
  obsolete INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'unreviewed',
  status_note TEXT,
  status_at TEXT
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  started TEXT NOT NULL,
  finished TEXT,
  commit_sha TEXT NOT NULL,
  args TEXT NOT NULL,
  note TEXT
);

CREATE TABLE IF NOT EXISTS renders (
  part_id TEXT NOT NULL REFERENCES parts(id),
  source TEXT NOT NULL,
  config_key TEXT NOT NULL,
  run_id INTEGER REFERENCES runs(id),
  made_at TEXT NOT NULL,
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  width REAL, height REAL,
  PRIMARY KEY (part_id, source, config_key)
);

CREATE TABLE IF NOT EXISTS measurements (
  run_id INTEGER NOT NULL REFERENCES runs(id),
  part_id TEXT NOT NULL,
  engine TEXT NOT NULL,
  missing_px INTEGER, extra_px INTEGER,
  missing_comps INTEGER,
  extra_d99 REAL, extra_d100 REAL,
  secs REAL,
  error TEXT, detail TEXT,
  PRIMARY KEY (run_id, part_id, engine)
);

CREATE TABLE IF NOT EXISTS defects (
  id TEXT PRIMARY KEY,
  part_id TEXT NOT NULL,
  engines TEXT NOT NULL,
  status TEXT NOT NULL,
  title TEXT NOT NULL,
  mark TEXT, kind TEXT, points TEXT,
  filed TEXT NOT NULL,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY,
  part_id TEXT,
  defect_id TEXT,
  written TEXT NOT NULL,
  body TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS measurements_by_part ON measurements(part_id, engine);
CREATE INDEX IF NOT EXISTS renders_by_part ON renders(part_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | str = DEFAULT_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    found = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'"
    ).fetchone()
    if found:
        version = conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        if int(version) > SCHEMA_VERSION:
            raise RuntimeError(
                f"{path} is at schema version {version}; this code speaks "
                f"{SCHEMA_VERSION}")
    conn.executescript(_SCHEMA)
    conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)",
                 (str(SCHEMA_VERSION),))
    conn.commit()
    return conn
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: PASS, 3 passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/db.py tests/test_db.py
git commit -m "add the corpus database schema"
```

---

### Task 2: Seed parts from the library

**Files:**
- Modify: `brick_icons/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

`partindex.build` wants a directory holding `parts/*.dat`, so the test writes four one-line files rather than reaching for the real library.

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: FAIL — `AttributeError: module 'brick_icons.db' has no attribute 'seed_parts'`

- [ ] **Step 3: Write minimal implementation**

The `INSERT … ON CONFLICT DO UPDATE` names only the library's own columns, which is what leaves a human's status alone on a reseed.

```python
from brick_icons.lab import partindex


def seed_parts(conn: sqlite3.Connection, ldraw_dir: Path | str) -> int:
    rows = []
    for entry in partindex.build(ldraw_dir).values():
        title = entry["description"]
        rows.append((entry["id"], title, title.split()[0] if title else None,
                     int(entry["printed"]),
                     int(title.startswith(("~", "_")))))
    conn.executemany(
        "INSERT INTO parts (id, title, category, printed, obsolete) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET title=excluded.title, "
        "category=excluded.category, printed=excluded.printed, "
        "obsolete=excluded.obsolete",
        rows)
    conn.commit()
    return len(rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/db.py tests/test_db.py
git commit -m "seed the parts table from the library's description lines"
```

---

### Task 3: Runs

**Files:**
- Modify: `brick_icons/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

Add `import json` to the test file's imports.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: FAIL — `AttributeError: module 'brick_icons.db' has no attribute 'start_run'`

- [ ] **Step 3: Write minimal implementation**

```python
def start_run(conn: sqlite3.Connection, kind: str, args: dict,
              commit_sha: str) -> int:
    cur = conn.execute(
        "INSERT INTO runs (kind, started, commit_sha, args) VALUES (?, ?, ?, ?)",
        (kind, now(), commit_sha, json.dumps(args, sort_keys=True)))
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int,
               note: str | None = None) -> None:
    conn.execute("UPDATE runs SET finished=?, note=? WHERE id=?",
                 (now(), note, run_id))
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/db.py tests/test_db.py
git commit -m "record a run and the arguments it was given"
```

---

### Task 4: Import a census JSONL

**Files:**
- Modify: `brick_icons/db.py`
- Test: `tests/test_db.py`

The rows are exactly what `scripts/compare-silhouette-truth.py` appends: a measured row carries `missing`/`extra` component lists and `extra_dist_px`, a failed row carries `error` and `detail` and neither.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: FAIL — `AttributeError: module 'brick_icons.db' has no attribute 'import_census_jsonl'`

- [ ] **Step 3: Write minimal implementation**

```python
def import_census_jsonl(conn: sqlite3.Connection, run_id: int,
                        path: Path | str) -> int:
    rows = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        dist = r.get("extra_dist_px") or {}
        rows.append((run_id, r["part"], r["engine"],
                     r.get("missing_px"), r.get("extra_px"),
                     len(r["missing"]) if "missing" in r else None,
                     dist.get("99"), dist.get("100"),
                     r.get("secs"), r.get("error"), r.get("detail")))
    conn.executemany(
        "INSERT OR REPLACE INTO measurements (run_id, part_id, engine, "
        "missing_px, extra_px, missing_comps, extra_d99, extra_d100, secs, "
        "error, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    return len(rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/db.py tests/test_db.py
git commit -m "import a census shard's JSONL as measurement rows"
```

---

### Task 5: Record a render

**Files:**
- Modify: `brick_icons/db.py`
- Test: `tests/test_db.py`

`config_key` comes from `lab.cache.key`, so a render the lab made and one the census made land on the same row instead of two.

- [ ] **Step 1: Write the failing test**

```python
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
```

Add `from brick_icons import db, goldens` to the test file's imports.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: FAIL — `AttributeError: module 'brick_icons.db' has no attribute 'record_render'`

- [ ] **Step 3: Write minimal implementation**

```python
from brick_icons import goldens
from brick_icons.lab import cache

# The one config each source's stored render is drawn at. A second config is a
# different drawing and belongs in out/lab's cache, not in the store.
_CANONICAL = {
    "naive": ["--engine", "naive", "--shading", "outline",
              "--shade-style", "flat3", "--angle", "iso"],
    "occt": ["--engine", "occt", "--shading", "outline",
             "--shade-style", "flat3", "--angle", "iso"],
    "decal": ["--decal", "--angle", "iso"],
    "ldview": ["--ldview", "--angle", "iso"],
}


def canonical_argv(part_id: str, source: str) -> list[str]:
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}, not {source!r}")
    return [part_id, *_CANONICAL[source]]


def record_render(conn: sqlite3.Connection, part_id: str, source: str,
                  path: Path | str, root: Path | str = ".",
                  run_id: int | None = None) -> str:
    argv = canonical_argv(part_id, source)
    path = Path(path)
    text = path.read_text()
    width = height = None
    if path.suffix == ".svg":
        box = goldens.summarize_svg(text)["viewBox"]
        if box:
            _, _, width, height = (float(v) for v in box.split())
    key = cache.key(argv)
    conn.execute(
        "INSERT OR REPLACE INTO renders (part_id, source, config_key, run_id, "
        "made_at, path, sha256, width, height) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (part_id, source, key, run_id, now(),
         str(path.resolve().relative_to(Path(root).resolve())),
         goldens.sha256(text), width, height))
    conn.commit()
    return key
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: PASS, 11 passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/db.py tests/test_db.py
git commit -m "record a render's file, hash and extent"
```

---

### Task 6: Defects in and out

**Files:**
- Modify: `brick_icons/db.py`
- Test: `tests/test_db.py`

`lab.defects` already reads and writes the TOML in a fixed field order. Import maps its records into rows and export hands them back to `defects.save`, so the file's format has exactly one owner.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: FAIL — `AttributeError: module 'brick_icons.db' has no attribute 'import_defects'`

- [ ] **Step 3: Write minimal implementation**

```python
from brick_icons.lab import defects as defects_toml


def import_defects(conn: sqlite3.Connection, path: Path | str) -> int:
    records = defects_toml.load(path)
    conn.executemany(
        "INSERT OR REPLACE INTO defects (id, part_id, engines, status, title, "
        "mark, kind, points, filed, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(r["id"], r["part"], json.dumps(r.get("engines", [])),
          r.get("status", "open"), r["title"],
          json.dumps(r["mark"]) if "mark" in r else None,
          r.get("kind"),
          json.dumps(r["points"]) if "points" in r else None,
          r["filed"], r.get("notes")) for r in records])
    conn.commit()
    return len(records)


def export_defects(conn: sqlite3.Connection, path: Path | str) -> int:
    records = []
    for row in conn.execute("SELECT * FROM defects ORDER BY id"):
        record = {"id": row["id"], "part": row["part_id"],
                  "engines": json.loads(row["engines"]),
                  "status": row["status"], "title": row["title"]}
        if row["mark"]:
            record["mark"] = json.loads(row["mark"])
        if row["kind"]:
            record["kind"] = row["kind"]
        if row["points"]:
            record["points"] = json.loads(row["points"])
        record["filed"] = row["filed"]
        if row["notes"]:
            record["notes"] = row["notes"]
        records.append(record)
    defects_toml.save(path, records)
    return len(records)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: PASS, 12 passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/db.py tests/test_db.py
git commit -m "read and write the defect TOML through the database"
```

---

### Task 7: Part status and notes

**Files:**
- Modify: `brick_icons/db.py`
- Modify: `brick_icons/lab/defects.py` — rename `_dump_value` to `dump_value`
- Test: `tests/test_db.py`

Both are hand-authored, so both are exported to one git-tracked file,
`tests/goldens/part-status.toml`, carrying a `[[part]]` array and a `[[note]]`
array.

- [ ] **Step 1: Write the failing test**

```python
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
    conn = db.connect(tmp_path / "corpus.db")
    db.seed_parts(conn, _library(tmp_path))
    db.set_status(conn, "3001", "broken", note="no stud row at all")
    db.add_note(conn, "second look agrees", part_id="3001")
    path = tmp_path / "part-status.toml"
    db.export_statuses(conn, path)

    fresh = db.connect(tmp_path / "fresh.db")
    db.seed_parts(fresh, _library(tmp_path))
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: FAIL — `AttributeError: module 'brick_icons.db' has no attribute 'set_status'`

- [ ] **Step 3: Write minimal implementation**

Both TOML files must quote and escape identically, so rename
`lab/defects.py`'s `_dump_value` to `dump_value` and update its three uses in
that file — one owner for the format, reachable from here. Only `unreviewed`
parts are written out; 24,000 rows nobody has looked at would bury the ones
somebody has.

```python
_STATUS_HEADER = """\
# What a human decided about a part, and any notes against one.
#
# Written by brick_icons.db from corpus.db, which is derived and gitignored.
# This file is the record: a status that is not here does not survive a
# rebuild.

"""


def set_status(conn: sqlite3.Connection, part_id: str, status: str,
               note: str | None = None) -> None:
    if status not in PART_STATUSES:
        raise ValueError(f"status must be one of {PART_STATUSES}, not {status!r}")
    conn.execute(
        "UPDATE parts SET status=?, status_note=?, status_at=? WHERE id=?",
        (status, note, now(), part_id))
    conn.commit()


def add_note(conn: sqlite3.Connection, body: str, part_id: str | None = None,
             defect_id: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO notes (part_id, defect_id, written, body) VALUES (?, ?, ?, ?)",
        (part_id, defect_id, now(), body))
    conn.commit()
    return cur.lastrowid


def notes_for(conn: sqlite3.Connection, part_id: str | None = None,
              defect_id: str | None = None) -> list[sqlite3.Row]:
    if part_id:
        return list(conn.execute(
            "SELECT * FROM notes WHERE part_id=? ORDER BY id", (part_id,)))
    return list(conn.execute(
        "SELECT * FROM notes WHERE defect_id=? ORDER BY id", (defect_id,)))


def export_statuses(conn: sqlite3.Connection, path: Path | str) -> int:
    dump = defects_toml.dump_value
    chunks, n = [_STATUS_HEADER], 0
    for row in conn.execute(
            "SELECT * FROM parts WHERE status != 'unreviewed' ORDER BY id"):
        lines = ["[[part]]", f"id = {dump(row['id'])}",
                 f"status = {dump(row['status'])}"]
        if row["status_note"]:
            lines.append(f"note = {dump(row['status_note'])}")
        if row["status_at"]:
            lines.append(f"at = {dump(row['status_at'])}")
        chunks.append("\n".join(lines) + "\n")
        n += 1
    for row in conn.execute("SELECT * FROM notes ORDER BY id"):
        lines = ["[[note]]"]
        if row["part_id"]:
            lines.append(f"part = {dump(row['part_id'])}")
        if row["defect_id"]:
            lines.append(f"defect = {dump(row['defect_id'])}")
        lines += [f"written = {dump(row['written'])}",
                  f"body = {dump(row['body'])}"]
        chunks.append("\n".join(lines) + "\n")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(chunks))
    return n


def import_statuses(conn: sqlite3.Connection, path: Path | str) -> int:
    import tomllib

    path = Path(path)
    if not path.exists():
        return 0
    data = tomllib.loads(path.read_text())
    parts = data.get("part", [])
    conn.executemany(
        "UPDATE parts SET status=?, status_note=?, status_at=? WHERE id=?",
        [(p["status"], p.get("note"), p.get("at"), p["id"]) for p in parts])
    conn.executemany(
        "INSERT INTO notes (part_id, defect_id, written, body) VALUES (?, ?, ?, ?)",
        [(n.get("part"), n.get("defect"), n["written"], n["body"])
         for n in data.get("note", [])])
    conn.commit()
    return len(parts)
```

Move `import tomllib` to the module's imports rather than leaving it inside the
function.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: PASS, 16 passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/db.py brick_icons/lab/defects.py tests/test_db.py
git commit -m "track a part's status and notes, exported as TOML"
```

---

### Task 8: The rebuild script

**Files:**
- Create: `scripts/build-corpus-db.py`
- Modify: `.gitignore`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

The script's work belongs in `db.rebuild` so it can be tested without a
subprocess; the script is then argument parsing and progress lines.

```python
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
    for _ in range(2):
        db.rebuild(tmp_path / "corpus.db", ldraw_dir=library, root=tmp_path,
                   census_dir=tmp_path / "census", commit_sha="abc1234")
    conn = db.connect(tmp_path / "corpus.db")
    assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: FAIL — `AttributeError: module 'brick_icons.db' has no attribute 'rebuild'`

- [ ] **Step 3: Write minimal implementation**

In `brick_icons/db.py`. A rebuild deletes the old file rather than merging into
it, so a row that no longer has a file behind it cannot survive.

```python
DEFAULT_STATUS_PATH = Path("tests/goldens/part-status.toml")


def rebuild(path: Path | str, ldraw_dir: Path | str, root: Path | str = ".",
            census_dir: Path | str = "out/census",
            defects_path: Path | str = defects_toml.DEFAULT_PATH,
            status_path: Path | str = DEFAULT_STATUS_PATH,
            commit_sha: str = "unknown",
            progress=lambda msg: None) -> dict[str, int]:
    path = Path(path)
    path.unlink(missing_ok=True)
    conn = connect(path)
    counts = {"parts": seed_parts(conn, ldraw_dir), "renders": 0,
              "measurements": 0, "defects": 0, "statuses": 0}
    progress(f"seeded {counts['parts']} parts")

    root = Path(root)
    for svg in sorted((root / "renders").rglob("*.svg")):
        source = svg.parent.name
        record_render(conn, svg.stem, source, svg, root=root)
        counts["renders"] += 1
        progress(f"render {counts['renders']}: {source}/{svg.stem}")

    shards = sorted(Path(census_dir).glob("*.jsonl"))
    if shards:
        run_id = start_run(conn, "census", {"shards": len(shards)}, commit_sha)
        for shard in shards:
            n = import_census_jsonl(conn, run_id, shard)
            counts["measurements"] += n
            progress(f"{shard.name}: {n} measurements")
        finish_run(conn, run_id, note=f"rebuilt from {len(shards)} shards")

    counts["defects"] = import_defects(conn, defects_path)
    counts["statuses"] = import_statuses(conn, status_path)
    progress(f"{counts['defects']} defects, {counts['statuses']} statuses")
    conn.close()
    return counts
```

Then `scripts/build-corpus-db.py`:

```python
#!/usr/bin/env python3
"""Rebuild corpus.db from the files that are the actual artifacts.

    .venv/bin/python scripts/build-corpus-db.py

The database is derived: this deletes and rewrites it from `renders/`, the
census JSONL and the git-tracked TOML. Nothing here renders anything.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402
from brick_icons.config import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--census-dir", default=str(ROOT / "out" / "census"))
    args = ap.parse_args()

    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    counts = db.rebuild(args.out, ldraw_dir=load_config().ldraw_dir, root=ROOT,
                        census_dir=args.census_dir, commit_sha=sha or "unknown",
                        progress=lambda m: print(m, flush=True))
    print(", ".join(f"{v} {k}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Add to `.gitignore`:

```
corpus.db
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: PASS, 18 passed

- [ ] **Step 5: Run it against the real corpus**

Run: `.venv/bin/python scripts/build-corpus-db.py`
Expected: a progress line per shard, then a summary naming ~24,591 parts and
the census rows currently on disk (7,156 and climbing while the shards run).
Confirm with:

```bash
.venv/bin/python -c "
from brick_icons import db
c = db.connect('corpus.db')
print(c.execute('SELECT count(*) FROM parts').fetchone()[0], 'parts')
print(c.execute('SELECT engine, count(*) FROM measurements GROUP BY engine').fetchall())
"
```

- [ ] **Step 6: Commit**

```bash
git add brick_icons/db.py scripts/build-corpus-db.py tests/test_db.py .gitignore
git commit -m "rebuild the corpus database from renders, TOML and census shards"
```

---

## What this plan does not build

The render job that fills `renders/` for every piece, the lab's findings view,
and the regression gate. Each is its own plan, per the spec's build order.
