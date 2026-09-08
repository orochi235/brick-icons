#!/usr/bin/env python3
"""Derive how every part is built, and ask which parts share a trait.

    .venv/bin/python scripts/part-features.py --build
    .venv/bin/python scripts/part-features.py --have off-axis --have torus
    .venv/bin/python scripts/part-features.py --defects

`--build` replaces `part_features` from the library; a full rebuild
(`build-corpus-db.py`) does the same thing on its way past, so this is for
when the extractor changed and nothing else did.

The other two forms are the reason the table exists. `--have` names a cohort
-- every part built the way some defect's part is built -- which is the
re-render list for a fix, found without anyone looking at a drawing:
`--have 'skew-deg>=5'` is the population that `3820-c-grip-fills-solid` came
out of.
`--defects` crosses the symptom classes against the traits and prints where a
class concentrates, which is a lead, not a finding: 9 hidden-leak rows are too
few for a share to mean much on its own.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db, features  # noqa: E402
from brick_icons.config import load_config  # noqa: E402


def build(conn) -> int:
    return db.seed_part_features(conn, load_config().ldraw_dir,
                                 progress=lambda m: print(m, flush=True))


def prevalence(conn) -> None:
    total = conn.execute("SELECT count(*) FROM parts").fetchone()[0]
    rows = conn.execute(
        "SELECT feature, count(*) n, avg(value) mean, max(value) most "
        "FROM part_features GROUP BY feature ORDER BY n DESC").fetchall()
    print(f"{'feature':<14} {'parts':>6} {'share':>7}  {'mean':>9} {'max':>8}")
    for r in rows:
        share = f"{100.0 * r['n'] / total:5.1f}%" if total else "    -"
        mean = f"{r['mean']:9.1f}" if r["mean"] is not None else "        -"
        most = f"{r['most']:8.0f}" if r["most"] is not None else "       -"
        print(f"{r['feature']:<14} {r['n']:6d}  {share}  {mean} {most}")


#: `skew-deg>=5` and friends. A flag is present or not, so it needs no
#: comparison; a measure is on every part and selects nothing without one.
_TEST = re.compile(r"^(?P<name>[a-z-]+)"
                   r"(?:(?P<op>>=|<=|>|<|=)(?P<value>-?[\d.]+))?$")


def parse_test(text: str) -> tuple[str, str, float | None]:
    m = _TEST.match(text)
    if not m:
        raise ValueError(f"cannot read {text!r} as a feature test")
    op = m["op"] or ""
    return m["name"], ("==" if op == "=" else op), (
        float(m["value"]) if m["value"] is not None else None)


def cohort(conn, have: list[str], limit: int) -> None:
    clauses, params = [], []
    for text in have:
        name, op, value = parse_test(text)
        if value is None:
            clauses.append("feature = ?")
            params.append(name)
        else:
            sql_op = "=" if op == "==" else op
            clauses.append(f"(feature = ? AND value {sql_op} ?)")
            params += [name, value]
    rows = conn.execute(
        "SELECT part_id FROM part_features "
        f"WHERE {' OR '.join(clauses)} "
        "GROUP BY part_id HAVING count(DISTINCT feature) = ? "
        "ORDER BY part_id", (*params, len(have))).fetchall()
    ids = [r["part_id"] for r in rows]
    print(f"{len(ids)} parts have all of {', '.join(have)}")
    for pid in ids[:limit]:
        print(pid)
    if len(ids) > limit:
        print(f"... {len(ids) - limit} more (--limit to see them)")


def by_class(conn) -> None:
    """Which traits the parts under each symptom class share, against the
    trait's share of the whole library. Printed as a lift, because a trait on
    90% of parts is on the defect's parts too and means nothing."""
    total = conn.execute("SELECT count(*) FROM parts").fetchone()[0]
    base = {r["feature"]: r["n"] / total for r in conn.execute(
        "SELECT feature, count(*) n FROM part_features GROUP BY feature")}
    parts_of: dict[str, set[str]] = defaultdict(set)
    for row in conn.execute("SELECT part_id, classes FROM defects "
                            "WHERE classes IS NOT NULL"):
        for name in json.loads(row["classes"]):
            parts_of[name].add(row["part_id"])
    for name in sorted(parts_of, key=lambda k: -len(parts_of[k])):
        ids = sorted(parts_of[name])
        held = Counter()
        for pid in ids:
            for r in conn.execute(
                    "SELECT feature FROM part_features WHERE part_id=? "
                    "AND value IS NULL", (pid,)):
                held[r["feature"]] += 1
        print(f"\n{name}  ({len(ids)} parts: {', '.join(ids)})")
        ranked = sorted(held.items(),
                        key=lambda kv: -(kv[1] / len(ids)) / max(base.get(kv[0], 1e-9), 1e-9))
        for feature, n in ranked[:6]:
            share = n / len(ids)
            lift = share / base[feature] if base.get(feature) else 0.0
            print(f"    {feature:<14} {n:2d}/{len(ids):<2d} {100 * share:5.1f}%"
                  f"  vs {100 * base[feature]:5.1f}% library"
                  f"  x{lift:5.2f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--build", action="store_true",
                    help="re-derive part_features from the library")
    ap.add_argument("--have", action="append", default=[], metavar="TEST",
                    help="a flag name, or a measure and a threshold such as "
                         "'skew-deg>=5'; repeatable, ANDed")
    ap.add_argument("--defects", action="store_true",
                    help="cross the defect classes against the features")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()

    conn = db.connect(args.db)
    if args.build:
        print(f"{build(conn)} feature rows")
    if args.have:
        unknown = [f for f in args.have
                   if parse_test(f)[0] not in features.FLAGS
                   and parse_test(f)[0] not in features.MEASURES]
        if unknown:
            ap.error(f"no such feature {unknown}; have "
                     f"{list(features.FLAGS) + list(features.MEASURES)}")
        cohort(conn, args.have, args.limit)
    elif args.defects:
        by_class(conn)
    elif not args.build:
        prevalence(conn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
