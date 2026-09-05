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

from brick_icons import goldens
from brick_icons.lab import cache, partindex
from brick_icons.lab import defects as defects_toml

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


# The one config each source's stored render is drawn at. A second config is a
# different drawing and belongs in out/lab's cache, not in the store.
_CANONICAL = {
    "naive": ["--engine", "naive", "--shading", "outline",
              "--shade-style", "flat3", "--angle", "iso", "--format", "svg"],
    "occt": ["--engine", "occt", "--shading", "outline",
             "--shade-style", "flat3", "--angle", "iso", "--format", "svg"],
    "decal": ["--decal", "--angle", "iso", "--format", "svg"],
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


def store_render(conn: sqlite3.Connection, part_id: str, source: str,
                 made: Path | str, root: Path | str = ".",
                 run_id: int | None = None) -> Path:
    """Copy a freshly rendered SVG into the store and index it."""
    dest = Path(root) / "renders" / source / f"{part_id}.svg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(Path(made).read_text())
    record_render(conn, part_id, source, dest, root=root, run_id=run_id)
    return dest


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
        record_render(conn, svg.stem, svg.parent.name, svg, root=root)
        counts["renders"] += 1
        progress(f"render {counts['renders']}: {svg.parent.name}/{svg.stem}")

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
