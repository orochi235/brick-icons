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
    """Every part in scope, with no filter applied. Wider than the
    dashboard's default working set, which leaves obsolete moulds out; here
    they are counted and land in `not_applicable`."""
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
    obsolete = {r["id"] for r in conn.execute(
        "SELECT id FROM parts WHERE obsolete = 1")}
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
                                            pid in drawn, pid in obsolete),
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


def owed(conn: sqlite3.Connection,
         sources: Sequence[str] | None = None) -> dict[str, int]:
    """How many parts each slot was ever going to draw.

    The denominator every share on the coverage chart needs. `size` is the
    whole in-scope corpus, and reading a line off that puts decal -- which
    draws printed parts and nothing else -- at half of what a slot covering
    the library scores for the same work. Obsolete moulds come out for every
    slot on the same grounds: `census-scope.py` takes `obsolete = 0`, so
    nothing ever queues one.

    The slot's own scope only, unlike `_coverage`'s `owed` in `stats.py`,
    which subtracts a count `coverage_of` has already let a render or an
    error displace. The two differ only where a slot errored on a part it
    does not cover, which is the contradiction `not_applicable` exists to
    show and is not something a denominator should move with.
    """
    ids = in_scope(conn)
    printed = {r["id"] for r in conn.execute(
        "SELECT id FROM parts WHERE printed = 1")}
    obsolete = {r["id"] for r in conn.execute(
        "SELECT id FROM parts WHERE obsolete = 1")}
    out = {}
    for source in (sources if sources is not None else tracked_sources(conn)):
        out[source] = sum(
            1 for pid in ids
            if not not_applicable(source, pid in printed, False,
                                  pid in obsolete))
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
        "SELECT taken, source, build, size, drawn, "
        "slot_failed, slot_timeout FROM tallies ORDER BY taken, source").fetchall()
    owed_by = owed(conn, sorted({r["source"] for r in rows}))
    want = set(sources) if sources else None
    # `owed` recomputed here, NOT read off the step's own `not_applicable`.
    # That column is only as good as whichever process wrote the row, and
    # several lab servers share this database: the stale ones predate
    # `obsolete` reaching `not_applicable` and write 0 where current code
    # writes 2,737. Read per step, the coverage line oscillated between 82.8%
    # and 93.5% on alternate tallies -- one writer's answer, then the
    # other's. One denominator for the whole series cannot do that.
    #
    # `clean` is what is on disk, which `history` must not read and this may:
    # the artifact there is that a rebuild re-stamped every `made_at` and a
    # run axis then credits a re-bake with parts it had already drawn. A
    # tally is dated by when it was taken and counts what stood at that
    # moment, and every tally in this corpus was taken after that rebuild.
    return [{"at": r["taken"], "source": r["source"], "build": r["build"],
             "size": r["size"], "owed": owed_by.get(r["source"], r["size"]),
             "clean": r["drawn"],
             "failed": r["slot_failed"], "timeout": r["slot_timeout"],
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


#: How much of a slot's OWED set a revision has to have measured before its
#: failure rate means anything.
#:
#: What disqualifies a revision is not a small sample but a chosen one. A
#: retry queue is aimed at the parts already known to break, so its rate is
#: high however many parts it covers: 1264.9cb8965 measured 1,298 parts of
#: silhouette-occt at 60.9% against the 10,513-part sweep's 1.4%, and one
#: point took the axis to 80% and flattened every real line under it.
#:
#: Against the slot's owed set, not against its widest run, which is what
#: this compared and which a growing retry queue walks straight past -- that
#: 60.9% point crossed a tenth of the widest run while this was being
#: written. Owed is a fixed target, so the bar means the same thing in
#: March as in September: did this revision sweep the slot, or pick at it?
MEANINGFUL_SHARE = 0.10


def by_build(conn: sqlite3.Connection,
             sources: Sequence[str] | None = None) -> list[dict]:
    """Failures per slot per engine revision, dated from git.

    The sparse prefix the tallies cannot reach. A build reads `1214.069c08b`
    -- a revision count, then the sha -- with a trailing `+` where the tree
    was dirty; the sha is what git can date, and a dirty tree is still that
    commit's code plus something uncommitted.

    A revision that picked at its slot rather than sweeping it is left out: a
    retry queue and a spot check are not rates, and they are the points that
    set the axis -- see `MEANINGFUL_SHARE`.

    Parts, not measurement rows. A census that measured a part twice under
    one build counted it twice, which put occt's widest run at 32,312 against
    an owed set of 20,598 -- a share over 100%, and a denominator no rate
    could be read against.
    """
    want = set(sources) if sources else None
    rows = [r for r in conn.execute(
        "SELECT source, build, "
        "count(DISTINCT CASE WHEN error IS NOT NULL "
        "     AND error != 'TimeoutError' THEN part_id END) AS failed, "
        "count(DISTINCT CASE WHEN error = 'TimeoutError' THEN part_id END) "
        "     AS timeout, "
        "count(DISTINCT part_id) AS n "
        "FROM measurements WHERE build IS NOT NULL AND source IS NOT NULL "
        "GROUP BY source, build")
        if want is None or r["source"] in want]

    shas = {r["build"].split(".")[-1].rstrip("+") for r in rows}
    dates = _commit_dates(sorted(shas))
    owed_by = owed(conn, sorted({r["source"] for r in rows}))

    out = []
    for r in rows:
        sha = r["build"].split(".")[-1].rstrip("+")
        if sha not in dates:
            continue
        if r["n"] < owed_by.get(r["source"], 0) * MEANINGFUL_SHARE:
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


def _revision(build: str | None) -> tuple[int, str] | None:
    """A build's revision count and its sha, or None for anything that is not
    a build. `1214.069c08b+` is the 1214th commit, `069c08b`, with the tree
    dirty; the count is what orders two revisions a rebuild gave the same
    date, which a sha alone cannot."""
    if not build:
        return None
    head, _, tail = build.rpartition(".")
    try:
        return int(head), tail.rstrip("+")
    except ValueError:
        return None


#: The last replay, against the corpus it was taken from. A pass over every
#: measurement and every attempt is 300 ms and the dashboard re-reads every
#: 30 seconds against a database that changes only on an ingest, so the answer
#: is kept until one lands.
_REPLAYED: tuple[tuple, list[dict]] | None = None


def _corpus_mark(conn: sqlite3.Connection) -> tuple:
    """What has to change before a replay can say something different."""
    return tuple(conn.execute(
        "SELECT (SELECT MAX(run_id) FROM measurements), "
        "       (SELECT count(*) FROM measurements), "
        "       (SELECT count(*) FROM attempts), "
        "       (SELECT count(*) FROM defects WHERE status = 'open')"
    ).fetchone())


def history(conn: sqlite3.Connection,
            sources: Sequence[str] | None = None) -> list[dict]:
    """Each slot's failing count over the WHOLE corpus after every ingest --
    the series for everything before anyone thought to write a tally.

    Not `by_build`, which is a rate over the parts one revision happened to
    touch. This carries each part's last known verdict forward, so an ingest
    of 11 parts moves the count by at most 11 and leaves 23,000 standing where
    they were, which is what "what will not draw" asks. Replayed in run order,
    the same order `count` reads, so the last step of this and the first
    recorded tally are the same number by construction.

    Ingests, not dates, and the distinction is the whole difficulty. A run is
    one ingest, not one revision: run 1 landed rows from six different builds
    at once and run 4 then landed two older ones, so ordering these by the
    commit each row names walks backwards through the history it is drawing.
    `runs.started` is no use either -- a rebuild re-stamps all 47 of them with
    the ingest time, which is why they read 11:16 on one morning. So the axis
    is the order this corpus learned things, and each step says which revision
    taught it: the newest build among that run's rows, or the run's own commit
    where none of them carries one.

    Within one run the newest revision wins, so run 1's six builds land
    oldest-first and the slot ends that ingest holding what its newest code
    said.

    An attempt that finished clean and produced no drawing counts as a
    failure of the slot, exactly as `coverage_of` reads it -- 2,480 printed
    parts come back so from the decal finder, which files no measurements at
    all and would otherwise show a flat 61.

    Defects are read at today's status, the only one recorded. A part that
    both errors and carries an open defect therefore reads `failed` here and
    `defect` in `count`; none does today.
    """
    global _REPLAYED
    mark = (*_corpus_mark(conn), tuple(sources) if sources else None)
    if _REPLAYED is not None and _REPLAYED[0] == mark:
        return _REPLAYED[1]

    ids = in_scope(conn)
    printed = {r["id"] for r in conn.execute(
        "SELECT id FROM parts WHERE printed = 1")}
    want = set(sources) if sources else None
    flagged_by_engine: dict[str, set[str]] = {}
    for row in conn.execute(
            "SELECT part_id, engines FROM defects WHERE status = 'open'"):
        for engine in ("naive", "occt"):
            if engine in row["engines"]:
                flagged_by_engine.setdefault(engine, set()).add(row["part_id"])

    # Tuples, not rows, and every run's newest build tracked as the walk
    # passes it: this is a pass over every measurement, attempt and render in
    # the corpus, 265,000 of them, and it runs on every dashboard read.
    #
    # Measurements and attempts only. `renders` cannot go on a run axis at
    # all: 66,238 of its 112,861 rows carry no run, a rebuild stamped every
    # `made_at` with the morning it read them back, and the row that survives
    # a re-bake names the re-bake. Read that way white-occt sits at 7% for
    # forty ingests and reaches 80% at run 45 -- where 18,034 of that bake's
    # 18,117 drawings were parts the slot had already measured clean. So
    # `clean` below counts what a slot renders without failing, which every
    # row does date, and not what is on disk.
    rows = [r for r in conn.execute(
        "SELECT source, build, run_id, part_id, error, NULL AS state "
        "FROM measurements WHERE source IS NOT NULL "
        "UNION ALL "
        "SELECT source, NULL AS build, run_id, part_id, error, state "
        "FROM attempts").fetchall()
        if r[3] in ids and (want is None or r[0] in want)]

    commits = {r[0]: r[1] for r in conn.execute(
        "SELECT id, commit_sha FROM runs")}
    revisions = {r[1]: _revision(r[1]) for r in rows}
    counts = {build: (mark[0] if mark else -1)
              for build, mark in revisions.items()}

    out: list[dict] = []
    by_source: dict[str, list[tuple]] = {}
    for row in rows:
        by_source.setdefault(row[0], []).append(row)

    owed_by = owed(conn, sorted(by_source))
    for source, mine in sorted(by_source.items()):
        flagged = flagged_by_engine.get(engine_for(source), set())
        mine.sort(key=lambda r: (r[2], counts[r[1]]))
        covers = not not_applicable(source, True, False)
        covers_plain = not not_applicable(source, False, False)
        verdict: dict[str, str | None] = {}
        held = {"failed": 0, "timeout": 0, "na": 0}
        seen = 0
        newest: str | None = None
        rank = -2

        for i, row in enumerate(mine):
            _, build, run_id, pid, error, state = row
            if counts[build] > rank:
                newest, rank = build, counts[build]
            if pid in flagged:
                now_ = None
            elif error:
                now_ = "timeout" if error == "TimeoutError" else "failed"
            elif state == "none":
                # A slot with nothing to draw for this part has not failed at
                # it and has not covered it either, so it counts as neither.
                now_ = ("failed" if (covers if pid in printed else covers_plain)
                        else "na")
            else:
                now_ = None
            if pid not in verdict:
                seen += 1
            was = verdict.get(pid)
            if was != now_:
                if was:
                    held[was] -= 1
                if now_:
                    held[now_] += 1
            verdict[pid] = now_
            if i + 1 == len(mine) or mine[i + 1][2] != run_id:
                bad = held["failed"] + held["timeout"]
                out.append({"run": run_id, "source": source,
                            "build": newest or commits.get(run_id),
                            "size": len(ids),
                            "owed": owed_by.get(source, len(ids)),
                            "failed": held["failed"],
                            "timeout": held["timeout"],
                            "bad": bad,
                            # What the slot renders without failing -- not
                            # what is on disk for it, which no run dates.
                            # Not `size - bad` either: a part no run has
                            # reached is untried, neither clean nor failed.
                            "clean": seen - bad - held["na"]})
                newest, rank = None, -2
    out.sort(key=lambda r: (r["run"], r["source"]))
    _REPLAYED = (mark, out)
    return out
