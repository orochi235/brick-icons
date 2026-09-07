"""What the corpus database holds, tallied over a working set.

The dashboard's whole backend. Coverage labels come from `cells.coverage_of`,
the same function the wall's own grouping reads, so the two pages cannot come
to disagree about what `drawn` means.
"""
import datetime as dt
import json
import sqlite3

from brick_icons import tags as part_tags
from brick_icons.db import OUT_OF_SCOPE_CATEGORIES
from brick_icons.lab.cells import COVERAGE_ORDER, coverage_of, engine_for

# Seconds a render took, bucketed the way the census notes talk about it.
SECS_EDGES = (1.0, 3.0, 10.0, 30.0, 60.0, 120.0)

# The part-kind filters. The wall's `rendered` / `unrendered` / `errors` are
# not here: each is a statement about one slot, and the coverage chart already
# breaks every slot out that way.
KINDS = ("all", "printed", "obsolete", "base")

# Where one render's wall-clock went, in stacking order. Every row that
# carries phases at all carries these four, and they are exclusive.
PHASE_ORDER = ("render", "rasterize", "truth_mask", "compare")

# How `render` itself divides, for the rows measured since `brick_icons.timing`
# existed. Most of the census predates it, so this is tallied over its own
# smaller n rather than mixed into the four above -- a row that never named a
# split would otherwise donate its whole render to `rest`.
SPLIT_ORDER = ("geometry", "decoration", "fill", "rest")

# How many parts the per-part strip draws. Enough that the tail has a shape,
# few enough to stay one screen wide.
SLOWEST_N = 40


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
        index = len(SECS_EDGES)
        for i, edge in enumerate(SECS_EDGES):
            if v < edge:
                index = i
                break
        out[index]["n"] += 1
    return out


def members(conn: sqlite3.Connection, *, kind: str = "all", moved: bool = False,
            out_of_scope: bool = True, excluded: tuple[str, ...] = (),
            badges: tuple[str, ...] = ()) -> tuple[set[str], list[sqlite3.Row]]:
    """The parts in the working set, and their rows.

    The same membership the wall's sidebar expresses, decided here so the
    tallies and the wall agree on which parts they are about.
    """
    scope_marks = ",".join("?" * len(OUT_OF_SCOPE_CATEGORIES))
    rows = list(conn.execute(
        f"SELECT id, title, category, printed, obsolete, "
        f"(printed = 0 AND obsolete = 0 AND id NOT LIKE '%c__' "
        f"AND id NOT LIKE '%d__' AND id NOT LIKE 'u9%') AS base, "
        f"(category IN ({scope_marks})) AS out_of_scope, "
        f"(title LIKE '~Moved to%') AS moved "
        f"FROM parts ORDER BY id", OUT_OF_SCOPE_CATEGORIES))

    years = {r["part_id"]: r for r in conn.execute(
        "SELECT part_id, year_to, sets FROM part_years")}
    successors = {r["part_id"] for r in conn.execute(
        "SELECT part_id FROM part_successors")}

    excluded_set = {e for e in excluded}
    wanted_badges = set(badges)
    keep = []
    for row in rows:
        if row["moved"] and not moved:
            continue
        if row["out_of_scope"] and not out_of_scope:
            continue
        if kind == "printed" and not row["printed"]:
            continue
        if kind == "obsolete" and not row["obsolete"]:
            continue
        if kind == "base" and not row["base"]:
            continue
        if part_tags.clean_category(row["category"]) in excluded_set:
            continue
        if wanted_badges:
            year = years.get(row["id"])
            carried = part_tags.tags_for(
                row["category"], bool(row["printed"]), bool(row["obsolete"]),
                year["year_to"] if year else None,
                year["sets"] if year else None,
                title=row["title"], part_id=row["id"],
                successor=row["id"] in successors or None)
            if not wanted_badges <= set(carried):
                continue
        keep.append(row)
    return {r["id"] for r in keep}, keep


def _coverage(conn: sqlite3.Connection, ids: set[str]) -> list[dict]:
    sources = [r["source"] for r in conn.execute(
        "SELECT source, count(*) AS n FROM renders GROUP BY source "
        "ORDER BY n DESC")]
    out = []
    for source in sources:
        engine = engine_for(source)
        drawn = {r["part_id"] for r in conn.execute(
            "SELECT part_id FROM renders WHERE source = ?", (source,))}
        errors = {r["part_id"]: r["error"] for r in conn.execute(
            "SELECT m.part_id, m.error FROM measurements m JOIN "
            "(SELECT part_id, MAX(run_id) AS run_id FROM measurements "
            " WHERE source = ? GROUP BY part_id) latest "
            "ON m.part_id = latest.part_id AND m.run_id = latest.run_id "
            "WHERE m.source = ?", (source, source))}
        flagged = {r["part_id"] for r in conn.execute(
            "SELECT part_id, engines FROM defects WHERE status = 'open'")
            if engine in r["engines"]}
        counts = dict.fromkeys(COVERAGE_ORDER, 0)
        for pid in ids:
            label = coverage_of(sha="x" if pid in drawn else None,
                                error=errors.get(pid),
                                open_defects=1 if pid in flagged else 0)
            counts[label] += 1
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


def _bands(phases: dict) -> dict[str, float]:
    return {k: float(phases.get(k, 0.0)) for k in PHASE_ORDER}


def _render_split(phases: dict) -> dict[str, float] | None:
    """How `render` divides, or None if this row was measured before it did.

    `geometry` is the marker: `decoration` only appears on a printed part and
    `fill` only where there is a shaded face, so neither says whether the row
    was instrumented."""
    if "geometry" not in phases:
        return None
    named = {k: float(phases.get(k, 0.0)) for k in SPLIT_ORDER if k != "rest"}
    named["rest"] = max(0.0, float(phases.get("render", 0.0)) - sum(named.values()))
    return named


def _phases(rows: list[sqlite3.Row], ids: set[str]) -> list[dict]:
    per_engine: dict[str, list[tuple[str, dict, dict | None]]] = {}
    for row in rows:
        if row["part_id"] not in ids or not row["phases"]:
            continue
        phases = json.loads(row["phases"])
        per_engine.setdefault(row["engine"], []).append(
            (row["part_id"], _bands(phases), _render_split(phases)))

    out = []
    for engine, measured in sorted(per_engine.items()):
        totals = {k: round(sum(b[k] for _, b, _ in measured), 3) for k in PHASE_ORDER}
        splits = [s for _, _, s in measured if s is not None]
        ranked = sorted(measured, key=lambda m: -sum(m[1].values()))
        out.append({
            "engine": engine,
            "n": len(measured),
            "total": round(sum(totals.values()), 3),
            "totals": totals,
            "split": {
                "n": len(splits),
                "total": round(sum(sum(s.values()) for s in splits), 3),
                "totals": {k: round(sum(s[k] for s in splits), 3)
                           for k in SPLIT_ORDER},
            } if splits else None,
            "slowest": [{"part_id": pid,
                         "total": round(sum(bands.values()), 3),
                         "secs": {k: round(v, 3) for k, v in bands.items()},
                         "split": ({k: round(v, 3) for k, v in split.items()}
                                   if split else None)}
                        for pid, bands, split in ranked[:SLOWEST_N]],
        })
    return out


def _runs(conn: sqlite3.Connection, ids: set[str]) -> list[dict]:
    measured: dict[int, int] = {}
    for row in conn.execute("SELECT run_id, part_id FROM measurements "
                            "GROUP BY run_id, part_id"):
        if row["part_id"] in ids:
            measured[row["run_id"]] = measured.get(row["run_id"], 0) + 1
    return [{"id": r["id"], "kind": r["kind"], "started": r["started"],
             "finished": r["finished"], "open": r["finished"] is None,
             "commit_sha": r["commit_sha"], "args": r["args"],
             "note": r["note"], "parts": measured.get(r["id"], 0)}
            for r in conn.execute("SELECT * FROM runs ORDER BY started DESC, id DESC")]


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


def stats(conn: sqlite3.Connection, *, kind: str = "all", moved: bool = False,
          out_of_scope: bool = True, excluded: tuple[str, ...] = (),
          badges: tuple[str, ...] = ()) -> dict:
    """Every tally the dashboard draws, for one working set."""
    ids, rows = members(conn, kind=kind, moved=moved,
                        out_of_scope=out_of_scope, excluded=tuple(excluded),
                        badges=tuple(badges))
    total = conn.execute("SELECT count(*) FROM parts").fetchone()[0]
    latest = _latest_measurements(conn)
    speed, error = _speed_and_error(latest, ids)
    return {
        "set": {"size": len(ids), "total": total, "kind": kind,
                "moved": moved, "out_of_scope": out_of_scope,
                "excluded": list(excluded), "badges": list(badges)},
        "coverage": _coverage(conn, ids),
        "speed": speed,
        "error": error,
        "phases": _phases(latest, ids),
        "runs": _runs(conn, ids),
        "shape": _shape(conn, rows, ids),
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
