"""Renders that displaced an older one, and what a reviewer made of them.

An append-only JSONL log rather than a `corpus.db` table, for the reason
`requests.py` gives: a rebuild drops the database and re-derives it from the
render trees, and a displacement is in no tree. The `review` table mirrors the
log and `replay` rebuilds it.

The displaced file is copied under `store-queue/before/` when the line is
written. A fleet round leaves its drawings in its own `out/<task>/` tree, but
a local redraw writes over `renders/<slot>/<part>.svg` in place, and that is
the one path where the before would otherwise be gone.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Iterable
from pathlib import Path

DEFAULT_PATH = Path("store-queue") / "review.jsonl"
BEFORE_DIR = Path("store-queue") / "before"
VERDICTS = ("fixed", "better", "neutral", "regression")

SCHEMA = """
CREATE TABLE IF NOT EXISTS review (
  id TEXT PRIMARY KEY,
  part_id TEXT NOT NULL,
  source TEXT NOT NULL,
  at TEXT NOT NULL,
  run_id INTEGER,
  made_by TEXT,
  before_path TEXT NOT NULL,
  before_sha TEXT NOT NULL,
  before_made_at TEXT,
  before_run_id INTEGER,
  before_kept TEXT,
  after_path TEXT NOT NULL,
  after_sha TEXT NOT NULL,
  diff_components INTEGER,
  diff_pixels INTEGER,
  diff_width INTEGER,
  diff_at TEXT,
  diff_panel TEXT,
  verdict TEXT,
  note TEXT,
  judged_at TEXT,
  judged_by TEXT,
  judged_defects TEXT
);
CREATE INDEX IF NOT EXISTS review_part ON review(part_id, source);
"""


#: Columns added to `review` after the table shipped. `CREATE TABLE IF NOT
#: EXISTS` cannot add one, so an existing corpus.db needs them put on.
_ADDED_COLUMNS = (("diff_panel", "TEXT"),)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    have = {r[1] for r in conn.execute("PRAGMA table_info(review)")}
    for column, decl in _ADDED_COLUMNS:
        if column not in have:
            conn.execute(f"ALTER TABLE review ADD COLUMN {column} {decl}")
    conn.commit()


def _column(row, name, default=None):
    """A column an older row object may predate."""
    try:
        return row[name]
    except (IndexError, KeyError):
        return default


def _now() -> str:
    from . import db
    return db.now()


def entry_id(source: str, part: str, after_sha: str) -> str:
    return f"{source}/{part}/{after_sha[:12]}"


def by_from_path(path: Path | str) -> str:
    """Who drew this: the round's tree name under `out/`, else the store."""
    parts = Path(path).parts
    if len(parts) > 1 and parts[0] == "out":
        return parts[1]
    return "store"


def append(path: Path | str, record: dict) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    return record


def load(path: Path | str) -> list[dict]:
    """Every line, oldest first. A torn last line from a writer that died
    mid-append is skipped rather than failing every reader."""
    path = Path(path)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict) and {"kind", "id", "at"} <= r.keys():
            out.append(r)
    return out


def fold(lines: list[dict]) -> dict[str, dict]:
    """The current state of each entry: its `replaced` line, the latest
    `diff` and the latest `judged`. A diff or verdict for an id no line
    introduced is dropped."""
    entries: dict[str, dict] = {}
    for line in lines:
        kind, eid = line["kind"], line["id"]
        if kind == "replaced":
            entries.setdefault(eid, {**line, "diff": None, "judged": None})
        elif eid in entries and kind == "diff":
            entries[eid]["diff"] = {k: line[k] for k in
                                    ("components", "pixels", "width", "at")}
        elif eid in entries and kind == "judged":
            entries[eid]["judged"] = {k: line.get(k) for k in
                                      ("verdict", "note", "by", "defects", "at")}
        elif eid in entries and kind == "unjudged":
            entries[eid]["judged"] = None
        elif kind == "dropped":
            entries.pop(eid, None)
    return entries


def upsert(conn: sqlite3.Connection, entry: dict) -> None:
    ensure_schema(conn)
    diff, judged = entry.get("diff") or {}, entry.get("judged") or {}
    conn.execute(
        "INSERT OR REPLACE INTO review (id, part_id, source, at, run_id, "
        "made_by, before_path, before_sha, before_made_at, before_run_id, "
        "before_kept, after_path, after_sha, diff_components, diff_pixels, "
        "diff_width, diff_at, verdict, note, judged_at, judged_by, "
        "judged_defects) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
        "?, ?, ?, ?, ?, ?, ?)",
        (entry["id"], entry["part"], entry["source"], entry["at"],
         entry.get("run_id"), entry.get("by"),
         entry["before"]["path"], entry["before"]["sha256"],
         entry["before"].get("made_at"), entry["before"].get("run_id"),
         entry["before"].get("kept"),
         entry["after"]["path"], entry["after"]["sha256"],
         diff.get("components"), diff.get("pixels"), diff.get("width"),
         diff.get("at"),
         judged.get("verdict"), judged.get("note"), judged.get("at"),
         judged.get("by"),
         json.dumps(judged["defects"]) if judged else None))
    conn.commit()


def replay(conn: sqlite3.Connection, path: Path | str) -> int:
    ensure_schema(conn)
    entries = fold(load(path))
    for entry in entries.values():
        upsert(conn, entry)
    return len(entries)


def keep_before(root: Path | str, source: str, part: str, path: Path | str,
                sha: str) -> str | None:
    """Copy the displaced file to its sha-named place; the path relative to
    root, or None when the file is already gone."""
    src = Path(root) / path
    if not src.is_file():
        return None
    dest = Path(root) / BEFORE_DIR / source / f"{part}.{sha[:8]}{src.suffix}"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    return str(dest.relative_to(Path(root)))


def record_replaced(conn: sqlite3.Connection, root: Path | str,
                    log: Path | str, *, part: str, source: str,
                    before: dict, after: dict, run_id: int | None,
                    by: str) -> dict | None:
    """One displacement. `before` is the row being replaced (`path`,
    `sha256`, `made_at`, `run_id`), `after` the new file's `path` and
    `sha256`, both relative to root. Nothing is written when the id is
    already in the table: the watcher re-reads a tree every pass."""
    eid = entry_id(source, part, after["sha256"])
    ensure_schema(conn)
    if conn.execute("SELECT 1 FROM review WHERE id = ?", (eid,)).fetchone():
        return None
    kept = keep_before(root, source, part, before["path"], before["sha256"])
    line = {"kind": "replaced", "id": eid, "at": _now(), "part": part,
            "source": source, "run_id": run_id, "by": by,
            "before": {**before, "kept": kept}, "after": dict(after)}
    append(log, line)
    upsert(conn, {**line, "diff": None, "judged": None})
    return line


def record_diff(conn: sqlite3.Connection, log: Path | str, eid: str,
                components: int, pixels: int, width: int) -> dict:
    line = {"kind": "diff", "id": eid, "at": _now(), "components": components,
            "pixels": pixels, "width": width}
    append(log, line)
    conn.execute("UPDATE review SET diff_components = ?, diff_pixels = ?, "
                 "diff_width = ?, diff_at = ? WHERE id = ?",
                 (components, pixels, width, line["at"], eid))
    conn.commit()
    return line


def record_judged(conn: sqlite3.Connection, log: Path | str, eid: str,
                  verdict: str, note: str, *, by: str,
                  defects: list[str],
                  restore: dict[str, dict] | None = None) -> dict:
    """`restore` is what the verdict is about to overwrite, per defect id:
    the `status`, `checked` and `notes` held before the write, so an undo
    puts them back verbatim rather than reconstructing them. Lines written
    before it existed have none, and an undo on one can only guess."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}, not {verdict!r}")
    line = {"kind": "judged", "id": eid, "at": _now(), "verdict": verdict,
            "note": note, "by": by, "defects": list(defects),
            "restore": restore or {}}
    append(log, line)
    conn.execute("UPDATE review SET verdict = ?, note = ?, judged_at = ?, "
                 "judged_by = ?, judged_defects = ? WHERE id = ?",
                 (verdict, note, line["at"], by, json.dumps(line["defects"]),
                  eid))
    conn.commit()
    return line


def last_judged(log: Path | str, eid: str) -> dict | None:
    """The `judged` line an undo of this entry is taking back, or None when
    the entry has been unjudged since -- or was never judged at all."""
    found = None
    for line in load(log):
        if line["id"] != eid:
            continue
        if line["kind"] == "judged":
            found = line
        elif line["kind"] == "unjudged":
            found = None
    return found


def record_unjudged(conn: sqlite3.Connection, log: Path | str, eid: str, *,
                    by: str) -> dict:
    """Take a verdict back. The log is append-only, so this is a line of its
    own and `fold` clears the verdict when it replays one."""
    line = {"kind": "unjudged", "id": eid, "at": _now(), "by": by}
    append(log, line)
    conn.execute("UPDATE review SET verdict = NULL, note = NULL, "
                 "judged_at = NULL, judged_by = NULL, judged_defects = NULL "
                 "WHERE id = ?", (eid,))
    conn.commit()
    return line


def record_dropped(conn: sqlite3.Connection, log: Path | str, eid: str, *,
                   by: str) -> dict:
    """Retire an entry nobody is going to judge.

    The log is append-only and `fold` rebuilds the table from it, so deleting
    the row alone is undone by the next rebuild -- a drop has to be a line of
    its own. The displaced drawing under `before/` is NOT removed here: a
    reaper can only know a kept copy is unreferenced by looking at every
    entry at once, which is `scripts/flush-review.py`'s job."""
    line = {"kind": "dropped", "id": eid, "at": _now(), "by": by}
    append(log, line)
    conn.execute("DELETE FROM review WHERE id = ?", (eid,))
    conn.commit()
    return line


def side_files(root: Path | str, row) -> tuple[Path, Path] | None:
    """The two files a row names, inside root, or None when either is gone.
    The kept copy first: the displaced path may have been written over."""
    base = Path(root).resolve()

    def inside(rel):
        if not rel:
            return None
        path = (base / rel).resolve()
        return path if base in path.parents and path.is_file() else None

    before = inside(row["before_kept"]) or inside(row["before_path"])
    after = inside(row["after_path"])
    return (before, after) if before and after else None


def panel_signature() -> str:
    """What the cached panel was painted with. A row stamped with anything
    else is measured again: the threshold moved once and every entry already
    measured kept its old drawing and its old count, which was the bug the
    move existed to fix."""
    from .lab import diff
    return (f"thr={diff.PANEL_THRESHOLD} min={diff.PANEL_MIN_PX} "
            f"w={diff.RASTER_WIDTH}")


def measure(conn: sqlite3.Connection, root: Path | str, log: Path | str,
            cache_dir: Path | str, row) -> Path:
    """Paint the row's diff panel into `cache_dir/<id>/diff.png`, recording
    its counts when the row has none. Raises FileNotFoundError when a side is
    gone and RuntimeError when resvg refuses one."""
    from .lab import diff
    out = Path(cache_dir) / row["id"].replace("/", "_")
    panel = out / "diff.png"
    signature = panel_signature()
    stale = _column(row, "diff_panel") != signature
    if panel.is_file() and row["diff_components"] is not None and not stale:
        return panel
    sides = side_files(root, row)
    if sides is None:
        raise FileNotFoundError(f"{row['id']}: a side is no longer on disk")
    image, components, pixels = diff.measure_pair(*sides, out)
    out.mkdir(parents=True, exist_ok=True)
    image.save(panel)
    if row["diff_components"] is None or stale:
        record_diff(conn, log, row["id"], components, pixels, diff.RASTER_WIDTH)
    conn.execute("UPDATE review SET diff_panel = ? WHERE id = ?",
                 (signature, row["id"]))
    conn.commit()
    return panel


def measure_unmeasured(conn: sqlite3.Connection, root: Path | str,
                       log: Path | str, cache_dir: Path | str,
                       limit: int | None = None,
                       progress=lambda msg: None,
                       only: Iterable[str] | None = None) -> tuple[int, list[dict]]:
    """Measure the newest entries with no diff, and the ones whose panel was
    painted under other settings, `limit` of them or all, narrowed to the ids
    in `only` when it is given. (measured, [{id, error}] for the ones that
    could not be).

    A stale panel counts as unmeasured or a threshold change reaches only the
    entries someone happens to open: the rest keep the drawing the change
    exists to replace.
    """
    ensure_schema(conn)
    ids = None if only is None else list(only)
    if ids is not None and not ids:
        return 0, []
    rows = conn.execute(
        "SELECT * FROM review WHERE (diff_components IS NULL "
        "   OR diff_panel IS NOT ?)"
        + ("" if ids is None
           else f" AND id IN ({','.join('?' * len(ids))})")
        + " ORDER BY at DESC"
        + (f" LIMIT {int(limit)}" if limit is not None else ""),
        (panel_signature(), *(ids or ()))).fetchall()
    measured, failed = 0, []
    for i, row in enumerate(rows, 1):
        try:
            measure(conn, root, log, cache_dir, row)
            measured += 1
            progress(f"{i}/{len(rows)} {row['id']}")
        except (FileNotFoundError, RuntimeError) as e:
            failed.append({"id": row["id"], "error": str(e)})
            progress(f"{i}/{len(rows)} {row['id']}: {e}")
    return measured, failed
