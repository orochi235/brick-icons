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

# Matched on source, not engine. Two facets of one engine are both "naive", so
# the newest run per engine is whichever facet was indexed last -- which handed
# the oracle slots the white facet's figures, both valid rows, no error. A slot
# with no measurements of its own shows none: these numbers are not comparable
# across facets, so a borrowed one is worse than a blank.
_LATEST_MEASURE = """
SELECT m.part_id, m.extra_d99, m.secs, m.error FROM measurements m
JOIN (SELECT part_id, MAX(run_id) AS run_id FROM measurements
      WHERE source = ? GROUP BY part_id) latest
  ON m.part_id = latest.part_id AND m.run_id = latest.run_id
WHERE m.source = ?
"""

# Newest run per other source -- never the newest run overall, or a part whose
# other slot has since gone clean would still read as erroring elsewhere.
_LATEST_OTHER_ERRORS = """
SELECT m.part_id FROM measurements m
JOIN (SELECT part_id, source, MAX(run_id) AS run_id FROM measurements
      WHERE source != ? GROUP BY part_id, source) latest
  ON m.part_id = latest.part_id AND m.source = latest.source
 AND m.run_id = latest.run_id
WHERE m.source != ? AND m.error IS NOT NULL
"""


_NO_DEFECTS = {"here": 0, "elsewhere": 0, "accepted": 0}


def _open_defects(conn: sqlite3.Connection, ids: list[str],
                   engine: str) -> dict[str, dict[str, int]]:
    """Defect counts for a page of parts: open here, open elsewhere, and the
    ones filed against this engine that were accepted rather than fixed.

    One query for the page, following `findings._attach_defects`. A `wontfix`
    defect used to count as open, so a decision to live with something painted
    the same as a live fault for as long as the record stood.
    """
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    out: dict[str, dict[str, int]] = {}
    for d in conn.execute(
            f"SELECT part_id, engines, status FROM defects WHERE part_id IN ({marks}) "
            f"AND status NOT IN ('fixed', 'notabug')", ids):
        bucket = out.setdefault(d["part_id"], dict(_NO_DEFECTS))
        here = engine in json.loads(d["engines"])
        if d["status"] == "wontfix":
            # Only here: a fault someone accepted in another slot says nothing
            # about this one.
            bucket["accepted"] += int(here)
        elif here:
            bucket["here"] += 1
        else:
            bucket["elsewhere"] += 1
    return out


def engine_for(source: str) -> str:
    """The engine a slot's measurements are filed under.

    `renders.source` names a slot and `measurements.engine` names an engine, so
    a qualified slot has to drop its qualifier or every metric joins to nothing
    and the wall sorts an unsorted column without erroring. The qualifier goes
    in front and can be more than one word -- `white-naive` is the naive
    engine drawing the white facet -- so it is the LAST segment that names the
    engine. A bare slot name carries no hyphen and is returned as it stands.
    """
    return source.rsplit("-", 1)[-1] if "-" in source else source


COVERAGE_ORDER = ("defect", "failed", "timeout", "drawn", "untried")


#: Routes in `part_years.matched` whose `sets` and `colors` describe some
#: OTHER part -- the base mould a print was struck from, or the moulds a design
#: id names -- or no part at all. Only `exact` counts the part itself, and
#: `sheet` counts the sticker sheet the part is one of, which ships with it.
#:
#: Reporting an inherited count is not a rounding error, it is a different
#: claim: `3069bp1f` is one silver-arched-window print, and it read as 5,766
#: sets and `popular` because the plain 1 x 2 tile it is printed on is.
BORROWED_COUNT_ROUTES = frozenset({"base", "design", "design-id-base",
                                   "keywords"})


def sets_for(year: sqlite3.Row | None) -> int | None:
    """How many sets this part is in, or None where the number is not its own."""
    if year is None or year["matched"] in BORROWED_COUNT_ROUTES:
        return None
    return year["sets"]


def colors_for(year: sqlite3.Row | None) -> int | None:
    """How many colors this part was made in, on the same rule as `sets_for`."""
    if year is None or year["matched"] in BORROWED_COUNT_ROUTES:
        return None
    return year["colors"]


def coverage_of(*, sha: str | None, error: str | None, open_defects: int) -> str:
    """How far this slot got with a part, worst news first. Mirrored by
    `Coverage` in the wall's `facts.ts`, which reads this rather than deriving
    it a second time."""
    if open_defects > 0:
        return "defect"
    if error and error != "TimeoutError":
        return "failed"
    if error:
        return "timeout"
    return "drawn" if sha else "untried"


def cells(conn: sqlite3.Connection, source: str = "silhouette-naive",
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
        _LATEST_MEASURE, (source, source))}
    error_elsewhere = {r["part_id"] for r in conn.execute(
        _LATEST_OTHER_ERRORS, (source, source))}

    version = max((r["made_at"] for r in renders.values()), default="")
    wanted = order
    if since is not None:
        wanted = sorted(pid for pid, r in renders.items()
                        if r["made_at"] > since)

    defects = _open_defects(conn, wanted, engine)
    years = {r["part_id"]: r for r in conn.execute(
        "SELECT part_id, year_from, year_to, sets, colors, matched "
        "FROM part_years")}
    successors = {r["part_id"]: r["successor"] for r in conn.execute(
        "SELECT part_id, successor FROM part_successors")}

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
        bucket = defects.get(pid, _NO_DEFECTS)
        year = years.get(pid)
        successor = successors.get(pid)
        rows.append({
            "id": pid,
            "index": index[pid],
            "title": part["title"],
            "category": part["category"],
            # Which sideline theme, not just that there is one -- the wall
            # captions it, and "weird" alone does not say Fabuland or Znap.
            "family": part_tags.weird_theme(part["title"]),
            "printed": bool(part["printed"]),
            "obsolete": bool(part["obsolete"]),
            "base": bool(part["base"]),
            "out_of_scope": bool(part["out_of_scope"]),
            # A redirect to the part that replaced it, not a part -- LDraw
            # keeps the file so old models still load.
            "moved": bool(part["moved"]),
            "year_from": year["year_from"] if year else None,
            "year_to": year["year_to"] if year else None,
            "sets": sets_for(year),
            "colors": colors_for(year),
            # The part that replaced this one, where one is known: the wall's
            # updated badge links to it.
            "successor": successor,
            "tags": part_tags.tags_for(
                part["category"], bool(part["printed"]), bool(part["obsolete"]),
                year["year_to"] if year else None,
                sets_for(year),
                title=part["title"], part_id=pid, successor=successor),
            "status": part["status"],
            "sha": render["sha256"] if render else None,
            "made_at": render["made_at"] if render else None,
            "extra_d99": measure["extra_d99"] if measure else None,
            "secs": measure["secs"] if measure else None,
            "error": measure["error"] if measure else None,
            "coverage": coverage_of(
                sha=render["sha256"] if render else None,
                error=measure["error"] if measure else None,
                open_defects=bucket["here"]),
            "open_defects": bucket["here"],
            "open_defects_elsewhere": bucket["elsewhere"],
            "accepted_defects": bucket["accepted"],
            "error_elsewhere": pid in error_elsewhere,
        })
    return {"cells": rows, "count": len(order), "version": version,
            "source": source}


def slot_states(conn: sqlite3.Connection, part_id: str,
                sources: list[str]) -> dict[str, dict]:
    """What each of a part's slots would color its cell, keyed by source.

    The same four reads `cells` makes, narrowed to one part, so the detail
    view cannot drift from the wall it was opened from. `out_of_scope` is the
    part's and belongs to the caller that already has the row.
    """
    out: dict[str, dict] = {}
    for source in sources:
        engine = engine_for(source)
        measure = conn.execute(
            _LATEST_MEASURE + " AND m.part_id = ?",
            (source, source, part_id)).fetchone()
        elsewhere = conn.execute(
            _LATEST_OTHER_ERRORS + " AND m.part_id = ?",
            (source, source, part_id)).fetchone()
        bucket = _open_defects(conn, [part_id], engine).get(part_id, _NO_DEFECTS)
        out[source] = {
            "error": measure["error"] if measure else None,
            "open_defects": bucket["here"],
            "open_defects_elsewhere": bucket["elsewhere"],
            "accepted_defects": bucket["accepted"],
            "error_elsewhere": elsewhere is not None,
        }
    return out
