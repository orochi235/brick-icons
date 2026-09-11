#!/usr/bin/env python3
"""Fold a live render tree into corpus.db as its results land.

    .venv/bin/python scripts/ingest-watch.py out/slot-occt out/slot-occt-r2

A fleet job delivers for hours, and until something reads what came back the
wall and every coverage number describe the corpus as it was before the job
started. `census-ingest.sh` closes that by REBUILDING: it drops and reseeds
every table from every tree, so each pass costs the whole corpus and replaces
whatever another session ingested by hand. This one appends. Per pass it takes
only the parts it has not already recorded, so the cost is the new parts.

What it makes is what a later rebuild would make of the same tree, which is
the point -- drawings are indexed WHERE THEY LIE, under the slot the tree's
SOURCE marker names, and the scores go through `import_census_jsonl`, the one
writer of `measurements`. So a rebuild after this is a no-op rather than a
correction.

Give it the trees a job is writing to, not `out/`: a finished tree has nothing
to add and rescanning it is the only cost this script has.

A REFRESH needs `--overwrite`. Every part a re-render draws already holds a row
in its slot, and the default pass skips exactly those -- it would report
success and index nothing, which is how the pose re-render was lost.

`--until <task>` ties this to the job it is ingesting: while onto still lists
that task the watch keeps going, and once it does not, one `onto fetch
--stream` and a last pass close the round. A node onto cannot reach is not an
answer -- a task on it is invisible rather than finished -- so the watch stays
up.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402
from brick_icons.lab import tally  # noqa: E402


def _engine(tree: Path, source: str) -> str:
    """The engine that drew this tree, from a row it wrote.

    Read rather than parsed off the slot name: `decal` and `ldview` name no
    engine, and a slot that gains a facet word would silently parse wrong.
    """
    for log in sorted(tree.glob("*.jsonl")):
        for line in log.read_text().splitlines():
            if line.strip():
                return json.loads(line)["engine"]
    return source.rsplit("-", 1)[-1]


def _sha() -> str:
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                       capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


def _watch_run(conn: sqlite3.Connection, tree: Path) -> int:
    """This tree's watch run, reused across passes and across restarts.

    A run per pass would file one `measurements` row per part per pass -- and
    every reader taking the newest run per part and engine would still be
    right, after reading seventy copies to get there. Keyed the way
    `db.store_run` keys its own, and flagged so a rebuild's run for the same
    tree stays a separate row rather than being reused for different work.
    """
    row = conn.execute(
        "SELECT id FROM runs WHERE kind = 'census' "
        "AND json_extract(args, '$.dir') = ? "
        "AND json_extract(args, '$.watch') = 1 ORDER BY id LIMIT 1",
        (str(tree),)).fetchone()
    if row is not None:
        return row[0]
    return db.start_run(conn, "census", {"dir": str(tree), "watch": True},
                        _sha())


def _take_scores(conn: sqlite3.Connection, tree: Path, run_id: int,
                 seen: dict[Path, tuple[int, float]]) -> int:
    """Import every JSONL whose size or mtime moved since the last pass.

    `import_census_jsonl` re-reads a whole file, and a batch appends to its
    own log until the batch ends -- so a log is re-read while it grows and
    left alone once it stops. INSERT OR REPLACE makes the re-reads free of
    consequence.
    """
    took = 0
    for log in sorted(tree.glob("*.jsonl")):
        try:
            st = log.stat()
        except OSError:
            continue
        key = (st.st_size, st.st_mtime)
        if seen.get(log) == key:
            continue
        try:
            took += db.import_census_jsonl(conn, run_id, log, census_dir=tree)
        except (ValueError, KeyError) as e:  # a line half-written this second
            print(f"  {log.name}: {type(e).__name__} {e}", flush=True)
            continue
        seen[log] = key
    return took


def _take_renders(conn: sqlite3.Connection, tree: Path, engine: str,
                  source: str, run_id: int, overwrite: bool = False,
                  seen: dict[Path, tuple[int, float]] | None = None
                  ) -> tuple[int, int]:
    """Index the drawings this tree holds, as (new, replaced).

    The job is still writing, so a half-written SVG is expected traffic:
    `record_render` parses it, raises, and the next pass takes it whole.

    Under `--overwrite` a part already in the slot is redrawn rather than
    skipped -- `record_render` replaces on (part, source, config_key), and the
    bake keys on the render's sha, so only the sheets that actually moved are
    redrawn. The size/mtime map is what keeps that from rewriting every row
    every pass.
    """
    kept = tree / "renders" / engine
    if not kept.is_dir():
        return 0, 0
    if seen is None:
        seen = {}
    known = {r[0] for r in conn.execute("SELECT id FROM parts")}
    have = {r[0] for r in conn.execute(
        "SELECT part_id FROM renders WHERE source = ?", (source,))}
    took = redrew = 0
    for svg in sorted(kept.glob("*.svg")):
        pid = svg.stem
        if pid not in known or (pid in have and not overwrite):
            continue
        try:
            st = svg.stat()
        except OSError:
            continue
        if seen.get(svg) == (st.st_size, st.st_mtime):
            continue
        try:
            db.record_render(conn, pid, source, svg, root=ROOT, run_id=run_id)
        except Exception as e:  # noqa: BLE001
            print(f"  {pid}: {type(e).__name__} {e}", flush=True)
            continue
        seen[svg] = (st.st_size, st.st_mtime)
        if pid in have:
            redrew += 1
        else:
            took += 1
    if took or redrew:
        conn.commit()
    return took, redrew


def _tasks_running(tasks: Sequence[str]) -> bool | None:
    """Whether onto still lists any of these tasks. None means it could not say.

    A node onto cannot reach carries jobs it cannot report, so an unreachable
    fleet reads as unknown rather than as finished -- msb-uai's agent died once
    under a live job, and a watch that took silence for completion would have
    closed the round mid-render.
    """
    r = subprocess.run(["onto", "jobs", "--json"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        got = json.loads(r.stdout)
    except ValueError:
        return None
    if got.get("unreachable"):
        return None
    wanted = set(tasks)
    return any(j.get("task") in wanted for j in got.get("jobs", ()))


def _fetch(task: str) -> bool:
    """One quiet pass for what `--to` did not deliver.

    A job exiting 0 does not mean its drawings are home: four slot fills left
    32, 30, 28 and 1,240 files on their nodes. `--stream` returns once the job
    writing the tree has ended, which by here it has.
    """
    log = ROOT / "out" / f"fetch-{task}.log"
    with log.open("w") as fh:
        r = subprocess.run(["onto", "fetch", "--stream", task],
                           stdout=fh, stderr=subprocess.STDOUT, cwd=ROOT)
    return r.returncode == 0


def _bake(source: str) -> bool:
    """Re-bake the slot's sheets. Idempotent by render sha, so this costs the
    new parts -- but it is the step that puts them on the wall, and skipping
    it leaves a database that is current and a wall that is not."""
    log = ROOT / "out" / f"bake-{source}.log"
    with log.open("w") as fh:
        r = subprocess.run([str(ROOT / ".venv/bin/python"),
                            str(ROOT / "scripts/bake-thumbs.py"),
                            "--source", source],
                           stdout=fh, stderr=subprocess.STDOUT, cwd=ROOT)
    return r.returncode == 0


def watch(trees: list[Path], every: int, once: bool, bake: bool,
          overwrite: bool = False, until: Sequence[str] = (),
          fetch: bool = True) -> int:
    seen: dict[Path, tuple[int, float]] = {}
    drawings: dict[Path, tuple[int, float]] = {}
    closing = False
    # A bake or a fetch that fails stays failed; the per-icon parse error in
    # _take_renders does not, because a half-written SVG is taken whole on the
    # next pass. Counting those would report failures that fix themselves.
    failed = 0
    while True:
        # Two trees can fill one slot -- a job per node, or a round each --
        # and the bake is per slot, so it happens once a pass however many
        # trees fed it.
        touched: set[str] = set()
        for tree in trees:
            if not tree.is_dir():
                print(f"{time.strftime('%H:%M:%S')} {tree}: not there yet",
                      flush=True)
                continue
            source = db.census_source(tree, "")
            conn = db.connect()
            try:
                engine = _engine(tree, source)
                run_id = _watch_run(conn, tree)
                scores = _take_scores(conn, tree, run_id, seen)
                drawn, redrew = _take_renders(conn, tree, engine, source,
                                              run_id, overwrite, drawings)
                total = conn.execute(
                    "SELECT count(*) FROM renders WHERE source = ?",
                    (source,)).fetchone()[0]
            finally:
                conn.close()
            if drawn or redrew:
                touched.add(source)
            print(f"{time.strftime('%H:%M:%S')} {tree.name} -> {source}: "
                  f"+{drawn} drawn, {redrew} redrawn, +{scores} scored, "
                  f"{total} in the slot", flush=True)
            # onto has no total for a watcher, so it draws these as figures.
            # Cumulative, because it re-reads a window of the log.
            print(f"onto: count {total} in {source}", flush=True)
            print(f"onto: count {failed} failed", flush=True)
        # One tally per PASS, not per tree: a tally is a statement about the
        # whole corpus at a moment, and taking one between two trees would
        # record a step that never existed.
        conn = db.connect()
        try:
            moved = tally.take(conn)
        finally:
            conn.close()
        if moved:
            print(f"{time.strftime('%H:%M:%S')} tallied {moved} slot(s)",
                  flush=True)

        for source in sorted(touched) if bake else ():
            ok = _bake(source)
            failed += 0 if ok else 1
            print(f"{time.strftime('%H:%M:%S')} baked {source}"
                  f"{'' if ok else '  BAKE FAILED'}", flush=True)
        if once or closing:
            return 0
        if until:
            # The pass that follows the job's end is the one that sees a tree
            # nobody is writing to, so the watch closes on the pass AFTER it
            # stops, not on the reading that says so.
            running = _tasks_running(until)
            if running is False:
                closing = True
                for task in until if fetch else ():
                    ok = _fetch(task)
                    failed += 0 if ok else 1
                    print(f"{time.strftime('%H:%M:%S')} fetched {task}"
                          f"{'' if ok else '  FETCH FAILED'}", flush=True)
                print(f"{time.strftime('%H:%M:%S')} "
                      f"{', '.join(until)} stopped; one last pass", flush=True)
                continue
            if running is None:
                print(f"{time.strftime('%H:%M:%S')} onto could not say what is "
                      f"running; staying up", flush=True)
        time.sleep(every)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("trees", nargs="+", type=Path)
    ap.add_argument("--every", type=int, default=300,
                    help="seconds between passes (default 300)")
    ap.add_argument("--once", action="store_true", help="one pass, then stop")
    ap.add_argument("--no-bake", dest="bake", action="store_false",
                    help="index only; the wall stays a round behind")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace a part's row rather than skipping it, for a "
                         "re-render of a slot that already holds every part")
    ap.add_argument("--until", default="",
                    help="comma-separated onto task names; watch until none "
                         "of them is running, then fetch and close")
    ap.add_argument("--no-fetch", dest="fetch", action="store_false",
                    help="with --until, skip the closing onto fetch")
    a = ap.parse_args()
    until = [t for t in a.until.split(",") if t]
    return watch([Path(t) for t in a.trees], a.every, a.once, a.bake,
                 a.overwrite, until, a.fetch)


if __name__ == "__main__":
    raise SystemExit(main())
