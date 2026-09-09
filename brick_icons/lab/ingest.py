"""The ingestion log: the `runs` table with what each run took in.

Read-only. A run writes ONE of the three tables -- a store run files attempts,
a census or a watcher files measurements and renders -- so every count here
reads all three. Tallying attempts alone reported each of the others as having
taken nothing in, which is exactly what a pass that did nothing reports, and
telling those two apart is what the log is for.
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


def _parts(counts: dict[str, int]) -> int:
    """Parts, not rows. The attempt states partition the parts a store run
    tried, so those add up; `drawn` and `scored` are two views of one set of
    parts -- a part that timed out is scored and not drawn -- so the larger
    stands for both rather than summing to twice the work."""
    states = sum(n for k, n in counts.items() if k not in ("drawn", "scored"))
    return states + max(counts.get("drawn", 0), counts.get("scored", 0))


def runs(conn: sqlite3.Connection) -> list[dict]:
    """Every ingest, newest first, each with its own tally of what it took in.

    Counted across all three tables a run can write, because a run writes one
    of them and reading only `attempts` reported every census and every
    watcher as having taken nothing in -- indistinguishable from a pass that
    genuinely did nothing, which is the one thing the log exists to tell apart.

    From `attempts` the key is the state, with everything that failed under
    `error`: a null state and an error are the same row seen twice, and the
    log is read for how many did not make it, not for which exception said so.
    `drawn` and `scored` are the other two tables, which have no state to key
    on -- a row there is a part that came back.
    """
    tally: dict[int, dict[str, int]] = {}
    for run_id, state, error, n in conn.execute(
            "SELECT run_id, state, error, count(*) FROM attempts "
            "GROUP BY run_id, state, error"):
        key = "error" if state is None or error is not None else state
        counts = tally.setdefault(run_id, {})
        counts[key] = counts.get(key, 0) + n
    for key, table in (("drawn", "renders"), ("scored", "measurements")):
        for run_id, n in conn.execute(
                f"SELECT run_id, count(*) FROM {table} "
                f"WHERE run_id IS NOT NULL GROUP BY run_id"):
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
                    "counts": counts, "total": _parts(counts)})
    return out


#: What a part was in this slot before the run being read touched it: the
#: newest row about it from a run that STARTED EARLIER. Without it a row says
#: only where the part ended up, and the log is read to find out what an
#: ingest CHANGED -- a part that was already drawn and one that had been
#: timing out for a week are the same line otherwise.
#:
#: All three tables, because which one holds that last state depends on what
#: last touched the part, and they do not overlap: the refix run's parts had
#: no earlier attempt and no measurement under `occt` at all, only a render,
#: and reading two tables called every one of them never seen before.
#:
#: A render is dated by its own `made_at`, never by the run that filed it:
#: 112,688 of the 117,351 render rows carry NO run_id -- `index-slot-renders`
#: and the rebuild both record a drawing without one -- so joining runs to
#: order them dropped 96% of the evidence and answered "never seen before"
#: for parts drawn weeks ago.
_PRIOR = """(
  SELECT was FROM (
    SELECT COALESCE(p.error, p.state) AS was, pr.started AS at, p.run_id AS rid
      FROM attempts p JOIN runs pr ON pr.id = p.run_id
     WHERE p.part_id = {t}.part_id AND p.source IS {t}.source
       AND pr.started < r.started
    UNION ALL
    SELECT COALESCE(p.error, 'drawn'), pr.started, p.run_id
      FROM measurements p JOIN runs pr ON pr.id = p.run_id
     WHERE p.part_id = {t}.part_id AND p.source IS {t}.source
       AND pr.started < r.started
    UNION ALL
    SELECT 'drawn', p.made_at, COALESCE(p.run_id, 0)
      FROM renders p
     WHERE p.part_id = {t}.part_id AND p.source IS {t}.source
       AND p.made_at < r.started)
  ORDER BY at DESC, rid DESC LIMIT 1)"""


def attempts(conn: sqlite3.Connection, run_id: int, *,
             failed_only: bool = False, limit: int = ROW_CAP) -> dict:
    """One run's rows: the errors rolled up, and a capped sample of parts.

    `total` counts what the sample was drawn from, so a page never implies
    the run was as small as the list it is showing.

    A run writes `attempts` or it writes `measurements` -- a store run the
    first, a census or a watcher the second -- so the rows come from whichever
    it filled. `kind` says which, because the columns differ: an attempt has a
    state, a measurement has seconds and a score.

    Every row carries `prior`, what that part was in the slot before this run,
    or null for a part this run met first.
    """
    started = conn.execute("SELECT started FROM runs WHERE id = ?",
                           (run_id,)).fetchone()
    if started is None:
        return {"rows": [], "errors": [], "total": 0, "kind": "attempts"}
    n_attempts = conn.execute(
        "SELECT count(*) FROM attempts WHERE run_id = ?", (run_id,)).fetchone()[0]
    if n_attempts == 0 and conn.execute(
            "SELECT count(*) FROM measurements WHERE run_id = ?",
            (run_id,)).fetchone()[0] > 0:
        return _measured(conn, run_id, failed_only, limit)

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
        f"SELECT a.part_id, a.source, a.state, a.secs, a.error, a.detail, "
        f"       {_PRIOR.format(t='a')} AS prior "
        f"FROM attempts a JOIN runs r ON r.id = a.run_id "
        f"WHERE a.{where} ORDER BY a.part_id LIMIT ?", [*params, limit])]
    return {"rows": rows, "errors": errors, "total": total,
            "kind": "attempts"}


def _measured(conn: sqlite3.Connection, run_id: int, failed_only: bool,
              limit: int) -> dict:
    """The same shape for a run that scored parts instead of storing them.

    `state` is filled with `drawn` so one table renders both kinds: what the
    reader wants of either column is where the part ended up.
    """
    where = "run_id = ?"
    params: list = [run_id]
    if failed_only:
        where += " AND error IS NOT NULL"
    total = conn.execute(
        f"SELECT count(*) FROM measurements WHERE {where}", params).fetchone()[0]
    errors = [{"error": error, "n": n} for error, n in conn.execute(
        "SELECT error, count(*) AS n FROM measurements "
        "WHERE run_id = ? AND error IS NOT NULL "
        "GROUP BY error ORDER BY n DESC, error", (run_id,))]
    rows = [dict(r) for r in conn.execute(
        f"SELECT m.part_id, m.source, "
        f"       CASE WHEN m.error IS NULL THEN 'drawn' END AS state, "
        f"       m.secs, m.error, m.detail, {_PRIOR.format(t='m')} AS prior "
        f"FROM measurements m JOIN runs r ON r.id = m.run_id "
        f"WHERE m.{where} ORDER BY m.part_id LIMIT ?", [*params, limit])]
    return {"rows": rows, "errors": errors, "total": total,
            "kind": "measurements"}
