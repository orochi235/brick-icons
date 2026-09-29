"""One part's measurements over calendar time, one series per slot.

A point is dated by when its drawing was written (`drawn_at`). A row whose
drawing was gone before anyone read it has no such date, so it takes its
engine revision's commit date instead -- `runs.started` would not do, because
it is when the row was ingested, and a rebuild re-ingested everything on one day.
"""
from __future__ import annotations

import sqlite3
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=4096)
def _commit_date(root: str, sha: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", root, "show", "-s", "--format=%cI", sha],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    # UTC, like `drawn_at`, so the two sort together as strings.
    when = datetime.fromisoformat(out.stdout.strip()).astimezone(timezone.utc)
    return when.isoformat(timespec="seconds")


def _build_sha(build: str | None) -> str | None:
    """`1494.3c9e936+` -> `3c9e936`: the count and the dirty mark carry no
    commit."""
    if not build or "." not in build:
        return None
    return build.split(".", 1)[1].rstrip("+") or None


def part_history(conn: sqlite3.Connection, part_id: str,
                 root: Path | str) -> dict:
    series: dict[str, list[dict]] = {}
    for r in conn.execute(
            "SELECT m.source, m.engine, m.build, m.secs, m.bytes, m.objects, "
            "m.drawn_at, m.error, m.run_id FROM measurements m "
            "WHERE m.part_id = ?", (part_id,)):
        sha = _build_sha(r["build"])
        at = r["drawn_at"] or (_commit_date(str(root), sha) if sha else None)
        if at is None:
            continue
        series.setdefault(r["source"] or r["engine"], []).append({
            "at": at, "secs": r["secs"], "bytes": r["bytes"],
            "objects": r["objects"], "build": r["build"], "error": r["error"],
            "run_id": r["run_id"], "dated_by": "drawn" if r["drawn_at"] else "build"})
    return {"series": [{"source": source, "points": sorted(points, key=lambda p: p["at"])}
                       for source, points in sorted(series.items())]}
