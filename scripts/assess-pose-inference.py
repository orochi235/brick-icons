"""Would a decoration-facing rule pick the turn LDraw already declares?

394 parts carry a `!PREVIEW` matrix, which is the library saying its default
view shows the wrong side. That is a free oracle: any rule we invent for the
parts that declare nothing has to reproduce the library's answer on the parts
that do. This scores every quarter-turn of the cube by how squarely it puts a
part's decoration toward the iso camera, takes the best, and reports how often
that equals the declaration.

Run it over the undeclared printed parts too (`--undeclared`) to count how many
renders such a rule would change.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brick_icons import hlr  # noqa: E402


def cube_rotations() -> list[tuple[str, np.ndarray]]:
    """The 24 proper rotations of the cube, as signed permutation matrices.

    Mike's rule is quarter turns only, and this is exactly that set: every
    axis-aligned orientation reachable without tilting the part off the grid.
    """
    out = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            m = np.zeros((3, 3))
            for row, col in enumerate(perm):
                m[row, col] = signs[row]
            if round(np.linalg.det(m)) == 1:
                out.append((matrix_key(m), m))
    return out


def matrix_key(m: np.ndarray) -> str:
    return " ".join(f"{int(round(v)):d}" for v in np.asarray(m).ravel())


def declared_matrix(preview: str) -> np.ndarray | None:
    """The 3x3 out of a `!PREVIEW` line: colour, x y z, then the matrix."""
    f = preview.split()
    if len(f) < 13:
        return None
    try:
        vals = [float(x) for x in f[4:13]]
    except ValueError:
        return None
    return np.array(vals).reshape(3, 3)


def decoration_normal(tris, tri_colors) -> tuple[np.ndarray, float] | None:
    """Area-weighted normal of everything the part declares as decoration.

    Colour 16 is "inherit", which is the body. Anything else on a printed part
    is the print -- the same signal `unwrap.bind_groups` binds on, and the only
    one that survives the library's defects, since it is declared rather than
    inferred from shape.
    """
    acc = np.zeros(3)
    area = 0.0
    for tri, code in zip(np.asarray(tris, float), tri_colors):
        if code == 16:
            continue
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        mag = np.linalg.norm(n)
        if mag <= 0:
            continue
        acc += n            # already area-weighted: |cross| is twice the area
        area += mag / 2
    if area <= 0 or np.linalg.norm(acc) <= 0:
        return None
    return acc / np.linalg.norm(acc), area


IDENTITY = "1 0 0 0 1 0 0 0 1"


def turn_size(m: np.ndarray) -> float:
    """Rotation angle in degrees, so "the smallest turn that works" can be
    asked for. trace = 1 + 2cos(theta) for a proper rotation."""
    c = (float(np.trace(m)) - 1.0) / 2.0
    return float(np.degrees(np.arccos(max(-1.0, min(1.0, c)))))


def keeps_vertical(m: np.ndarray) -> bool:
    """Does this turn leave the part's vertical axis vertical?

    LDraw Y is the gravity axis. A turn that sends Y to X or Z stands the part
    on its edge, which the library almost never does -- 388 of its 394
    declarations map Y to plus or minus Y.
    """
    return abs(abs(float((m @ np.array([0.0, 1.0, 0.0]))[1])) - 1.0) < 1e-9


def best_turn(n: np.ndarray, rotations, toward: np.ndarray, rule: str):
    """The turn a given rule would pick, as (facing, key).

    Every rule scores `facing` the same way -- the dot of the turned
    decoration normal with the direction back to the camera, so +1 is square
    on and -1 is facing away. They differ only in which turns they will
    consider and how they break a tie. Identity sorts first throughout, so a
    tie always leaves the part alone.
    """
    if rule == "upright":
        rotations = [(k, m) for k, m in rotations if keeps_vertical(m)]
    scored = [(float(np.dot(m @ n, toward)), key, m) for key, m in rotations]
    if rule == "min-turn":
        # Leave anything already facing the camera; otherwise take the
        # smallest turn that gets it there, not the squarest.
        here = next(s for s in scored if s[1] == IDENTITY)
        if here[0] >= 0:
            return here[0], IDENTITY
        works = [s for s in scored if s[0] > 0]
        if not works:
            return here[0], IDENTITY
        best = min(works, key=lambda s: (turn_size(s[2]), -s[0]))
        return best[0], best[1]
    best = max(scored, key=lambda s: s[0])
    return best[0], best[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="corpus.db")
    ap.add_argument("--ldraw", default="vendor/ldraw")
    ap.add_argument("--undeclared", action="store_true",
                    help="score the printed parts that declare nothing")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sample", type=int, default=0,
                    help="score a random sample of this many, for a count "
                         "with an interval rather than an exact one")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--rule", default="max-facing",
                    choices=["max-facing", "upright", "min-turn"],
                    help="max-facing: squarest of all 24 quarter turns. "
                         "upright: squarest of the 8 that keep the part's "
                         "vertical axis vertical. min-turn: leave anything "
                         "already facing the camera, else the smallest turn "
                         "that brings it round.")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    if args.undeclared:
        sql = ("SELECT id, preview FROM parts WHERE preview IS NULL "
               "AND printed = 1 AND obsolete = 0 ORDER BY id")
    else:
        sql = "SELECT id, preview FROM parts WHERE preview IS NOT NULL ORDER BY id"
    rows = conn.execute(sql).fetchall()
    if args.sample and args.sample < len(rows):
        import random
        total = len(rows)
        rows = random.Random(args.seed).sample(list(rows), args.sample)
        rows.sort(key=lambda r: r["id"])
        print(f"sampling {len(rows)} of {total}", flush=True)
    if args.limit:
        rows = rows[:args.limit]

    rotations = cube_rotations()
    # Identity first so `max` keeps it on a tie: no turn beats an equal turn.
    rotations.sort(key=lambda kv: kv[0] != IDENTITY)
    _, _, fwd = hlr.view_basis(30.0, 45.0)
    toward = -np.asarray(fwd, float)

    results = []
    agree = disagree = nodecor = failed = 0
    t0 = time.time()
    for i, row in enumerate(rows, 1):
        pid = row["id"]
        try:
            tris, colors, _ = hlr.part_geometry(pid, args.ldraw)
        except Exception as e:
            failed += 1
            print(f"{i}/{len(rows)}  {pid}  failed: {type(e).__name__}: {e}",
                  flush=True)
            continue
        got = decoration_normal(tris, colors) if len(tris) else None
        if got is None:
            nodecor += 1
            results.append({"id": pid, "verdict": "no-decoration"})
            print(f"{i}/{len(rows)}  {pid}  no decoration", flush=True)
            continue
        n, area = got
        score, key = best_turn(n, rotations, toward, args.rule)
        rec = {"id": pid, "picked": key, "score": round(score, 4),
               "decor_area": round(area, 2)}
        if row["preview"]:
            want = declared_matrix(row["preview"])
            want_key = matrix_key(want) if want is not None else None
            rec["declared"] = want_key
            hit = want_key == key
            rec["verdict"] = "agree" if hit else "disagree"
            agree += hit
            disagree += not hit
            mark = "agree   " if hit else "DISAGREE"
            print(f"{i}/{len(rows)}  {pid}  {mark}  picked [{key}]  "
                  f"declared [{want_key}]  facing {score:+.3f}", flush=True)
        else:
            rec["verdict"] = "turn" if key != IDENTITY else "leave"
            print(f"{i}/{len(rows)}  {pid}  {rec['verdict']:6s}  [{key}]  "
                  f"facing {score:+.3f}", flush=True)
        results.append(rec)

    turned = sum(1 for r in results if r.get("verdict") == "turn")
    left = sum(1 for r in results if r.get("verdict") == "leave")
    print(f"\n{len(rows)} parts, rule {args.rule}, in {time.time() - t0:.1f}s")
    if args.undeclared:
        print(f"  would turn      {turned}")
        print(f"  would leave     {left}")
    else:
        seen = agree + disagree
        rate = f"{agree / seen:.1%}" if seen else "n/a"
        print(f"  agrees with LDraw   {agree}/{seen}  ({rate})")
        print(f"  disagrees           {disagree}")
    print(f"  no decoration found {nodecor}")
    print(f"  failed              {failed}")

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=1))
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
