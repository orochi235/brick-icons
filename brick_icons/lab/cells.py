"""The corpus wall's cells: one per part, in the order the sheets are baked in.

A cell's index is its position in part-id order over every part. The sprite
sheet is baked in that same order, so index is the only thing that has to agree
between this and `brick_icons.thumbs` -- and both take it from `ORDER BY id`.
"""
from __future__ import annotations

import json
import sqlite3

from brick_icons import tags as part_tags
from brick_icons.db import OUT_OF_SCOPE_CATEGORIES

_LATEST_MEASURE = """
SELECT m.part_id, m.extra_d99, m.secs, m.error FROM measurements m
JOIN (SELECT part_id, MAX(run_id) AS run_id FROM measurements
      WHERE engine = ? GROUP BY part_id) latest
  ON m.part_id = latest.part_id AND m.run_id = latest.run_id
WHERE m.engine = ?
"""

# Newest run per (part, engine) among engines other than this one -- never the
# newest run overall, or a part whose other engine has since gone clean would
# still read as erroring elsewhere.
_LATEST_OTHER_ERRORS = """
SELECT m.part_id FROM measurements m
JOIN (SELECT part_id, engine, MAX(run_id) AS run_id FROM measurements
      WHERE engine != ? GROUP BY part_id, engine) latest
  ON m.part_id = latest.part_id AND m.engine = latest.engine
 AND m.run_id = latest.run_id
WHERE m.engine != ? AND m.error IS NOT NULL
"""


def _open_defects(conn: sqlite3.Connection, ids: list[str],
                   engine: str) -> dict[str, dict[str, int]]:
    """Open-defect counts for a page of parts, split here vs. elsewhere.

    One query for the page, following `findings._attach_defects`.
    """
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    out: dict[str, dict[str, int]] = {}
    for d in conn.execute(
            f"SELECT part_id, engines FROM defects WHERE part_id IN ({marks}) "
            f"AND status NOT IN ('fixed', 'notabug')", ids):
        bucket = out.setdefault(d["part_id"], {"here": 0, "elsewhere": 0})
        if engine in json.loads(d["engines"]):
            bucket["here"] += 1
        else:
            bucket["elsewhere"] += 1
    return out


def engine_for(source: str) -> str:
    """The engine a slot's measurements are filed under.

    `renders.source` names a slot and `measurements.engine` names an engine, so
    the census slots have to drop their prefix or every metric joins to nothing
    and the wall sorts an unsorted column without erroring.
    """
    return source[len("census-"):] if source.startswith("census-") else source


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
    engine = engine_for(source)
    measures = {r["part_id"]: r for r in conn.execute(
        _LATEST_MEASURE, (engine, engine))}
    error_elsewhere = {r["part_id"] for r in conn.execute(
        _LATEST_OTHER_ERRORS, (engine, engine))}

    version = max((r["made_at"] for r in renders.values()), default="")
    wanted = order
    if since is not None:
        wanted = sorted(pid for pid, r in renders.items()
                        if r["made_at"] > since)

    defects = _open_defects(conn, wanted, engine)
    years = {r["part_id"]: r for r in conn.execute(
        "SELECT part_id, year_from, year_to, sets FROM part_years")}

    rows = []
    marks = ",".join("?" * len(wanted)) if wanted else "NULL"
    scope_marks = ",".join("?" * len(OUT_OF_SCOPE_CATEGORIES))
    for part in conn.execute(
            f"SELECT id, title, category, printed, obsolete, status, "
            f"(printed = 0 AND obsolete = 0 AND id NOT LIKE '%c__' "
            f"AND id NOT LIKE '%d__' AND id NOT LIKE 'u9%') AS base, "
            f"(category IN ({scope_marks})) AS out_of_scope, "
            f"(title LIKE '~Moved to%') AS moved "
            f"FROM parts WHERE id IN ({marks}) ORDER BY id",
            (*OUT_OF_SCOPE_CATEGORIES, *wanted)):
        pid = part["id"]
        render = renders.get(pid)
        measure = measures.get(pid)
        bucket = defects.get(pid, {"here": 0, "elsewhere": 0})
        year = years.get(pid)
        rows.append({
            "id": pid,
            "index": index[pid],
            "title": part["title"],
            "category": part["category"],
            "printed": bool(part["printed"]),
            "obsolete": bool(part["obsolete"]),
            "base": bool(part["base"]),
            "out_of_scope": bool(part["out_of_scope"]),
            # A redirect to the part that replaced it, not a part -- LDraw
            # keeps the file so old models still load.
            "moved": bool(part["moved"]),
            "year_from": year["year_from"] if year else None,
            "year_to": year["year_to"] if year else None,
            "sets": year["sets"] if year else None,
            "tags": part_tags.tags_for(
                part["category"], bool(part["printed"]), bool(part["obsolete"]),
                year["year_to"] if year else None,
                year["sets"] if year else None),
            "status": part["status"],
            "sha": render["sha256"] if render else None,
            "made_at": render["made_at"] if render else None,
            "extra_d99": measure["extra_d99"] if measure else None,
            "secs": measure["secs"] if measure else None,
            "error": measure["error"] if measure else None,
            "open_defects": bucket["here"],
            "open_defects_elsewhere": bucket["elsewhere"],
            "error_elsewhere": pid in error_elsewhere,
        })
    return {"cells": rows, "count": len(order), "version": version,
            "source": source}
