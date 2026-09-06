"""The corpus database: part status, defects, renders and measurement history.

Derived, never authoritative. The artifacts are `renders/<source>/<part>.svg`
and the git-tracked TOML; `scripts/build-corpus-db.py` rebuilds this file from
them.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import tomllib
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from brick_icons import goldens
from brick_icons.lab import cache, partindex
from brick_icons.lab import defects as defects_toml

DEFAULT_PATH = Path("corpus.db")
SCHEMA_VERSION = 5
PART_STATUSES = ("unreviewed", "good", "suspect", "broken", "wontfix")
# Part categories the project is not trying to draw yet. A rule over the
# library's own category, not a list of ids: it covers parts nobody has seen
# yet, and it is not a judgment about any one part, so it stays out of
# `parts.status` and its hand-written record. `|` is LDraw's mark for a part
# nobody at LEGO made -- third-party electronics and wheels that fit LEGO.
OUT_OF_SCOPE_CATEGORIES = ("Sticker", "|")
SOURCES = ("naive", "occt", "decal", "ldview",
           "census-naive", "census-occt",
           "census-white-naive", "census-white-occt")

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
  -- The render source these numbers describe. `engine` cannot stand in for
  -- it: two facets of one engine are both "naive", so a query picking the
  -- newest run per engine hands a slot the other facet's measurements.
  source TEXT,
  -- The engine revision that drew this row, stamped by the machine that
  -- rendered it. runs.commit_sha is the INGESTING checkout and says nothing
  -- about the render, so a tree merged across passes needs this per row.
  build TEXT,
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

-- Production years and how many sets a part appears in, derived from
-- Rebrickable's dumps by scripts/fetch-part-years.py. Its own table rather
-- than columns on `parts`: `seed_parts` rebuilds that from the LDraw library,
-- which knows none of this.
CREATE TABLE IF NOT EXISTS part_years (
  part_id TEXT PRIMARY KEY,
  year_from INTEGER,
  year_to INTEGER,
  sets INTEGER NOT NULL DEFAULT 0,
  colors INTEGER NOT NULL DEFAULT 0,
  matched TEXT NOT NULL
);

-- The part that replaced this one, from Rebrickable's part_relationships
-- dump. LDraw records no such thing: `~Moved to` is a file rename, and 2780
-- has no redirect because 2780 and 61332 are genuinely different parts.
CREATE TABLE IF NOT EXISTS part_successors (
  part_id TEXT PRIMARY KEY,
  successor TEXT NOT NULL,
  rel TEXT NOT NULL
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
    conn = sqlite3.connect(path, timeout=60)
    conn.row_factory = sqlite3.Row
    # The store job shards across processes. WAL lets them write concurrently
    # and lets the lab read while they do; the timeout makes a collision a wait
    # rather than an exception a batch runner would log as a dead part.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    found = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'"
    ).fetchone()
    if found:
        # A concurrent opener may have created `meta` and not yet stamped it,
        # so a missing row means "brand new", not "corrupt".
        row = conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if row and int(row[0]) > SCHEMA_VERSION:
            raise RuntimeError(
                f"{path} is at schema version {row[0]}; this code speaks "
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
                        path: Path | str,
                        census_dir: Path | str | None = None) -> int:
    """`census_dir` names the facet: without it a row's source is left null and
    a reader can only fall back to the engine, which does not distinguish."""
    rows = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        dist = r.get("extra_dist_px") or {}
        source = census_source(census_dir, r["engine"]) if census_dir else None
        rows.append((run_id, r["part"], r["engine"], source, r.get("build"),
                     r.get("missing_px"), r.get("extra_px"),
                     len(r["missing"]) if "missing" in r else None,
                     dist.get("99"), dist.get("100"),
                     r.get("secs"), r.get("error"), r.get("detail")))
    conn.executemany(
        "INSERT OR REPLACE INTO measurements (run_id, part_id, engine, source, "
        "build, missing_px, extra_px, missing_comps, extra_d99, extra_d100, "
        "secs, error, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
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
    # The census's oracle drawing, not the store's: strokeless, so the fills
    # carry the silhouette and no stroke overhang has to be subtracted from
    # the comparison. One source per engine because the census writes
    # out/census/renders/<engine>/<part>.svg and the path holds only one.
    "census-naive": ["--format", "svg", "--shading", "outline",
                     "--shade-style", "flat3", "--angle", "iso",
                     "--engine", "naive", "--line-width", "0",
                     "--silhouette-width", "0"],
    "census-occt": ["--format", "svg", "--shading", "outline",
                    "--shade-style", "flat3", "--angle", "iso",
                    "--engine", "occt", "--line-width", "0",
                    "--silhouette-width", "0"],
    # The white facet: opaque white fills that only occlude, strokes carrying
    # the drawing. Its own source per engine because the key is derived from
    # the source alone -- indexed as census-<engine> it would REPLACE the
    # oracle's row for every part, the drawing silently swapped underneath.
    "census-white-naive": ["--format", "svg", "--shading", "outline",
                           "--shade-style", "white", "--angle", "iso",
                           "--engine", "naive", "--line-width", "2",
                           "--silhouette-width", "2"],
    "census-white-occt": ["--format", "svg", "--shading", "outline",
                          "--shade-style", "white", "--angle", "iso",
                          "--engine", "occt", "--line-width", "2",
                          "--silhouette-width", "2"],
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


def import_part_successors(conn: sqlite3.Connection, path: Path | str) -> int:
    """Load `scripts/fetch-part-years.py`'s successor CSV into
    `part_successors`."""
    with Path(path).open(newline="") as fh:
        rows = [(r["part_id"], r["successor"], r["rel"])
                for r in csv.DictReader(fh)]
    conn.executemany(
        "INSERT OR REPLACE INTO part_successors (part_id, successor, rel) "
        "VALUES (?, ?, ?)", rows)
    conn.commit()
    return len(rows)


def import_part_years(conn: sqlite3.Connection, path: Path | str) -> int:
    """Load `scripts/fetch-part-years.py`'s CSV into `part_years`."""
    with Path(path).open(newline="") as fh:
        rows = [(r["part_id"], int(r["year_from"]), int(r["year_to"]),
                 int(r["sets"]), int(r["colors"]), r["matched"])
                for r in csv.DictReader(fh)]
    conn.executemany(
        "INSERT OR REPLACE INTO part_years (part_id, year_from, year_to, sets, "
        "colors, matched) VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    return len(rows)


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
DEFAULT_YEARS_PATH = Path("tests/goldens/part-years.csv")
DEFAULT_SUCCESSORS_PATH = Path("tests/goldens/part-successors.csv")


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def census_source(census_dir: Path | str, engine: str) -> str:
    """The render source a census tree's drawings are filed under.

    A tree gets its own source only if it names one this module knows;
    anything else is another run of the base census and files under
    census-<engine>, so out/census-run2 still replaces out/census part for
    part. That fallback is what keeps the rule from swallowing a re-run: only
    a declared facet like census-white-naive sits beside the oracle instead of
    overwriting it, and it has to, because a render's config_key comes from
    its source alone.
    """
    stem = Path(census_dir).name
    named = stem if stem.endswith(f"-{engine}") else f"{stem}-{engine}"
    return named if named in SOURCES else f"census-{engine}"


def census_trees(root: Path | str = ".") -> list[Path]:
    """Every census tree under `root`: one per node, plus run 1's archive.

    A node added later needs no edit. There is one definition of this and it
    lives here -- a caller with its own idea of where the trees are indexes the
    ones it knows and returns a smaller number than it should, with no error.
    """
    return sorted(d for d in (Path(root) / "out").glob("census*") if d.is_dir())


def rebuild(path: Path | str, ldraw_dir: Path | str, root: Path | str = ".",
            census_dirs: Sequence[Path | str] | None = None,
            defects_path: Path | str = defects_toml.DEFAULT_PATH,
            status_path: Path | str = DEFAULT_STATUS_PATH,
            years_path: Path | str = DEFAULT_YEARS_PATH,
            successors_path: Path | str = DEFAULT_SUCCESSORS_PATH,
            commit_sha: str = "unknown",
            progress=lambda msg: None) -> dict[str, int]:
    path = Path(path)
    path.unlink(missing_ok=True)
    conn = connect(path)
    counts = {"parts": seed_parts(conn, ldraw_dir), "renders": 0,
              "measurements": 0, "skipped": 0, "replaced": 0,
              "defects": 0, "statuses": 0, "years": 0, "successors": 0}
    progress(f"seeded {counts['parts']} parts")

    root = Path(root)
    if census_dirs is None:
        census_dirs = census_trees(root)
    progress(f"{len(census_dirs)} census tree(s): "
             f"{', '.join(Path(d).name for d in census_dirs)}")

    for svg in sorted((root / "renders").rglob("*.svg")):
        record_render(conn, svg.stem, svg.parent.name, svg, root=root)
        counts["renders"] += 1
        progress(f"render {counts['renders']}: {svg.parent.name}/{svg.stem}")

    # A part drawn by two trees under one engine resolves to one row, and the
    # tree sorting last wins it. Nothing today collides -- the nodes run an
    # engine each -- but an archive that carries renders would, and the totals
    # would not move. Counted so the rebuild says so instead.
    from_tree: dict[tuple[str, str], Path] = {}

    for census_dir in census_dirs:
        census_dir = Path(census_dir)
        if not census_dir.is_dir():
            progress(f"{census_dir}: not there, skipped")
            continue

        # The census's renders stay out of git but are indexed all the same,
        # under their own source so they cannot be mistaken for the store's
        # drawing: it renders strokeless, so its fills carry the silhouette.
        for svg in sorted(census_dir.glob("renders/*/*.svg")):
            source = census_source(census_dir, svg.parent.name)
            if source not in SOURCES:
                continue
            first = from_tree.get((svg.stem, source))
            if first is not None:
                counts["replaced"] += 1
                progress(f"replaced {source}/{svg.stem}: {first} by {svg}")
            try:
                record_render(conn, svg.stem, source, svg, root=root)
            except Exception as e:  # noqa: BLE001
                # A census still running leaves half-written files behind it.
                counts["skipped"] += 1
                progress(f"skipped {source}/{svg.stem}: {type(e).__name__} {e}")
                continue
            if first is None:
                # A replacement is the same row rewritten, not another one.
                counts["renders"] += 1
            from_tree[(svg.stem, source)] = svg
            progress(f"render {counts['renders']}: {source}/{svg.stem}")

        # rglob, because the backfill gives each batch its own JSONL below the
        # census directory. One run per directory: run 1's archive holds the
        # same rows as the live tree it is a prefix of, and the run is the only
        # thing that tells the two apart.
        shards = sorted(census_dir.rglob("*.jsonl"))
        if not shards:
            continue
        where = _relative(census_dir, root)
        run_id = start_run(conn, "census",
                           {"dir": where, "shards": len(shards)}, commit_sha)
        for shard in shards:
            n = import_census_jsonl(conn, run_id, shard, census_dir)
            counts["measurements"] += n
            progress(f"{shard.name}: {n} measurements")
        finish_run(conn, run_id,
                   note=f"rebuilt from {len(shards)} shards in {where}")

    counts["defects"] = import_defects(conn, defects_path)
    counts["statuses"] = import_statuses(conn, status_path)
    # The CSV is the record, the way part-status.toml is: a rebuild drops the
    # database, and re-deriving these means downloading Rebrickable's dumps
    # again.
    if Path(years_path).is_file():
        counts["years"] = import_part_years(conn, years_path)
    if Path(successors_path).is_file():
        counts["successors"] = import_part_successors(conn, successors_path)
    progress(f"{counts['defects']} defects, {counts['statuses']} statuses, "
             f"{counts['years']} part years, {counts['successors']} successors")
    conn.close()
    return counts
