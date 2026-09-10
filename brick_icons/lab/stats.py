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
from brick_icons.lab.cells import (COVERAGE_ORDER, coverage_of, engine_for,
                                   not_applicable)

# Seconds a render took, bucketed the way the census notes talk about it.
SECS_EDGES = (1.0, 3.0, 10.0, 30.0, 60.0, 120.0)

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
                successor=row["id"] in successors or None,
                posed=bool(row["preview"]))
            if not wanted_badges <= set(carried):
                continue
        keep.append(row)
    return {r["id"] for r in keep}, keep


def _coverage(conn: sqlite3.Connection, ids: set[str]) -> list[dict]:
    sources = [r["source"] for r in conn.execute(
        "SELECT source, count(*) AS n FROM renders GROUP BY source "
        "ORDER BY n DESC")]
    printed = {r["id"] for r in conn.execute(
        "SELECT id FROM parts WHERE printed = 1")}
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
                                open_defects=1 if pid in flagged else 0,
                                inapplicable=not_applicable(
                                    source, pid in printed, pid in drawn))
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


def _split_of(phases: dict) -> list[dict] | None:
    """The tree below the top four bands, or None if this row never named one.

    Most of the census predates `brick_icons.timing`, and those rows carry
    `render` and nothing under it. Folding them in would put every unmeasured
    second into `rest` -- so the split is tallied over its own smaller `n`,
    and the node-level `n` says which of those parts reached each stage.
    """
    named = normalize(phases)
    if not any("/" in path for path in named):
        return None
    return tree(phases)


def _phases(rows: list[sqlite3.Row], ids: set[str]) -> list[dict]:
    per_engine: dict[str, list[dict]] = {}
    for row in rows:
        if row["part_id"] not in ids or not row["phases"]:
            continue
        phases = json.loads(row["phases"])
        bands = _bands(phases)
        per_engine.setdefault(row["engine"], []).append({
            "part_id": row["part_id"],
            "bands": bands,
            "total": round(sum(bands.values()), 3),
            "nodes": _split_of(phases),
        })

    out = []
    for engine, measured in sorted(per_engine.items()):
        totals = {k: round(sum(m["bands"][k] for m in measured), 3)
                  for k in PHASE_ORDER}
        ranked = sorted(measured, key=lambda m: -m["total"])
        split = [m for m in measured if m["nodes"] is not None]
        out.append({
            "engine": engine,
            "n": len(measured),
            "total": round(sum(totals.values()), 3),
            "totals": totals,
            "split": {
                "n": len(split),
                "total": round(sum(n["secs"] for m in split
                                   for n in m["nodes"]), 3),
                "nodes": _sum_trees(split),
            } if split else None,
            "slowest": [{"part_id": m["part_id"], "total": m["total"],
                         "secs": {k: round(v, 3) for k, v in m["bands"].items()},
                         "split": m["nodes"]}
                        for m in ranked[:SLOWEST_N]],
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
