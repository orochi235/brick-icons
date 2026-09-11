"""How many parts each slot fails on, counted over the whole corpus and kept.

Two series, because neither alone answers "is this getting better".

`take` writes a row per slot whenever a count moves, which is the only clock
the database has: `rebuild` drops the file and re-stamps every `runs.started`
and `renders.made_at` with the ingest time, so nothing else in here says when
a part failed.

`by_build` reads the other way, off `measurements.build` -- the engine
revision the rendering machine stamped, which survives a rebuild because it
travels in the row. It reaches back before the first tally and ties a step to
the commit that caused it, but only where a row carries a build, and only for
slots that file measurements at all.
"""
from __future__ import annotations

import subprocess
from collections.abc import Sequence

import sqlite3

from brick_icons.db import MOVED_PREFIX, OUT_OF_SCOPE_CATEGORIES, now
from brick_icons.lab.cells import (COVERAGE_ORDER, coverage_of, engine_for,
                                   errors_by_engine, not_applicable)

# The counted columns, in schema order. `not_applicable` is the odd spelling:
# `coverage_of` returns the label in camelCase, the column is snake.
_COLUMNS = ("drawn", "failed", "timeout", "defect", "untried",
            "not_applicable", "slot_failed", "slot_timeout")

#: What "bad" means in a tile: the part did not draw. A `defect` drew
#: something and is wrong about it, which is a different question and has its
#: own page -- folding the two together would report a fixed crash and a newly
#: filed defect as no change at all.
BAD = ("failed", "timeout")


def _column(label: str) -> str:
    return "not_applicable" if label == "notApplicable" else label


def in_scope(conn: sqlite3.Connection) -> set[str]:
    """Every part a slot is expected to draw -- the dashboard's own default
    working set, with no filter applied."""
    marks = ",".join("?" * len(OUT_OF_SCOPE_CATEGORIES))
    return {r["id"] for r in conn.execute(
        f"SELECT id FROM parts WHERE category NOT IN ({marks}) "
        f"AND title NOT LIKE '{MOVED_PREFIX}%'", OUT_OF_SCOPE_CATEGORIES)}


def count(conn: sqlite3.Connection) -> list[dict]:
    """Each slot's coverage over the whole corpus, right now.

    The same `coverage_of` the wall reads, given the same facts -- including
    `drew_nothing`, which the dashboard's own coverage omits and which is
    almost all of what the decal slot gets wrong.
    """
    ids = in_scope(conn)
    marks = ",".join("?" * len(OUT_OF_SCOPE_CATEGORIES))
    printed = {r["id"] for r in conn.execute(
        "SELECT id FROM parts WHERE printed = 1")}
    flagged_by_engine: dict[str, set[str]] = {}
    for row in conn.execute(
            "SELECT part_id, engines FROM defects WHERE status = 'open'"):
        for engine in ("naive", "occt"):
            if engine in row["engines"]:
                flagged_by_engine.setdefault(engine, set()).add(row["part_id"])
    errors = errors_by_engine(conn)

    out = []
    for row in conn.execute(
            "SELECT source, count(*) AS n FROM renders GROUP BY source "
            "ORDER BY source"):
        source = row["source"]
        engine = engine_for(source)
        drawn = {r["part_id"] for r in conn.execute(
            "SELECT part_id FROM renders WHERE source = ?", (source,))}
        drew_nothing = {r["part_id"] for r in conn.execute(
            "SELECT DISTINCT part_id FROM attempts WHERE source = ? "
            "AND state = 'none'", (source,))}
        slot_errors = errors.get(engine, {})
        flagged = flagged_by_engine.get(engine, set())
        build = conn.execute(
            "SELECT build FROM measurements WHERE source = ? AND build IS NOT "
            "NULL ORDER BY run_id DESC LIMIT 1", (source,)).fetchone()
        # This slot's OWN latest error, from its own measurements and its own
        # attempts. decal files no measurements at all -- its whole record is
        # `attempts` -- so a measurements-only reading reports the slot with
        # the most failures in the corpus as having none.
        own_errors = {r["part_id"]: r["error"] for r in conn.execute(
            "SELECT m.part_id, m.error FROM measurements m JOIN "
            "(SELECT part_id, MAX(run_id) AS run_id FROM measurements "
            " WHERE source = ? GROUP BY part_id) latest "
            "ON m.part_id = latest.part_id AND m.run_id = latest.run_id "
            "WHERE m.source = ? AND m.error IS NOT NULL", (source, source))}
        own_errors.update({r["part_id"]: r["error"] for r in conn.execute(
            "SELECT part_id, error FROM attempts WHERE source = ? "
            "AND error IS NOT NULL", (source,))})

        counts = dict.fromkeys((_column(c) for c in COVERAGE_ORDER), 0)
        own = {"failed": 0, "timeout": 0}
        for pid in ids:
            shared = dict(
                sha="x" if pid in drawn else None,
                open_defects=1 if pid in flagged else 0,
                inapplicable=not_applicable(source, pid in printed,
                                            pid in drawn),
                drew_nothing=pid in drew_nothing)
            counts[_column(coverage_of(error=slot_errors.get(pid),
                                       **shared))] += 1
            mine = coverage_of(error=own_errors.get(pid), **shared)
            if mine in own:
                own[mine] += 1
        out.append({"source": source, "build": build["build"] if build else None,
                    "size": len(ids), "slot_failed": own["failed"],
                    "slot_timeout": own["timeout"], **counts})
    return out


def tracked_sources(conn: sqlite3.Connection) -> list[str]:
    """The slots the failure chart follows: every occt facet, and decal.

    naive's facets are left out for the same reason the timing sections drop
    them -- it is the reference, so its failures measure the oracle, not the
    engine being worked on.
    """
    have = [r["source"] for r in conn.execute(
        "SELECT DISTINCT source FROM renders ORDER BY source")]
    return [s for s in have if engine_for(s) == "occt" or s == "decal"]


def take(conn: sqlite3.Connection, at: str | None = None) -> int:
    """Record how the corpus stands, skipping any slot that has not moved.

    Written on every ingest, and a watch ingests every half hour -- so a slot
    whose counts are unchanged writes nothing and the series stays a step
    function rather than a flat line sampled 48 times a day.
    """
    at = at or now()
    latest = {}
    for row in conn.execute(
            "SELECT t.* FROM tallies t JOIN (SELECT source, MAX(taken) AS taken "
            "FROM tallies GROUP BY source) last ON t.source = last.source "
            "AND t.taken = last.taken"):
        latest[row["source"]] = row

    written = 0
    for row in count(conn):
        was = latest.get(row["source"])
        if was is not None and all(
                was[c] == row[c] for c in (*_COLUMNS, "size")):
            continue
        conn.execute(
            "INSERT OR REPLACE INTO tallies (taken, source, build, size, "
            "drawn, failed, timeout, defect, untried, not_applicable, "
            "slot_failed, slot_timeout) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (at, row["source"], row["build"], row["size"],
             *(row[c] for c in _COLUMNS)))
        written += 1
    conn.commit()
    return written


def series(conn: sqlite3.Connection,
           sources: Sequence[str] | None = None) -> list[dict]:
    """Every tally, oldest first, one entry per slot per step.

    Each slot's OWN failures, not its engine's: four facets sharing one
    pooled number draw as one line four times over, and the point of a line
    per facet is to see them diverge."""
    rows = conn.execute(
        "SELECT taken, source, build, size, slot_failed, slot_timeout "
        "FROM tallies ORDER BY taken, source")
    want = set(sources) if sources else None
    return [{"at": r["taken"], "source": r["source"], "build": r["build"],
             "size": r["size"], "failed": r["slot_failed"],
             "timeout": r["slot_timeout"],
             "bad": r["slot_failed"] + r["slot_timeout"]}
            for r in rows if want is None or r["source"] in want]


_DATES: dict[str, str | None] = {}


def _commit_dates(shas: Sequence[str]) -> dict[str, str]:
    """When each commit landed. A sha the checkout has never heard of is
    dropped rather than guessed at -- a build drawn on a branch that was never
    merged has no place on a time axis."""
    out = {}
    for sha in shas:
        if sha in _DATES:
            if _DATES[sha]:
                out[sha] = _DATES[sha]
            continue
        try:
            done = subprocess.run(
                ["git", "log", "-1", "--format=%cI", sha],
                capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            continue
        _DATES[sha] = (done.stdout.strip()
                       if done.returncode == 0 and done.stdout.strip() else None)
        if _DATES[sha]:
            out[sha] = _DATES[sha]
    return out


#: The least of a slot's widest run a revision has to cover before its failure
#: rate means anything. white-occt's first revision drew 277 parts of the
#: 20,213 it draws now and 58% of them failed, which took the chart's axis to
#: 60% and flattened every real line into the bottom tenth of it.
MEANINGFUL_SHARE = 0.10


def by_build(conn: sqlite3.Connection,
             sources: Sequence[str] | None = None) -> list[dict]:
    """Failures per slot per engine revision, dated from git.

    The sparse prefix the tallies cannot reach. A build reads `1214.069c08b`
    -- a revision count, then the sha -- with a trailing `+` where the tree
    was dirty; the sha is what git can date, and a dirty tree is still that
    commit's code plus something uncommitted.

    A revision that covered a sliver of what its slot has drawn is left out:
    a bring-up run and a spot check are not rates, and they are the points
    that set the axis -- see `MEANINGFUL_SHARE`.
    """
    want = set(sources) if sources else None
    rows = [r for r in conn.execute(
        "SELECT source, build, "
        "sum(error IS NOT NULL AND error != 'TimeoutError') AS failed, "
        "sum(error = 'TimeoutError') AS timeout, count(*) AS n "
        "FROM measurements WHERE build IS NOT NULL AND source IS NOT NULL "
        "GROUP BY source, build")
        if want is None or r["source"] in want]

    shas = {r["build"].split(".")[-1].rstrip("+") for r in rows}
    dates = _commit_dates(sorted(shas))

    widest: dict[str, int] = {}
    for r in rows:
        widest[r["source"]] = max(widest.get(r["source"], 0), r["n"])

    out = []
    for r in rows:
        sha = r["build"].split(".")[-1].rstrip("+")
        if sha not in dates:
            continue
        if r["n"] < widest[r["source"]] * MEANINGFUL_SHARE:
            continue
        out.append({"at": dates[sha], "source": r["source"], "build": r["build"],
                    "size": r["n"], "failed": r["failed"] or 0,
                    "timeout": r["timeout"] or 0,
                    "bad": (r["failed"] or 0) + (r["timeout"] or 0)})
    return sorted(out, key=lambda r: (r["at"], r["source"]))


def latest(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    """The most recent tally per slot."""
    return {r["source"]: r for r in conn.execute(
        "SELECT t.* FROM tallies t JOIN (SELECT source, MAX(taken) AS taken "
        "FROM tallies GROUP BY source) last ON t.source = last.source "
        "AND t.taken = last.taken")}


def totals(conn: sqlite3.Connection) -> dict:
    """The corpus-wide bad count behind each tile.

    Read off the last tally rather than recounted: counting is a pass over
    every part in every slot, and doing it per page load put ten seconds on
    the dashboard. It also keeps the tile and the chart's last point saying
    the same number, which recounting between them did not guarantee.

    occt is the family as one number: a part is counted once however many
    facets it fails in, because the tile answers "how many pieces are bad",
    not "how many slot-part pairs are". That is why it reads the error per
    ENGINE -- `occt` files no measurements of its own, and every occt failure
    is written under whichever facet was running.

    decal fails differently and the two do not sum. Almost none of its bad
    parts crashed: they ran clean and drew nothing.
    """
    rows = latest(conn)
    if not rows:
        return {"size": len(in_scope(conn)), "taken": None,
                "occt": {"bad": 0, "failed": 0, "timeout": 0, "facets": []},
                "decal": {"bad": 0, "failed": 0, "timeout": 0}}

    facets = sorted(s for s in rows if engine_for(s) == "occt")
    # Any occt facet carries the engine-pooled count, which is the same in all
    # of them by construction -- that is what `errors_by_engine` pools.
    occt = rows[facets[0]] if facets else None
    decal = rows.get("decal")
    size = max(r["size"] for r in rows.values())
    return {
        "size": size,
        "taken": max(r["taken"] for r in rows.values()),
        "occt": {"bad": (occt["failed"] + occt["timeout"]) if occt else 0,
                 "failed": occt["failed"] if occt else 0,
                 "timeout": occt["timeout"] if occt else 0,
                 "facets": facets},
        "decal": {"bad": (decal["failed"] + decal["timeout"]) if decal else 0,
                  "failed": decal["failed"] if decal else 0,
                  "timeout": decal["timeout"] if decal else 0},
    }
