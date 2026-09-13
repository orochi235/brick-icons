"""Parts somebody asked a slot to draw again.

An append-only JSONL log rather than a `corpus.db` table: `census-ingest.sh`
rebuilds the database from the render trees, and a request is in no tree.
A request is pending while its slot holds no render made after it, so nothing
ever clears a line -- the render landing is the answer.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import db

DEFAULT_PATH = Path("store-queue") / "requests.jsonl"

#: A redraw expected to take no longer than this is drawn on the spot rather
#: than queued for a fleet round.
LOCAL_MAX_SECS = 20.0

#: Slots drawn by LDView or a browser, which nothing in this repository runs.
DRAWN_ELSEWHERE = ("reference", "ldview")


def draws_here(source: str, secs: float | None) -> bool:
    """Whether a redraw is drawn now rather than queued. Decal always is: it
    costs seconds, and no slot round draws it -- a queued decal would wait
    for a pass that never comes."""
    return source == "decal" or (secs is not None and secs <= LOCAL_MAX_SECS)


def add(path: Path | str, part: str, source: str, by: str = "lab",
        at: str | None = None) -> dict:
    record = {"part": part, "source": source, "at": at or db.now(), "by": by}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    return record


def load(path: Path | str) -> list[dict]:
    """Every request, oldest first. A torn last line from a writer that died
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
        if isinstance(r, dict) and {"part", "source", "at"} <= r.keys():
            out.append(r)
    return out


def _latest(path, source=None, part=None) -> dict[tuple[str, str], str]:
    asked = {}
    for r in load(path):
        if (source is None or r["source"] == source) and (
                part is None or r["part"] == part):
            key = (r["part"], r["source"])
            asked[key] = max(asked.get(key, ""), r["at"])
    return asked


def _unanswered(conn: sqlite3.Connection, asked: dict) -> dict:
    # made_at and a request's `at` are both db.now() strings, which order as
    # text.
    return {key: at for key, at in asked.items()
            if conn.execute(
                "SELECT 1 FROM renders WHERE part_id = ? AND source = ? "
                "AND made_at > ? LIMIT 1", (*key, at)).fetchone() is None}


def pending(conn: sqlite3.Connection, source: str,
            path: Path | str = DEFAULT_PATH) -> list[str]:
    """Parts still waiting on a redraw in `source`, longest-waiting first."""
    waiting = _unanswered(conn, _latest(path, source=source))
    return [part for (part, _s), _at in
            sorted(waiting.items(), key=lambda kv: kv[1])]


def pending_for(conn: sqlite3.Connection, part: str,
                path: Path | str = DEFAULT_PATH) -> dict[str, str]:
    """{slot: when it was asked} for this part's unanswered requests."""
    return {source: at for (_p, source), at in
            _unanswered(conn, _latest(path, part=part)).items()}


def cost(conn: sqlite3.Connection, part: str, source: str) -> float | None:
    """Seconds this part is expected to take in `source`: its latest attempt,
    else its latest clean measurement, else the slot's mean. None when the
    slot has never been timed at all."""
    for query in (
            "SELECT secs FROM attempts WHERE part_id = ? AND source = ? "
            "AND secs IS NOT NULL ORDER BY run_id DESC LIMIT 1",
            "SELECT secs FROM measurements WHERE part_id = ? AND source = ? "
            "AND error IS NULL AND secs IS NOT NULL "
            "ORDER BY run_id DESC LIMIT 1"):
        row = conn.execute(query, (part, source)).fetchone()
        if row is not None:
            return float(row[0])
    for table, clean in (("measurements", "AND error IS NULL"),
                         ("attempts", "")):
        row = conn.execute(
            f"SELECT AVG(secs) FROM {table} WHERE source = ? "
            f"AND secs IS NOT NULL {clean}", (source,)).fetchone()
        if row is not None and row[0] is not None:
            return float(row[0])
    return None


def front_load(lines: list[str], parts: list[str],
               per_batch: int = 12) -> list[str]:
    """A batch list with `parts` first, in batches of `per_batch`, and each of
    them dropped from wherever else the list already held it."""
    first = set(parts)
    rest = [p for line in lines for p in line.split(",")
            if p.strip() and p not in first]
    rest_lines = [",".join(rest[i:i + per_batch])
                  for i in range(0, len(rest), per_batch)]
    ahead = [",".join(parts[i:i + per_batch])
             for i in range(0, len(parts), per_batch)]
    return ahead + rest_lines
