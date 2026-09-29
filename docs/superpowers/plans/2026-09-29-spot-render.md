# Spot Rendering (brick-icons side) Implementation Plan

**Status: unbuilt, planned 2026-09-29.** It depends on two pieces built in
other repositories, both released since the spec was written: onto's service
jobs (onto build be0cf2f, guide at `site/src/content/docs/guides/services.mdx`
in the onto repo) and pezlie 0.3.0. No task is blocked on either; the adapter
for each is one module, tested against a stub.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The lab's **Redraw** button draws a part on a warm worker on the fleet
within seconds, then swaps the new drawing into the lightbox and the wall cell
without a reload. Nothing renders on this Mac, and the cost split and lazy
queue are gone.

**Architecture:** A worker module (`brick_icons.spot_worker`) runs under
`onto service up` on studio. It imports the engine once, then draws each
request through the CLI's own path, in a forked child of a two-process pool,
under the batch per-part cap. The lab calls it through one adapter
(`brick_icons/lab/spot.py`, which shells out to `onto call`), stores the reply
with `db.store_render`, writes an `attempts` row, bakes and patches the part's
sheet cells, and announces the change over server-sent events. Pages hearing
it reload the lightbox and ask pezlie's wall to poll. The wire shapes and the
framing live in `brick_icons/spot_protocol.py`.

**Tech Stack:** Python 3 (FastAPI, Pillow, pytest), `concurrent.futures`, onto
CLI, TypeScript/React (Vite, vitest), pezlie 0.3.0.

**Spec:** `docs/superpowers/specs/2026-09-29-spot-render-design.md`.

---

## Conventions for every task

- **Python tests run one file, locally.** In the main checkout:
  `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/<file> -q`. A linked
  worktree has no `.venv` of its own; point at the main checkout's interpreter
  and keep `PYTHONPATH=$PWD`, or the tests import the main tree's code
  (DEVELOPING.md, "A worktree imports the main tree").
- **Lab tests run the task's own files:** `cd lab && npx vitest run <paths>`,
  then `npm run typecheck` once at the end of the task.
- **Never run the full Python suite here.** It goes to the fleet in Task 25.
- **Before any commit touching `lab/`, use the `prepare-js-commit` skill.**
- Commit subjects are imperative and name the change. End every commit
  message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Run every `onto` command with the Bash sandbox disabled. Sandboxed, onto
  reports every node `offline`.

## File map

| file | change | responsibility |
|---|---|---|
| `brick_icons/__init__.py` | modify | `build_of(rev)`, `commit_of(rev)` beside `build()` |
| `brick_icons/db.py` | modify | one attempts writer, a run per spot redraw, `touch_render` |
| `brick_icons/batch.py` | modify | `Runner.call`: the capped, isolated call without a log |
| `brick_icons/lab/runner.py` | modify | `draw(argv, out_dir)`: the CLI's render path, raising |
| `brick_icons/lab/store.py` | modify | `drawing_in(names, source)`: which file a render kept |
| `brick_icons/spot_protocol.py` | create | request and reply shapes, and onto's line framing |
| `brick_icons/spot_worker.py` | create | the warm worker: `render`, `warm`, `serve`, `main` |
| `scripts/spot-worker.sh` | create | the service command: check the tree, `uv sync`, start the worker |
| `brick_icons/thumbs.py` | modify | lossless masters, a counter version, `patch_cell`, a lock |
| `brick_icons/lab/events.py` | create | an in-process broker and the SSE stream |
| `brick_icons/lab/spot.py` | create | the `onto call` adapter, and the worker's status |
| `brick_icons/lab/redraw.py` | create | one redraw, from the call to the event |
| `brick_icons/lab/app.py` | modify | the redraw, status, events and manifest routes |
| `brick_icons/requests.py` | modify | the request log as a record; the queue removed |
| `scripts/ingest-watch.py`, `scripts/run-slot.sh`, `scripts/refill-slot.sh` | modify | stop reading the queue |
| `scripts/render-requests.py` | delete | the queue's shell front end |
| `scripts/lab-agents.sh` | modify | onto on the agent's PATH; `stat` reports the worker |
| `lab/package.json` | modify | pezlie ^0.3.0 |
| `lab/src/api/types.ts`, `lab/src/api/client.ts` | modify | redraw states, `spotStatus`, `onChanged` |
| `lab/src/api/useChanged.ts` | create | `changed` events, batched per quarter second |
| `lab/src/corpus/Lightbox.tsx`, `Lightbox.css`, `types.ts` | modify | button states, the events listener, the queued note removed |
| `lab/src/wall/BrickWall.tsx` | modify | a batch of events makes the wall poll |
| `lab/src/corpus/useLooseThumbs.ts`, `useVectorThumbs.ts` | modify | caches keyed by pezlie's `imageKey` |
| `lab/src/corpus/useSheets.ts`, `CorpusWall.tsx` | modify | `/corpus` refetches its sheets after a redraw |
| `DEVELOPING.md` | modify | provisioning and the launch recipe |
| `tests/conftest.py` | modify | `stub_spot` fixture |

## The external contracts

**onto service jobs.** Everything the lab assumes about `onto call` is a
constant in `brick_icons/lab/spot.py`:

| onto says | the lab does |
|---|---|
| `onto call [--timeout <dur>] [--commit <sha>] <name> -` reads the request from stdin and prints the reply | sends the request on stdin; `--timeout` in seconds (`195s`) |
| exit 0 | reads the reply |
| exit 65, bad request | `failed`, error `BadRequest` |
| exit 69, down (40 ms, measured by onto) | `down`: "spot render is down" |
| exit 75, the process died mid-request | retries once, then `failed`, error `ProcessDied` |
| exit 78, the roll failed | `failed`, error `RollFailed`, onto's stderr as the detail |
| exit 124, no reply in time | `failed`, error `TimeoutError` |
| `--commit` takes a 7-40 hex sha on the tree's origin, never a ref | resolves `origin/main` to its full sha per call |
| a status ping must not roll | the ping is sent without `--commit` |

**The worker process** (framing, in `spot_protocol.read`/`write` only):
newline-delimited JSON. A request line is the caller's fields plus onto's
`"id"` (and `"commit"` when the call named one); the reply is one object per
line echoing the `"id"`. Requests arrive concurrently and may be answered out
of order. Non-JSON stdout and all stderr go to the job log. There is no ready
handshake: requests sent early wait in the pipe.

**A roll** is a forced reset of the tree to the commit: untracked files go,
ignored ones (`.venv`, `vendor/ldraw`) stay. Installing a changed dependency
is the process's job at startup, so the service command is
`scripts/spot-worker.sh`, which runs `uv sync` before starting the worker.

**pezlie 0.3.0.** Cell images are keyed on `item.sha` (`imageKey(item)` is
`id@sha`, and tile and SVG URLs carry `shaVersion(sha)`); brick-icons adds
nothing to its spec. `WallHeader.poll()` makes the wall ask the host's
`fetchItems(slot, since)` for changes now. When a poll moves a sha, the wall
refetches that cell's 128 px tile and SVG and draws its per-level tiles into
its in-memory sheets; it never refetches a sheet. Each poll that moves a sha
copies every sheet level once (the 32 px sheet about 110 MB transiently,
pezlie's estimate), so the lab polls once per batch of events, not per event.

---

### Task 1: Name the build of any revision

The lab tells the worker which commit to draw at: origin/main's, not the
lab's own checkout's. `build()` only knows HEAD, and onto's `--commit` needs a
full sha.

**Files:**
- Modify: `brick_icons/__init__.py` (the whole `build` function, lines 12-30)
- Test: `tests/test_db.py` (beside `test_the_build_names_a_revision_and_flags_an_uncommitted_engine`)

- [ ] **Step 1: Write the failing tests**

Add after `test_the_build_names_a_revision_and_flags_an_uncommitted_engine` in `tests/test_db.py`:

```python
def test_a_named_revision_has_the_build_form_without_a_dirty_mark():
    import brick_icons
    head = brick_icons.build()
    if head == "unknown":
        pytest.skip("no git here")
    assert brick_icons.build_of("HEAD") == head.rstrip("+")


def test_a_revision_git_cannot_find_is_unknown():
    import brick_icons
    assert brick_icons.build_of("no-such-rev-anywhere") == "unknown"
    assert brick_icons.commit_of("no-such-rev-anywhere") is None


def test_a_commit_is_named_in_full():
    import brick_icons
    sha = brick_icons.commit_of("HEAD")
    assert sha is None or re.fullmatch(r"[0-9a-f]{40}", sha), sha
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_db.py -q -k "named_revision or git_cannot or named_in_full"`
Expected: FAIL with `AttributeError: module 'brick_icons' has no attribute 'build_of'`

- [ ] **Step 3: Implement**

Replace lines 12-30 of `brick_icons/__init__.py` (the `@cache` decorator through the end of `build`) with:

```python
_ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str) -> str:
    return subprocess.run(("git", "-C", str(_ROOT)) + args, check=True,
                          capture_output=True, text=True).stdout.strip()


def build_of(rev: str) -> str:
    """`build()`'s `<count>.<short sha>` for any revision, or "unknown".

    Never suffixed `+`: only a working tree can be dirty, and this names a
    commit. The lab asks it of origin/main, the build it tells the spot worker
    to draw at.
    """
    try:
        return f"{_git('rev-list', '--count', rev)}.{_git('rev-parse', '--short', rev)}"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def commit_of(rev: str) -> str | None:
    """The full sha `rev` names, or None where git cannot say."""
    try:
        return _git("rev-parse", "--verify", f"{rev}^{{commit}}")
    except (OSError, subprocess.CalledProcessError):
        return None


@cache
def build() -> str:
    """The engine revision that drew something, as `<count>.<short sha>`.

    Derived from git rather than stored: a counter kept in a file conflicts
    on every branch and cannot be recomputed for a commit that already
    exists, while `rev-list --count` is exact for any revision after the
    fact. Suffixed `+` when the tree is dirty -- an uncommitted engine is
    not the commit it sits on.
    """
    made = build_of("HEAD")
    if made == "unknown":
        return made
    try:
        dirty = _git("status", "--porcelain", "--", "brick_icons")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return made + ("+" if dirty else "")
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_db.py -q -k "build or named_revision or git_cannot or named_in_full"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brick_icons/__init__.py tests/test_db.py
git commit -m "name the build and commit of any revision, not only HEAD"
```

---

### Task 2: One attempts writer, and a run per spot redraw

A spot redraw writes an `attempts` row, which `store_render` does not. The
row belongs to a run of kind `store` whose `dir` is `out/store/spot`, because
`db.rebuild` carries across only store runs' attempts (`_stored_attempts`).
Each redraw gets a run of its own, so `cells._LATEST_ATTEMPT`, which takes the
highest `run_id`, reads the newest redraw as the latest attempt.

**Files:**
- Modify: `brick_icons/db.py` (`import_store_jsonl` at ~503-526; `_stored_attempts` query at ~1063-1067; the carried-attempts insert in `rebuild` at ~1218-1221)
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_db.py`:

```python
def test_a_spot_redraw_is_an_attempt_in_its_own_run(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    first = db.spot_run(conn, "7.abc1234", "3001", "occt")
    db.record_attempt(conn, first, {"part": "3001", "source": "occt",
                                    "state": None, "secs": 150.2,
                                    "error": "TimeoutError", "detail": "cap"})
    second = db.spot_run(conn, "7.abc1234", "3001", "occt")
    db.record_attempt(conn, second, {"part": "3001", "source": "occt",
                                     "state": "stored", "secs": 4.1})
    assert second > first
    run = conn.execute("SELECT kind, commit_sha, args FROM runs WHERE id = ?",
                       (second,)).fetchone()
    assert run["kind"] == "store"
    assert run["commit_sha"] == "7.abc1234"
    assert json.loads(run["args"])["dir"] == db.SPOT_TREE
    rows = conn.execute("SELECT run_id, state, secs, error FROM attempts "
                        "ORDER BY run_id").fetchall()
    assert [tuple(r) for r in rows] == [
        (first, None, 150.2, "TimeoutError"), (second, "stored", 4.1, None)]


def test_a_rebuild_keeps_the_newest_spot_attempt(tmp_path):
    out = tmp_path / "corpus.db"
    lib = _library(tmp_path)
    db.rebuild(out, lib, root=tmp_path, census_dirs=[])
    conn = db.connect(out)
    for state, error in ((None, "TimeoutError"), ("stored", None)):
        run_id = db.spot_run(conn, "7.abc1234", "3001", "occt")
        db.record_attempt(conn, run_id, {"part": "3001", "source": "occt",
                                         "state": state, "error": error,
                                         "secs": 3.0})
    conn.close()

    db.rebuild(out, lib, root=tmp_path, census_dirs=[])
    conn = db.connect(out)
    row = conn.execute("SELECT state, error FROM attempts "
                       "WHERE part_id = '3001'").fetchone()
    assert (row["state"], row["error"]) == ("stored", None)


def test_touching_a_render_moves_only_its_stamp(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    conn.execute("INSERT INTO parts (id, title, printed, obsolete) "
                 "VALUES ('3001', 'Brick', 0, 0)")
    conn.execute("INSERT INTO renders (part_id, source, config_key, made_at, "
                 "path, sha256) VALUES ('3001', 'occt', 'k', "
                 "'2020-01-01T00:00:00+00:00', 'renders/occt/3001.svg', 'x')")
    conn.commit()
    db.touch_render(conn, "3001", "occt")
    row = conn.execute("SELECT made_at, sha256 FROM renders").fetchone()
    assert row["made_at"] > "2020-01-01T00:00:00+00:00"
    assert row["sha256"] == "x"
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_db.py -q -k "spot or touching_a_render"`
Expected: FAIL with `AttributeError: module 'brick_icons.db' has no attribute 'spot_run'`

- [ ] **Step 3: Implement**

In `brick_icons/db.py`, replace `import_store_jsonl` with:

```python
_ATTEMPT_UPSERT = (
    "INSERT OR REPLACE INTO attempts (run_id, part_id, source, state, "
    "secs, error, detail) VALUES (?, ?, ?, ?, ?, ?, ?)")

#: The store tree every spot redraw's run names. No log is ever written
#: there; the name is what `rebuild` groups the carried attempts under.
SPOT_TREE = "out/store/spot"


def _attempt_row(run_id: int, r: dict) -> tuple:
    return (run_id, r["part"], r["source"], r.get("state"), r.get("secs"),
            r.get("error"), r.get("detail"))


def import_store_jsonl(conn: sqlite3.Connection, run_id: int,
                       path: Path | str) -> int:
    """One row per part a render-store run attempted, drawn or not.

    Deliberately not `measurements`: those are scores against the part's own
    polygons, and every reader takes the newest run per part and engine -- a
    store row landing there would hand each occt finding a null where its
    d99 was. A part logged twice in one run keeps its last row, so a retry
    settles the failure before it -- what `Runner.remaining` already assumes.
    """
    rows = [_attempt_row(run_id, json.loads(line))
            for line in Path(path).read_text().splitlines() if line.strip()]
    conn.executemany(_ATTEMPT_UPSERT, rows)
    conn.commit()
    return len(rows)


def record_attempt(conn: sqlite3.Connection, run_id: int, row: dict) -> None:
    """One attempt, as a store log line would carry it: `part`, `source`,
    and any of `state`, `secs`, `error`, `detail`."""
    conn.execute(_ATTEMPT_UPSERT, _attempt_row(run_id, row))
    conn.commit()


def spot_run(conn: sqlite3.Connection, build: str, part: str,
             source: str) -> int:
    """A run for one spot redraw, stamped with the build the worker drew at.

    One per redraw, so the newest redraw holds the highest run id and reads as
    the part's latest attempt."""
    return start_run(conn, "store", {"dir": SPOT_TREE, "via": "spot",
                                     "part": part, "source": source}, build)


def touch_render(conn: sqlite3.Connection, part_id: str, source: str) -> None:
    """Restamp a slot's render as made now, for a redraw that drew the same
    bytes: the drawing is current, and nothing else about it changed."""
    conn.execute("UPDATE renders SET made_at = ? WHERE part_id = ? "
                 "AND source = ?", (now(), part_id, source))
    conn.commit()
```

In `_stored_attempts`, make the carried rows come out oldest run first, so
`INSERT OR REPLACE` leaves the newest. Change

```python
                "WHERE r.kind = 'store' AND json_extract(r.args, '$.dir') = ?",
                (where,))]
```

to

```python
                "WHERE r.kind = 'store' AND json_extract(r.args, '$.dir') = ? "
                "ORDER BY a.run_id",
                (where,))]
```

In `rebuild`, change the carried-attempts insert

```python
        conn.executemany(
            "INSERT OR REPLACE INTO attempts (run_id, part_id, source, state, "
            "secs, error, detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(run_id, *r) for r in rows])
```

to

```python
        conn.executemany(_ATTEMPT_UPSERT, [(run_id, *r) for r in rows])
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_db.py -q`
Expected: PASS (every test in the file, including the store-attempt tests this refactor touches)

- [ ] **Step 5: Commit**

```bash
git add brick_icons/db.py tests/test_db.py
git commit -m "write spot redraw attempts through one attempts writer"
```

---

### Task 3: A capped, isolated call that logs nothing

The worker needs `Runner`'s fork, timeout and memory cap, but not its log: a
reply row holds a whole SVG, and the lab keeps the record.

**Files:**
- Modify: `brick_icons/batch.py` (`Runner.__init__` at 136-140; `Runner.run` at 198-217)
- Test: `tests/test_batch.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_batch.py`:

```python
def test_a_call_returns_the_row_and_writes_no_log(tmp_path):
    runner = batch.Runner(None, timeout=5, isolate=True, key="part")
    row = runner.call("3001", lambda part: {"part": part, "svg": "<svg/>"})
    assert row["svg"] == "<svg/>"
    assert row["secs"] >= 0
    assert list(tmp_path.iterdir()) == []


def test_a_call_past_the_cap_is_a_timeout_row():
    runner = batch.Runner(None, timeout=0.3, isolate=True, key="part")
    row = runner.call("3001", _spin)
    assert row["error"] == "TimeoutError"
    assert row["part"] == "3001"
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_batch.py -q -k "a_call"`
Expected: FAIL with `TypeError: expected str, bytes or os.PathLike object, not NoneType`

- [ ] **Step 3: Implement**

In `Runner.__init__`, replace

```python
    def __init__(self, log: Path | str, timeout: float = 0, key: str = "item",
                 extra: dict | None = None, isolate: bool = False,
                 mem_gb: float = 0):
        self.log = Path(log)
        self.inflight = Path(f"{self.log}.inflight")
```

with

```python
    def __init__(self, log: Path | str | None, timeout: float = 0,
                 key: str = "item", extra: dict | None = None,
                 isolate: bool = False, mem_gb: float = 0):
        # None is a runner for `call` alone, which keeps no record.
        self.log = Path(log) if log is not None else None
        self.inflight = Path(f"{self.log}.inflight") if log is not None else None
```

Replace `Runner.run` with `call` plus a `run` that uses it:

```python
    def call(self, item: str, work) -> dict:
        """`work(item)` under the cap, as `run` does it, with no log and no
        inflight marker: for a caller that keeps its own record."""
        started = time.time()
        row = self._isolated(item, work) if self.isolate else self._here(item, work)
        row["secs"] = round(time.time() - started, 1)
        return row

    def run(self, item: str, work) -> dict:
        """`work(item)` under the cap. Its dict is returned and logged; a
        failure becomes a row naming the exception.

        Without `isolate` this is best effort: the alarm lands between Python
        bytecodes, so an item stuck inside a C call runs past it.
        """
        self.inflight.write_text(item)
        # onto reads this off the item's own stdout pipe and shows it as the
        # worker's label, so a batched item names the part in hand rather than
        # the one it started with. Consumed, not forwarded: it never reaches
        # the job log. Capped at 48 runes by onto.
        print(f"onto: item {item[:48]}", flush=True)
        row = {**self.extra, **self.call(item, work)}
        self.write(row)
        self.inflight.unlink(missing_ok=True)
        return row
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_batch.py -q`
Expected: PASS (all of `test_batch.py`, since `run` now goes through `call`)

- [ ] **Step 5: Commit**

```bash
git add brick_icons/batch.py tests/test_batch.py
git commit -m "add Runner.call, the capped isolated call without a log"
```

---

### Task 4: The CLI's render path, raising

The worker must draw with the CLI's own path ("the lab must not fork the
CLI"), and it needs the exception's type for the `attempts` row: the wall
reads `error == 'TimeoutError'`. `_render_here` flattens every failure to a
string, so the path is split out as `draw`, and `_render_here` calls it.

**Files:**
- Modify: `brick_icons/lab/runner.py` (`_render_here`, lines 58-71)
- Test: `tests/test_lab_runner.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lab_runner.py`:

```python
def test_draw_is_the_cli_path_and_writes_the_drawing(tmp_path, ldraw_dir):
    runner.draw(["3005", "--format", "svg", "--shading", "outline"], tmp_path)
    assert (tmp_path / "3005.svg").is_file()


def test_draw_raises_what_the_render_raised(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="no part given"):
        runner.draw(["--format", "svg"], tmp_path)
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_lab_runner.py -q -k draw`
Expected: FAIL with `AttributeError: module 'brick_icons.lab.runner' has no attribute 'draw'`

- [ ] **Step 3: Implement**

Insert above `_render_here`:

```python
def draw(argv: list[str], out_dir: Path) -> None:
    """One part drawn by the CLI's own path: its parser, its Config,
    `process_one`. Raises whatever the render raises."""
    args, _ = cli.build_parser().parse_known_args(argv)
    cfg = cli._config_from_args(args)
    parts = cli._gather_parts(args)
    if not parts:
        raise ValueError("no part given")
    cli.process_one(cfg, parts[0], out_dir)
```

In `_render_here`, delete the unused `started = time.perf_counter()` line and
replace the five lines inside its `try:`

```python
        args, _ = cli.build_parser().parse_known_args(argv)
        cfg = cli._config_from_args(args)
        parts = cli._gather_parts(args)
        if not parts:
            raise ValueError("no part given")
        cli.process_one(cfg, parts[0], out_dir)
```

with

```python
        draw(argv, out_dir)
```

leaving its `except` clause and both return statements as they are.

- [ ] **Step 4: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_lab_runner.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/runner.py tests/test_lab_runner.py
git commit -m "split the lab runner's CLI render path out as draw"
```

---

### Task 5: Which file a render kept

`render_into_store` decides which artifact is the drawing and what a decal
that found nothing means. The worker has to decide the same way, so the rule
moves into one function both call.

**Files:**
- Modify: `brick_icons/lab/store.py` (`render_into_store`, lines 26-39)
- Test: `tests/test_lab_store.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lab_store.py`:

```python
"""Which of a render's files the store keeps."""
import pytest

from brick_icons.lab import store


def test_an_svg_outranks_a_raster():
    assert store.drawing_in(["3001.png", "3001.svg"], "occt") == "3001.svg"


def test_a_raster_slot_keeps_its_png():
    assert store.drawing_in(["3001.png"], "occt") == "3001.png"


def test_a_decal_with_nothing_to_draw_is_none():
    assert store.drawing_in([], "decal") is None


def test_any_other_slot_drawing_nothing_is_an_error():
    with pytest.raises(RuntimeError, match="render produced no drawing"):
        store.drawing_in(["3001.json"], "occt")
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_lab_store.py -q`
Expected: FAIL with `AttributeError: module 'brick_icons.lab.store' has no attribute 'drawing_in'`

- [ ] **Step 3: Implement**

In `brick_icons/lab/store.py`, add above `render_into_store`:

```python
def drawing_in(names: list[str], source: str) -> str | None:
    """The file a render made that the store keeps: its SVG where it drew one,
    the raster otherwise -- ldview has no vector form, and picking by
    extension alone would take a thumbnail.

    None for a decal that drew nothing. That is not a failure: most of the
    library carries no print, and a part whose decoration shattered past
    unwrap.MAX_DECALS is declining to draw rather than erroring. Any other
    slot drawing nothing raises.
    """
    drawn = ([n for n in names if n.endswith(".svg")]
             or [n for n in names if n.endswith(".png")])
    if drawn:
        return drawn[0]
    if source == "decal":
        return None
    raise RuntimeError(f"render produced no drawing: {names}")
```

and in `render_into_store`, replace everything from the comment
`# An SVG where a slot draws one, the raster otherwise:` through
`made = cache.dir_for(argv, root=lab_root) / drawn[0]` with:

```python
    name = drawing_in([a["name"] for a in result["artifacts"]], source)
    if name is None:
        # Logged, so a later pass can tell a part that was tried and had
        # nothing from one nobody has reached.
        return {"part": part, "source": source, "state": "none"}
    made = cache.dir_for(argv, root=lab_root) / name
```

(the following `db.store_render(...)` line and the `return` stay).

- [ ] **Step 4: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_lab_store.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/store.py tests/test_lab_store.py
git commit -m "decide which file a render kept in one place"
```

---

### Task 6: The spot request and reply shapes

The commit a redraw wants is not part of the request: the lab passes it to
`onto call --commit`, which rolls the worker before delivering.

**Files:**
- Create: `brick_icons/spot_protocol.py`
- Test: `tests/test_spot_protocol.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_spot_protocol.py`:

```python
"""What the lab and the spot worker say to each other."""
import io
import json

import pytest

from brick_icons import spot_protocol as sp


def test_a_request_carries_what_the_worker_needs():
    req = sp.request("3001", "occt", ["3001", "--engine", "occt"],
                     build="7.abc1234")
    assert req == {"part": "3001", "source": "occt",
                   "argv": ["3001", "--engine", "occt"], "build": "7.abc1234"}


def test_a_ping_is_told_apart_from_a_render():
    assert sp.is_ping(sp.ping())
    assert not sp.is_ping(sp.request("3001", "occt", [], "b"))
    assert sp.pong("7.abc1234") == {"pong": True, "build": "7.abc1234"}


def test_a_drawn_reply_passes_the_check():
    got = sp.reply(svg="<svg/>", secs=1.2, build="7.abc1234", state="drawn")
    assert sp.check_reply(got) == {"svg": "<svg/>", "secs": 1.2,
                                   "build": "7.abc1234", "state": "drawn",
                                   "error": None, "detail": None}


def test_a_failed_reply_needs_no_state():
    got = sp.reply(secs=150.0, build="b", error="TimeoutError",
                   detail="exceeded 150s")
    assert sp.check_reply(got)["state"] is None


def test_the_check_ignores_the_id_onto_echoes():
    got = {"id": "onto-7", **sp.reply(build="b", state="none")}
    assert sp.check_reply(got) is got


@pytest.mark.parametrize("bad", [
    None,
    {"svg": "<svg/>"},
    {**sp.reply(build="b", state="drawn"), "svg": None},
    {**sp.reply(build="b", state="sideways")},
])
def test_a_malformed_reply_is_refused(bad):
    with pytest.raises(ValueError):
        sp.check_reply(bad)


def test_a_request_line_is_split_into_onto_s_id_and_the_request():
    line = json.dumps({"id": "onto-7", "commit": "c" * 40,
                       **sp.request("3001", "occt", ["3001"], "b")})
    ((rid, req),) = list(sp.read(io.StringIO(line + "\n")))
    assert rid == "onto-7"
    assert req["part"] == "3001" and "id" not in req


def test_a_line_that_is_not_an_object_is_a_bad_request():
    got = list(sp.read(io.StringIO("{not json\n[1, 2]\n\n")))
    assert got == [(None, None), (None, None)]


def test_a_reply_echoes_its_id_on_one_line():
    out = io.StringIO()
    sp.write(out, "onto-7", sp.pong("b"))
    assert out.getvalue() == '{"id": "onto-7", "pong": true, "build": "b"}\n'
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_spot_protocol.py -q`
Expected: FAIL with `ImportError: cannot import name 'spot_protocol'`

- [ ] **Step 3: Implement**

Create `brick_icons/spot_protocol.py`:

```python
"""What the lab and the spot render worker say to each other, and how it
travels between onto's node agent and the worker process.

The framing is onto's (its services guide): one JSON object per line each
way. A request line is the caller's fields plus onto's `id`, and the reply
must echo that id. Requests may be answered in any order.
"""
from __future__ import annotations

import json
from typing import IO, Iterator

NAME = "brick-spot-render"
REPLY_KEYS = ("svg", "secs", "build", "state", "error", "detail")
#: `drawn` carries an SVG; `none` is a decal with nothing to draw.
STATES = ("drawn", "none")


def request(part: str, source: str, argv: list[str], build: str) -> dict:
    """`build` is the revision the lab expects, in `brick_icons.build()` form.
    The commit itself travels as `onto call --commit`, which rolls the
    service to it before this is delivered."""
    return {"part": part, "source": source, "argv": list(argv), "build": build}


def ping() -> dict:
    return {"ping": True}


def is_ping(req: dict) -> bool:
    return req.get("ping") is True


def pong(build: str) -> dict:
    return {"pong": True, "build": build}


def reply(*, build: str, svg: str | None = None, secs: float | None = None,
          state: str | None = None, error: str | None = None,
          detail: str | None = None) -> dict:
    """`error` is the exception's type name -- the wall reads `TimeoutError`
    as its own state -- and `detail` its message."""
    return {"svg": svg, "secs": secs, "build": build, "state": state,
            "error": error, "detail": detail}


def check_reply(obj) -> dict:
    """The reply, or ValueError saying what is wrong with it."""
    if not isinstance(obj, dict) or any(k not in obj for k in REPLY_KEYS):
        raise ValueError(f"not a spot reply: {obj!r:.200}")
    if obj["error"] is None and obj["state"] not in STATES:
        raise ValueError(f"a reply with no error has state {obj['state']!r}")
    if obj["state"] == "drawn" and not isinstance(obj["svg"], str):
        raise ValueError("a drawn reply carries no SVG")
    return obj


def read(stream: IO[str]) -> Iterator[tuple[str | None, dict | None]]:
    """(onto's id, the request) per line. The request is None for a line
    that is not a JSON object, which the caller answers as a bad request."""
    for line in stream:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            yield None, None
            continue
        if not isinstance(obj, dict):
            yield None, None
            continue
        rid = obj.pop("id", None)
        obj.pop("commit", None)
        yield rid, obj


def write(stream: IO[str], rid: str | None, body: dict) -> None:
    stream.write(json.dumps({"id": rid, **body}) + "\n")
    stream.flush()
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_spot_protocol.py -q`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add brick_icons/spot_protocol.py tests/test_spot_protocol.py
git commit -m "define the spot render request, reply and line framing"
```

---

### Task 7: The worker draws one request

`render` is what a pool process runs per request: a forked child under the
batch cap, drawing through `lab.runner.draw`. The reply's SVG must be
byte-identical to the CLI's for the same argv.

**Files:**
- Create: `brick_icons/spot_worker.py`
- Test: `tests/test_spot_worker.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_spot_worker.py`:

```python
"""The spot render worker draws what the CLI draws."""
import time

from brick_icons import cli, db, spot_protocol, spot_worker


def _req(part="3005", source="naive"):
    return spot_protocol.request(part, source, db.canonical_argv(part, source),
                                 build="b")


def test_a_request_draws_the_same_bytes_as_the_cli(tmp_path, ldraw_dir):
    reply = spot_worker.render(_req())
    assert reply["error"] is None, reply["detail"]
    assert reply["state"] == "drawn"
    out = tmp_path / "cli"
    assert cli.main([*db.canonical_argv("3005", "naive"), "--out", str(out)]) == 0
    (svg,) = out.glob("*.svg")
    assert reply["svg"] == svg.read_text()
    assert spot_protocol.check_reply(reply) is reply


def test_a_part_past_the_cap_is_a_timeout_reply(monkeypatch):
    monkeypatch.setattr(spot_worker.lab_runner, "draw",
                        lambda argv, out: time.sleep(30))
    started = time.time()
    reply = spot_worker.render(_req(), timeout=0.5)
    assert time.time() - started < 10
    assert (reply["error"], reply["state"], reply["svg"]) == \
        ("TimeoutError", None, None)


def test_an_engine_error_is_named_in_the_reply(monkeypatch):
    def boom(argv, out):
        raise ValueError("boom")
    monkeypatch.setattr(spot_worker.lab_runner, "draw", boom)
    reply = spot_worker.render(_req())
    assert (reply["error"], reply["detail"]) == ("ValueError", "boom")


def test_a_decal_with_nothing_to_draw_is_a_none_reply(monkeypatch):
    monkeypatch.setattr(spot_worker.lab_runner, "draw", lambda argv, out: None)
    reply = spot_worker.render(_req("3005", "decal"))
    assert (reply["state"], reply["svg"], reply["error"]) == ("none", None, None)


def test_the_reply_names_the_build_that_drew_it(monkeypatch):
    import brick_icons
    monkeypatch.setattr(spot_worker.lab_runner, "draw", lambda argv, out: None)
    assert spot_worker.render(_req("3005", "decal"))["build"] == brick_icons.build()


def test_the_pool_holds_two_workers_by_default():
    assert spot_worker.POOL == 2
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_spot_worker.py -q`
Expected: FAIL with `ImportError: cannot import name 'spot_worker'`

- [ ] **Step 3: Implement**

Create `brick_icons/spot_worker.py`:

```python
"""The spot render worker: one warm process on the fleet that draws a part
the moment the lab asks.

onto runs it as a service through `scripts/spot-worker.sh` (DEVELOPING.md,
"Spot rendering"). Each pool process imports the engine once, then draws
every request it is handed in a forked child, through the CLI's own path and
under the batch per-part cap, so a redraw pays for the render and not for
Python starting up.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from . import batch, build, spot_protocol
from .lab import runner as lab_runner
from .lab import store

#: Redraws drawn at once; a third waits for one of them.
POOL = int(os.environ.get("BRICK_SPOT_POOL", "2"))
#: The render store's own cap (`scripts/build-render-store.py --mem-gb`).
MEM_GB = 8.0


def warm() -> None:
    """Pool initializer: the engine's imports, once per pool process. A forked
    request inherits them."""
    from . import cli, hlr  # noqa: F401
    try:
        from . import occt  # noqa: F401
    except ImportError:
        pass


def render(req: dict, timeout: float = batch.RENDER_TIMEOUT_S) -> dict:
    """One request's reply. Never raises: a part that fails is a reply
    saying so."""
    part, source, argv = req["part"], req["source"], list(req["argv"])
    # Removed here rather than by the child, which a timeout kills mid-render.
    scratch = Path(tempfile.mkdtemp(prefix="brick-spot-"))

    def work(item: str) -> dict:
        lab_runner.draw(argv, scratch)
        name = store.drawing_in(sorted(p.name for p in scratch.iterdir()), source)
        if name is None:
            return {"part": item, "state": "none", "svg": None}
        if not name.endswith(".svg"):
            raise RuntimeError(f"{source} drew {name}, which is not an SVG")
        return {"part": item, "state": "drawn",
                "svg": (scratch / name).read_text()}

    try:
        row = batch.Runner(None, timeout=timeout, key="part", isolate=True,
                           mem_gb=MEM_GB).call(part, work)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    failed = row.get("error") is not None
    return spot_protocol.reply(
        svg=None if failed else row.get("svg"), secs=row["secs"],
        build=build(), state=None if failed else row["state"],
        error=row.get("error"), detail=row.get("detail"))
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_spot_worker.py -q`
Expected: PASS (6 tests). If the byte-identity test fails, diff the two SVGs
before changing anything: a difference means the worker's path has drifted
from the CLI's, which is the bug this test exists to catch.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/spot_worker.py tests/test_spot_worker.py
git commit -m "add the spot render worker's per-request render"
```

---

### Task 8: The worker's loop and entry point

Requests arrive concurrently and may be answered out of order, so the loop
reads lines, answers a ping itself, hands each render to the pool, and writes
each reply as it finishes. stdout is the framing: onto sends non-JSON stdout
to the job log, but a line starting `{"id":` would be misread, so fd 1 goes to
stderr for the worker and everything it starts.

**Files:**
- Modify: `brick_icons/spot_worker.py` (append `serve`, `main`)
- Test: `tests/test_spot_worker.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_spot_worker.py`:

```python
import io
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _lines(*requests):
    return io.StringIO("".join(json.dumps(r) + "\n" for r in requests))


def test_two_requests_draw_at_once_and_each_reply_names_its_request():
    together = threading.Barrier(2, timeout=5)

    def answer(req):
        together.wait()
        return spot_protocol.reply(svg=f"<svg id='{req['part']}'/>", secs=0.1,
                                   build="b", state="drawn")

    out = io.StringIO()
    with ThreadPoolExecutor(spot_worker.POOL) as pool:
        spot_worker.serve(_lines({"id": "onto-1", **_req("3001")},
                                 {"id": "onto-2", **_req("3002")}),
                          out, pool, answer)
    replies = {r["id"]: r for r in map(json.loads, out.getvalue().splitlines())}
    assert replies["onto-1"]["svg"] == "<svg id='3001'/>"
    assert replies["onto-2"]["svg"] == "<svg id='3002'/>"


def test_a_ping_is_answered_without_the_pool():
    import brick_icons
    out = io.StringIO()
    with ThreadPoolExecutor(1) as pool:
        spot_worker.serve(_lines({"id": "p", **spot_protocol.ping()}),
                          out, pool, lambda req: 1 / 0)
    (line,) = out.getvalue().splitlines()
    assert json.loads(line) == {"id": "p", **spot_protocol.pong(brick_icons.build())}


def test_a_line_that_is_not_json_is_answered_not_fatal():
    out = io.StringIO()
    with ThreadPoolExecutor(1) as pool:
        spot_worker.serve(io.StringIO("{not json\n"), out, pool, lambda r: None)
    (line,) = out.getvalue().splitlines()
    got = json.loads(line)
    assert (got["id"], got["error"]) == (None, "BadRequest")


def test_a_render_that_raises_in_the_pool_is_a_reply():
    def die(req):
        raise RuntimeError("pool gone")
    out = io.StringIO()
    with ThreadPoolExecutor(1) as pool:
        spot_worker.serve(_lines({"id": "onto-1", **_req()}), out, pool, die)
    reply = json.loads(out.getvalue())
    assert (reply["error"], reply["detail"]) == ("RuntimeError", "pool gone")


def test_the_module_answers_a_ping_on_a_clean_stdout():
    repo = Path(__file__).resolve().parent.parent
    got = subprocess.run(
        [sys.executable, "-m", "brick_icons.spot_worker"],
        input=json.dumps({"id": "p", **spot_protocol.ping()}) + "\n",
        capture_output=True, text=True, timeout=60, cwd=repo,
        env={**os.environ, "PYTHONPATH": str(repo)})
    assert got.returncode == 0, got.stderr
    (line,) = got.stdout.splitlines()
    assert json.loads(line)["pong"] is True
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_spot_worker.py -q -k "at_once or ping or not_json or raises_in or module"`
Expected: FAIL with `AttributeError: module 'brick_icons.spot_worker' has no attribute 'serve'`

- [ ] **Step 3: Implement**

In `brick_icons/spot_worker.py`, extend the imports:

```python
import multiprocessing
import os
import shutil
import sys
import tempfile
import threading
from concurrent.futures import Executor, Future, ProcessPoolExecutor, wait
from pathlib import Path
from typing import IO, Callable
```

and append:

```python
def _failed(exc: BaseException) -> dict:
    return spot_protocol.reply(build=build(), error=type(exc).__name__,
                               detail=str(exc)[:300])


def serve(inp: IO[str], out: IO[str], pool: Executor,
          answer: Callable[[dict], dict]) -> None:
    """Answer every request on `inp` until it closes. A ping is answered
    here; a render goes to `pool`, so two draw at once with the default
    pool, and each reply is written as it finishes."""
    lock = threading.Lock()
    running: set[Future] = set()

    def send(rid, body: dict) -> None:
        with lock:
            spot_protocol.write(out, rid, body)

    def done(rid, fut: Future) -> None:
        exc = fut.exception()
        send(rid, _failed(exc) if exc is not None else fut.result())

    for rid, req in spot_protocol.read(inp):
        if req is None:
            send(rid, spot_protocol.reply(build=build(), error="BadRequest",
                                          detail="not a JSON object"))
        elif spot_protocol.is_ping(req):
            send(rid, spot_protocol.pong(build()))
        else:
            fut = pool.submit(answer, req)
            running.add(fut)
            fut.add_done_callback(lambda f, rid=rid: done(rid, f))
    wait(running)


def main() -> int:
    # stdout is the framing. Anything the engine prints would share it, so
    # fd 1 goes to stderr for this process and every one it starts.
    out = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)
    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(POOL, mp_context=ctx, initializer=warm) as pool:
        serve(sys.stdin, out, pool, render)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_spot_worker.py -q`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add brick_icons/spot_worker.py tests/test_spot_worker.py
git commit -m "serve spot render requests from a two-process pool"
```

---

### Task 9: Patch one cell into a slot's sheets

A redraw has to change one cell of `sheet-8` and `sheet-32`, not re-compose
24,591 of them. pezlie's wall draws a changed cell into its in-memory sheets
itself; this is for the next fresh page load, and for `/corpus`.

Patching the WebP in place is ruled out by measurement: one decode and
re-encode of the occt slot's `sheet-32.webp` (5652 px square, q90) changed
8.7M of its 32M pixels and took 3.2 s. So every sheet gets a lossless master
beside it (`sheet-<level>.master.png`, compress level 1: 32 MB, 0.7 s to write
for sheet-32), `patch_cell` edits the master, and the WebP is re-encoded from
it. The published WebP stays one generation from the master however many
cells are patched.

The manifest's `version` becomes a counter written with it, never the image's
mtime in whole seconds. It is `max(previous + 1, unix seconds)`: two writes in
one second still differ, and a slot wiped and rebaked never reuses a version a
browser has cached.

A lock file serializes `compose` and `patch_cell` on one slot directory, so a
bake landing during a redraw cannot publish a sheet without the patch.

**Files:**
- Modify: `brick_icons/thumbs.py` (imports; after `THUMB_SAVE`; `compose` at 201-231)
- Test: `tests/test_thumbs.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_thumbs.py`:

```python
import shutil
import time

import numpy as np

DISC = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
        '<circle cx="128" cy="85" r="60" fill="black"/></svg>')
ORDER = ["a", "b", "c", "d", "e"]


def _baked_slot(tmp_path):
    out = tmp_path / "slot"
    svg = tmp_path / "rect.svg"
    svg.write_text(SVG)
    for pid in ORDER:
        thumbs.bake_part(pid, svg, out, sha=f"old-{pid}")
    thumbs.compose(out, ORDER)
    return out


def _master(out, level):
    with Image.open(out / f"sheet-{level}.master.png") as img:
        return np.asarray(img.convert("RGBA"))


def _redraw_c(tmp_path, out):
    disc = tmp_path / "disc.svg"
    disc.write_text(DISC)
    thumbs.bake_part("c", disc, out, sha="new-c")


def test_a_patched_cell_is_what_a_full_compose_would_draw(tmp_path):
    out = _baked_slot(tmp_path)
    before = {lvl: _master(out, lvl) for lvl in thumbs.SHEET_LEVELS}
    _redraw_c(tmp_path, out)

    thumbs.patch_cell(out, "c", ORDER.index("c"), len(ORDER))

    oracle = tmp_path / "oracle"
    shutil.copytree(out, oracle)
    thumbs.compose(oracle, ORDER)
    for lvl in thumbs.SHEET_LEVELS:
        after = _master(out, lvl)
        assert np.array_equal(after, _master(oracle, lvl)), lvl
        g = thumbs.geometry(len(ORDER), lvl)
        x0, y0, x1, y1 = g.cell_box(ORDER.index("c"))
        ys, xs = np.nonzero((after != before[lvl]).any(axis=2))
        assert len(xs) > 0, lvl
        assert xs.min() >= x0 - g.gutter and xs.max() < x1 + g.gutter, lvl
        assert ys.min() >= y0 - g.gutter and ys.max() < y1 + g.gutter, lvl


def test_a_patch_records_the_new_sha_and_a_new_version(tmp_path):
    out = _baked_slot(tmp_path)
    was = json.loads((out / "sheet-32.json").read_text())
    _redraw_c(tmp_path, out)
    versions = thumbs.patch_cell(out, "c", 2, len(ORDER))
    now = json.loads((out / "sheet-32.json").read_text())
    assert now["baked"]["c"] == "new-c"
    assert now["baked"]["a"] == "old-a"
    assert int(now["version"]) > int(was["version"])
    assert versions == {8: json.loads((out / "sheet-8.json").read_text())["version"],
                        32: now["version"]}


def test_two_writes_in_one_second_get_two_versions(tmp_path):
    out = _baked_slot(tmp_path)
    first = json.loads((out / "sheet-8.json").read_text())["version"]
    thumbs.compose(out, ORDER)
    second = json.loads((out / "sheet-8.json").read_text())["version"]
    assert int(second) > int(first)


def test_a_fresh_slot_starts_its_version_at_the_clock(tmp_path):
    before = int(time.time())
    out = _baked_slot(tmp_path)
    assert int(json.loads((out / "sheet-8.json").read_text())["version"]) >= before


def test_a_patch_refuses_a_sheet_baked_for_another_part_count(tmp_path):
    out = _baked_slot(tmp_path)
    with pytest.raises(ValueError, match="rebake"):
        thumbs.patch_cell(out, "c", 2, len(ORDER) + 1)


def test_a_patch_refuses_a_slot_with_no_master(tmp_path):
    out = _baked_slot(tmp_path)
    (out / "sheet-32.master.png").unlink()
    with pytest.raises(FileNotFoundError, match="rebake"):
        thumbs.patch_cell(out, "c", 2, len(ORDER))


def test_a_cell_with_no_tile_is_cleared(tmp_path):
    out = _baked_slot(tmp_path)
    for lvl in thumbs.LEVELS:
        (out / str(lvl) / f"c.{thumbs.THUMB_EXT}").unlink()
    thumbs.patch_cell(out, "c", 2, len(ORDER))
    g = thumbs.geometry(len(ORDER), 32)
    x0, y0, x1, y1 = g.cell_box(2)
    assert not _master(out, 32)[y0:y1, x0:x1].any()


def test_has_sheets_says_whether_a_slot_was_composed(tmp_path):
    assert not thumbs.has_sheets(tmp_path / "slot")
    assert thumbs.has_sheets(_baked_slot(tmp_path))
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_thumbs.py -q -k "patch or version or has_sheets or cleared"`
Expected: FAIL (no `sheet-8.master.png` from `compose` yet, or `AttributeError: ... 'patch_cell'`)

- [ ] **Step 3: Implement**

In `brick_icons/thumbs.py`, extend the imports:

```python
import fcntl
import json
import math
import os
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
```

After `THUMB_SAVE`, add:

```python
#: The lossless copy of each sheet that a patch edits. Re-encoding the WebP
#: itself is generational: one pass over the occt slot's sheet-32 changed 8.7M
#: of its 32M pixels. One per sheet, overwritten in place.
MASTER = "sheet-{level}.master.png"
MASTER_SAVE = {"format": "PNG", "compress_level": 1}
_LOCK = ".sheets.lock"
```

Replace `compose` with:

```python
@contextmanager
def _sheets_locked(out: Path):
    """One writer of a slot's sheets at a time: a bake composing while a
    redraw patches would otherwise publish a sheet without the patch."""
    out.mkdir(parents=True, exist_ok=True)
    with open(out / _LOCK, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _save_atomic(img: Image.Image, path: Path, **save) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    img.save(tmp, **save)
    os.replace(tmp, path)


def _next_version(previous) -> str:
    """Later than the last one, and never a number a browser may have cached
    from a slot since wiped: seconds since the epoch, or one past the last."""
    try:
        last = int(previous)
    except (TypeError, ValueError):
        last = 0
    return str(max(last + 1, int(time.time())))


def _tile(out: Path, level: int, part_id: str) -> Image.Image | None:
    path = out / str(level) / f"{part_id}.{THUMB_EXT}"
    if not path.is_file():
        return None
    with Image.open(path) as img:
        return img.convert("RGBA")


def _paste_cell(sheet: Image.Image, g: Geometry, index: int,
                cell: Image.Image | None) -> None:
    """The cell and its gutter, drawn from `cell`, or cleared without one."""
    x0, y0, x1, y1 = g.cell_box(index)
    if cell is None:
        sheet.paste((0, 0, 0, 0), (x0 - g.gutter, y0 - g.gutter,
                                   x1 + g.gutter, y1 + g.gutter))
        return
    sheet.paste(cell, (x0, y0))
    if g.gutter:
        _replicate_edges(sheet, cell, x0, y0, g.gutter)


def _publish(out: Path, level: int, sheet: Image.Image, manifest: dict) -> str:
    """Master, WebP, then manifest, each whole or not at all. The manifest
    goes last: it names the version a reader fetches the image under."""
    path = out / f"sheet-{level}.json"
    version = _next_version(_read_json(path).get("version"))
    _save_atomic(sheet, out / MASTER.format(level=level), **MASTER_SAVE)
    _save_atomic(sheet, out / f"sheet-{level}.{THUMB_EXT}", **THUMB_SAVE)
    _write_json(path, {**manifest, "version": version})
    return version


def has_sheets(out: Path | str) -> bool:
    return all((Path(out) / f"sheet-{level}.json").is_file()
               for level in SHEET_LEVELS)


def compose(out: Path | str, order: list[str]) -> list[Path]:
    """Paste every baked thumbnail onto its sheet, in `order`'s index order.

    `order` is every part, not only the drawn ones: an index is a position in
    the corpus, so a part gaining a render later fills the cell it already had.
    """
    out = Path(out)
    written = []
    with _sheets_locked(out):
        shas = baked_shas(out)
        for level in SHEET_LEVELS:
            g = geometry(len(order), level)
            sheet = Image.new("RGBA", (g.size, g.size), (0, 0, 0, 0))
            for index, part_id in enumerate(order):
                cell = _tile(out, level, part_id)
                if cell is not None:
                    _paste_cell(sheet, g, index, cell)
            _publish(out, level, sheet, {
                "level": level, "gutter": g.gutter, "pitch": g.pitch,
                "cols": g.cols, "rows": g.rows, "count": len(order),
                "size": g.size, "baked": shas})
            written.append(out / f"sheet-{level}.{THUMB_EXT}")
    return written


def patch_cell(out: Path | str, part_id: str, index: int,
               count: int) -> dict[int, str]:
    """Redraw one part's cell on every sheet from its baked tiles, as
    `compose` would draw it, and nothing else. Returns each level's new
    version.

    `count` is the corpus size now. A sheet baked for another count has every
    index after the change shifted, so it is refused rather than patched.
    """
    out = Path(out)
    versions = {}
    with _sheets_locked(out):
        shas = baked_shas(out)
        for level in SHEET_LEVELS:
            manifest = _read_json(out / f"sheet-{level}.json")
            if manifest.get("count") != count:
                raise ValueError(
                    f"{out}/sheet-{level} holds {manifest.get('count')} cells "
                    f"and the corpus {count}; rebake the slot")
            master = out / MASTER.format(level=level)
            if not master.is_file():
                raise FileNotFoundError(f"{master} is missing; rebake the slot")
            with Image.open(master) as img:
                sheet = img.convert("RGBA")
            _paste_cell(sheet, geometry(count, level), index,
                        _tile(out, level, part_id))
            baked = {k: v for k, v in manifest.get("baked", {}).items()
                     if k != part_id}
            if part_id in shas:
                baked[part_id] = shas[part_id]
            versions[level] = _publish(out, level, sheet,
                                       {**manifest, "baked": baked})
    return versions
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_thumbs.py -q`
Expected: PASS (every test in the file; the existing compose tests read the WebP sheet and manifest, whose shape gains only `version`)

- [ ] **Step 5: Commit**

```bash
git add brick_icons/thumbs.py tests/test_thumbs.py
git commit -m "patch one cell into a slot's sheets from a lossless master"
```

---

### Task 10: A broker and the events stream

`GET /api/events` streams server-sent events. Redraws run in route threads;
the stream is an async generator fed across the thread boundary with
`call_soon_threadsafe`, so an open stream holds no worker thread.
`GZipMiddleware` already skips `text/event-stream` (Starlette 1.6).

**Files:**
- Create: `brick_icons/lab/events.py`
- Modify: `brick_icons/lab/app.py` (imports; `app.state.events`; the route)
- Test: `tests/test_lab_events.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lab_events.py`:

```python
"""The lab's event stream: what a published change looks like on the wire."""
import asyncio

from brick_icons.lab import events


def test_a_subscriber_hears_each_publish_once():
    broker = events.Broker()
    heard = []
    stop = broker.subscribe(lambda kind, data: heard.append((kind, data)))
    broker.publish("changed", {"part": "3001"})
    stop()
    broker.publish("changed", {"part": "3002"})
    assert heard == [("changed", {"part": "3001"})]


def test_one_bad_subscriber_does_not_silence_the_rest():
    broker = events.Broker()
    heard = []
    broker.subscribe(lambda kind, data: 1 / 0)
    broker.subscribe(lambda kind, data: heard.append(data))
    broker.publish("changed", {"part": "3001"})
    assert heard == [{"part": "3001"}]


def test_an_event_is_framed_as_sse():
    assert events.frame("changed", {"sha": "ab", "part": "3001"}) == \
        'event: changed\ndata: {"part": "3001", "sha": "ab"}\n\n'


def test_the_stream_says_hello_then_carries_a_publish():
    broker = events.Broker()

    async def run():
        async def connected():
            return False
        stream = events.stream(broker, connected)
        first = await stream.__anext__()
        asyncio.get_running_loop().call_later(
            0.05, broker.publish, "changed", {"part": "3001"})
        second = await stream.__anext__()
        await stream.aclose()
        return first, second

    first, second = asyncio.run(run())
    assert first == ": connected\n\n"
    assert second == events.frame("changed", {"part": "3001"})


def test_a_closed_stream_stops_listening():
    broker = events.Broker()

    async def run():
        async def connected():
            return False
        stream = events.stream(broker, connected)
        await stream.__anext__()
        assert broker.listeners() == 1
        await stream.aclose()

    asyncio.run(run())
    assert broker.listeners() == 0
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_lab_events.py -q`
Expected: FAIL with `ImportError: cannot import name 'events'`

- [ ] **Step 3: Implement the module**

Create `brick_icons/lab/events.py`:

```python
"""Things that happened in the lab, told to every open page.

Published from route threads, streamed as server-sent events. Only `changed`
for now -- a stored redraw -- which a page acts on at once instead of waiting
for its next poll.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import AsyncIterator, Awaitable, Callable

log = logging.getLogger(__name__)

#: Seconds between keepalive comments on an idle stream, so a proxy between
#: the page and the lab does not close it for silence.
KEEPALIVE_S = 15.0

Listener = Callable[[str, dict], None]


class Broker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def stop() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)
        return stop

    def publish(self, kind: str, data: dict) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(kind, data)
            except Exception:                           # noqa: BLE001
                log.exception("an event listener failed on %s", kind)

    def listeners(self) -> int:
        with self._lock:
            return len(self._listeners)


def frame(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, sort_keys=True)}\n\n"


async def stream(broker: Broker,
                 disconnected: Callable[[], Awaitable[bool]]) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
    stop = broker.subscribe(
        lambda kind, data: loop.call_soon_threadsafe(queue.put_nowait, (kind, data)))
    try:
        yield ": connected\n\n"
        while not await disconnected():
            try:
                kind, data = await asyncio.wait_for(queue.get(), KEEPALIVE_S)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield frame(kind, data)
    finally:
        stop()
```

- [ ] **Step 4: Mount the route**

In `brick_icons/lab/app.py`:

- change `from fastapi import FastAPI, HTTPException, Query` to
  `from fastapi import FastAPI, HTTPException, Query, Request`;
- change `from fastapi.responses import FileResponse, JSONResponse, Response` to
  `from fastapi.responses import (FileResponse, JSONResponse, Response, StreamingResponse)`;
- add `events` to the `from . import (...)` list;
- after `app.state.flights = flight.Flights()` add `app.state.events = events.Broker()`;
- after the `get_health` route add:

```python
    @app.get("/api/events")
    async def get_events(request: Request):
        return StreamingResponse(
            events.stream(app.state.events, request.is_disconnected),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"})
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_lab_events.py -q`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add brick_icons/lab/events.py brick_icons/lab/app.py tests/test_lab_events.py
git commit -m "stream lab events to open pages as server-sent events"
```

---

### Task 11: The lab's `onto call` adapter, and a stub for tests

Every assumption about onto's CLI is a constant here (see "The external
contracts"). The status ping is how the lightbox knows before it posts
whether a roll is coming: it compares the worker's build with origin/main's.

**Files:**
- Create: `brick_icons/lab/spot.py`
- Modify: `tests/conftest.py` (append the stub and its fixture)
- Test: `tests/test_lab_spot.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lab_spot.py`:

```python
"""The lab's adapter for `onto call`, against a fake onto."""
import json

import pytest

from brick_icons import spot_protocol as sp
from brick_icons.lab import spot

EXPECTED = ("c" * 40, "9.ccccccc")
REQ = sp.request("3001", "occt", ["3001"], "9.ccccccc")


def _onto(tmp_path, stdout="", code=0, stderr="", sleep=0, codes=None):
    """A fake onto: records its argv and stdin, then answers. `codes` is a
    sequence of exit statuses, one per call, for a retry test."""
    (tmp_path / "stdout").write_text(stdout)
    (tmp_path / "stderr").write_text(stderr)
    (tmp_path / "codes").write_text(" ".join(map(str, codes or [code])))
    script = tmp_path / "onto"
    script.write_text(
        "#!/bin/sh\n"
        f"for a in \"$@\"; do printf '%s\\n' \"$a\"; done > {tmp_path}/argv\n"
        f"cat > {tmp_path}/stdin\n"
        f"echo x >> {tmp_path}/calls\n"
        + (f"sleep {sleep}\n" if sleep else "")
        + f"n=$(wc -l < {tmp_path}/calls)\n"
        f"code=$(cut -d' ' -f$n {tmp_path}/codes)\n"
        f"[ -n \"$code\" ] || code=$(awk '{{print $NF}}' {tmp_path}/codes)\n"
        f"cat {tmp_path}/stdout\ncat {tmp_path}/stderr >&2\nexit $code\n")
    script.chmod(0o755)
    return spot.OntoSpot(onto=str(script), expected=lambda: EXPECTED)


def _drawn():
    return json.dumps({"id": "onto-1", **sp.reply(
        svg="<svg/>", secs=1.0, build="9.ccccccc", state="drawn")})


def test_a_call_sends_the_request_on_stdin_with_its_commit(tmp_path):
    client = _onto(tmp_path, stdout=_drawn())
    assert client.draw(REQ, commit="c" * 40)["svg"] == "<svg/>"
    argv = (tmp_path / "argv").read_text().splitlines()
    assert argv == ["call", spot.TIMEOUT_FLAG, f"{int(spot.CALL_TIMEOUT_S)}s",
                    spot.COMMIT_FLAG, "c" * 40, sp.NAME, "-"]
    assert json.loads((tmp_path / "stdin").read_text()) == REQ


def test_no_commit_means_no_roll(tmp_path):
    client = _onto(tmp_path, stdout=_drawn())
    client.draw(REQ, commit=None)
    assert spot.COMMIT_FLAG not in (tmp_path / "argv").read_text().splitlines()


def test_a_down_service_is_spot_down(tmp_path):
    client = _onto(tmp_path, code=spot.DOWN_EXIT, stderr="no such service")
    with pytest.raises(spot.SpotDown, match="no such service"):
        client.draw(REQ, commit=None)


def test_no_onto_at_all_is_spot_down(tmp_path):
    client = spot.OntoSpot(onto=str(tmp_path / "absent"), expected=lambda: EXPECTED)
    with pytest.raises(spot.SpotDown):
        client.draw(REQ, commit=None)


@pytest.mark.parametrize("code, error", [
    (spot.ROLL_FAILED_EXIT, "RollFailed"),
    (spot.TIMEOUT_EXIT, "TimeoutError"),
    (spot.BAD_REQUEST_EXIT, "BadRequest"),
    (1, "SpotError"),
])
def test_each_failure_names_itself_with_onto_s_words(tmp_path, code, error):
    client = _onto(tmp_path, code=code, stderr="roll to cccc failed: uv sync")
    with pytest.raises(spot.SpotError, match="uv sync") as got:
        client.draw(REQ, commit=None)
    assert got.value.error == error


def test_a_process_that_died_mid_request_is_asked_once_more(tmp_path):
    client = _onto(tmp_path, stdout=_drawn(), codes=[spot.DIED_EXIT, 0])
    assert client.draw(REQ, commit=None)["svg"] == "<svg/>"
    assert len((tmp_path / "calls").read_text().splitlines()) == 2


def test_a_process_that_dies_twice_is_a_failure(tmp_path):
    client = _onto(tmp_path, code=spot.DIED_EXIT, stderr="exited 139")
    with pytest.raises(spot.SpotError) as got:
        client.draw(REQ, commit=None)
    assert got.value.error == "ProcessDied"


def test_a_reply_that_is_not_json_is_a_spot_error(tmp_path):
    client = _onto(tmp_path, stdout="panic: nil map")
    with pytest.raises(spot.SpotError, match="no JSON"):
        client.draw(REQ, commit=None)


def test_a_malformed_reply_is_a_spot_error(tmp_path):
    client = _onto(tmp_path, stdout='{"svg": "<svg/>"}')
    with pytest.raises(spot.SpotError, match="not a spot reply"):
        client.draw(REQ, commit=None)


def test_onto_that_never_answers_is_a_timeout(tmp_path):
    client = _onto(tmp_path, sleep=5)
    client.slack_s = 0
    with pytest.raises(spot.SpotError) as got:
        client.call(sp.ping(), timeout=1, commit=None)
    assert got.value.error == "TimeoutError"


def test_status_is_up_when_the_worker_is_at_origin_main(tmp_path):
    client = _onto(tmp_path, stdout=json.dumps({"id": "p", **sp.pong("9.ccccccc")}))
    assert client.status() == {"state": "up", "build": "9.ccccccc",
                               "want": "9.ccccccc", "detail": None}
    assert spot.COMMIT_FLAG not in (tmp_path / "argv").read_text().splitlines()


def test_status_is_stale_when_a_redraw_would_roll_it(tmp_path):
    client = _onto(tmp_path, stdout=json.dumps(sp.pong("8.bbbbbbb")))
    assert client.status()["state"] == "stale"


def test_status_is_down_when_onto_cannot_reach_it(tmp_path):
    client = _onto(tmp_path, code=spot.DOWN_EXIT, stderr="studio offline")
    got = client.status()
    assert (got["state"], got["detail"]) == ("down", "studio offline")


@pytest.mark.parametrize("status, line", [
    ({"state": "up", "build": "9.c", "want": "9.c", "detail": None}, "up at 9.c"),
    ({"state": "stale", "build": "8.b", "want": "9.c", "detail": None},
     "up at 8.b, rolls to 9.c on the next redraw"),
    ({"state": "down", "build": None, "want": "9.c", "detail": "offline"},
     "down: offline"),
])
def test_status_reads_as_one_line(status, line):
    assert spot.status_line(status) == line
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_lab_spot.py -q`
Expected: FAIL with `ImportError: cannot import name 'spot'`

- [ ] **Step 3: Implement the adapter**

Create `brick_icons/lab/spot.py`:

```python
"""The lab's line to the spot render worker, through `onto call`.

Every assumption about onto's CLI is a constant here (onto's services guide,
"Calling it"), so a change on onto's side changes this file and nothing else.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Callable

from .. import batch, build_of, commit_of, spot_protocol

BAD_REQUEST_EXIT = 65
DOWN_EXIT = 69
#: The process exited before replying; onto restarts it, and one retry is safe.
DIED_EXIT = 75
ROLL_FAILED_EXIT = 78
TIMEOUT_EXIT = 124
TIMEOUT_FLAG = "--timeout"
COMMIT_FLAG = "--commit"
#: How long a redraw may wait on a roll to a new commit (onto measured 1.1 s).
ROLL_WAIT_S = 30
CALL_TIMEOUT_S = batch.RENDER_TIMEOUT_S + ROLL_WAIT_S + 15
PING_TIMEOUT_S = 5
#: Past onto's own timeout, before the lab stops waiting for onto itself.
SLACK_S = 10
#: The revision the worker is told to draw at: pushed work only.
REVISION = "origin/main"

_FAILURES = {BAD_REQUEST_EXIT: "BadRequest", ROLL_FAILED_EXIT: "RollFailed",
             TIMEOUT_EXIT: "TimeoutError", DIED_EXIT: "ProcessDied"}


class SpotDown(Exception):
    """The service is not there to ask. Nothing was tried."""


class SpotError(Exception):
    """onto answered, but with no reply from the worker. `error` names why,
    as a reply's `error` would: `RollFailed`, `TimeoutError`, ..."""

    def __init__(self, detail: str, error: str = "SpotError"):
        super().__init__(detail)
        self.error = error


def _origin_main() -> tuple[str | None, str]:
    return commit_of(REVISION), build_of(REVISION)


class OntoSpot:
    def __init__(self, onto: str | None = None,
                 expected: Callable[[], tuple[str | None, str]] = _origin_main):
        self.onto = onto
        self.expected = expected
        self.slack_s = SLACK_S

    def _once(self, request: dict, timeout: float,
              commit: str | None) -> subprocess.CompletedProcess:
        onto = self.onto or shutil.which("onto")
        if onto is None:
            raise SpotDown("onto is not on the lab's PATH")
        argv = [onto, "call", TIMEOUT_FLAG, f"{int(timeout)}s",
                *([COMMIT_FLAG, commit] if commit else []),
                spot_protocol.NAME, "-"]
        try:
            return subprocess.run(argv, input=json.dumps(request),
                                  capture_output=True, text=True,
                                  timeout=timeout + self.slack_s)
        except FileNotFoundError:
            raise SpotDown(f"no onto at {onto}") from None
        except subprocess.TimeoutExpired:
            raise SpotError(f"no reply in {int(timeout)}s",
                            "TimeoutError") from None

    def call(self, request: dict, timeout: float, commit: str | None) -> dict:
        got = self._once(request, timeout, commit)
        if got.returncode == DIED_EXIT:
            got = self._once(request, timeout, commit)
        said = got.stderr.strip()
        if got.returncode == DOWN_EXIT:
            raise SpotDown(said or "the spot render service is down")
        if got.returncode != 0:
            raise SpotError(said or f"onto call exited {got.returncode}",
                            _FAILURES.get(got.returncode, "SpotError"))
        try:
            return json.loads(got.stdout)
        except json.JSONDecodeError:
            raise SpotError(f"onto call printed no JSON: {got.stdout[:200]!r}") from None

    def draw(self, request: dict, commit: str | None) -> dict:
        try:
            return spot_protocol.check_reply(
                self.call(request, CALL_TIMEOUT_S, commit))
        except ValueError as e:
            raise SpotError(str(e)) from None

    def status(self) -> dict:
        """Asked without a commit, so asking never rolls the worker."""
        _commit, want = self.expected()
        try:
            got = self.call(spot_protocol.ping(), PING_TIMEOUT_S, commit=None)
        except (SpotDown, SpotError) as e:
            return {"state": "down", "build": None, "want": want, "detail": str(e)}
        built = got.get("build") if isinstance(got, dict) else None
        return {"state": "up" if built == want else "stale", "build": built,
                "want": want, "detail": None}


def status_line(status: dict) -> str:
    if status["state"] == "down":
        return f"down: {status['detail']}"
    if status["state"] == "stale":
        return (f"up at {status['build']}, rolls to {status['want']} "
                f"on the next redraw")
    return f"up at {status['build']}"
```

- [ ] **Step 4: Add the stub the route tests use**

Append to `tests/conftest.py`:

```python
class StubSpot:
    """The spot worker as the lab sees it, answering from a script instead
    of through onto: `reply` is what a draw returns, `down` or `error` (with
    `error_kind`) make it raise instead, and `gate` holds a draw until set."""

    def __init__(self, reply=None, *, down=None, error=None,
                 error_kind="SpotError", status=None, want="9.ccccccc",
                 gate=None):
        self.reply, self.down, self.error = reply, down, error
        self.error_kind, self.want, self.gate = error_kind, want, gate
        self._status = status or {"state": "up", "build": want, "want": want,
                                  "detail": None}
        self.calls = []

    def expected(self):
        return ("c" * 40, self.want)

    def draw(self, request, commit):
        from brick_icons.lab import spot
        self.calls.append((request, commit))
        if self.gate is not None:
            self.gate.wait(5)
        if self.down:
            raise spot.SpotDown(self.down)
        if self.error:
            raise spot.SpotError(self.error, self.error_kind)
        return self.reply

    def status(self):
        return self._status


@pytest.fixture
def stub_spot():
    """The `StubSpot` class, to build one per test."""
    return StubSpot
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_lab_spot.py -q`
Expected: PASS (19 tests)

- [ ] **Step 6: Commit**

```bash
git add brick_icons/lab/spot.py tests/test_lab_spot.py tests/conftest.py
git commit -m "call the spot render worker through onto call"
```

---

### Task 12: Stop the fleet scripts reading the redraw queue

With every redraw drawn on the spot, nothing waits in the queue, so the
scripts that front-load or accept "pending" redraws go. This lands before
`requests.pending` is deleted (Task 15).

**Files:**
- Modify: `scripts/ingest-watch.py` (import at 54; `_take_renders` at 125-161; `watch` at ~304-336; `main` at ~415-438)
- Modify: `scripts/run-slot.sh` (lines 24-28 and the `ingest-watch.py` launch at ~145)
- Modify: `scripts/refill-slot.sh` (lines 59-68)
- Delete: `scripts/render-requests.py`
- Modify: `.claude/skills/render-corpus-batch/SKILL.md` (~237-239)
- Test: `tests/test_ingest_watch.py`

- [ ] **Step 1: Replace the tests of the requested-redraw path**

In `tests/test_ingest_watch.py`, delete
`test_a_requested_redraw_replaces_only_the_part_asked_for` and
`test_no_request_leaves_a_drawn_part_alone`, and add:

```python
def test_a_drawn_part_is_left_alone_without_overwrite(tree):
    root, conn = tree
    took, redrew, *_ = watch_mod._take_renders(
        conn, root / "out" / "store-restale-occt", "occt", "occt", 1)
    assert (took, redrew) == (1, 0)


def test_the_watch_takes_no_requested_flag():
    import inspect
    assert "requested" not in inspect.signature(watch_mod._take_renders).parameters
    assert "overwrite_requested" not in inspect.signature(watch_mod.watch).parameters
```

- [ ] **Step 2: Run the file to see the signature test fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_ingest_watch.py -q`
Expected: FAIL on `test_the_watch_takes_no_requested_flag`

- [ ] **Step 3: Strip the queue from ingest-watch**

In `scripts/ingest-watch.py`:

Delete `from brick_icons import requests as render_requests  # noqa: E402`.

Change the `_take_renders` signature to:

```python
def _take_renders(conn: sqlite3.Connection, tree: Path, engine: str,
                  source: str, run_id: int, overwrite: bool = False,
                  seen: dict[Path, tuple[int, float]] | None = None
                  ) -> tuple[int, int]:
```

Delete from its body:

```python
    # A redraw somebody asked for replaces the drawn part it names, and no
    # other drawn part a fill round happens to hold.
    asked = ({slot: set(render_requests.pending(
        conn, slot, ROOT / render_requests.DEFAULT_PATH))
        for _d, slot in walks} if requested else {})
```

and change

```python
        if pid not in known or (pid in have[slot] and not overwrite
                                and pid not in asked.get(slot, ())):
```

to

```python
        if pid not in known or (pid in have[slot] and not overwrite):
```

Change the `watch` signature's `fetch: bool = True, overwrite_requested: bool = False,`
line to `fetch: bool = True,` so it reads:

```python
def watch(trees: list[Path], every: int, once: bool, bake: bool,
          overwrite: bool = False, until: Sequence[str] = (),
          fetch: bool = True, measure: bool = False) -> int:
```

and its call to

```python
                drawn, redrew, slots = _take_renders(
                    conn, tree, engine, source, run_id, overwrite, drawings)
```

In `main`, delete the `ap.add_argument("--overwrite-requested", ...)` call with
its `help=`, and change the final call to:

```python
    return watch([Path(t) for t in a.trees], a.every, a.once, a.bake,
                 a.overwrite, until, a.fetch, a.measure)
```

- [ ] **Step 4: Strip it from the launch scripts**

In `scripts/run-slot.sh`, change `watch_flags=(--overwrite-requested)` to
`watch_flags=()`, and in the `ingest-watch.py` launch change
`"${watch_flags[@]}"` to `${watch_flags[@]+"${watch_flags[@]}"}` (macOS bash
3.2 treats an empty array as unbound under `set -u`).

In `scripts/refill-slot.sh`, replace

```bash
# Redraws somebody asked for go first, whatever the gap selection picked, and
# a round still launches when the gap itself is empty.
asked=$(.venv/bin/python scripts/render-requests.py pending --slot "$slot" \
    --into "$list")
requested=$(printf '%s\n' "$asked" | tail -1)
echo "requested redraws: $requested"
[ "$survey_rc" -eq 0 ] || [ "$requested" -gt 0 ] || exit "$survey_rc"
survey="$survey
$asked"
```

with

```bash
[ "$survey_rc" -eq 0 ] || exit "$survey_rc"
```

Delete the queue's shell front end:

```bash
git rm scripts/render-requests.py
```

In `.claude/skills/render-corpus-batch/SKILL.md`, change

```
not move. Add `--overwrite` at launch when the batch list came from parts that
are already drawn, or file the parts as redraw requests and use
`--overwrite-requested`.
```

to

```
not move. Add `--overwrite` at launch when the batch list came from parts that
are already drawn.
```

- [ ] **Step 5: Check the shell edits parse, and run the test file**

Run: `bash -n scripts/run-slot.sh && bash -n scripts/refill-slot.sh && PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_ingest_watch.py -q`
Expected: nothing from `bash -n`; PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/ingest-watch.py scripts/run-slot.sh scripts/refill-slot.sh \
  .claude/skills/render-corpus-batch/SKILL.md tests/test_ingest_watch.py
git commit -m "stop the fleet scripts reading the redraw queue"
```

---

### Task 13: Record the build a redraw asked for, and refuse every reference slot

**Files:**
- Modify: `brick_icons/requests.py` (`DRAWN_ELSEWHERE`; `add`)
- Test: `tests/test_requests.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_requests.py`:

```python
def test_a_request_records_the_build_it_asked_for(tmp_path):
    log = tmp_path / "requests.jsonl"
    requests.add(log, "3001", "occt", build="9.ccccccc")
    (record,) = requests.load(log)
    assert record["build"] == "9.ccccccc"


def test_every_reference_slot_is_drawn_elsewhere():
    assert set(requests.DRAWN_ELSEWHERE) == {
        "reference", "reference-gray", "reference-lines"}
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_requests.py -q -k "build_it_asked or drawn_elsewhere"`
Expected: FAIL with `TypeError: add() got an unexpected keyword argument 'build'`

- [ ] **Step 3: Implement**

In `brick_icons/requests.py`, replace

```python
#: Slots drawn by LDView or a browser, which nothing in this repository runs.
DRAWN_ELSEWHERE = ("reference", "ldview")
```

with

```python
#: Slots drawn by LDView or a browser, which nothing in this repository runs.
#: `db.is_reference_slot` decides which those are, so a new reference slot
#: is refused without a second list to remember.
DRAWN_ELSEWHERE = tuple(s for s in db.SOURCES if db.is_reference_slot(s))
```

and replace `add` with:

```python
def add(path: Path | str, part: str, source: str, by: str = "lab",
        at: str | None = None, build: str | None = None) -> dict:
    """`build` is the one the redraw asked the worker to draw at."""
    record = {"part": part, "source": source, "at": at or db.now(), "by": by}
    if build is not None:
        record["build"] = build
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    return record
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_requests.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brick_icons/requests.py tests/test_requests.py
git commit -m "record a redraw's build, and refuse all 3 reference slots"
```

---

### Task 14: Redraw on the spot worker

**Built differently from the steps below; `brick_icons/lab/redraw.py` and
`tests/test_lab_redraw.py` are the record.** Decided after this plan was
written: `changed` goes out as soon as the drawing is stored and its attempt
recorded, carrying `{part, source, sha, build}` and no sheet versions. The
sheet patch (`bake_part` + `patch_cell`, about 4.5 s) runs afterwards on the
app's `SheetPatches` executor, one worker per slot, and publishes
`sheets {part, source, versions}` when it lands. The redraw answer carries no
`sheet_version`.

The route checks the ask, then runs one redraw under single-flight.
`brick_icons/lab/redraw.py` holds the redraw itself, so `app.py` stays routes
only. Every outcome is a `state` in a 200 body; only a refused ask is an HTTP
error.

| outcome | `state` | attempts row | render row | sheets | event |
|---|---|---|---|---|---|
| drew a new drawing | `stored` | `stored`, secs | replaced | baked and patched in the background | `changed`, then `sheets` |
| drew the same bytes | `unchanged` | `stored`, secs | `made_at` refreshed | untouched | none |
| engine raised or timed out | `failed` | error, detail, secs | untouched | untouched | none |
| a decal with nothing to draw | `none` | `none`, secs | untouched | untouched | none |
| service down | `down` | none | untouched | untouched | none |
| roll failed, call timed out, died twice | `failed` (`RollFailed`, `TimeoutError`, `ProcessDied`) | none | untouched | untouched | none |
| sheet patch failed | `stored` | `stored` | replaced | a warning in the log | `changed` only |

A spot redraw files no measurement, so the part detail's `build` for a slot
(which the lightbox's age tag shows) comes from the spot run when the slot's
render came from one.

**Files:**
- Create: `brick_icons/lab/redraw.py`
- Modify: `brick_icons/lab/app.py` (imports; `create_app`; `get_corpus_part`; `post_redraw`; `get_sheet`; new `/api/spot` routes)
- Modify: `tests/test_lab_app.py` (delete the redraw tests and `_redraw_client`)
- Test: `tests/test_lab_redraw.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lab_redraw.py`:

```python
"""A redraw, from the button's POST to the event the page hears."""
import json
import logging
import threading

import pytest
from fastapi.testclient import TestClient

from brick_icons import db, goldens, spot_protocol, thumbs
from brick_icons.lab import app as lab_app
from brick_icons.lab import cache

OLD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
       '<rect x="0" y="0" width="256" height="170" fill="black"/></svg>')
NEW = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
       '<circle cx="128" cy="85" r="60" fill="black"/></svg>')


def _drawn(svg=NEW, secs=4.2):
    return spot_protocol.reply(svg=svg, secs=secs, build="9.ccccccc",
                               state="drawn")


@pytest.fixture
def lab(tmp_path):
    """`lab(spot, sheets=False)`: a client over a corpus of 3001 and 3002,
    3001 already drawn in occt, and the events it publishes."""
    conn = db.connect(tmp_path / "corpus.db")
    for pid in ("3001", "3002"):
        conn.execute("INSERT INTO parts (id, title, category, printed, "
                     "obsolete, status) VALUES (?, 'Brick', 'Brick', 0, 0, "
                     "'good')", (pid,))
    held = tmp_path / "renders" / "occt" / "3001.svg"
    held.parent.mkdir(parents=True)
    held.write_text(OLD)
    conn.execute("INSERT INTO renders (part_id, source, config_key, made_at, "
                 "path, sha256) VALUES ('3001', 'occt', ?, "
                 "'2020-01-01T00:00:00+00:00', 'renders/occt/3001.svg', ?)",
                 (cache.key(db.canonical_argv("3001", "occt")),
                  goldens.sha256(OLD.encode())))
    conn.commit()
    conn.close()

    def make(spot, sheets=False):
        slot = tmp_path / "thumbs" / "occt"
        if sheets:
            thumbs.bake_part("3001", held, slot, sha="old")
            thumbs.compose(slot, ["3001", "3002"])
        app = lab_app.create_app(
            root=tmp_path, cache_root=tmp_path / "cache",
            corpus_db=tmp_path / "corpus.db", thumbs_root=tmp_path / "thumbs",
            requests_path=tmp_path / "requests.jsonl",
            review_path=tmp_path / "review.jsonl", spot=spot)
        heard = []
        app.state.events.subscribe(lambda kind, data: heard.append((kind, data)))
        return TestClient(app), heard
    return make


def _redraw(client, part="3001", source="occt"):
    r = client.post("/api/corpus/redraw", json={"part": part, "source": source})
    assert r.status_code == 200, r.text
    return r.json()


def _one(tmp_path, sql, *args):
    conn = db.connect(tmp_path / "corpus.db")
    try:
        return conn.execute(sql, args).fetchone()
    finally:
        conn.close()


def test_a_new_drawing_is_stored_timed_and_announced(lab, stub_spot, tmp_path):
    client, heard = lab(stub_spot(_drawn()), sheets=True)
    body = _redraw(client)
    sha = goldens.sha256(NEW.encode())
    assert (body["state"], body["sha"], body["secs"]) == ("stored", sha, 4.2)
    assert (tmp_path / "renders" / "occt" / "3001.svg").read_text() == NEW
    assert _one(tmp_path, "SELECT sha256 FROM renders WHERE part_id = '3001' "
                          "AND source = 'occt'")[0] == sha
    assert tuple(_one(tmp_path, "SELECT state, secs, error FROM attempts")) == \
        ("stored", 4.2, None)
    (kind, data), = heard
    assert kind == "changed"
    assert (data["part"], data["source"], data["sha"]) == ("3001", "occt", sha)
    manifest = json.loads((tmp_path / "thumbs" / "occt" / "sheet-32.json").read_text())
    assert data["sheet_version"]["32"] == manifest["version"]
    assert manifest["baked"]["3001"] == sha


def test_the_wall_s_delta_carries_the_new_sha(lab, stub_spot):
    client, _ = lab(stub_spot(_drawn()))
    since = client.get("/api/corpus/cells", params={"source": "occt"}).json()["version"]
    body = _redraw(client)
    delta = client.get("/api/corpus/cells",
                       params={"source": "occt", "since": since}).json()
    assert [(c["id"], c["sha"]) for c in delta["cells"]] == [("3001", body["sha"])]


def test_the_worker_is_asked_for_the_slot_s_own_argv_at_origin_main(
        lab, stub_spot, tmp_path):
    spot = stub_spot(_drawn())
    client, _ = lab(spot)
    _redraw(client)
    ((req, commit),) = spot.calls
    assert req == spot_protocol.request("3001", "occt",
                                        db.canonical_argv("3001", "occt"),
                                        build="9.ccccccc")
    assert commit == "c" * 40
    (asked,) = [json.loads(l) for l in
                (tmp_path / "requests.jsonl").read_text().splitlines()]
    assert (asked["part"], asked["source"], asked["build"]) == \
        ("3001", "occt", "9.ccccccc")


def test_the_same_bytes_are_unchanged_and_announce_nothing(lab, stub_spot, tmp_path):
    client, heard = lab(stub_spot(_drawn(OLD)), sheets=True)
    was = (tmp_path / "thumbs" / "occt" / "sheet-32.json").read_text()
    assert _redraw(client)["state"] == "unchanged"
    assert heard == []
    assert _one(tmp_path, "SELECT made_at FROM renders")[0] > "2020-01-01"
    assert (tmp_path / "thumbs" / "occt" / "sheet-32.json").read_text() == was
    assert _one(tmp_path, "SELECT state FROM attempts")[0] == "stored"


def test_a_timeout_is_an_attempt_and_leaves_the_drawing(lab, stub_spot, tmp_path):
    reply = spot_protocol.reply(secs=150.3, build="9.ccccccc",
                                error="TimeoutError", detail="exceeded 150s")
    client, heard = lab(stub_spot(reply))
    body = _redraw(client)
    assert (body["state"], body["error"]) == ("failed", "TimeoutError")
    assert tuple(_one(tmp_path, "SELECT state, secs, error FROM attempts")) == \
        (None, 150.3, "TimeoutError")
    assert (tmp_path / "renders" / "occt" / "3001.svg").read_text() == OLD
    assert heard == []


def test_a_decal_with_nothing_to_draw_is_recorded_as_none(lab, stub_spot, tmp_path):
    reply = spot_protocol.reply(secs=1.0, build="9.ccccccc", state="none")
    client, heard = lab(stub_spot(reply))
    assert _redraw(client, source="decal")["state"] == "none"
    assert _one(tmp_path, "SELECT state FROM attempts")[0] == "none"
    assert heard == []


def test_a_down_service_is_said_and_tries_nothing(lab, stub_spot, tmp_path):
    client, heard = lab(stub_spot(down="no such service"))
    body = _redraw(client)
    assert (body["state"], body["detail"]) == ("down", "no such service")
    assert _one(tmp_path, "SELECT count(*) FROM attempts")[0] == 0
    assert heard == []


def test_a_failed_roll_is_a_failure_in_onto_s_words(lab, stub_spot, tmp_path):
    client, _ = lab(stub_spot(error="checkout cccc: uv sync failed",
                              error_kind="RollFailed"))
    body = _redraw(client)
    assert (body["state"], body["error"], body["detail"]) == \
        ("failed", "RollFailed", "checkout cccc: uv sync failed")
    assert _one(tmp_path, "SELECT count(*) FROM attempts")[0] == 0


def test_a_sheet_that_cannot_be_patched_still_stores_the_drawing(
        lab, stub_spot, caplog):
    client, heard = lab(stub_spot(_drawn()), sheets=False)
    with caplog.at_level(logging.WARNING):
        body = _redraw(client)
    assert body["state"] == "stored"
    assert body["sheet_version"] is None
    assert "the next bake repairs them" in caplog.text
    (_kind, data), = heard
    assert data["sheet_version"] is None


def test_a_second_click_joins_the_first(lab, stub_spot, concurrently):
    gate = threading.Event()
    spot = stub_spot(_drawn(), gate=gate)
    client, heard = lab(spot)
    threading.Timer(0.5, gate.set).start()
    got = concurrently(2, lambda: _redraw(client))
    assert len(spot.calls) == 1
    assert got[0] == got[1]
    assert len(heard) == 1


@pytest.mark.parametrize("source", ["reference", "reference-gray",
                                    "reference-lines"])
def test_a_reference_slot_refuses_a_redraw(lab, stub_spot, source):
    client, _ = lab(stub_spot(_drawn()))
    r = client.post("/api/corpus/redraw", json={"part": "3001", "source": source})
    assert r.status_code == 400


def test_a_redraw_of_an_unknown_part_is_404(lab, stub_spot):
    client, _ = lab(stub_spot(_drawn()))
    r = client.post("/api/corpus/redraw", json={"part": "9999", "source": "occt"})
    assert r.status_code == 404


def test_the_status_route_passes_the_worker_s_state_through(lab, stub_spot):
    status = {"state": "stale", "build": "8.bbbbbbb", "want": "9.ccccccc",
              "detail": None}
    client, _ = lab(stub_spot(status=status))
    assert client.get("/api/spot").json() == status
    assert client.get("/api/spot/status.txt").text == \
        "up at 8.bbbbbbb, rolls to 9.ccccccc on the next redraw"


def test_a_sheet_manifest_is_served_with_its_own_version(lab, stub_spot, tmp_path):
    client, _ = lab(stub_spot(_drawn()), sheets=True)
    manifest = json.loads((tmp_path / "thumbs" / "occt" / "sheet-8.json").read_text())
    assert client.get("/api/thumbs/occt/sheet-8.json").json()["version"] == \
        manifest["version"]


def test_the_part_detail_names_the_spot_build_and_no_queue(lab, stub_spot):
    client, _ = lab(stub_spot(_drawn()))
    _redraw(client)
    slots = {s["source"]: s for s in
             client.get("/api/corpus/part/3001").json()["slots"]}
    assert slots["occt"]["build"] == "9.ccccccc"
    assert all("requested_at" not in s for s in slots.values())
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_lab_redraw.py -q`
Expected: FAIL with `TypeError: create_app() got an unexpected keyword argument 'spot'`

- [ ] **Step 3: Write the redraw module**

Create `brick_icons/lab/redraw.py`:

```python
"""One redraw: ask the spot worker, store what it drew, bring the wall up to
date, and say so.

Every outcome is a `state` the lightbox reads: stored, unchanged, none,
failed or down. An ask the lab refuses before calling is the route's
business, not this module's.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .. import db, goldens, spot_protocol, thumbs
from .. import requests as render_requests
from .events import Broker
from .spot import SpotDown, SpotError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Where:
    corpus_db: Path
    root: Path
    thumbs_root: Path
    requests_path: Path
    #: Where a reply's SVG waits to be copied into the store; emptied as it goes.
    scratch: Path


def redraw(part: str, source: str, spot, events: Broker, where: Where) -> dict:
    commit, want = spot.expected()
    render_requests.add(where.requests_path, part, source, build=want)
    request = spot_protocol.request(part, source, db.canonical_argv(part, source),
                                    build=want)
    try:
        reply = spot.draw(request, commit)
    except SpotDown as e:
        return {"state": "down", "detail": str(e)}
    except SpotError as e:
        return {"state": "failed", "error": e.error, "detail": str(e)}
    conn = db.connect(where.corpus_db)
    try:
        run_id = db.spot_run(conn, reply["build"], part, source)
        try:
            return _take(conn, run_id, part, source, reply, events, where)
        finally:
            db.finish_run(conn, run_id)
    finally:
        conn.close()


def _take(conn, run_id: int, part: str, source: str, reply: dict,
          events: Broker, where: Where) -> dict:
    tried = {"part": part, "source": source, "secs": reply["secs"],
             "error": reply["error"], "detail": reply["detail"]}
    said = {"secs": reply["secs"], "build": reply["build"]}
    if reply["error"] is not None:
        db.record_attempt(conn, run_id, {**tried, "state": None})
        return {"state": "failed", "error": reply["error"],
                "detail": reply["detail"], **said}
    if reply["state"] == "none":
        db.record_attempt(conn, run_id, {**tried, "state": "none"})
        return {"state": "none", **said}
    data = reply["svg"].encode()
    sha = goldens.sha256(data)
    held = conn.execute("SELECT sha256 FROM renders WHERE part_id = ? "
                        "AND source = ?", (part, source)).fetchone()
    db.record_attempt(conn, run_id, {**tried, "state": "stored"})
    if held is not None and held["sha256"] == sha:
        db.touch_render(conn, part, source)
        return {"state": "unchanged", "sha": sha, **said}
    where.scratch.mkdir(parents=True, exist_ok=True)
    made = where.scratch / f"{part}.{source}.svg"
    made.write_bytes(data)
    try:
        dest = db.store_render(conn, part, source, made, root=where.root,
                               run_id=run_id)
    finally:
        made.unlink(missing_ok=True)
    sheets = _patch_wall(conn, part, source, dest, sha, where)
    events.publish("changed", {"part": part, "source": source, "sha": sha,
                               "sheet_version": sheets})
    return {"state": "stored", "sha": sha, "sheet_version": sheets, **said}


def _patch_wall(conn, part: str, source: str, dest: Path, sha: str,
                where: Where) -> dict[str, str] | None:
    """The part's tiles, then its cell on the slot's sheets and their masks.
    A failure is a warning: the drawing is stored, and the next full bake
    draws the sheets from the store."""
    index = conn.execute("SELECT count(*) FROM parts WHERE id < ?",
                         (part,)).fetchone()[0]
    count = conn.execute("SELECT count(*) FROM parts").fetchone()[0]
    slot = where.thumbs_root / source
    try:
        thumbs.bake_part(part, dest, slot, sha)
        versions = thumbs.patch_cell(slot, part, index, count)
        masks = slot / thumbs.MASK_DIR
        if thumbs.has_sheets(masks):
            thumbs.patch_cell(masks, part, index, count)
    except Exception as e:                              # noqa: BLE001
        log.warning("%s in %s is stored, but its sheets were not patched "
                    "(%s: %s); the next bake repairs them",
                    part, source, type(e).__name__, e)
        return None
    return {str(level): v for level, v in versions.items()}
```

- [ ] **Step 4: Rewrite the routes**

In `brick_icons/lab/app.py`:

- change `from fastapi.responses import (FileResponse, JSONResponse, Response, StreamingResponse)` to
  `from fastapi.responses import (FileResponse, PlainTextResponse, Response, StreamingResponse)` (`JSONResponse` served only the manifest route being rewritten);
- in `from . import (...)`, remove `store` and add `redraw as redraw_mod` and `spot as spot_client` (`jobs` and `runner` stay, for the other routes);
- add `spot=None` as the last parameter of `create_app`, and after `app.state.review_path = ...` add:

```python
    app.state.spot = spot if spot is not None else spot_client.OntoSpot()
```

- in `get_corpus_part`, right after the `builds = {...}` comprehension, add:

```python
            # A spot redraw files no measurement; its run carries the build
            # the worker drew at, and its render is the newer drawing.
            builds.update({r["source"]: r["commit_sha"] for r in conn.execute(
                "SELECT r.source, ru.commit_sha FROM renders r "
                "JOIN runs ru ON ru.id = r.run_id WHERE r.part_id = ? "
                "AND json_extract(ru.args, '$.via') = 'spot'", (part_id,))})
```

- in `get_corpus_part`, delete

```python
            asked = render_requests.pending_for(conn, part_id,
                                                app.state.requests_path)
```

and

```python
            slot["requested_at"] = asked.get(slot["source"])
```

(the loop keeps `slot.update(states[slot["source"]])`);

- replace the whole `post_redraw` route with:

```python
    @app.post("/api/corpus/redraw")
    def post_redraw(req: RedrawRequest):
        """Draw a part again in one slot on the fleet's spot worker. A second
        ask for the same part and slot while one is out joins it."""
        _check_source(req.source)
        if req.source in render_requests.DRAWN_ELSEWHERE:
            raise HTTPException(400, f"{req.source} is not drawn by this "
                                     f"repository")
        conn = corpus_conn()
        try:
            if conn.execute("SELECT 1 FROM parts WHERE id = ?",
                            (req.part,)).fetchone() is None:
                raise HTTPException(404, "no such part")
        finally:
            conn.close()
        where = redraw_mod.Where(
            corpus_db=Path(app.state.corpus_db), root=Path(app.state.root),
            thumbs_root=Path(app.state.thumbs_root),
            requests_path=Path(app.state.requests_path),
            scratch=Path(app.state.cache_root) / "spot")
        return app.state.flights.run(
            ("redraw", req.part, req.source),
            lambda: redraw_mod.redraw(req.part, req.source, app.state.spot,
                                      app.state.events, where))

    @app.get("/api/spot")
    def get_spot():
        """The spot worker: up at origin/main's build, up at another (the
        next redraw rolls it), or down."""
        return app.state.spot.status()

    @app.get("/api/spot/status.txt", response_class=PlainTextResponse)
    def get_spot_line():
        """The same, as the one line `brick-lab stat` prints."""
        return spot_client.status_line(app.state.spot.status())
```

- in `get_sheet`, replace the `if ext == "json":` block with:

```python
        if ext == "json":
            path = slot / f"sheet-{level}.json"
            if not path.is_file():
                raise HTTPException(404, "no such sheet manifest")
            # The manifest carries its own version, bumped with every write of
            # the image, so a browser holding an older atlas refetches it.
            return FileResponse(path, media_type="application/json")
```

- [ ] **Step 5: Delete the old redraw tests**

In `tests/test_lab_app.py`, delete `_redraw_client`,
`test_a_cheap_redraw_draws_now_rather_than_queueing`,
`test_a_slow_redraw_is_queued_and_the_part_says_so`,
`test_a_slot_drawn_elsewhere_refuses_a_redraw` and
`test_a_redraw_of_an_unknown_part_is_404` (the block starting at
`def _redraw_client`). The last two are covered in `tests/test_lab_redraw.py`.

- [ ] **Step 6: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_lab_redraw.py -q`
Expected: PASS (17 tests). `tests/test_lab_app.py` is covered by the fleet run
in Task 25.

- [ ] **Step 7: Commit**

```bash
git add brick_icons/lab/redraw.py brick_icons/lab/app.py \
  tests/test_lab_redraw.py tests/test_lab_app.py
git commit -m "redraw on the fleet's spot worker and patch the wall's cell"
```

---

### Task 15: Remove the redraw queue

Nothing calls `pending`, `pending_for`, `cost`, `draws_here`, `front_load` or
`LOCAL_MAX_SECS` any more (Tasks 12 and 14). The log stays, as a record the
review queue links displacements to (`review_api.linked_request`). The design
doc for the queue describes something that no longer exists.

**Files:**
- Modify: `brick_icons/requests.py`
- Delete: `docs/superpowers/specs/2026-09-13-render-requests-design.md`
- Test: `tests/test_requests.py`

- [ ] **Step 1: Confirm nothing else calls the queue**

Run: `grep -rnE "pending_for|requests\.pending|render_requests\.pending|requests\.cost|draws_here|front_load|LOCAL_MAX_SECS" --include='*.py' --include='*.sh' brick_icons scripts tests`
Expected: matches only in `brick_icons/requests.py` and `tests/test_requests.py`.

- [ ] **Step 2: Rewrite the tests**

Replace the whole of `tests/test_requests.py` with:

```python
"""The redraw log: what was asked for, when, and at which build."""
from brick_icons import requests


def test_a_request_is_read_back_as_written(tmp_path):
    log = tmp_path / "requests.jsonl"
    requests.add(log, "3001", "occt", at="2026-09-10T00:00:00+00:00")
    assert requests.load(log) == [{"part": "3001", "source": "occt",
                                   "at": "2026-09-10T00:00:00+00:00",
                                   "by": "lab"}]


def test_a_torn_line_does_not_break_the_log(tmp_path):
    log = tmp_path / "requests.jsonl"
    requests.add(log, "3001", "occt")
    with log.open("a") as fh:
        fh.write('{"part": "3004", "sour')
    assert [r["part"] for r in requests.load(log)] == ["3001"]


def test_no_log_is_no_requests(tmp_path):
    assert requests.load(tmp_path / "absent.jsonl") == []


def test_a_request_records_the_build_it_asked_for(tmp_path):
    log = tmp_path / "requests.jsonl"
    requests.add(log, "3001", "occt", build="9.ccccccc")
    (record,) = requests.load(log)
    assert record["build"] == "9.ccccccc"


def test_every_reference_slot_is_drawn_elsewhere():
    assert set(requests.DRAWN_ELSEWHERE) == {
        "reference", "reference-gray", "reference-lines"}


def test_the_queue_is_gone():
    for name in ("pending", "pending_for", "cost", "draws_here", "front_load",
                 "LOCAL_MAX_SECS"):
        assert not hasattr(requests, name), name
```

- [ ] **Step 3: Run the tests to see the last one fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_requests.py -q`
Expected: FAIL on `test_the_queue_is_gone` (`pending`)

- [ ] **Step 4: Rewrite the module**

Replace the whole of `brick_icons/requests.py` with:

```python
"""Parts somebody asked a slot to draw again: part, slot, when, by whom, and
the build the redraw asked for.

A record, not a queue: every redraw is drawn at once by the spot worker. The
review queue links a displaced drawing to the ask that caused it
(`lab.review_api.linked_request`). An append-only JSONL log rather than a
`corpus.db` table, because `census-ingest.sh` rebuilds the database from the
render trees, and a request is in no tree.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import db

DEFAULT_PATH = Path("store-queue") / "requests.jsonl"

#: Slots drawn by LDView or a browser, which nothing in this repository runs.
#: `db.is_reference_slot` decides which those are, so a new reference slot
#: is refused without a second list to remember.
DRAWN_ELSEWHERE = tuple(s for s in db.SOURCES if db.is_reference_slot(s))


def add(path: Path | str, part: str, source: str, by: str = "lab",
        at: str | None = None, build: str | None = None) -> dict:
    """`build` is the one the redraw asked the worker to draw at."""
    record = {"part": part, "source": source, "at": at or db.now(), "by": by}
    if build is not None:
        record["build"] = build
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    return record


def load(path: Path | str) -> list[dict]:
    """Every request, oldest first. A torn last line from a writer that died
    mid-append is skipped rather than failing every reader."""
    path = Path(path)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict) and {"part", "source", "at"} <= r.keys():
            out.append(r)
    return out
```

Then delete the superseded design doc:

```bash
git rm docs/superpowers/specs/2026-09-13-render-requests-design.md
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_requests.py -q`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add brick_icons/requests.py tests/test_requests.py
git commit -m "remove the redraw queue, keeping its log as a record"
```

---

### Task 16: `brick-lab stat` reports the worker

The lab API agent's PATH lacks `~/.local/bin`, where `onto` lives on this Mac,
so the adapter could never find it under launchd. `$bin` (where `install`
links `brick-lab`, `~/.local/bin` by default) joins the PATH.

**Files:**
- Modify: `scripts/lab-agents.sh` (the `PATH` string in `plist()`; the comment in `write()`; a `spot()` helper; the `stat)` case)
- Test: `tests/test_lab_agents.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lab_agents.py`:

```python
def test_the_agents_find_onto_where_install_links_brick_lab(home):
    tmp_path, env = home
    assert run(SCRIPT, "plists", env).returncode == 0
    path = agent(tmp_path, API)["EnvironmentVariables"]["PATH"].split(":")
    assert path[1] == str(tmp_path / "bin")


def _curl(tmp_path, body):
    curl = tmp_path / "nodebin" / "curl"
    curl.write_text(body)
    curl.chmod(0o755)


def _spot_line(stdout):
    (line,) = [l for l in stdout.splitlines() if l.startswith("spot render")]
    return line


def test_stat_reports_the_spot_worker(home):
    tmp_path, env = home
    _curl(tmp_path, "#!/bin/sh\n"
                    "case \"$*\" in\n"
                    "  */api/spot/status.txt*) printf 'up at 9.ccccccc' ;;\n"
                    "  *) printf '200' ;;\n"
                    "esac\n")
    got = run(SCRIPT, "stat", env)
    assert got.returncode == 0, got.stderr
    assert _spot_line(got.stdout).endswith("up at 9.ccccccc")


def test_stat_says_so_when_the_api_cannot_be_asked(home):
    tmp_path, env = home
    _curl(tmp_path, "#!/bin/sh\nexit 7\n")
    got = run(SCRIPT, "stat", env)
    assert _spot_line(got.stdout).endswith("unknown: the api did not answer")
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_lab_agents.py -q`
Expected: FAIL on the three new tests

- [ ] **Step 3: Implement**

In `scripts/lab-agents.sh`, in `plist()`, change

```
		<string>$nodedir:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
```

to

```
		<string>$nodedir:$bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
```

In `write()`, change the comment `# launchd starts with almost no PATH, and vite is a node shebang.` to

```sh
  # launchd starts with almost no PATH: vite is a node shebang, and the API
  # calls onto, which lives beside brick-lab in $bin.
```

After `answers()`, add:

```sh
spot() { # the spot render worker, as the API sees it
  line=$(curl -s -m 8 "http://127.0.0.1:$api_port/api/spot/status.txt") || line=
  echo "${line:-unknown: the api did not answer}"
}
```

In the `stat)` case, after the `front answers` line, add:

```sh
    printf '%-45s %s\n' 'spot render' "$(spot)"
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_lab_agents.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/lab-agents.sh tests/test_lab_agents.py
git commit -m "report the spot render worker in brick-lab stat"
```

---

### Task 17: Take pezlie 0.3.0

**Files:**
- Modify: `lab/package.json`, `lab/package-lock.json`
- Test: `lab/src/wall/BrickWall.test.tsx`, `lab/src/wall/host.test.ts` (existing, unchanged)

- [ ] **Step 1: Take the release**

Run: `cd lab && npm install pezlie@^0.3.0`
Expected: `package.json` names `"pezlie": "^0.3.0"`, and the lockfile moves with it.

- [ ] **Step 2: Run the wall's tests and the typecheck**

Run: `cd lab && npx vitest run src/wall && npm run typecheck`
Expected: PASS; clean. 0.3.0 changes `Sheet.image` to `SheetImage`
(an image or a canvas); the lab reads its own `useSheets`, not pezlie's, so
nothing here should notice. If the typecheck names a file, fix that file's
use to accept `HTMLImageElement | HTMLCanvasElement`.

- [ ] **Step 3: Commit**

Use `prepare-js-commit`, then:

```bash
git add lab/package.json lab/package-lock.json
git commit -m "take pezlie 0.3.0"
```

---

### Task 18: The client's redraw states, status and events

`useChanged` is the one way a page hears redraws. It batches: the first event
starts a quarter-second window, and every event in it arrives in one call.
pezlie's wall copies every sheet level on each poll that moves a sha, so a
burst of redraws must become one poll.

**Files:**
- Modify: `lab/src/api/types.ts` (append types)
- Modify: `lab/src/api/client.ts` (imports; `redraw`; add `spotStatus`, `onChanged`)
- Create: `lab/src/api/useChanged.ts`
- Test: `lab/src/api/client.test.ts`, `lab/src/api/useChanged.test.ts` (create)

- [ ] **Step 1: Write the failing tests**

Append inside the `describe('createClient', ...)` block of `lab/src/api/client.test.ts`:

```ts
  it('asks the spot worker how it is', async () => {
    const status = { state: 'stale', build: '8.b', want: '9.c', detail: null };
    const fetchImpl = stub({ '/api/spot': status });
    const api = createClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    expect(await api.spotStatus()).toEqual(status);
  });

  it('posts a redraw and returns its state', async () => {
    const fetchImpl = stub({ '/api/corpus/redraw': { state: 'unchanged', sha: 'ab' } });
    const api = createClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    expect((await api.redraw('3001', 'occt')).state).toBe('unchanged');
    const init = fetchImpl.mock.calls[0]![1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({ part: '3001', source: 'occt' });
  });

  it('hears changed events until told to stop', () => {
    const made: FakeEvents[] = [];
    class FakeEvents {
      listeners: Record<string, (e: MessageEvent) => void> = {};
      closed = false;
      constructor(public url: string) { made.push(this); }
      addEventListener(kind: string, f: (e: MessageEvent) => void) { this.listeners[kind] = f; }
      close() { this.closed = true; }
    }
    vi.stubGlobal('EventSource', FakeEvents);
    const api = createClient({ fetchImpl: stub({}) as unknown as typeof fetch });
    const heard: unknown[] = [];
    const stop = api.onChanged((e) => heard.push(e));
    expect(made[0]!.url).toBe('/api/events');
    const event = { part: '3001', source: 'occt', sha: 'ab', build: '9.c' };
    made[0]!.listeners.changed!({ data: JSON.stringify(event) } as MessageEvent);
    expect(heard).toEqual([event]);
    stop();
    expect(made[0]!.closed).toBe(true);
    vi.unstubAllGlobals();
  });
```

Create `lab/src/api/useChanged.test.ts`:

```ts
import { afterEach, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import type { ChangedEvent } from '@lab/api/types';
import { CHANGED_BATCH_MS, useChanged } from '@lab/api/useChanged';

afterEach(() => vi.useRealTimers());

const event = (part: string): ChangedEvent =>
  ({ part, source: 'occt', sha: `${part}-sha`, build: '9.c' });

function source() {
  let tell: (e: ChangedEvent) => void = () => {};
  const stop = vi.fn();
  const client = { onChanged: vi.fn((f: (e: ChangedEvent) => void) => { tell = f; return stop; }) };
  return { client, stop, tell: (e: ChangedEvent) => tell(e) };
}

it('hands a burst of events over as one batch', () => {
  vi.useFakeTimers();
  const { client, tell } = source();
  const batches: ChangedEvent[][] = [];
  renderHook(() => useChanged(client, (b) => batches.push(b)));
  tell(event('3001'));
  tell(event('3002'));
  vi.advanceTimersByTime(CHANGED_BATCH_MS - 1);
  expect(batches).toEqual([]);
  tell(event('3003'));
  vi.advanceTimersByTime(1);
  expect(batches.map((b) => b.map((e) => e.part))).toEqual([['3001', '3002', '3003']]);
});

it('does not let a steady stream hold a batch back', () => {
  vi.useFakeTimers();
  const { client, tell } = source();
  const batches: ChangedEvent[][] = [];
  renderHook(() => useChanged(client, (b) => batches.push(b)));
  for (let i = 0; i < 10; i++) {
    tell(event(`p${i}`));
    vi.advanceTimersByTime(CHANGED_BATCH_MS / 2);
  }
  expect(batches.length).toBeGreaterThanOrEqual(4);
});

it('stops listening and drops a pending batch on unmount', () => {
  vi.useFakeTimers();
  const { client, stop, tell } = source();
  const batches: ChangedEvent[][] = [];
  const { unmount } = renderHook(() => useChanged(client, (b) => batches.push(b)));
  tell(event('3001'));
  unmount();
  vi.advanceTimersByTime(CHANGED_BATCH_MS);
  expect(stop).toHaveBeenCalled();
  expect(batches).toEqual([]);
});

it('is quiet for a client that cannot listen', () => {
  expect(() => renderHook(() => useChanged({}, () => {}))).not.toThrow();
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd lab && npx vitest run src/api/client.test.ts src/api/useChanged.test.ts`
Expected: FAIL (`api.spotStatus is not a function`; `@lab/api/useChanged` not found)

- [ ] **Step 3: Add the types and client methods**

Append to `lab/src/api/types.ts`:

```ts
/** How a redraw ended. Every outcome is one of these in a 200 body; only an
 *  ask the server refuses outright is an HTTP error. */
export type RedrawState = 'stored' | 'unchanged' | 'none' | 'failed' | 'down';

export interface RedrawAnswer {
  state: RedrawState;
  sha?: string;
  secs?: number | null;
  build?: string | null;
  /** Why it failed, as a type name: `TimeoutError`, `RollFailed`, ... */
  error?: string | null;
  detail?: string | null;
}

/** The spot worker as the lab API sees it. `stale` is up but on another
 *  build than origin/main, so the next redraw rolls it first. */
export interface SpotStatus {
  state: 'up' | 'stale' | 'down';
  build: string | null;
  want: string;
  detail: string | null;
}

/** A redraw stored, published on `/api/events`. Its slot's sheets are
 *  patched afterwards, announced by a `SheetsEvent`. */
export interface ChangedEvent {
  part: string;
  source: string;
  sha: string;
  build: string;
}

/** A slot's sheets patched with a redrawn cell: each level's new version. */
export interface SheetsEvent {
  part: string;
  source: string;
  versions: Record<string, string>;
}
```

In `lab/src/api/client.ts`, change the first import to:

```ts
import type { Artifact, ChangedEvent, JobState, LabConfig, LdrawColor, PartHit,
  RedrawAnswer, RenderResult, SchemaField, SpotStatus } from '@lab/api/types';
```

and replace the `redraw` method (with its comment) with:

```ts
    /** Draw a part again in one slot, on the fleet's spot worker. */
    async redraw(part: string, source: string): Promise<RedrawAnswer> {
      return json<RedrawAnswer>(
        fetchImpl, at('/api/corpus/redraw'), post('/api/corpus/redraw', { part, source }));
    },

    async spotStatus(): Promise<SpotStatus> {
      return json<SpotStatus>(fetchImpl, at('/api/spot'));
    },

    /** Every stored redraw, as it lands. Returns the unsubscribe. Prefer
     *  `useChanged`, which batches them. */
    onChanged(listener: (event: ChangedEvent) => void): () => void {
      if (typeof EventSource === 'undefined') return () => {};
      const events = new EventSource(at('/api/events'));
      events.addEventListener('changed', (e) => {
        listener(JSON.parse((e as MessageEvent<string>).data) as ChangedEvent);
      });
      return () => events.close();
    },
```

- [ ] **Step 4: Write the hook**

Create `lab/src/api/useChanged.ts`:

```ts
import { useEffect, useRef } from 'react';
import type { ChangedEvent } from '@lab/api/types';

/** How long the first event of a burst waits for the rest. pezlie's wall
 *  copies every sheet level on each poll that moves a sha, so ten redraws
 *  landing together must be one poll, not ten. */
export const CHANGED_BATCH_MS = 250;

interface Listens {
  onChanged?: (listener: (event: ChangedEvent) => void) => () => void;
}

/** `onBatch` with every redraw stored in each window of `CHANGED_BATCH_MS`,
 *  starting at the first. A client that cannot listen -- a test stub -- is
 *  simply quiet. */
export function useChanged(client: Listens, onBatch: (events: ChangedEvent[]) => void,
                           windowMs = CHANGED_BATCH_MS): void {
  const latest = useRef(onBatch);
  latest.current = onBatch;
  useEffect(() => {
    let held: ChangedEvent[] = [];
    let timer: ReturnType<typeof setTimeout> | null = null;
    const stop = client.onChanged?.((event) => {
      held.push(event);
      if (timer !== null) return;
      timer = setTimeout(() => {
        const batch = held;
        held = [];
        timer = null;
        latest.current(batch);
      }, windowMs);
    });
    return () => {
      if (timer !== null) clearTimeout(timer);
      stop?.();
    };
  }, [client, windowMs]);
}
```

- [ ] **Step 5: Run the tests**

Run: `cd lab && npx vitest run src/api/client.test.ts src/api/useChanged.test.ts`
Expected: PASS. (The typecheck waits for Task 19: `Lightbox.tsx` still reads
the old redraw answer's `local` and `job`.)

- [ ] **Step 6: Commit**

Use `prepare-js-commit`, then:

```bash
git add lab/src/api/types.ts lab/src/api/client.ts lab/src/api/client.test.ts \
  lab/src/api/useChanged.ts lab/src/api/useChanged.test.ts
git commit -m "give the lab client redraw states, worker status and batched events"
```

---

### Task 19: The lightbox's redraw states, and its events listener

Button text by moment:

| moment | button |
|---|---|
| idle | `Redraw <slot>` |
| worker at origin/main, drawing | `Drawing…` |
| worker on another build, rolling then drawing | `updating worker…` |
| worker down (status or answer) | `spot render is down` |
| the same bytes came back | `unchanged` |

A failure shows under the buttons: `Redraw failed: timed out` for
`TimeoutError`, `Redraw failed: updating worker failed: <onto's stderr>` for
`RollFailed`, else `Redraw failed: <error>: <detail>`. Changing slot resets
the button.

**Files:**
- Modify: `lab/src/corpus/Lightbox.tsx` (imports; state at ~150-152; effects at ~164 and ~186-190; `redrawShown` at ~225-245; `queuedAt` at ~263; the button at ~410-413; the queued note at ~436-440)
- Modify: `lab/src/corpus/Lightbox.css` (delete `.corpus-queued`, ~258-264)
- Modify: `lab/src/corpus/types.ts` (delete `requested_at` and its comment, ~132-133)
- Test: `lab/src/corpus/Lightbox.test.tsx`

- [ ] **Step 1: Replace the lightbox's redraw tests**

In `lab/src/corpus/Lightbox.test.tsx`, delete the `settled` helper and the
three tests `redraws a cheap slot on the spot and shows what it drew`,
`says a slow slot is queued for its next round` and `says why a redraw failed`,
and put these in their place:

```tsx
const up = { state: 'up', build: '9.c', want: '9.c', detail: null };
const redrawn = { ...detail, slots: [detail.slots[0],
                                     { ...detail.slots[1], sha256: 'feedface0000' }] };
const naiveSrc = () =>
  screen.getByRole('img', { name: '3001 drawn by naive' }).getAttribute('src');
const answering = (answer: unknown, status: unknown = up) => ({
  corpusPart: async () => detail,
  redraw: async () => answer,
  spotStatus: async () => status,
});

it('redraws the slot and shows what it drew', async () => {
  const corpusPart = vi.fn().mockResolvedValueOnce(detail).mockResolvedValue(redrawn);
  const redraw = vi.fn(async () => ({ state: 'stored', sha: 'feedface0000' }));
  render(<Lightbox partId="3001" source="naive" onClose={() => {}}
                   client={{ corpusPart, redraw, spotStatus: async () => up } as any} />);
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByText('Redraw naive'));
  await waitFor(() => expect(naiveSrc()).toContain('v=feedface'));
  expect(redraw).toHaveBeenCalledWith('3001', 'naive');
  expect(screen.getByText('Redraw naive')).toBeTruthy();
});

it('says the worker is down without asking for a redraw', async () => {
  const redraw = vi.fn();
  const down = { state: 'down', build: null, want: '9.c', detail: 'offline' };
  render(<Lightbox partId="3001" source="naive" onClose={() => {}}
                   client={{ corpusPart: async () => detail, redraw,
                             spotStatus: async () => down } as any} />);
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByText('Redraw naive'));
  await waitFor(() => screen.getByText('spot render is down'));
  expect(redraw).not.toHaveBeenCalled();
});

it('says the worker is down when it goes away mid-click', async () => {
  render(<Lightbox partId="3001" source="naive" onClose={() => {}}
                   client={answering({ state: 'down', detail: 'gone' }) as any} />);
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByText('Redraw naive'));
  await waitFor(() => screen.getByText('spot render is down'));
});

it('says the worker is updating while a redraw waits on a roll', async () => {
  let land: (v: unknown) => void = () => {};
  const stale = { state: 'stale', build: '8.b', want: '9.c', detail: null };
  render(<Lightbox partId="3001" source="naive" onClose={() => {}}
                   client={{ corpusPart: async () => detail,
                             redraw: () => new Promise((resolve) => { land = resolve; }),
                             spotStatus: async () => stale } as any} />);
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByText('Redraw naive'));
  await waitFor(() => screen.getByText('updating worker…'));
  expect((screen.getByText('updating worker…') as HTMLButtonElement).disabled).toBe(true);
  land({ state: 'unchanged', sha: 'deadbeef0000' });
  await waitFor(() => screen.getByText('unchanged'));
});

it('says Drawing while a redraw is out', async () => {
  render(<Lightbox partId="3001" source="naive" onClose={() => {}}
                   client={{ corpusPart: async () => detail,
                             redraw: () => new Promise(() => {}),
                             spotStatus: async () => up } as any} />);
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByText('Redraw naive'));
  await waitFor(() => screen.getByText('Drawing…'));
});

it('says a timeout in words', async () => {
  render(<Lightbox partId="3001" source="naive" onClose={() => {}}
                   client={answering({ state: 'failed', error: 'TimeoutError',
                                       detail: 'exceeded 150s' }) as any} />);
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByText('Redraw naive'));
  await waitFor(() => screen.getByText('Redraw failed: timed out'));
});

it('says a failed roll in onto\'s words', async () => {
  render(<Lightbox partId="3001" source="naive" onClose={() => {}}
                   client={answering({ state: 'failed', error: 'RollFailed',
                                       detail: 'uv sync failed' }) as any} />);
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByText('Redraw naive'));
  await waitFor(() => screen.getByText('Redraw failed: updating worker failed: uv sync failed'));
});

it('says why any other redraw failed', async () => {
  render(<Lightbox partId="3001" source="naive" onClose={() => {}}
                   client={answering({ state: 'failed', error: 'ValueError',
                                       detail: 'boom' }) as any} />);
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByText('Redraw naive'));
  await waitFor(() => screen.getByText('Redraw failed: ValueError: boom'));
});

it('follows a redraw of this part made anywhere', async () => {
  let tell: (e: unknown) => void = () => {};
  const stop = vi.fn();
  const onChanged = vi.fn((listener: (e: unknown) => void) => { tell = listener; return stop; });
  const corpusPart = vi.fn().mockResolvedValueOnce(detail).mockResolvedValue(redrawn);
  const { unmount } = render(
    <Lightbox partId="3001" source="naive" onClose={() => {}}
              client={{ corpusPart, onChanged } as any} />);
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  tell({ part: '9999', source: 'naive', sha: 'x', build: '9.c' });
  await new Promise((resolve) => setTimeout(resolve, 300));
  expect(corpusPart).toHaveBeenCalledTimes(1);
  tell({ part: '3001', source: 'naive', sha: 'feedface0000', build: '9.c' });
  await waitFor(() => expect(naiveSrc()).toContain('v=feedface'));
  unmount();
  expect(stop).toHaveBeenCalled();
});

it('shows no queued note, since nothing is queued any more', async () => {
  render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  expect(document.querySelector('.corpus-queued')).toBeNull();
});
```

- [ ] **Step 2: Run the file to see it fail**

Run: `cd lab && npx vitest run src/corpus/Lightbox.test.tsx`
Expected: FAIL (the new labels never appear)

- [ ] **Step 3: Rework the lightbox**

In `lab/src/corpus/Lightbox.tsx`:

Replace `import { settledJob } from '@lab/api/jobPoll';` with

```tsx
import type { RedrawAnswer } from '@lab/api/types';
import { useChanged } from '@lab/api/useChanged';
```

After the `whyNothing` function, add:

```tsx
/** What the Redraw button is doing, or last had to say. */
type RedrawUi =
  | { busy: 'drawing' | 'updating' }
  | { said: 'down' | 'unchanged' }
  | { error: string }
  | null;

const BUSY_LABEL = { drawing: 'Drawing…', updating: 'updating worker…' } as const;
const SAID_LABEL = { down: 'spot render is down', unchanged: 'unchanged' } as const;

/** A failed redraw in words. A timeout is the one met most, and its bare
 *  class name reads as a crash; a failed roll is onto's to explain. */
function failure(answer: RedrawAnswer): string {
  if (answer.error === 'TimeoutError') return 'timed out';
  if (answer.error === 'RollFailed') return `updating worker failed: ${answer.detail ?? ''}`;
  if (answer.error && answer.detail) return `${answer.error}: ${answer.detail}`;
  return answer.error ?? answer.detail ?? 'unknown error';
}
```

Replace

```tsx
  const [redraw, setRedraw] = useState<{ drawing: true } | { error: string } | null>(null);
```

with

```tsx
  const [redraw, setRedraw] = useState<RedrawUi>(null);
```

and delete `const gone = useRef(new AbortController());`.

Replace `useEffect(() => { setShown(source); }, [source]);` with:

```tsx
  useEffect(() => { setShown(source); }, [source]);
  useEffect(() => { setRedraw(null); }, [shown]);

  // A redraw of this part from anywhere -- this lightbox, another tab, a
  // script -- lands here at once rather than on the next open.
  useChanged(client, (events) => {
    if (events.some((event) => event.part === partId)) {
      void client.corpusPart(partId).then(setDetail);
    }
  });
```

Delete the effect that aborts `gone`:

```tsx
  useEffect(() => {
    const ctl = gone.current;
    return () => ctl.abort();
  }, []);
```

Replace `redrawShown` (with its doc comment) and the `drawing` const after it with:

```tsx
  /** Draw the slot on screen again, on the fleet's spot worker. Asking the
   *  worker's state first is what lets the button say a roll is coming, and
   *  a down worker is said without a request that would only fail. */
  const redrawShown = async () => {
    try {
      const spot = await client.spotStatus();
      if (spot.state === 'down') { setRedraw({ said: 'down' }); return; }
      setRedraw({ busy: spot.state === 'stale' ? 'updating' : 'drawing' });
      const answer = await client.redraw(partId, shown);
      if (answer.state === 'stored') {
        setRedraw(null);
        setDetail(await client.corpusPart(partId));
      } else if (answer.state === 'down' || answer.state === 'unchanged') {
        setRedraw({ said: answer.state });
      } else if (answer.state === 'none') {
        setRedraw({ error: 'nothing to draw in this slot' });
      } else {
        setRedraw({ error: failure(answer) });
      }
    } catch (e) {
      setRedraw({ error: e instanceof Error ? e.message : String(e) });
    }
  };
  const busy = redraw !== null && 'busy' in redraw;
  const redrawLabel = redraw !== null && 'busy' in redraw ? BUSY_LABEL[redraw.busy]
    : redraw !== null && 'said' in redraw ? SAID_LABEL[redraw.said]
    : `Redraw ${shown}`;
```

Delete `const queuedAt = slots.find((slot) => slot.source === shown)?.requested_at;`.

Replace the button

```tsx
            <button type="button" className="corpus-action" disabled={drawing}
                    onClick={() => void redrawShown()}>
              {drawing ? 'Drawing…' : `Redraw ${shown}`}
            </button>
```

with

```tsx
            <button type="button" className="corpus-action" disabled={busy}
                    onClick={() => void redrawShown()}>
              {redrawLabel}
            </button>
```

Delete the queued note:

```tsx
          {queuedAt && (
            <p className="corpus-queued">
              Queued for the next {shown} round · asked {queuedAt.slice(0, 10)}
            </p>
          )}
```

In `lab/src/corpus/Lightbox.css`, delete the `.corpus-queued { ... }` rule. In
`lab/src/corpus/types.ts`, delete

```ts
    /** When a redraw of this slot was asked for and has not landed yet. */
    requested_at?: string | null;
```

- [ ] **Step 4: Run the tests and the typecheck**

Run: `cd lab && npx vitest run src/corpus/Lightbox.test.tsx && npm run typecheck`
Expected: PASS; clean. `useRef` stays imported: `closeRef` and
`zoomOpenerRef` use it.

- [ ] **Step 5: Commit**

Use `prepare-js-commit`, then:

```bash
git add lab/src/corpus/Lightbox.tsx lab/src/corpus/Lightbox.css \
  lab/src/corpus/Lightbox.test.tsx lab/src/corpus/types.ts
git commit -m "show the spot worker's state on the Redraw button and follow redraws live"
```

---

### Task 20: The wall polls when a redraw lands

The Wall page already keeps the latest `WallHeader` in `wall.current` (for
`reveal`). pezlie 0.3.0 adds `poll()` to it, so a batch of `changed` events
for the slot on screen asks the feed for its delta at once, instead of on the
next 10-second tick. The delta carries the new sha because `record_render`
stamps `indexed_at`, which `cells` reads as `landed` (Task 14's
`test_the_wall_s_delta_carries_the_new_sha` pins it).

**Files:**
- Modify: `lab/src/wall/BrickWall.tsx`
- Test: `lab/src/wall/BrickWall.test.tsx`

- [ ] **Step 1: Write the failing test**

Append to `lab/src/wall/BrickWall.test.tsx`:

```tsx
it('asks for the delta at once when a redraw lands in the slot on screen', async () => {
  let tell: (e: unknown) => void = () => {};
  const cells = vi.fn(() => Promise.resolve(
    { cells: [], count: 0, version: 'v1', source: 'occt' }));
  const listening = { ...client, cells,
                      onChanged: (f: (e: unknown) => void) => { tell = f; return () => {}; } };
  render(<BrickWall client={listening} />);
  await screen.findByRole('radiogroup', { name: 'Engine' });
  await waitFor(() => expect(cells).toHaveBeenCalled());
  // Let the opening fetches settle, so the count below is only the poll's.
  await new Promise((resolve) => setTimeout(resolve, 300));
  const asked = cells.mock.calls.length;
  tell({ part: '3001', source: 'reference', sha: 'x', build: '9.c' });
  await new Promise((resolve) => setTimeout(resolve, 300));
  expect(cells.mock.calls.length).toBe(asked);
  tell({ part: '3001', source: 'occt', sha: 'x', build: '9.c' });
  await waitFor(() => expect(cells.mock.calls.length).toBe(asked + 1));
});
```

- [ ] **Step 2: Run the file to see it fail**

Run: `cd lab && npx vitest run src/wall/BrickWall.test.tsx`
Expected: FAIL on the new test (no second `cells` call)

- [ ] **Step 3: Implement**

In `lab/src/wall/BrickWall.tsx`, add `import { useChanged } from '@lab/api/useChanged';`,
and after the `const wall = useRef<WallHeader | null>(null);` line add:

```tsx
  // One poll per batch: each poll that moves a sha copies every sheet level.
  useChanged(client, (events) => {
    const shown = wall.current;
    if (shown && events.some((event) => event.source === shown.slot)) shown.poll();
  });
```

- [ ] **Step 4: Run the tests and the typecheck**

Run: `cd lab && npx vitest run src/wall/BrickWall.test.tsx && npm run typecheck`
Expected: PASS; clean

- [ ] **Step 5: Commit**

Use `prepare-js-commit`, then:

```bash
git add lab/src/wall/BrickWall.tsx lab/src/wall/BrickWall.test.tsx
git commit -m "poll the wall at once when a redraw lands in its slot"
```

---

### Task 21: The loose-thumb cache keys on the render's sha

The lab's `/corpus` wall (`CorpusWall`) keeps its 128 px images in
`useLooseThumbs`, whose `requested` set is keyed by part id and only grows,
so a redrawn cell is never fetched again. pezlie's `imageKey` (`id@sha`) is
the one definition of what names a cell's picture; the lab uses it rather
than a second copy.

**Files:**
- Modify: `lab/src/corpus/useLooseThumbs.ts` (`wanted`; the fetch effect; the resets)
- Test: `lab/src/corpus/useLooseThumbs.test.ts`

- [ ] **Step 1: Write the failing tests**

In `lab/src/corpus/useLooseThumbs.test.ts`, add `import { imageKey } from 'pezlie';`;
in `keeps asking for cells behind the cap once the front of the view is in hand`
change `const have = new Set(many.slice(0, 200).map((c) => c.id));` to
`const have = new Set(many.slice(0, 200).map(imageKey));`; and append:

```ts
it('asks again for a cell whose render changed', () => {
  const was = cell('3001', 0, 'deadbeef');
  const now = cell('3001', 0, 'feedface');
  const have = new Set([imageKey(was)]);
  expect(wanted([was], [0], 128, have)).toEqual([]);
  expect(wanted([now], [0], 128, have).map((c) => c.sha)).toEqual(['feedface']);
});
```

- [ ] **Step 2: Run the file to see it fail**

Run: `cd lab && npx vitest run src/corpus/useLooseThumbs.test.ts`
Expected: FAIL on the two tests using `imageKey`

- [ ] **Step 3: Implement**

In `lab/src/corpus/useLooseThumbs.ts`, add `import { imageKey } from 'pezlie';`.
In `wanted`, change `if (!cell || !cell.sha || have.has(cell.id)) continue;` to
`if (!cell || !cell.sha || have.has(imageKey(cell))) continue;`, and in its
doc comment change "`have` is what is already requested" to "`have` is the
`imageKey`s already requested, so a redrawn cell is wanted again".

After `const requested = useRef<Set<string>>(new Set());` add:

```ts
  // The key each part was last asked for under, so a slow load of an older
  // render cannot land over the newer one.
  const latest = useRef<Map<string, string>>(new Map());
```

In the `[source]` effect and in the handle's `reset`, add
`latest.current = new Map();` beside each `requested.current = new Set();`.

Replace the fetch effect:

```ts
  useEffect(() => {
    for (const cell of wanted(cells, visible, level, requested.current)) {
      requested.current.add(cell.id);
      const img = new Image();
      img.onload = () => {
        if (!mounted.current) return;
        setLoose((prev) => new Map(prev).set(cell.id, img));
      };
      img.src = thumbUrl(cell, source);
    }
  }, [cells, visible, level, source]);
```

with

```ts
  useEffect(() => {
    for (const cell of wanted(cells, visible, level, requested.current)) {
      const key = imageKey(cell);
      requested.current.add(key);
      latest.current.set(cell.id, key);
      const img = new Image();
      img.onload = () => {
        if (!mounted.current || latest.current.get(cell.id) !== key) return;
        setLoose((prev) => new Map(prev).set(cell.id, img));
      };
      img.src = thumbUrl(cell, source);
    }
  }, [cells, visible, level, source]);
```

- [ ] **Step 4: Run the tests and the typecheck**

Run: `cd lab && npx vitest run src/corpus/useLooseThumbs.test.ts && npm run typecheck`
Expected: PASS; clean

- [ ] **Step 5: Commit**

Use `prepare-js-commit`, then:

```bash
git add lab/src/corpus/useLooseThumbs.ts lab/src/corpus/useLooseThumbs.test.ts
git commit -m "key the loose-thumb cache on the render's sha"
```

---

### Task 22: The vector cache keys on the render's sha

`useVectorThumbs` keys its fetched bytes, its in-flight set and its rasters by
part id, so a redrawn cell keeps rasterizing the old SVG.

**Files:**
- Modify: `lab/src/corpus/useVectorThumbs.ts` (`splitWork`; `RasterEntry`; the residency sweep; `drain`; `rasterOne`; `enqueue`)
- Test: `lab/src/corpus/useVectorThumbs.test.ts`

- [ ] **Step 1: Write the failing tests**

In `lab/src/corpus/useVectorThumbs.test.ts`, add `import { imageKey } from 'pezlie';`,
change the two existing `splitWork` calls to carry the key:

```ts
  const { now, onSettle } = splitWork(want, new Map([['a', { px: 400, key: imageKey(cell('a', 'x')) }]]), 400);
```

```ts
  const { now, onSettle } = splitWork(want, new Map([['a', { px: 200, key: imageKey(cell('a', 'x')) }]]), 800);
```

and append:

```ts
it('rasterizes a redrawn cell now, whatever size its old raster was', () => {
  const have = new Map([['a', { px: 400, key: imageKey(cell('a', 'old')) }]]);
  const { now, onSettle } = splitWork([cell('a', 'new')], have, 400);
  expect(now.map((c) => c.sha)).toEqual(['new']);
  expect(onSettle).toEqual([]);
});

it('fetches the new render of a redrawn cell', async () => {
  const fetched = vi.mocked(fetchRender);
  fetched.mockClear();
  const visible = [0];
  const { rerender } = renderHook(
    ({ cells }) => useVectorThumbs(cells, visible, VECTOR_LEVEL, 'naive', 256),
    { initialProps: { cells: [cell('a', 'old00000')] } });
  await waitFor(() => expect(fetched).toHaveBeenCalledTimes(1));
  rerender({ cells: [cell('a', 'new00000')] });
  await waitFor(() => expect(fetched).toHaveBeenCalledTimes(2));
  expect(String(fetched.mock.calls[1]![0])).toContain('v=new00000');
});
```

- [ ] **Step 2: Run the file to see it fail**

Run: `cd lab && npx vitest run src/corpus/useVectorThumbs.test.ts`
Expected: FAIL on the two new tests

- [ ] **Step 3: Implement**

In `lab/src/corpus/useVectorThumbs.ts`, add `import { imageKey } from 'pezlie';`
and replace `splitWork` and `RasterEntry` with:

```ts
export function splitWork(want: Cell[], have: Map<string, { px: number; key: string }>,
                          targetPx: number): { now: Cell[]; onSettle: Cell[] } {
  const now: Cell[] = [];
  const onSettle: Cell[] = [];
  for (const cell of want) {
    const cached = have.get(cell.id);
    // A raster of another render is no raster: the cell is showing the wrong
    // drawing, not the right one at the wrong size.
    if (!cached || cached.key !== imageKey(cell)) now.push(cell);
    else if (needsRerender(cached.px, targetPx)) onSettle.push(cell);
  }
  return { now, onSettle };
}

interface RasterEntry { image: CanvasImageSource; px: number; key: string }
```

The byte cache now holds picture keys, so in the residency sweep change

```ts
    for (const id of bytes.current.keys()) {
      if (!wantedIds.current.has(id)) bytes.current.delete(id);
    }
```

to

```ts
    const wantedKeys = new Set(want.map(imageKey));
    for (const key of bytes.current.keys()) {
      if (!wantedKeys.has(key)) bytes.current.delete(key);
    }
```

In `drain`, replace both `inFlight.current.delete(job.cell.id)` with
`inFlight.current.delete(imageKey(job.cell))`.

Replace `rasterOne` with:

```ts
    const rasterOne = async (cell: Cell, px: number) => {
      try {
        const key = imageKey(cell);
        const url = vectorUrl(cell, source);
        let render = bytes.current.get(key);
        if (render === undefined) {
          render = await fetchRender(url);
          if (!mounted.current) return;
          bytes.current.set(key, render);
        }
        const image = await rasterize(render, px, px);
        if (!mounted.current || !wantedIds.current.has(cell.id)) return;
        arrived.current.set(cell.id, { image, px, key });
        scheduleFlush();
      } catch {
        /* the 128px loose thumb stays the fallback */
      }
    };
```

In `enqueue`, replace

```ts
        if (inFlight.current.has(cell.id)) continue;
        inFlight.current.add(cell.id);
```

with

```ts
        const key = imageKey(cell);
        if (inFlight.current.has(key)) continue;
        inFlight.current.add(key);
```

- [ ] **Step 4: Run the tests and the typecheck**

Run: `cd lab && npx vitest run src/corpus/useVectorThumbs.test.ts && npm run typecheck`
Expected: PASS; clean

- [ ] **Step 5: Commit**

Use `prepare-js-commit`, then:

```bash
git add lab/src/corpus/useVectorThumbs.ts lab/src/corpus/useVectorThumbs.test.ts
git commit -m "key the vector-thumb cache on the render's sha"
```

---

### Task 23: dropped -- `/corpus` is retired

This task would have made `/corpus` refetch its sheets after a redraw. `/corpus`
itself is gone: `/wall` (pezlie's `WallView`) replaced it, and the page was
deleted in the commit that retires it (see HANDOFF.md). Tasks 21 and 22, both
`/corpus`-only, were skipped for the same reason and are not being revisited.

---

### Task 24: The service command, provisioning, and the launch recipe

A roll resets the tree and keeps ignored files, so `.venv` and `vendor/ldraw`
survive it, but a dependency change in the new commit is the process's to
install. `scripts/spot-worker.sh` is the service command: it refuses a tree
without the parts library, syncs the environment, then starts the worker.
onto runs it again after every roll and every crash.

**Files:**
- Create: `scripts/spot-worker.sh`
- Modify: `DEVELOPING.md` (a new section after "The lab")
- Test: `tests/test_spot_launch.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_spot_launch.py`:

```python
"""The spot worker's service command: what onto runs after every roll."""
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "spot-worker.sh"


def _tree(tmp_path, ldraw=True):
    """A copy of the script in a tree with a fake uv and a fake python that
    record how they were called."""
    tree = tmp_path / "tree"
    (tree / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, tree / "scripts" / "spot-worker.sh")
    if ldraw:
        (tree / "vendor" / "ldraw" / "parts").mkdir(parents=True)
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    uv = home / ".local" / "bin" / "uv"
    uv.write_text(f"#!/bin/sh\necho \"$@\" > {tmp_path}/uv\n")
    uv.chmod(0o755)
    py = tree / ".venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text(f"#!/bin/sh\necho \"$@\" > {tmp_path}/python\n")
    py.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "PATH": "/usr/bin:/bin"}
    return tree, env


def test_it_syncs_the_environment_then_starts_the_worker(tmp_path):
    tree, env = _tree(tmp_path)
    got = subprocess.run(["bash", str(tree / "scripts" / "spot-worker.sh")],
                         env=env, capture_output=True, text=True)
    assert got.returncode == 0, got.stderr
    assert (tmp_path / "uv").read_text().split() == [
        "sync", "--frozen", "--extra", "occt", "--extra", "census",
        "--extra", "lab"]
    assert (tmp_path / "python").read_text().split() == [
        "-m", "brick_icons.spot_worker"]
    assert got.stdout == ""


def test_a_tree_without_the_parts_library_is_refused(tmp_path):
    tree, env = _tree(tmp_path, ldraw=False)
    got = subprocess.run(["bash", str(tree / "scripts" / "spot-worker.sh")],
                         env=env, capture_output=True, text=True)
    assert got.returncode == 1
    assert "vendor/ldraw" in got.stderr
    assert not (tmp_path / "python").exists()
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_spot_launch.py -q`
Expected: FAIL (no such script)

- [ ] **Step 3: Write the script**

Create `scripts/spot-worker.sh` and `chmod +x` it:

```bash
#!/usr/bin/env bash
# The spot render worker's service command: what `onto service up` runs, and
# runs again after every roll to a new commit and every crash.
#
#   onto service up brick-spot-render --in brick-icons-spot --prefer studio \
#     -- scripts/spot-worker.sh
#
# A roll is a forced reset that keeps ignored files: .venv and vendor/ldraw
# survive it, but a dependency change in the new commit does not install
# itself. Nothing but the worker's replies may reach stdout.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"   # uv, resvg, potrace (provision-node.sh)

[ -d vendor/ldraw/parts ] || {
  echo "spot-worker: no vendor/ldraw in $PWD; provision this tree" \
       "(DEVELOPING.md, Spot rendering)" >&2
  exit 1
}
uv sync --frozen --extra occt --extra census --extra lab >&2
exec .venv/bin/python -m brick_icons.spot_worker
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_spot_launch.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Write the DEVELOPING.md section**

Insert after the paragraph of "The lab" that ends
"`tests/test_lab_schema.py` fails on it." in `DEVELOPING.md`:

````markdown
## Spot rendering

The lab's **Redraw** button draws on one warm worker on the fleet,
`brick_icons.spot_worker`, run by onto as the service `brick-spot-render`.
Nothing renders on this Mac. The lab calls it through `onto call`
(`brick_icons/lab/spot.py`), stores what comes back, patches the part's cell
into the slot's sheets, and tells open pages over `GET /api/events`.

It draws origin/main: every redraw passes origin/main's sha as
`onto call --commit`, and onto rolls the worker to it first if it is on
another. Unpushed work cannot be spot rendered; use the CLI for that.

The worker has its own tree, `brick-icons-spot`, so it never holds the
`brick-icons` tree that census and fill jobs sync into. Give a node that tree
once: sync it, then clone the provisioned tree's environment and parts
library into it (APFS clones, no extra space). A roll keeps both, since git
ignores them.

    onto sync --in brick-icons-spot studio
    ssh studio 'cd .config/onto/work && cp -cR brick-icons/.venv brick-icons-spot/ \
      && mkdir -p brick-icons-spot/vendor && cp -cR brick-icons/vendor/ldraw brick-icons-spot/vendor/'

A node with no provisioned `brick-icons` tree gets one first with
`scripts/provision-node.sh <node>`.

Start it. studio is tried first, then any node holding the tree; never this
Mac:

    onto service up brick-spot-render --in brick-icons-spot --prefer studio \
      -- scripts/spot-worker.sh

`scripts/spot-worker.sh` refuses a tree without `vendor/ldraw`, runs
`uv sync`, then starts the worker, and onto runs it again after every roll.
Check it:

    onto call brick-spot-render '{"ping": true}'    # {"id": ..., "pong": true, "build": ...}
    brick-lab stat                                  # spot render  up at <build>

Run both with the Bash sandbox disabled, or onto reports every node offline.
`onto service ls` lists the service and refreshes this Mac's record of where
it runs; `onto service down brick-spot-render` stops it. `BRICK_SPOT_POOL`
sets how many redraws draw at once (default 2); each is capped at
`batch.RENDER_TIMEOUT_S`.

A redraw keeps a lossless master of each sheet beside its WebP
(`out/thumbs/<slot>/sheet-<level>.master.png`, about 35 MB a slot, overwritten
in place) so that patching one cell does not re-encode every other one.
`scripts/bake-thumbs.py` writes them. A slot baked before them refuses a
patch until it is baked again; the drawing is still stored, and the lab's log
says so.
````

- [ ] **Step 6: Commit**

```bash
git add scripts/spot-worker.sh tests/test_spot_launch.py DEVELOPING.md
git commit -m "add the spot worker's service command and launch recipe"
```

---

### Task 25: Merge, test on the fleet, and check it end to end

Run once. The render happens on studio; this Mac runs only the lab and a
headless browser.

- [ ] **Step 1: Open the PR**

Ask before `gh pr create`. Merge once reviewed, then switch the main
checkout to `main` and pull. Delete the branch and its worktree.

- [ ] **Step 2: The full Python suite on the fleet, in the background**

Run (sandbox disabled, backgrounded, not waited on):
`onto test --in brick-icons --ref origin/main --node studio`
Read its exit code when it finishes; a failure becomes the next thing to fix.
An OOM kill or a timeout in a file this plan did not touch is contention, not
a regression.

- [ ] **Step 3: Rebake every slot's sheets, on the fleet**

The masters exist only once each slot has been composed by the new code. This
is a whole-corpus bake, so estimate it first (items times seconds per item,
from a timed bake of one slot, as core-hours and wall time) and launch it with
`onto run --kind bake` per CLAUDE.md, rather than on this Mac.

- [ ] **Step 4: Provision and start the worker**

Follow DEVELOPING.md, "Spot rendering": sync `brick-icons-spot` to studio,
clone `.venv` and `vendor/ldraw` into it, `onto service up`. Then check that
`onto call brick-spot-render '{"ping": true}'` answers at origin/main's build
and that `onto service ls` shows it on studio.

- [ ] **Step 5: Reload the lab and read its view of the worker**

Run: `brick-lab install` from the main checkout (it writes the new PATH into
the agents), then `brick-lab stat`.
Expected: `spot render` reads `up at <origin/main build>`.

- [ ] **Step 6: Redraw 612p01 headless**

With the playwright MCP (headless), open `http://localhost:5178/wall`, find
612p01, and note the wall cell's tile URL and the lightbox's `occt` image
`src` (`v=<sha8>`). Click `Redraw occt`. Expect `Drawing…` (or
`updating worker…` if the worker was rolled), then the image `src` changing to
a new `v=` and, within a second, the wall cell's 128 px tile fetched under the
new sha. No reload. Screenshot the lightbox and the cell before and after.

If the answer is `unchanged`, the path is proven but not the swap: the stored
drawing already matched origin/main. Pick a part drawn before the last engine
change instead:

    since=$(git log -1 --format=%cI -- brick_icons/)
    sqlite3 corpus.db "SELECT part_id FROM renders WHERE source = 'occt' \
      AND made_at < '$since' ORDER BY made_at LIMIT 5"

and redraw the first of those.

- [ ] **Step 7: Put the evidence on the wall**

Build one sheet with `scripts/_sheet.py`: a title line naming the part and
slot, panels labeled `before` and `after`, and the third diff panel. Send it
with `transom post <file>` to the `brick-icons` zone.

- [ ] **Step 8: Close the docs**

Move what stays true (the flow and the failure table) into DEVELOPING.md's
"Spot rendering" section, delete
`docs/superpowers/specs/2026-09-29-spot-render-design.md` and this plan, and
commit them as "retire the spot render spec and plan now that it is built".

- [ ] **Step 9: Stop what this check started**

Close the headless browser. The worker stays up: it is the service.
