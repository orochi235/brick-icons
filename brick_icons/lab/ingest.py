"""The ingestion log: the `runs` table with what each run took in.

Read-only. A run's tally comes from `attempts`, so a kind that writes
measurements instead -- a census rebuild -- shows a total of nothing rather
than being left off; "this ingest took nothing in" is an answer.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

# A store run holds thousands of attempts. The rollup answers what happened;
# the rows are there to name a few of the parts it happened to.
ROW_CAP = 200


def _secs(started: str, finished: str | None) -> float | None:
    if finished is None:
        return None
    try:
        return (datetime.fromisoformat(finished)
                - datetime.fromisoformat(started)).total_seconds()
    except ValueError:
        return None


def _args(raw: str) -> dict:
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def runs(conn: sqlite3.Connection) -> list[dict]:
    """Every ingest, newest first, each with its own tally of attempts.

    `counts` is keyed by state, with everything that failed under `error` --
    a null state and an error are the same row seen twice, and the log is
    read for how many did not make it, not for which exception said so.
    """
    tally: dict[int, dict[str, int]] = {}
    for run_id, state, error, n in conn.execute(
            "SELECT run_id, state, error, count(*) FROM attempts "
            "GROUP BY run_id, state, error"):
        key = "error" if state is None or error is not None else state
        counts = tally.setdefault(run_id, {})
        counts[key] = counts.get(key, 0) + n
    out = []
    for row in conn.execute(
            "SELECT id, kind, started, finished, commit_sha, args, note "
            "FROM runs ORDER BY started DESC, id DESC"):
        counts = tally.get(row["id"], {})
        out.append({"id": row["id"], "kind": row["kind"],
                    "started": row["started"], "finished": row["finished"],
                    "secs": _secs(row["started"], row["finished"]),
                    "commit_sha": row["commit_sha"], "note": row["note"],
                    "args": _args(row["args"]),
                    "counts": counts, "total": sum(counts.values())})
    return out


def attempts(conn: sqlite3.Connection, run_id: int, *,
             failed_only: bool = False, limit: int = ROW_CAP) -> dict:
    """One run's attempts: the errors rolled up, and a capped sample of rows.

    `total` counts what the sample was drawn from, so a page never implies
    the run was as small as the list it is showing.
    """
    where = "run_id = ?"
    params: list = [run_id]
    if failed_only:
        where += " AND (state IS NULL OR error IS NOT NULL)"
    total = conn.execute(
        f"SELECT count(*) FROM attempts WHERE {where}", params).fetchone()[0]
    errors = [{"error": error, "n": n} for error, n in conn.execute(
        "SELECT error, count(*) AS n FROM attempts "
        "WHERE run_id = ? AND error IS NOT NULL "
        "GROUP BY error ORDER BY n DESC, error", (run_id,))]
    rows = [dict(r) for r in conn.execute(
        f"SELECT part_id, source, state, secs, error, detail FROM attempts "
        f"WHERE {where} ORDER BY part_id LIMIT ?", [*params, limit])]
    return {"rows": rows, "errors": errors, "total": total}
