"""The corpus database: part status, defects, renders and measurement history.

Derived, never authoritative. The artifacts are `renders/<source>/<part>.<ext>`
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
from brick_icons import features
from brick_icons.lab import defects as defects_toml

DEFAULT_PATH = Path("corpus.db")
SCHEMA_VERSION = 6
PART_STATUSES = ("unreviewed", "good", "suspect", "broken", "wontfix")
# Part categories the project is not trying to draw. A rule over the library's
# own category, not a list of ids: it covers parts nobody has seen yet, and it
# is not a judgment about any one part, so it stays out of `parts.status` and
# its hand-written record. `|` is LDraw's mark for a part nobody at LEGO made
# -- third-party electronics and wheels that fit LEGO.
#
# Stickers were here and are not any more: occt draws 2,695 of the 2,701, so
# the exclusion was hiding a drawn category from every coverage number.
OUT_OF_SCOPE_CATEGORIES = ("|",)
SOURCES = ("naive", "occt", "decal", "ldview", "reference",
           "translucent-naive", "translucent-occt",
           "silhouette-naive", "silhouette-occt",
           "white-naive", "white-occt")

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
  -- Where those seconds went, as the census's own `phase` dict. JSON rather
  -- than columns because the phases follow the engine: three landed in one
  -- evening, and each would otherwise have been a migration.
  phases TEXT,
  -- Render facts that are not times, as the census's own `count` dict --
  -- today whether `UnifySameDomain` crashed and the engine drew the part
  -- with its faces unmerged. A phase cannot say that: the call took
  -- seconds either way.
  counts TEXT,
  error TEXT, detail TEXT,
  PRIMARY KEY (run_id, part_id, engine)
);

CREATE TABLE IF NOT EXISTS attempts (
  run_id INTEGER NOT NULL REFERENCES runs(id),
  part_id TEXT NOT NULL,
  -- The slot the run was drawing into, as `renders.source` names it.
  source TEXT NOT NULL,
  -- `stored`, `cached` or `present`; null when `error` says why nothing was
  -- drawn. A part that timed out leaves no render and no measurement, so this
  -- row is the only record it was ever tried.
  state TEXT,
  secs REAL,
  error TEXT, detail TEXT,
  PRIMARY KEY (run_id, part_id, source)
);

CREATE TABLE IF NOT EXISTS defects (
  id TEXT PRIMARY KEY,
  part_id TEXT NOT NULL,
  engines TEXT NOT NULL,
  status TEXT NOT NULL,
  title TEXT NOT NULL,
  -- The symptom families this defect belongs to, as a JSON list. A list and
  -- not a column because a row can show two independent faults -- 53119 has
  -- stray lines AND banding -- and splitting it would lose that they were
  -- seen together.
  classes TEXT,
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

-- How a part is built, from brick_icons.features: one row per feature, with
-- a value only where the feature is a measure. Derived from the library and
-- rebuilt whole, so nothing here is ever edited by hand -- a typed label would
-- outlive the extractor that disagreed with it, and say nothing.
CREATE TABLE IF NOT EXISTS part_features (
  part_id TEXT NOT NULL,
  feature TEXT NOT NULL,
  value REAL,
  PRIMARY KEY (part_id, feature)
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
CREATE INDEX IF NOT EXISTS attempts_by_part ON attempts(part_id, source);
CREATE INDEX IF NOT EXISTS renders_by_part ON renders(part_id);
-- Feature first: the question this table exists for is "which parts have
-- X", and part-first would scan every row to answer it.
CREATE INDEX IF NOT EXISTS part_features_by_feature
  ON part_features(feature, part_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: Columns added to a table that already existed. `CREATE TABLE IF NOT
#: EXISTS` leaves an old table alone, and several sessions share one
#: corpus.db, so a rebuild is not a thing to make them all do. Nullable and
#: additive only: SCHEMA_VERSION is deliberately not bumped for these, because
#: older code cannot misread a column it never selects.
_ADDED_COLUMNS = (("defects", "classes", "TEXT"),
                  ("measurements", "counts", "TEXT"))


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    for table, column, decl in _ADDED_COLUMNS:
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


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
    _add_missing_columns(conn)
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


def seed_part_features(conn: sqlite3.Connection, ldraw_dir: Path | str,
                       progress=lambda msg: None) -> int:
    """Derive every part's construction features and replace the table.

    Cleared first rather than upserted: a feature the extractor stops emitting
    has to disappear, and an ON CONFLICT update leaves it behind looking
    current.
    """
    conn.execute("DELETE FROM part_features")
    n = 0
    for part_id, feats in features.build(ldraw_dir, progress=progress):
        conn.executemany(
            "INSERT OR REPLACE INTO part_features (part_id, feature, value) "
            "VALUES (?, ?, ?)",
            [(part_id, name, value) for name, value in feats.items()])
        n += len(feats)
    conn.commit()
    return n


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
                     r.get("secs"),
                     json.dumps(r["phase"]) if r.get("phase") else None,
                     json.dumps(r["counts"]) if r.get("counts") else None,
                     r.get("error"), r.get("detail")))
    conn.executemany(
        "INSERT OR REPLACE INTO measurements (run_id, part_id, engine, source, "
        "build, missing_px, extra_px, missing_comps, extra_d99, extra_d100, "
        "secs, phases, counts, error, detail) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    return len(rows)


def import_store_jsonl(conn: sqlite3.Connection, run_id: int,
                       path: Path | str) -> int:
    """One row per part a render-store run attempted, drawn or not.

    Deliberately not `measurements`: those are scores against the part's own
    polygons, and every reader takes the newest run per part and engine -- a
    store row landing there would hand each occt finding a null where its
    d99 was. A part logged twice in one run keeps its last row, so a retry
    settles the failure before it -- what `Runner.remaining` already assumes.
    """
    rows = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        rows.append((run_id, r["part"], r["source"], r.get("state"),
                     r.get("secs"), r.get("error"), r.get("detail")))
    conn.executemany(
        "INSERT OR REPLACE INTO attempts (run_id, part_id, source, state, "
        "secs, error, detail) VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
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
    # The reference that is mathematically compatible with the library:
    # orthographic, and three.js's LDrawLoader substitutes no primitives, so
    # what it draws is the authored tessellation our own engine reads. LDView
    # is neither -- it renders perspective, and `-AllowPrimitiveSubstitution`
    # redraws a `4-4cyli` at whatever curve quality it likes.
    #
    # This argv is a config KEY and nothing runs it: the renderer is a browser,
    # and one page draws a whole list in one WebGL context. Bake the slot with
    # `scripts/shot-sink.py --list <parts> --out renders/reference`; a per-part
    # CLI flag would launch Chrome 24,591 times.
    "reference": ["--reference", "--angle", "iso"],
    # See-through bricks: the ordinary drawing with its fills let down, so
    # what the far side of a part does is visible against what the near side
    # draws. Opacity is stated rather than inherited -- a translucent LDraw
    # color otherwise supplies it, and the slot would be see-through for
    # some parts and solid for others.
    "translucent-naive": ["--engine", "naive", "--shading", "outline",
                          "--shade-style", "flat3", "--angle", "iso",
                          "--format", "svg", "--opacity", "0.5"],
    "translucent-occt": ["--engine", "occt", "--shading", "outline",
                         "--shade-style", "flat3", "--angle", "iso",
                         "--format", "svg", "--opacity", "0.5"],
    # The census's oracle drawing, not the store's: strokeless, so the fills
    # carry the silhouette and no stroke overhang has to be subtracted from
    # the comparison. One source per engine because the census writes
    # out/census/renders/<engine>/<part>.svg and the path holds only one.
    "silhouette-naive": ["--format", "svg", "--shading", "outline",
                         "--shade-style", "flat3", "--angle", "iso",
                         "--engine", "naive", "--line-width", "0",
                         "--silhouette-width", "0"],
    "silhouette-occt": ["--format", "svg", "--shading", "outline",
                        "--shade-style", "flat3", "--angle", "iso",
                        "--engine", "occt", "--line-width", "0",
                        "--silhouette-width", "0"],
    # The white facet: opaque white fills that only occlude, strokes carrying
    # the drawing. Its own source per engine because the key is derived from
    # the source alone -- indexed as silhouette-<engine> it would REPLACE the
    # oracle's row for every part, the drawing silently swapped underneath.
    "white-naive": ["--format", "svg", "--shading", "outline",
                    "--shade-style", "white", "--angle", "iso",
                    "--engine", "naive", "--line-width", "2",
                    "--silhouette-width", "2"],
    "white-occt": ["--format", "svg", "--shading", "outline",
                   "--shade-style", "white", "--angle", "iso",
                   "--engine", "occt", "--line-width", "2",
                   "--silhouette-width", "2"],
}


def canonical_argv(part_id: str, source: str) -> list[str]:
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}, not {source!r}")
    return [part_id, *_CANONICAL[source]]


#: What the rebuild will index. A slot's artifact is whatever its renderer
#: emits, and a format missing here is silently invisible: re-encoding the
#: ldview slot to WebP dropped all 3,896 of its rows and took the slot out of
#: the wall's picker, which reads `SELECT source, count(*) FROM renders`.
RENDER_SUFFIXES = (".svg", ".png", ".webp")


def record_render(conn: sqlite3.Connection, part_id: str, source: str,
                  path: Path | str, root: Path | str = ".",
                  run_id: int | None = None) -> str:
    argv = canonical_argv(part_id, source)
    path = Path(path)
    # A slot's artifact is whatever its renderer emits -- LDView writes a PNG
    # -- so the bytes are hashed, and only an SVG is parsed for its box.
    raw = path.read_bytes()
    width = height = None
    if path.suffix == ".svg":
        box = goldens.summarize_svg(raw.decode())["viewBox"]
        if box:
            _, _, width, height = (float(v) for v in box.split())
    key = cache.key(argv)
    conn.execute(
        "INSERT OR REPLACE INTO renders (part_id, source, config_key, run_id, "
        "made_at, path, sha256, width, height) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (part_id, source, key, run_id, now(),
         str(path.resolve().relative_to(Path(root).resolve())),
         goldens.sha256(raw), width, height))
    conn.commit()
    return key


def store_render(conn: sqlite3.Connection, part_id: str, source: str,
                 made: Path | str, root: Path | str = ".",
                 run_id: int | None = None) -> Path:
    """Copy a freshly rendered artifact into the store and index it.

    The extension follows what was made rather than being assumed: `ldview`
    is a raster slot, and reading a PNG as text corrupts it.
    """
    made = Path(made)
    dest = Path(root) / "renders" / source / f"{part_id}{made.suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(made.read_bytes())
    record_render(conn, part_id, source, dest, root=root, run_id=run_id)
    return dest


def import_defects(conn: sqlite3.Connection, path: Path | str) -> int:
    records = defects_toml.load(path)
    conn.executemany(
        "INSERT OR REPLACE INTO defects (id, part_id, engines, status, title, "
        "classes, mark, kind, points, filed, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(r["id"], r["part"], json.dumps(r.get("engines", [])),
          r.get("status", "open"), r["title"],
          json.dumps(r["classes"]) if r.get("classes") else None,
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
        if row["classes"]:
            record["classes"] = json.loads(row["classes"])
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


#: A tree may state its slot outright, in this file, rather than spelling it
#: in the directory name. Written by the job that filled the tree and fetched
#: home with it, so nothing on this side has to remember what a directory was
#: for. It is the only way to name the slots whose names carry no facet word
#: -- `occt` derives to `silhouette-occt` and always will, because that
#: fallback is what keeps a re-run like out/census-run2 replacing out/census
#: part for part instead of becoming a slot of its own.
SOURCE_MARKER = "SOURCE"


def census_source(census_dir: Path | str, engine: str) -> str:
    """The render source a census tree's drawings are filed under.

    A `SOURCE` file in the tree wins, naming the slot outright. Otherwise the
    directory name is read as a FACET, not a slot: the directories all begin
    `census` because they are census runs, and the slots dropped that word. A
    tree gets its own source only if what is left after the prefix and the
    engine names one this module knows; anything else is another run of the base
    census and files under silhouette-<engine>, so out/census-run2 still
    replaces out/census part for part. That fallback is what keeps the rule
    from swallowing a re-run: only a declared facet like census-white-naive
    sits beside the oracle instead of overwriting it, and it has to, because
    a render's config_key comes from its source alone.
    """
    marker = Path(census_dir) / SOURCE_MARKER
    try:
        stated = marker.read_text().strip()
    except OSError:
        stated = ""
    if stated in SOURCES:
        return stated

    stem = Path(census_dir).name
    facet = stem.removeprefix("census").strip("-").removesuffix(engine).strip("-")
    named = f"{facet}-{engine}" if facet else f"silhouette-{engine}"
    return named if named in SOURCES else f"silhouette-{engine}"


def census_trees(root: Path | str = ".") -> list[Path]:
    """Every census tree under `root`: one per node, plus run 1's archive.

    A node added later needs no edit. There is one definition of this and it
    lives here -- a caller with its own idea of where the trees are indexes the
    ones it knows and returns a smaller number than it should, with no error.

    A tree carrying a SOURCE_MARKER counts whatever it is called: a slot fill
    is named for its slot, not for the census, and a tree the rebuild cannot
    see is renders that came all the way home and indexed as nothing.
    """
    out = Path(root) / "out"
    if not out.is_dir():
        return []
    return sorted(d for d in out.iterdir() if d.is_dir()
                  and (d.name.startswith("census")
                       or (d / SOURCE_MARKER).is_file()))


def store_logs(tree: Path) -> list[Path]:
    """A store tree's JSONL logs. `Runner` names them `<log>.<source>` and
    keeps a `.inflight` marker beside them holding a part id, not JSON."""
    return sorted(p for p in tree.glob("*.jsonl.*")
                  if p.is_file() and not p.name.endswith(".inflight"))


def store_trees(root: Path | str = ".") -> list[Path]:
    """Every directory holding render-store logs: `out/store` itself, where a
    local sharded run writes, and the per-run directories a fleet run gets."""
    store = Path(root) / "out" / "store"
    if not store.is_dir():
        return []
    here = [d for d in sorted(store.iterdir()) if d.is_dir()]
    return [d for d in [store, *here] if store_logs(d)]


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
              "measurements": 0, "attempts": 0, "skipped": 0, "replaced": 0,
              "defects": 0, "statuses": 0, "years": 0, "successors": 0,
              "features": 0}
    progress(f"seeded {counts['parts']} parts")
    counts["features"] = seed_part_features(
        conn, ldraw_dir, progress=lambda m: progress(f"features {m}"))
    progress(f"derived {counts['features']} part features")

    root = Path(root)
    if census_dirs is None:
        census_dirs = census_trees(root)
    progress(f"{len(census_dirs)} census tree(s): "
             f"{', '.join(Path(d).name for d in census_dirs)}")

    for made in sorted(p for p in (root / "renders").rglob("*")
                       if p.suffix in RENDER_SUFFIXES):
        record_render(conn, made.stem, made.parent.name, made, root=root)
        counts["renders"] += 1
        progress(f"render {counts['renders']}: {made.parent.name}/{made.stem}")

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

    # The store's own logs, which no census tree carries: a part that timed
    # out here has no render to index and no measurement to import.
    for tree in store_trees(root):
        logs = store_logs(tree)
        where = _relative(tree, root)
        run_id = start_run(conn, "store", {"dir": where, "logs": len(logs)},
                           commit_sha)
        for log in logs:
            n = import_store_jsonl(conn, run_id, log)
            counts["attempts"] += n
            progress(f"{log.name}: {n} attempts")
        finish_run(conn, run_id,
                   note=f"rebuilt from {len(logs)} logs in {where}")

    counts["defects"] = import_defects(conn, defects_path)
    counts["statuses"] = import_statuses(conn, status_path)
    # The CSV is the record, the way part-status.toml is: a rebuild drops the
    # database, and re-deriving these means downloading Rebrickable's dumps
    # again.
    if Path(years_path).is_file():
        counts["years"] = import_part_years(conn, years_path)
    if Path(successors_path).is_file():
        counts["successors"] = import_part_successors(conn, successors_path)
    progress(f"{counts['attempts']} store attempts, "
             f"{counts['defects']} defects, {counts['statuses']} statuses, "
             f"{counts['years']} part years, {counts['successors']} successors")
    conn.close()
    return counts
