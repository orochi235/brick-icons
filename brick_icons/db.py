"""The corpus database: part status, defects, renders and measurement history.

Derived, never authoritative. The artifacts are `renders/<source>/<part>.svg`
and the git-tracked TOML; `scripts/build-corpus-db.py` rebuilds this file from
them.
"""
from __future__ import annotations

import json
import sqlite3
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from brick_icons.lab import partindex

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
    if path.parent != Path(""):
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
