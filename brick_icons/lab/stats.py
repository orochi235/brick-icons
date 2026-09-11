"""What the corpus database holds, tallied over a working set.

The dashboard's whole backend. Coverage labels come from `cells.coverage_of`,
the same function the wall's own grouping reads, so the two pages cannot come
to disagree about what `drawn` means.
"""
import datetime as dt
import json
import sqlite3

from brick_icons import tags as part_tags
from brick_icons.db import MOVED_PREFIX, OUT_OF_SCOPE_CATEGORIES
from brick_icons.lab import tally
from brick_icons.lab.cells import (COVERAGE_ORDER, coverage_of, engine_for,
                                   not_applicable)

# Seconds a render took, in even 2-second buckets to a minute, then one open
# bucket for the tail. Even is the point: bars of one width over buckets
# spanning 1s, 7s and 30s drew the same area for wildly different densities.
SECS_BUCKET = 2.0
SECS_TOP = 60.0
SECS_EDGES = tuple(SECS_BUCKET * i
                   for i in range(1, int(SECS_TOP // SECS_BUCKET) + 1))

# The part-kind filters. The wall's `rendered` / `unrendered` / `errors` are
# not here: each is a statement about one slot, and the coverage chart already
# breaks every slot out that way.
KINDS = ("all", "printed", "obsolete", "base")

# The top of the tree, in stacking order. Every row that carries phases at
# all carries these four, and they are exclusive of one another.
PHASE_ORDER = ("render", "rasterize", "truth_mask", "compare")

# Where a phase measured before `brick_icons.timing` recorded paths belongs.
# All three sit directly under `render` because that is how they were
# measured: the old accumulator subtracted nested time, so `decoration` ran
# inside `geometry` but was not counted in it. Nesting it where it actually
# runs would read that exclusive number as an inclusive one and take the
# same tenth of a second off `render`'s leftover twice.
LEGACY_PATHS = {"geometry": "render/geometry",
                "decoration": "render/decoration",
                "fill": "render/fill"}

# What a level's unnamed remainder is called. Never stored -- it is
# `parent - sum(children)`, worked out here so a new seam anywhere in the
# engine narrows `rest` instead of redefining the band above it.
REST = "rest"

# The engines the timing, phase and accuracy sections report on. naive is the
# reference implementation, not a candidate, so comparing the two engines here
# measured a race nobody is running. It keeps its coverage rows -- those say
# how much of the library each slot has drawn, which is still worth seeing.
REPORTED_ENGINES = ("occt",)


def _quantile(sorted_values: list[float], q: float) -> float | None:
    """Linear interpolation between the two neighbouring samples, which is
    what `numpy.quantile` does by default and what a reader expects a median
    of an even-length list to be."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    low = int(pos)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)


def _spread(values: list[float]) -> dict:
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "total": sum(ordered),
        "median": _quantile(ordered, 0.5),
        "p95": _quantile(ordered, 0.95),
        "max": ordered[-1] if ordered else None,
    }


def _bins(values: list[float]) -> list[dict]:
    edges = (0.0, *SECS_EDGES)
    out = [{"from": lo, "to": hi, "n": 0}
           for lo, hi in zip(edges, (*SECS_EDGES, None))]
    for v in values:
        index = min(max(int(v // SECS_BUCKET), 0), len(SECS_EDGES))
        out[index]["n"] += 1
    return out


def members(conn: sqlite3.Connection, *, kind: str = "all", moved: bool = False,
            out_of_scope: bool = True, obsolete: bool = False,
            posed: bool = True, excluded: tuple[str, ...] = (),
            badges: tuple[str, ...] = ()) -> tuple[set[str], list[sqlite3.Row]]:
    """The parts in the working set, and their rows.

    The same membership the wall's sidebar expresses, decided here so the
    tallies and the wall agree on which parts they are about.

    `obsolete` and `posed` say whether that class is on the map at all, which
    is not what `kind` asks: `kind="obsolete"` looks at nothing else.
    """
    scope_marks = ",".join("?" * len(OUT_OF_SCOPE_CATEGORIES))
    rows = list(conn.execute(
        f"SELECT id, title, category, printed, obsolete, preview, "
        f"(printed = 0 AND obsolete = 0 AND id NOT LIKE '%c__' "
        f"AND id NOT LIKE '%d__' AND id NOT LIKE 'u9%') AS base, "
        f"(category IN ({scope_marks})) AS out_of_scope, "
        f"(title LIKE '{MOVED_PREFIX}%') AS moved "
        f"FROM parts ORDER BY id", OUT_OF_SCOPE_CATEGORIES))

    years = {r["part_id"]: r for r in conn.execute(
        "SELECT part_id, year_to, sets FROM part_years")}
    successors = {r["part_id"] for r in conn.execute(
        "SELECT part_id FROM part_successors")}

    # Narrowing to the class puts it back on the map whatever the flag says,
    # which is what `kind="obsolete"` means and now matters: the flag is off.
    obsolete = obsolete or kind == "obsolete"
    excluded_set = {e for e in excluded}
    # By axis, as the wall's legend groups them: two tags on one axis are
    # alternatives, two axes narrow. A subset test read `technic` and `duplo`
    # as a part that is both, which is no part at all.
    wanted_axes = part_tags.by_axis(badges)
    keep = []
    for row in rows:
        if row["moved"] and not moved:
            continue
        if row["out_of_scope"] and not out_of_scope:
            continue
        if row["obsolete"] and not obsolete:
            continue
        if row["preview"] and not posed:
            continue
        if kind == "printed" and not row["printed"]:
            continue
        if kind == "obsolete" and not row["obsolete"]:
            continue
        if kind == "base" and not row["base"]:
            continue
        if part_tags.clean_category(row["category"]) in excluded_set:
            continue
        if wanted_axes:
            year = years.get(row["id"])
            carried = set(part_tags.tags_for(
                row["category"], bool(row["printed"]),
                year["year_to"] if year else None,
                year["sets"] if year else None,
                title=row["title"], part_id=row["id"],
                successor=row["id"] in successors or None))
            if not all(carried & set(group) for group in wanted_axes):
                continue
        keep.append(row)
    return {r["id"] for r in keep}, keep


#: Every slot's latest error per part, in ONE pass. Asked per slot instead,
#: this is a `MAX(run_id)` group-by over the whole measurements table once for
#: each of them -- 1,067 ms of a 3,700 ms page, and it grows with the slots.
_LATEST_ERROR_BY_SOURCE = """
SELECT m.part_id, m.source, m.error FROM measurements m
JOIN (SELECT part_id, source, MAX(run_id) AS run_id FROM measurements
      WHERE source IS NOT NULL GROUP BY part_id, source) latest
  ON m.part_id = latest.part_id AND m.source = latest.source
 AND m.run_id = latest.run_id
WHERE m.error IS NOT NULL
"""


def _coverage(conn: sqlite3.Connection, ids: set[str]) -> list[dict]:
    sources = [r["source"] for r in conn.execute(
        "SELECT source, count(*) AS n FROM renders GROUP BY source "
        "ORDER BY n DESC")]
    printed = {r["id"] for r in conn.execute(
        "SELECT id FROM parts WHERE printed = 1")}
    obsolete = {r["id"] for r in conn.execute(
        "SELECT id FROM parts WHERE obsolete = 1")}
    errors_by_source: dict[str, dict[str, str]] = {}
    for row in conn.execute(_LATEST_ERROR_BY_SOURCE):
        errors_by_source.setdefault(row["source"], {})[row["part_id"]] = row["error"]
    drawn_by_source: dict[str, set[str]] = {}
    for row in conn.execute("SELECT part_id, source FROM renders"):
        drawn_by_source.setdefault(row["source"], set()).add(row["part_id"])
    nothing_by_source: dict[str, set[str]] = {}
    for row in conn.execute(
            "SELECT DISTINCT part_id, source FROM attempts WHERE state = 'none'"):
        nothing_by_source.setdefault(row["source"], set()).add(row["part_id"])
    open_defects = list(conn.execute(
        "SELECT part_id, engines FROM defects WHERE status = 'open'"))
    out = []
    for source in sources:
        engine = engine_for(source)
        drawn = drawn_by_source.get(source, set())
        errors = errors_by_source.get(source, {})
        flagged = {r["part_id"] for r in open_defects if engine in r["engines"]}
        # Without this the two pages disagree, which the module docstring
        # promises they cannot: the wall reads a slot that ran and drew
        # nothing as `failed`, and the dashboard was calling the same 2,480
        # decal parts `untried` and asking the fleet to redo finished work.
        drew_nothing = nothing_by_source.get(source, set())
        counts = dict.fromkeys(COVERAGE_ORDER, 0)
        # `coverage_of` stays the definition -- the wall reads the same
        # function, and re-deriving its precedence here is how the two pages
        # come to disagree. Only the parts carrying news are asked about one
        # at a time; for the rest the answer turns on nothing but whether the
        # slot drew it, whether it is printed and whether it is obsolete, so
        # eight set sizes stand in for 23,000 calls a slot.
        told = (errors.keys() | flagged | drew_nothing) & ids
        for has_sha in (True, False):
            group = (ids & drawn if has_sha else ids - drawn) - told
            for is_printed in (True, False):
                same = group & printed if is_printed else group - printed
                for is_obsolete in (True, False):
                    n = len(same & obsolete if is_obsolete
                            else same - obsolete)
                    if not n:
                        continue
                    counts[coverage_of(
                        sha="x" if has_sha else None, error=None,
                        open_defects=0,
                        inapplicable=not_applicable(source, is_printed,
                                                    has_sha, is_obsolete),
                        drew_nothing=False)] += n
        for pid in told:
            counts[coverage_of(
                sha="x" if pid in drawn else None, error=errors.get(pid),
                open_defects=1 if pid in flagged else 0,
                inapplicable=not_applicable(source, pid in printed,
                                            pid in drawn, pid in obsolete),
                drew_nothing=pid in drew_nothing)] += 1
        out.append({"source": source, "engine": engine, "counts": counts,
                    "size": len(ids)})
    return out


def _latest_measurements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT m.part_id, m.engine, m.secs, m.extra_d99, m.missing_px, "
        "m.phases "
        "FROM measurements m JOIN "
        "(SELECT part_id, engine, MAX(run_id) AS run_id FROM measurements "
        " GROUP BY part_id, engine) latest "
        "ON m.part_id = latest.part_id AND m.engine = latest.engine "
        "AND m.run_id = latest.run_id"))


def _speed_and_error(rows: list[sqlite3.Row],
                     ids: set[str]) -> tuple[list[dict], list[dict]]:
    secs: dict[str, list[float]] = {}
    d99: dict[str, list[float]] = {}
    missing: dict[str, list[float]] = {}
    for row in rows:
        if row["part_id"] not in ids:
            continue
        engine = row["engine"]
        if row["secs"] is not None:
            secs.setdefault(engine, []).append(row["secs"])
        if row["extra_d99"] is not None:
            d99.setdefault(engine, []).append(row["extra_d99"])
        if row["missing_px"] is not None:
            missing.setdefault(engine, []).append(float(row["missing_px"]))

    speed = [{"engine": e, **_spread(v), "bins": _bins(v)}
             for e, v in sorted(secs.items())]
    error = [{"engine": e, "d99": _spread(d99.get(e, [])),
              "missing_px": _spread(missing.get(e, []))}
             for e in sorted(set(d99) | set(missing))]
    return speed, error


def normalize(phases: dict) -> dict[str, float]:
    """One row's phases as paths, whenever it was measured.

    A row written before `timing` recorded paths names bare `geometry` and
    `fill`; `LEGACY_PATHS` puts each where it actually ran. A path already
    carrying a separator is passed through, and an unrecognized bare name
    stays at the top rather than being guessed at.
    """
    out: dict[str, float] = {}
    for name, secs in phases.items():
        path = name if "/" in name else LEGACY_PATHS.get(name, name)
        out[path] = out.get(path, 0.0) + float(secs)
    return out


def tree(phases: dict) -> list[dict]:
    """One row's phases as the nested thing they describe.

    Each node is `{name, path, secs, children}` with `secs` inclusive of
    everything beneath it. A node whose children do not fill it gains a
    `rest` child for the difference, which is how an unnamed seam shows up as
    a gap rather than as a missing summand. A path whose parent was never
    recorded is grafted on at the depth it names, so a partial row still
    draws.
    """
    paths = normalize(phases)
    nodes: dict[str, dict] = {}
    for path in sorted(paths, key=lambda p: p.count("/")):
        parts = path.split("/")
        for i in range(len(parts)):
            at = "/".join(parts[:i + 1])
            nodes.setdefault(at, {"name": parts[i], "path": at,
                                  "secs": round(paths.get(at, 0.0), 3),
                                  "children": []})
    roots = []
    for path, node in nodes.items():
        parent = path.rsplit("/", 1)[0] if "/" in path else None
        (nodes[parent]["children"] if parent in nodes else roots).append(node)

    for node in nodes.values():
        node["children"].sort(key=lambda c: -c["secs"])
        named = sum(c["secs"] for c in node["children"])
        gap = round(node["secs"] - named, 3)
        # A hair over is float noise on three decimals, not an unnamed stage.
        if node["children"] and gap > 0.001:
            node["children"].append({"name": REST, "path": f"{node['path']}/{REST}",
                                     "secs": gap, "children": []})
    order = {name: i for i, name in enumerate(PHASE_ORDER)}
    roots.sort(key=lambda n: (order.get(n["name"], len(order)), n["name"]))
    return roots


def _bands(phases: dict) -> dict[str, float]:
    """The four top-level bands, for the stacked bar that compares engines."""
    named = normalize(phases)
    return {k: float(named.get(k, 0.0)) for k in PHASE_ORDER}


def _sum_paths(named: list[dict[str, float]]) -> list[dict]:
    """One tree over many rows, summed from their paths rather than from a
    tree apiece.

    Identical output to walking each row's own tree -- a node exists for every
    prefix of every named path, carrying that path's seconds or nothing --
    and `tree` is then run once instead of 19,931 times, which was a third of
    the dashboard's load.
    """
    secs: dict[str, float] = {}
    seen: dict[str, int] = {}
    for row in named:
        # Per ROW, so a row naming `render/geometry` twice still counts once
        # against `render` -- `seen` is how many parts reached a stage.
        reached: set[str] = set()
        for path in row:
            parts = path.split("/")
            for i in range(len(parts)):
                reached.add("/".join(parts[:i + 1]))
        for path in reached:
            secs[path] = secs.get(path, 0.0) + row.get(path, 0.0)
            seen[path] = seen.get(path, 0) + 1
    summed = tree(secs)

    def stamp(nodes):
        for node in nodes:
            if node["name"] != REST:
                node["n"] = seen.get(node["path"], 0)
            stamp(node["children"])

    stamp(summed)
    return summed


def _sum_trees(rows: list[dict]) -> list[dict]:
    """One tree over many parts: the same path added up wherever it appears.

    A part that never reached a stage simply has no node for it, so a seam
    added halfway through a census tallies over the parts that carry it
    rather than being diluted by the ones that do not. `n` says how many
    those were, which is the only honest way to read a node's share.
    """
    secs: dict[str, float] = {}
    seen: dict[str, int] = {}

    def walk(nodes):
        for node in nodes:
            if node["name"] == REST:
                continue          # re-derived below, never carried forward
            secs[node["path"]] = secs.get(node["path"], 0.0) + node["secs"]
            seen[node["path"]] = seen.get(node["path"], 0) + 1
            walk(node["children"])

    for row in rows:
        walk(row["nodes"])
    summed = tree(secs)

    def stamp(nodes):
        for node in nodes:
            # `rest` is derived, not measured. An `n` on it would answer a
            # question nobody asked with a 0 that reads as "no part got here".
            if node["name"] != REST:
                node["n"] = seen.get(node["path"], 0)
            stamp(node["children"])
    stamp(summed)
    return summed


def _phases(rows: list[sqlite3.Row], ids: set[str]) -> list[dict]:
    per_engine: dict[str, list[dict]] = {}
    for row in rows:
        if row["part_id"] not in ids or not row["phases"]:
            continue
        phases = json.loads(row["phases"])
        bands = _bands(phases)
        named = normalize(phases)
        per_engine.setdefault(row["engine"], []).append({
            "part_id": row["part_id"],
            "bands": bands,
            "total": round(sum(bands.values()), 3),
            "named": named,
            "split": any("/" in path for path in named),
        })

    out = []
    for engine, measured in sorted(per_engine.items()):
        totals = {k: round(sum(m["bands"][k] for m in measured), 3)
                  for k in PHASE_ORDER}
        split = [m for m in measured if m["split"]]
        nodes = _sum_paths([m["named"] for m in split]) if split else []
        out.append({
            "engine": engine,
            "n": len(measured),
            "total": round(sum(totals.values()), 3),
            "totals": totals,
            "split": {
                "n": len(split),
                "total": round(sum(n["secs"] for n in nodes), 3),
                "nodes": nodes,
            } if split else None,
        })
    return out


_TIMED_BY_SLOT = """
SELECT m.part_id, m.source, m.build, m.secs FROM measurements m JOIN
     (SELECT part_id, source, MAX(run_id) AS run_id FROM measurements
      WHERE secs IS NOT NULL GROUP BY part_id, source) latest
  ON m.part_id = latest.part_id AND m.source = latest.source
 AND m.run_id = latest.run_id
WHERE m.secs IS NOT NULL AND m.source IS NOT NULL AND m.build IS NOT NULL
"""

#: A slot that draws but never scores -- `decal` today -- records what it cost
#: in `attempts` and nothing in `measurements`. It is still a pass someone
#: pays for, so the panel reads it here, at the revision its run carried.
_TIMED_BY_ATTEMPT = """
SELECT a.part_id, a.source, r.commit_sha AS build, a.secs
FROM attempts a
JOIN runs r ON r.id = a.run_id
JOIN (SELECT part_id, source, MAX(run_id) AS run_id FROM attempts
      WHERE secs IS NOT NULL GROUP BY part_id, source) latest
  ON a.part_id = latest.part_id AND a.source = latest.source
 AND a.run_id = latest.run_id
WHERE a.secs IS NOT NULL
  AND a.source IN (SELECT DISTINCT source FROM renders)
  AND a.source NOT IN (SELECT DISTINCT source FROM measurements
                       WHERE source IS NOT NULL AND secs IS NOT NULL)
"""


def _cost_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """The newest timing per part per SLOT, which is not the same question as
    `_latest_measurements`: two facets of one engine are both `occt`, so a
    newest-per-engine pick hands a slot whichever facet ran last."""
    return [*conn.execute(_TIMED_BY_SLOT), *conn.execute(_TIMED_BY_ATTEMPT)]


def _cost(rows: list[sqlite3.Row], ids: set[str]) -> dict | None:
    """What one pass costs, slot by slot, as a share of running them all.

    Each slot is measured against the base slot over the parts the two share
    at one revision, not over the parts every slot shares: intersecting all of
    them cut a 17,611-part comparison down to 1,592, and any slot that has
    barely run takes every other slot down with it.

    Which revision matters, and it is per slot: a slot's stored seconds
    otherwise span every revision that ever drew it, and the spread swamps the
    answer -- silhouette-occt's oldest rows average 48.9s against 17.9s for
    the same slot at the current build. A row says the revision it was taken
    at, so a slot measured somewhere else than the base reads as what it is.
    """
    at: dict[str, dict[str, dict[str, float]]] = {}
    for row in rows:
        if row["part_id"] not in ids or not row["build"]:
            continue
        at.setdefault(row["source"], {}).setdefault(
            row["build"], {})[row["part_id"]] = row["secs"]
    if len(at) < 2:
        return None

    def widest(source: str) -> tuple[str, dict[str, float]]:
        build = max(at[source], key=lambda b: len(at[source][b]))
        return build, at[source][build]

    # A plain slot is the reference -- `occt` against `white-occt` is the
    # comparison a reader means -- and the widest of them when more than one
    # slot is nobody's facet.
    plain = [s for s in at if s == engine_for(s)]
    base = max(plain or list(at), key=lambda s: len(widest(s)[1]))
    base_build, base_secs = widest(base)

    measured = []
    for source in sorted(at):
        if source == base:
            common, build, secs = set(base_secs), base_build, base_secs
        else:
            # The base's own revision whenever the slot has it. Falling back
            # to whichever revision overlaps most would quietly pick a stale
            # one -- silhouette-occt has a build averaging 48.9s against 17.9s
            # for the same slot now -- so the fallback is a last resort and
            # the row says it happened.
            at_base = set(at[source].get(base_build, ())) & set(base_secs)
            build, common = (base_build, at_base) if at_base else max(
                ((b, set(by) & set(base_secs)) for b, by in at[source].items()),
                key=lambda pair: len(pair[1]))
            secs = at[source][build]
            if not common:
                continue
        mine = sum(secs[p] for p in common)
        theirs = sum(base_secs[p] for p in common)
        ordered = sorted(secs[p] for p in common)
        measured.append({
            "source": source, "build": build, "n": len(common),
            "total": round(mine, 1),
            "ratio": mine / theirs if theirs else None,
            "median": _quantile(ordered, 0.5),
            "p90": _quantile(ordered, 0.9),
        })

    # Shares off the ratios, not off the totals: the rows no longer share a
    # denominator, and summing seconds measured over different parts would
    # read a slot that has run more often as the expensive one.
    whole = sum(r["ratio"] or 0.0 for r in measured)
    for row in measured:
        row["share"] = (row["ratio"] or 0.0) / whole if whole else 0.0
    return {"build": base_build, "base": base,
            "n": len(base_secs),
            "total": round(sum(r["total"] for r in measured), 1),
            "slots": sorted(measured, key=lambda r: -r["share"])}


def _running(conn: sqlite3.Connection) -> bool:
    """Whether any run is unfinished, which is what sets the poll interval."""
    return conn.execute("SELECT 1 FROM runs WHERE finished IS NULL "
                        "LIMIT 1").fetchone() is not None


def _shape(conn: sqlite3.Connection, rows: list[sqlite3.Row],
           ids: set[str]) -> dict:
    categories: dict[str, int] = {}
    kinds = {"printed": 0, "obsolete": 0, "base": 0, "out_of_scope": 0,
             "moved": 0}
    for row in rows:
        name = part_tags.clean_category(row["category"])
        categories[name] = categories.get(name, 0) + 1
        for flag in kinds:
            if row[flag]:
                kinds[flag] += 1
    dated = sum(1 for r in conn.execute("SELECT part_id FROM part_years")
                if r["part_id"] in ids)
    return {
        "categories": sorted(categories.items(), key=lambda kv: -kv[1]),
        "kinds": kinds,
        "dated": dated,
    }


def _failures(conn: sqlite3.Connection) -> dict:
    """What fails to draw, corpus-wide and over time.

    Deliberately not filtered by the working set. The tiles answer "how much
    of the library is broken", which is not a question the Controls should be
    able to make a smaller number of -- so the labels say corpus-wide and the
    figures ignore every filter beside them.
    """
    tracked = [s for s in tally.tracked_sources(conn)]
    return {
        "totals": tally.totals(conn),
        "series": tally.series(conn, tracked),
        "history": tally.history(conn, tracked),
        "by_build": tally.by_build(conn, tracked),
    }


def stats(conn: sqlite3.Connection, *, kind: str = "all", moved: bool = False,
          out_of_scope: bool = True, obsolete: bool = False, posed: bool = True,
          excluded: tuple[str, ...] = (),
          badges: tuple[str, ...] = ()) -> dict:
    """Every tally the dashboard draws, for one working set."""
    ids, rows = members(conn, kind=kind, moved=moved,
                        out_of_scope=out_of_scope, obsolete=obsolete,
                        posed=posed, excluded=tuple(excluded),
                        badges=tuple(badges))
    total = conn.execute("SELECT count(*) FROM parts").fetchone()[0]
    latest = [r for r in _latest_measurements(conn)
              if r["engine"] in REPORTED_ENGINES]
    speed, error = _speed_and_error(latest, ids)
    return {
        "set": {"size": len(ids), "total": total, "kind": kind,
                "moved": moved, "out_of_scope": out_of_scope,
                "obsolete": obsolete, "posed": posed,
                "excluded": list(excluded), "badges": list(badges)},
        "coverage": _coverage(conn, ids),
        "speed": speed,
        "error": error,
        "phases": _phases(latest, ids),
        "cost": _cost(_cost_rows(conn), ids),
        "running": _running(conn),
        "shape": _shape(conn, rows, ids),
        "failures": _failures(conn),
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
