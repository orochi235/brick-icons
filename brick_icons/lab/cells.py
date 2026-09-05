"""The corpus wall's cells: one per part, in the order the sheets are baked in.

A cell's index is its position in part-id order over every part. The sprite
sheet is baked in that same order, so index is the only thing that has to agree
between this and `brick_icons.thumbs` -- and both take it from `ORDER BY id`.
"""
from __future__ import annotations

import sqlite3

_LATEST_MEASURE = """
SELECT m.part_id, m.extra_d99, m.secs, m.error FROM measurements m
JOIN (SELECT part_id, MAX(run_id) AS run_id FROM measurements
      WHERE engine = ? GROUP BY part_id) latest
  ON m.part_id = latest.part_id AND m.run_id = latest.run_id
WHERE m.engine = ?
"""


def cells(conn: sqlite3.Connection, source: str = "census-naive",
          since: str | None = None) -> dict:
    """Every cell, or only those whose render landed after `since`.

    `count` is always the corpus size: the wall lays out every part whether or
    not this response mentions it, and a delta must not shrink the grid.
    """
    order = [r["id"] for r in conn.execute("SELECT id FROM parts ORDER BY id")]
    index = {pid: i for i, pid in enumerate(order)}

    renders = {r["part_id"]: r for r in conn.execute(
        "SELECT part_id, sha256, made_at FROM renders WHERE source = ?",
        (source,))}
    measures = {r["part_id"]: r for r in conn.execute(
        _LATEST_MEASURE, (source, source))}

    version = max((r["made_at"] for r in renders.values()), default="")
    wanted = order
    if since is not None:
        wanted = sorted(pid for pid, r in renders.items()
                        if r["made_at"] > since)

    rows = []
    marks = ",".join("?" * len(wanted)) if wanted else "NULL"
    for part in conn.execute(
            f"SELECT id, title, category, printed, obsolete, status FROM parts "
            f"WHERE id IN ({marks}) ORDER BY id", wanted):
        pid = part["id"]
        render = renders.get(pid)
        measure = measures.get(pid)
        rows.append({
            "id": pid,
            "index": index[pid],
            "title": part["title"],
            "category": part["category"],
            "printed": bool(part["printed"]),
            "obsolete": bool(part["obsolete"]),
            "status": part["status"],
            "sha": render["sha256"] if render else None,
            "made_at": render["made_at"] if render else None,
            "extra_d99": measure["extra_d99"] if measure else None,
            "secs": measure["secs"] if measure else None,
            "error": measure["error"] if measure else None,
        })
    return {"cells": rows, "count": len(order), "version": version,
            "source": source}
