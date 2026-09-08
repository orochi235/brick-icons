"""What to look at next, answered from the database instead of a render batch.

A finding is one part under one engine, carrying its latest measurement, its
open defects, and the render already in the store if there is one. The store
fills as parts get rendered, so a view built on this shows what exists and asks
for the rest -- the whole reason not to fill the corpus in one pass.
"""
from __future__ import annotations

import sqlite3

ORDERS = {
    "extra_d99": "m.extra_d99",
    "extra_d100": "m.extra_d100",
    "missing_px": "m.missing_px",
    "missing_comps": "m.missing_comps",
    "secs": "m.secs",
    "part": "m.part_id",
}

# One row per part and engine, from that pair's newest run. A part measured
# again is one finding carrying the newer number, not two.
_LATEST = """
SELECT m.* FROM measurements m
JOIN (SELECT part_id, engine, MAX(run_id) AS run_id
      FROM measurements GROUP BY part_id, engine) latest
  ON m.part_id = latest.part_id AND m.engine = latest.engine
 AND m.run_id = latest.run_id
"""


def findings(conn: sqlite3.Connection, engine: str | None = None,
             status: str | None = None, part: str | None = None,
             stored: bool | None = None, errors_only: bool = False,
             order: str = "extra_d99", ascending: bool = False,
             limit: int = 100, offset: int = 0) -> dict:
    """Findings worst-first, with `total` counting every match, not the page.

    `stored` filters on whether the engine's render is already in the store:
    True for what can be shown now, False for what would have to be rendered.
    """
    if order not in ORDERS:
        raise ValueError(f"order must be one of {sorted(ORDERS)}, not {order!r}")

    where, args = [], []
    if engine:
        where.append("m.engine = ?")
        args.append(engine)
    if status:
        where.append("p.status = ?")
        args.append(status)
    if part:
        where.append("m.part_id LIKE ?")
        args.append(f"%{part}%")
    if errors_only:
        where.append("m.error IS NOT NULL")
    if stored is True:
        where.append("r.path IS NOT NULL")
    elif stored is False:
        where.append("r.path IS NULL")
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    # The render is joined on the engine's own source, so a naive finding never
    # reports occt's drawing as its own.
    body = f"""
    FROM ({_LATEST}) m
    LEFT JOIN parts p ON p.id = m.part_id
    LEFT JOIN renders r ON r.part_id = m.part_id AND r.source = m.engine
    {clause}
    """

    total = conn.execute(f"SELECT count(*) {body}", args).fetchone()[0]
    direction = "ASC" if ascending else "DESC"
    rows = conn.execute(
        f"""SELECT m.part_id, m.engine, m.run_id, m.missing_px, m.extra_px,
                   m.missing_comps, m.extra_d99, m.extra_d100, m.secs,
                   m.error, m.detail,
                   p.title, p.status, p.status_note, p.printed,
                   r.path AS render, r.sha256
            {body}
            ORDER BY {ORDERS[order]} {direction} NULLS LAST, m.part_id ASC
            LIMIT ? OFFSET ?""", [*args, limit, offset]).fetchall()

    out = [dict(row) for row in rows]
    _attach_defects(conn, out)
    return {"total": total, "rows": out, "order": order,
            "ascending": ascending, "limit": limit, "offset": offset}


def _attach_defects(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """One query for the page, not one per row."""
    ids = {r["part_id"] for r in rows}
    if not ids:
        return
    marks = ",".join("?" * len(ids))
    counts: dict[str, dict] = {}
    for d in conn.execute(
            f"SELECT part_id, status, count(*) AS n FROM defects "
            f"WHERE part_id IN ({marks}) GROUP BY part_id, status", list(ids)):
        counts.setdefault(d["part_id"], {})[d["status"]] = d["n"]
    for row in rows:
        by_status = counts.get(row["part_id"], {})
        row["defects"] = by_status
        row["open_defects"] = sum(
            n for s, n in by_status.items() if s not in ("fixed", "notabug"))


def summary(conn: sqlite3.Connection) -> dict:
    """What the database holds, for a view to say how much of the corpus it can
    answer for without rendering anything."""
    one = lambda q: conn.execute(q).fetchone()[0]  # noqa: E731
    by_source = {r["source"]: r["n"] for r in conn.execute(
        "SELECT source, count(*) AS n FROM renders GROUP BY source")}
    by_status = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, count(*) AS n FROM parts GROUP BY status")}
    return {
        "parts": one("SELECT count(*) FROM parts"),
        "measured": one("SELECT count(DISTINCT part_id) FROM measurements"),
        "renders": by_source,
        "statuses": by_status,
        "defects": one("SELECT count(*) FROM defects"),
        "runs": one("SELECT count(*) FROM runs"),
    }
