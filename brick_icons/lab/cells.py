"""The corpus wall's cells: one per part, in the order the sheets are baked in.

A cell's index is its position in part-id order over every part. The sprite
sheet is baked in that same order, so index is the only thing that has to agree
between this and `brick_icons.thumbs` -- and both take it from `ORDER BY id`.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tomllib
from pathlib import Path

from brick_icons import tags as part_tags
from brick_icons.lab import defects as defects_toml
from brick_icons.db import MOVED_PREFIX, OUT_OF_SCOPE_CATEGORIES, SOURCES

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

# Every slot's latest error, gathered per ENGINE below. One query for the whole
# wall: the alternative is a query per slot per part, and the wall asks for all
# 24,591.
_LATEST_ERRORS = """
SELECT m.part_id, m.source, m.error, r.finished FROM measurements m
JOIN (SELECT part_id, source, MAX(run_id) AS run_id FROM measurements
      GROUP BY part_id, source) latest
  ON m.part_id = latest.part_id AND m.source = latest.source
 AND m.run_id = latest.run_id
JOIN runs r ON r.id = m.run_id
WHERE m.error IS NOT NULL
"""


#: What an engine can be saying about a part, matching the conditions
#: `states.ts` colors. The wall draws one slot and reports every OTHER engine
#: as `elsewhere`, so this list is the vocabulary both ends share: add one here
#: and in the conditions table there, and its `<key>Elsewhere` sibling is
#: derived at both ends.
CONDITIONS = ("review", "defect", "timeout", "failed", "accepted")


#: The slots that draw only some of the library, and what makes a part one
#: they have something to draw. Everything not named here applies to every
#: part, so nothing in it is ever `not_applicable`. `decal` draws a part's
#: decoration: a plain brick has none, which is a different thing from a
#: decorated part whose decal the finder missed -- that one is still owed and
#: stays `unknown`.
SLOT_DRAWS = {"decal": lambda printed: printed}


#: Parts that take a machine down rather than failing. Every generated batch
#: drops them, so they are the same practical class as an out-of-scope
#: category: something nothing will ever queue. Read from the file
#: `slot-coverage.py` reads, so the two cannot come to disagree about it.
DEGENERATE_PATH = Path("tests/goldens/degenerate-parts.toml")


def degenerate(path: Path | str = DEGENERATE_PATH) -> frozenset[str]:
    """The ids on that list, or nothing where the file is not there."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return frozenset()
    return frozenset(e["id"] for e in tomllib.loads(raw.decode()).get("part", ()))


def not_applicable(source: str, printed: bool, drawn: bool,
                   obsolete: bool = False, out_of_scope: bool = False) -> bool:
    """Whether this slot has nothing to draw for this part.

    Two signals have to agree: the part is one no batch will ask this slot
    for, and nothing was drawn for it. Where they ever disagree -- a plain
    part with a decal against its name, an obsolete mould `reference` drew
    anyway -- the cell keeps whatever state its render gives it, so a
    contradiction shows rather than being colored over.

    Neither obsolete nor out of scope is a property of the slot: both are
    parts `census-scope.py` and `slot-coverage.py` drop before a batch is
    picked, so nothing will ever queue them. Reading an obsolete mould as
    untried put 2,733 parts into every occt slot's backlog; the `|` categories
    -- LDraw's mark for parts nobody at LEGO made -- were occt's ENTIRE
    22-part untried count, a dark tip on the bar that no job could clear.
    """
    draws = SLOT_DRAWS.get(source)
    covered = (not obsolete and not out_of_scope
               and (draws is None or draws(printed)))
    return not covered and not drawn


def errors_by_engine(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """Each engine's latest error per part.

    An error belongs to an ENGINE, not to the slot that happened to record it.
    `occt` files no measurements of its own and every failure of the occt
    engine is written under `silhouette-occt`, so a slot that asked only about
    itself painted a clean wall over 2,432 parts that do not draw at all.

    Worst news first where an engine's facets disagree: a real error outranks a
    timeout, so one facet giving up on the clock cannot mask another failing
    outright.
    """
    return _latest_errors(conn)[0]


def _latest_errors(
        conn: sqlite3.Connection) -> tuple[dict[str, dict[str, str]],
                                           dict[str, dict[str, str]]]:
    """Each engine's latest error per part, and when the run recording it
    finished. One query, because the wall wants both and this one is a
    group-by over the whole measurements table.

    The two disagree on purpose where an engine's facets do: the text is the
    worst news, so a timeout cannot mask a failure, while the time is the
    latest of them -- what "this failed most recently" has to mean.
    """
    out: dict[str, dict[str, str]] = {}
    at: dict[str, dict[str, str]] = {}
    for row in conn.execute(_LATEST_ERRORS):
        engine = engine_for(row["source"])
        bucket = out.setdefault(engine, {})
        have = bucket.get(row["part_id"])
        if have is None or (have == "TimeoutError"
                            and row["error"] != "TimeoutError"):
            bucket[row["part_id"]] = row["error"]
        when = at.setdefault(engine, {})
        if row["finished"] and row["finished"] > when.get(row["part_id"], ""):
            when[row["part_id"]] = row["finished"]
    return out, at


_NO_DEFECTS = {"open": 0, "review": 0, "accepted": 0}


def live_defects(conn: sqlite3.Connection) -> list[dict]:
    """Every defect that still says something, in the shape the TOML uses.

    `fixed` and `notabug` are dropped here rather than at each use: they are
    settled, and a settled record that reached a tally once painted a closed
    fault the same as a live one.
    """
    return [{"part": r["part_id"], "engines": json.loads(r["engines"]),
             "status": r["status"],
             "checked": json.loads(r["checked"]) if r["checked"] else {}}
            for r in conn.execute(
                "SELECT part_id, engines, status, checked FROM defects "
                "WHERE status NOT IN ('fixed', 'notabug')")]


def tally_defects(records: list[dict], part_id: str, engine: str,
                  source: str, sha: str | None) -> dict[str, int]:
    """This slot's defects, split three ways.

    Disjoint on purpose: a defect waiting on a fresh render is counted under
    `review` and nowhere else, so the wall can show that something changed
    without a part's other, untouched defects hiding it.
    """
    out = dict(_NO_DEFECTS)
    for record in records:
        if record["part"] != part_id or engine not in record["engines"]:
            continue
        if record["status"] == "wontfix":
            # Only here: a fault someone accepted in another slot says nothing
            # about this one.
            out["accepted"] += 1
        elif defects_toml.wants_review(record, source, sha):
            out["review"] += 1
        else:
            out["open"] += 1
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


COVERAGE_ORDER = ("defect", "failed", "timeout", "drawn", "untried",
                  "notApplicable")


#: Routes in `part_years.matched` whose `sets` and `colors` describe some
#: OTHER part -- the base mould a print was struck from, or the moulds a design
#: id names -- or no part at all. Only `exact` counts the part itself, and
#: `sheet` counts the sticker sheet the part is one of, which ships with it.
#:
#: Reporting an inherited count is not a rounding error, it is a different
#: claim: `3069bp1f` is one silver-arched-window print, and it read as 5,766
#: sets and `popular` because the plain 1 x 2 tile it is printed on is.
#:
#: `prints` and `keywords` store a literal 0, which is the same trap read the
#: other way -- a part in no inventory would report as being in no sets.
BORROWED_COUNT_ROUTES = frozenset({"base", "design", "design-id-base",
                                   "keywords", "prints"})


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


#: Routes whose YEARS describe another part, which is a shorter list than
#: `BORROWED_COUNT_ROUTES`. `keywords` and `prints` carry no set count anyone
#: can use, but the span each reads is this part's own -- the sets LDraw names
#: for it, and the years of the prints cut from the mould. `base` is the span
#: of the one mould the print is struck on, which is a fact about the print.
#:
#: A design id is not: it names every mould cut from that id, and the span is
#: the union across all of them. 699 printed torsos read 1983-2026 that way,
#: and the wall drew every one as still in production since 1983.
BORROWED_YEAR_ROUTES = frozenset({"design", "design-id-base"})


def years_for(year: sqlite3.Row | None) -> tuple[int | None, int | None]:
    """The years this part was made, or a pair of Nones where the span is not
    its own."""
    if year is None or year["matched"] in BORROWED_YEAR_ROUTES:
        return None, None
    return year["year_from"], year["year_to"]


def live_sources(conn: sqlite3.Connection) -> list[str]:
    """The slots this corpus has anything to say about, in `SOURCES` order.

    A slot counts as live once anything has pointed the renderer at it --
    a render, an attempt or a measurement. The detail view lays out one tile
    per live slot, so a slot nobody has ever run stays out of the strip
    instead of standing there empty on all 24,591 parts.
    """
    seen: set[str] = set()
    for table in ("renders", "attempts", "measurements"):
        seen |= {r["source"] for r in
                 conn.execute(f"SELECT DISTINCT source FROM {table}")}
    return [source for source in SOURCES if source in seen]


_LATEST_ATTEMPT = """
SELECT a.source, a.state, a.secs, a.error FROM attempts a
JOIN (SELECT source, MAX(run_id) AS run_id FROM attempts
      WHERE part_id = ? GROUP BY source) latest
  ON a.source = latest.source AND a.run_id = latest.run_id
WHERE a.part_id = ?
"""


def slot_attempts(conn: sqlite3.Connection, part_id: str) -> dict[str, dict]:
    """What each slot's last run of this part did, keyed by source.

    A part that times out leaves no render and no measurement, so this is the
    only record it was tried at all -- and the only place its seconds are.
    """
    return {row["source"]: {"state": row["state"], "secs": row["secs"],
                            "error": row["error"]}
            for row in conn.execute(_LATEST_ATTEMPT, (part_id, part_id))}


def coverage_of(*, sha: str | None, error: str | None, open_defects: int,
                inapplicable: bool = False, drew_nothing: bool = False) -> str:
    """How far this slot got with a part, worst news first. Mirrored by
    `Coverage` in the wall's `facts.ts`, which reads this rather than deriving
    it a second time.

    `inapplicable` only ever displaces `untried`: a slot erroring on a part it
    does not cover is a real event, and burying it under "nothing to draw"
    would hide the contradiction `not_applicable` exists to show.

    `drew_nothing` is an attempt that finished clean and produced no drawing.
    On a part the slot covers that is a failure of the renderer, not work
    still owed -- 2,480 printed parts came back so from the decal finder, and
    reading them as untried asks the fleet for a job that has already run.
    """
    if open_defects > 0:
        return "defect"
    if error and error != "TimeoutError":
        return "failed"
    if error:
        return "timeout"
    if sha:
        return "drawn"
    if inapplicable:
        return "notApplicable"
    return "failed" if drew_nothing else "untried"


def judged(conn: sqlite3.Connection) -> tuple[set[str], str]:
    """The parts somebody has said something about, and a stamp over what was
    said. Small -- defects and reviewed statuses are in the tens against
    twenty thousand parts -- so resending all of them when the stamp moves
    costs nothing, and it is the only way to catch a change no row dates."""
    rows = list(conn.execute(
        "SELECT part_id AS id, status, COALESCE(checked, '') AS extra "
        "FROM defects "
        "UNION ALL "
        "SELECT id, status, COALESCE(status_at, '') FROM parts "
        "WHERE status <> 'unreviewed' ORDER BY id, status"))
    digest = hashlib.sha256(
        "".join(f"{r['id']}\x1f{r['status']}\x1f{r['extra']}\x1e"
                for r in rows).encode()).hexdigest()[:16]
    return {r["id"] for r in rows}, digest


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
    errors_text, errors_at = _latest_errors(conn)
    errors = errors_text.get(engine, {})
    errored_at = errors_at.get(engine, {})
    # By SOURCE, unlike `errors`: drawing nothing is this slot's own outcome,
    # not the engine's. A stale one cannot mislead -- a later render gives the
    # cell a sha, and `coverage_of` answers "drawn" before it looks here.
    never_queued = degenerate()
    drew_nothing = {r["part_id"] for r in conn.execute(
        "SELECT DISTINCT part_id FROM attempts WHERE source = ? "
        "AND state = 'none'", (source,))}
    others = other_conditions(conn, source)

    # Two halves, because two unrelated things change a cell and only one of
    # them has a timestamp. A render dates itself; a defect and a part's
    # status do not, so they are fingerprinted and the whole judged set is
    # resent whenever that fingerprint moves. Without the second half, filing
    # a defect updated the lightbox and left the cell behind it stale until a
    # reload -- the delta is built from renders, and no render had happened.
    drawn = max((r["made_at"] for r in renders.values()), default="")
    said_about, stamp = judged(conn)
    version = f"{drawn}|{stamp}"
    wanted = order
    if since is not None:
        was_drawn, _, was_stamp = since.partition("|")
        wanted = {pid for pid, r in renders.items()
                  if r["made_at"] > was_drawn}
        if was_stamp != stamp:
            wanted |= said_about
        wanted = sorted(wanted)

    records = live_defects(conn)
    years = {r["part_id"]: r for r in conn.execute(
        "SELECT part_id, year_from, year_to, sets, colors, matched "
        "FROM part_years")}
    successors = {r["part_id"]: r["successor"] for r in conn.execute(
        "SELECT part_id, successor FROM part_successors")}

    rows = []
    marks = ",".join("?" * len(wanted)) if wanted else "NULL"
    scope_marks = ",".join("?" * len(OUT_OF_SCOPE_CATEGORIES))
    for part in conn.execute(
            f"SELECT id, title, category, printed, obsolete, preview, status, "
            f"(printed = 0 AND obsolete = 0 AND id NOT LIKE '%c__' "
            f"AND id NOT LIKE '%d__' AND id NOT LIKE 'u9%') AS base, "
            f"(category IN ({scope_marks})) AS out_of_scope, "
            f"(title LIKE '{MOVED_PREFIX}%') AS moved "
            f"FROM parts WHERE id IN ({marks}) ORDER BY id",
            (*OUT_OF_SCOPE_CATEGORIES, *wanted)):
        pid = part["id"]
        render = renders.get(pid)
        measure = measures.get(pid)
        bucket = tally_defects(records, pid, engine, source,
                               render["sha256"] if render else None)
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
            # LDraw declaring a `!PREVIEW` turn is the library saying the
            # default view shows the wrong side of this part -- a prediction
            # about the render, not a fact about the moulding.
            "posed": bool(part["preview"]),
            "base": bool(part["base"]),
            "out_of_scope": bool(part["out_of_scope"]),
            # A redirect to the part that replaced it, not a part -- LDraw
            # keeps the file so old models still load.
            "moved": bool(part["moved"]),
            "year_from": years_for(year)[0],
            "year_to": years_for(year)[1],
            "sets": sets_for(year),
            "colors": colors_for(year),
            # The part that replaced this one, where one is known: the wall's
            # updated badge links to it.
            "successor": successor,
            "tags": part_tags.tags_for(
                part["category"], bool(part["printed"]),
                year["year_to"] if year else None,
                sets_for(year),
                title=part["title"], part_id=pid, successor=successor),
            "status": part["status"],
            "sha": render["sha256"] if render else None,
            "made_at": render["made_at"] if render else None,
            # d99 and secs stay this SLOT's -- they are not comparable across
            # facets, so a borrowed figure is worse than a blank. The error is
            # the engine's, because failing to draw is not a property of which
            # facet was asked.
            "extra_d99": measure["extra_d99"] if measure else None,
            "secs": measure["secs"] if measure else None,
            "error": errors.get(pid),
            "error_at": errored_at.get(pid),
            "coverage": coverage_of(
                sha=render["sha256"] if render else None,
                error=errors.get(pid),
                open_defects=bucket["open"] + bucket["review"],
                inapplicable=not_applicable(
                    source, bool(part["printed"]), render is not None,
                    bool(part["obsolete"]),
                    part["category"] in OUT_OF_SCOPE_CATEGORIES
                    or pid in never_queued),
                drew_nothing=pid in drew_nothing),
            "open_defects": bucket["open"],
            "review_defects": bucket["review"],
            "accepted_defects": bucket["accepted"],
            # Which conditions hold in a slot that is not this one. The wall
            # draws each as the condition's own `<key>Elsewhere` sibling, so a
            # condition added here needs no second field of its own.
            "elsewhere": sorted(others.get(pid, ())),
            "not_applicable": not_applicable(
                source, bool(part["printed"]), render is not None,
                bool(part["obsolete"])),
        })
    return {"cells": rows, "count": len(order), "version": version,
            "source": source}


#: The three corpus-wide reads `other_conditions` makes, so a caller asking
#: about several slots at once pays for them once. Every slot sees the same
#: errors, renders and defects; only the engine to exclude changes.
Elsewhere = tuple[dict[str, dict[str, str]], dict[str, dict[str, str]], list[dict]]


def elsewhere_context(conn: sqlite3.Connection) -> Elsewhere:
    shas: dict[str, dict[str, str]] = {}
    for row in conn.execute("SELECT part_id, source, sha256 FROM renders"):
        shas.setdefault(row["source"], {})[row["part_id"]] = row["sha256"]
    return errors_by_engine(conn), shas, live_defects(conn)


def other_conditions(conn: sqlite3.Connection, source: str,
                     context: Elsewhere | None = None) -> dict[str, set[str]]:
    """Per part, the conditions that hold somewhere other than `source`.

    Everything here is keyed by ENGINE, errors as much as defects: a fault is
    a property of what drew the part, not of which facet was asked for. So a
    slot is never `elsewhere` from a sibling that shares its engine -- that
    would draw one fault twice and let the weaker color win nothing but
    confusion -- and a defect counts whether or not the engine it names has
    ever got as far as drawing this part.
    """
    engine = engine_for(source)
    errors, shas, records = context or elsewhere_context(conn)
    out: dict[str, set[str]] = {}

    for other, by_part in errors.items():
        if other == engine:
            continue
        for pid, error in by_part.items():
            out.setdefault(pid, set()).add(
                "timeout" if error == "TimeoutError" else "failed")

    for record in records:
        # `accepted` has no sibling -- a fault someone chose to live with in
        # another slot asks nothing of this one.
        if record["status"] == "wontfix":
            continue
        engines = [e for e in record["engines"] if e != engine]
        if not engines:
            continue
        asks = any(
            defects_toml.wants_review(record, slot,
                                      shas.get(slot, {}).get(record["part"]))
            for slot in shas if engine_for(slot) in engines)
        out.setdefault(record["part"], set()).add("review" if asks else "defect")
    return out


def slot_states(conn: sqlite3.Connection, part_id: str,
                sources: list[str]) -> dict[str, dict]:
    """What each of a part's slots would color its cell, keyed by source.

    The same reads `cells` makes, narrowed to one part, so the detail view
    cannot drift from the wall it was opened from. `out_of_scope` is the
    part's and belongs to the caller that already has the row.
    """
    context = elsewhere_context(conn)
    errors, _, records = context
    # A slot that timed out files no measurement, so its own attempt is the
    # only thing that knows -- and it is what a tile with no render shows.
    tried = slot_attempts(conn, part_id)
    row = conn.execute("SELECT printed, obsolete FROM parts WHERE id = ?",
                       (part_id,)).fetchone()
    printed = bool(row["printed"] if row else 0)
    obsolete = bool(row["obsolete"] if row else 0)
    others = {source: other_conditions(conn, source, context)
              for source in sources}
    out: dict[str, dict] = {}
    for source in sources:
        render = conn.execute(
            "SELECT sha256 FROM renders WHERE source = ? AND part_id = ?",
            (source, part_id)).fetchone()
        bucket = tally_defects(records, part_id, engine_for(source), source,
                               render["sha256"] if render else None)
        out[source] = {
            "error": (errors.get(engine_for(source), {}).get(part_id)
                      or tried.get(source, {}).get("error")),
            "open_defects": bucket["open"],
            "review_defects": bucket["review"],
            "accepted_defects": bucket["accepted"],
            "elsewhere": sorted(others[source].get(part_id, ())),
            "not_applicable": not_applicable(source, printed,
                                             render is not None, obsolete),
        }
    return out
