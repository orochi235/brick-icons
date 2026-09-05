# Render store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill `renders/<source>/<part>.svg` — the tracked store of one canonical render per part per source — and index each one in `corpus.db`.

**Architecture:** A batch job with the same shape as the census: detached, resumable, one progress line per part, and hardened against a part that segfaults the process. That hardening exists once already inside `scripts/compare-silhouette-truth.py`; a second consumer is what justifies lifting it into `brick_icons/batch.py` rather than copying it.

**Tech Stack:** Python 3.14. Renders go through `brick_icons.lab.runner.render`, which is the CLI's own path and writes into the argv-keyed cache — so a part already rendered at that config costs nothing to store.

Spec: `docs/superpowers/specs/2026-09-04-corpus-database-design.md`. Part 1 (`brick_icons/db.py`) is built; this is part 2 of its build order.

---

## Why this cannot reuse the census's renders

The census keeps flagged renders under `out/census/renders`, and they are the
wrong drawing: the oracle renders with `--line-width 0 --silhouette-width 0` so
that fills carry the silhouette and no stroke overhang has to be subtracted.
The store's render is the ordinary stroked drawing `db.canonical_argv` names.
This was tried and backed out in `5cbcd4e`; do not try it again.

## File structure

- **Create `brick_icons/batch.py`** — the guard a long unattended run needs: a
  per-part wall-clock cap, an inflight marker so a native crash costs one part
  rather than the run, and a resume that skips what is done. Lifted verbatim
  from `scripts/compare-silhouette-truth.py`, which then imports it.
- **Create `scripts/build-render-store.py`** — the job.
- **Create `tests/test_batch.py`** — the guard's tests.
- **Modify `scripts/compare-silhouette-truth.py`** — import the guard instead of defining it.

---

### Task 1: Lift the batch guard into its own module

**Files:**
- Create: `brick_icons/batch.py`
- Test: `tests/test_batch.py`

The three pieces to move, unchanged in behavior: `_on_alarm`/`_ARMED` and
`run_guarded`, the `<jsonl>.inflight` marker read and write, and the
`--skip-done` filter.

- [ ] **Step 1: Write the failing test**

```python
import json

import pytest

from brick_icons import batch


def test_a_timeout_is_a_row_not_the_end_of_the_run(tmp_path):
    log = tmp_path / "out.jsonl"
    runner = batch.Runner(log, timeout=0.2)
    done = []
    for item in ("a", "b", "c"):
        done.append(runner.run(item, lambda i: _spin() if i == "b" else {"item": i}))
    assert [d.get("item") for d in done] == ["a", None, "c"]
    assert done[1]["error"] == "TimeoutError"


def _spin():
    while True:
        pass


def test_resume_skips_what_is_done_and_buries_what_crashed(tmp_path):
    log = tmp_path / "out.jsonl"
    log.write_text(json.dumps({"item": "a"}) + "\n")
    (tmp_path / "out.jsonl.inflight").write_text("b")
    runner = batch.Runner(log, timeout=0)
    assert runner.remaining(["a", "b", "c"]) == ["c"]
    rows = [json.loads(l) for l in log.read_text().splitlines()]
    assert rows[-1] == {"item": "b", "error": "ProcessDied",
                        "detail": "killed mid-render; not retried"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_batch.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'brick_icons.batch'`

- [ ] **Step 3: Write the implementation**

```python
"""What a long unattended batch needs to survive itself.

A part that raises is a row and the run continues; a part that segfaults the
interpreter is named in a marker file and buried on the way back in, so a
resume cannot loop on it forever.
"""
from __future__ import annotations

import json
import signal
import time
import traceback
from pathlib import Path

_ARMED = None


def _on_alarm(signum, frame):
    """Installed once and never removed: SIGALRM's default action is to KILL,
    so a timer that expires in the microseconds before the itimer is disarmed
    takes the whole run down silently."""
    if _ARMED:
        raise TimeoutError(f"exceeded {_ARMED}s")


class Runner:
    """One append-only JSONL log, one item at a time.

    `key` names the field an item is recorded under, so a caller whose rows are
    keyed by something other than `item` can say so.
    """

    def __init__(self, log: Path | str, timeout: float = 0, key: str = "item"):
        self.log = Path(log)
        self.inflight = Path(f"{self.log}.inflight")
        self.timeout = timeout
        self.key = key
        if timeout:
            signal.signal(signal.SIGALRM, _on_alarm)

    def remaining(self, items: list[str]) -> list[str]:
        """`items` minus what the log already holds, with a crashed item
        recorded and dropped."""
        if self.inflight.exists():
            crashed = self.inflight.read_text().strip()
            if crashed:
                self.write({self.key: crashed, "error": "ProcessDied",
                            "detail": "killed mid-render; not retried"})
            self.inflight.unlink()
        if not self.log.exists():
            return list(items)
        done = {json.loads(line)[self.key]
                for line in self.log.read_text().splitlines() if line.strip()}
        return [i for i in items if i not in done]

    def write(self, row: dict) -> None:
        with self.log.open("a") as fh:
            fh.write(json.dumps(row) + "\n")

    def run(self, item: str, work) -> dict:
        """`work(item)` under the cap. Its dict is returned and logged; a
        failure becomes a row naming the exception."""
        global _ARMED
        self.inflight.write_text(item)
        started = time.time()
        try:
            if self.timeout:
                _ARMED = self.timeout
                signal.setitimer(signal.ITIMER_REAL, self.timeout)
            row = work(item)
        except BaseException as exc:
            row = {self.key: item, "error": type(exc).__name__,
                   "detail": str(exc)[:300],
                   "traceback": traceback.format_exc()[-1200:]}
        finally:
            if self.timeout:
                signal.setitimer(signal.ITIMER_REAL, 0)
                _ARMED = None
        row["secs"] = round(time.time() - started, 1)
        self.write(row)
        self.inflight.unlink(missing_ok=True)
        return row
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_batch.py -q`
Expected: PASS, 2 passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/batch.py tests/test_batch.py
git commit -m "lift the batch guard out of the census script"
```

---

### Task 2: Point the census at the shared guard

**Files:**
- Modify: `scripts/compare-silhouette-truth.py`

Its rows are keyed `part`, not `item`, so it constructs `Runner(..., key="part")`.
Delete `_ARMED`, `_on_alarm`, `run_guarded` and the inflight and `--skip-done`
handling from the script; keep every flag it already offers.

- [ ] **Step 1: Rewrite the loop against `Runner`**

```python
from brick_icons.batch import Runner

    runner = Runner(args.jsonl, timeout=args.timeout, key="part") if args.jsonl else None
    ids = runner.remaining(ids) if (runner and args.skip_done) else ids
    for n, pid in enumerate(ids, 1):
        r = runner.run(pid, lambda p: one(p, args, tmp)) if runner \
            else one(pid, args, tmp)
        ...
```

- [ ] **Step 2: Prove the behavior did not move**

Run: `.venv/bin/python scripts/compare-silhouette-truth.py 3004 --timeout 1 --jsonl /tmp/guard.jsonl`
Expected: one `FAILED TimeoutError` line, exit 0, and `/tmp/guard.jsonl.inflight` gone afterwards.

Then run it again with `--skip-done` and expect `resuming: 1 done, 0 left`.

- [ ] **Step 3: Commit**

```bash
git add scripts/compare-silhouette-truth.py
git commit -m "run the census through the shared batch guard"
```

---

### Task 3: Store one render

**Files:**
- Modify: `brick_icons/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

```python
def test_storing_a_render_puts_it_under_source_and_part(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "corpus.db")
    made = tmp_path / "work" / "3001.svg"
    made.parent.mkdir()
    made.write_text(SVG)

    path = db.store_render(conn, "3001", "naive", made, root=tmp_path)
    assert path == tmp_path / "renders" / "naive" / "3001.svg"
    assert path.read_text() == SVG
    row = conn.execute("SELECT path, sha256 FROM renders").fetchone()
    assert row["path"] == "renders/naive/3001.svg"
    assert row["sha256"] == goldens.sha256(SVG)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: FAIL — `AttributeError: module 'brick_icons.db' has no attribute 'store_render'`

- [ ] **Step 3: Write the implementation**

```python
def store_render(conn: sqlite3.Connection, part_id: str, source: str,
                 made: Path | str, root: Path | str = ".",
                 run_id: int | None = None) -> Path:
    """Copy a freshly rendered SVG into the store and index it."""
    dest = Path(root) / "renders" / source / f"{part_id}.svg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(Path(made).read_text())
    record_render(conn, part_id, source, dest, root=root, run_id=run_id)
    return dest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brick_icons/db.py tests/test_db.py
git commit -m "copy a render into the store and index it"
```

---

### Task 4: The job

**Files:**
- Create: `scripts/build-render-store.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Render every part in a list into the tracked store, one canonical drawing
per source.

    .venv/bin/python scripts/build-render-store.py --list out/census/parts.txt \
        --sources naive,occt --timeout 180 --log out/store/naive.jsonl

Detach it: a foreground call dies at its caller's timeout no matter what the
process is doing. Resumable -- a part already in the log is skipped, and one
that segfaults the interpreter is buried rather than retried forever, which
occt makes necessary (92738, u9236c03, 76110p01 and u9105p01c04 all crash it).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402
from brick_icons.batch import Runner  # noqa: E402
from brick_icons.lab import runner as lab_runner  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--list")
    ap.add_argument("--sources", default="naive,occt")
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--log", default=str(ROOT / "out" / "store" / "store.jsonl"))
    ap.add_argument("--force", action="store_true",
                    help="re-render a part already in the store")
    args = ap.parse_args()

    ids = list(args.parts)
    if args.list:
        ids += [s for line in Path(args.list).read_text().splitlines()
                if (s := line.split("#")[0].strip())]
    if not ids:
        ap.error("name at least one part, or pass --list")

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    Path(args.log).parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(ROOT / db.DEFAULT_PATH)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    run_id = db.start_run(conn, "render", {"sources": sources}, sha or "unknown")

    for source in sources:
        batch = Runner(f"{args.log}.{source}", timeout=args.timeout, key="part")
        todo = batch.remaining(ids)
        print(f"{source}: {len(todo)} of {len(ids)} to render", flush=True)

        def work(part: str, source=source) -> dict:
            dest = ROOT / "renders" / source / f"{part}.svg"
            if dest.exists() and not args.force:
                return {"part": part, "source": source, "cached": True}
            result = lab_runner.render(db.canonical_argv(part, source),
                                       root=ROOT / "out" / "lab")
            if not result["ok"]:
                raise RuntimeError(result["error"])
            made = next((ROOT / "out" / "lab" / result["key"]).glob("*.svg"))
            db.store_render(conn, part, source, made, root=ROOT, run_id=run_id)
            return {"part": part, "source": source, "cached": result["cached"]}

        for n, part in enumerate(todo, 1):
            row = batch.run(part, work)
            state = row.get("error") or ("cached" if row.get("cached") else "stored")
            print(f"{n}/{len(todo)} {source} {part}: {state} [{row['secs']}s]",
                  flush=True)

    db.finish_run(conn, run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Prove it on three parts**

Run: `.venv/bin/python scripts/build-render-store.py 3001 3004 3005 --sources naive --timeout 180 --log /tmp/store.jsonl`
Expected: three `stored` lines, and `renders/naive/{3001,3004,3005}.svg` on disk.

Re-run the same command and expect three `cached` lines with the store
untouched, then confirm the index:

```bash
.venv/bin/python -c "
from brick_icons import db
c = db.connect('corpus.db')
print(c.execute('SELECT count(*) FROM renders').fetchone()[0], 'renders indexed')"
```

- [ ] **Step 3: Commit the script and its first renders**

```bash
git add scripts/build-render-store.py renders
git commit -m "render a part list into the tracked store"
```

---

### Task 5: Fill the store for real

- [ ] **Step 1: Wait for the census, or stop it**

Both jobs render, and eight shards already have the box. Check with
`pgrep -f compare-silhouette | wc -l` and either wait or `pkill -f
compare-silhouette`.

- [ ] **Step 2: Start it detached, naive first**

```bash
nohup .venv/bin/python scripts/build-render-store.py --list out/census/parts.txt \
  --sources naive --timeout 180 --log out/store/run.jsonl > out/store/naive.log 2>&1 &
```

Naive first because occt segfaults on at least four parts and its coverage is
the one the census is already behind on.

- [ ] **Step 3: Commit the store in batches, not at the end**

A commit per few thousand renders keeps any one commit reviewable and means a
crash costs a batch rather than a night.

```bash
git add renders && git commit -m "store the naive renders for <range>"
```
