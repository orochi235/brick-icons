# Corpus Wall Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group the corpus wall by coverage, category or release year, color its cells by outside facts, and give it a sidebar that switches between those and switches categories off.

**Architecture:** Rebrickable's free CSVs are joined once by a script into three new tables in `corpus.db`; the cells route carries the scalars per cell and the category names once. The `Layout` type grows a `bands` array so a strategy can report group headers, and two packers — one that flows blocks, one that stacks bands of blocks — cover all three groupings. A DOM sidebar drives grouping, order, cell color and a category facet list.

**Tech Stack:** Python 3 + sqlite3 + pytest; React + TypeScript + vitest; Canvas2D through `paintCommands`.

**Spec:** `docs/superpowers/specs/2026-09-05-corpus-grouping-design.md`

---

## Before you start

**This plan is gated on `corpus-wall` merging to `main`.** Every file under
`lab/src/corpus/` and `brick_icons/lab/cells.py` comes from that branch. If
`git log main --oneline -- lab/src/corpus/layout.ts` is empty, stop: the branch
has not merged and nothing here applies yet.

**Task 22 of the corpus-wall plan — the caret — must have landed first, with
geometric adjacency.** This plan inserts whitespace between blocks. A caret that
moves by `index ± 1` or by grid arithmetic passes every test written against a
dense grid and breaks the moment a band gap exists. Task 16 re-checks it.

**Work in a worktree**, per `superpowers:using-git-worktrees`. Two traps carried
over from the corpus-wall branch and still true:

- Run Python tests as `.venv/bin/python -m pytest`, never `.venv/bin/pytest`.
  The venv is shared with the main checkout and the console script imports the
  wrong tree.
- Do not symlink `out/` into the worktree. `db.record_render` resolves paths
  relative to the root and silently skips everything that resolves outside it.

**Do not run the full suite until Task 17.** Run only the files each task names.

---

## File structure

**Created**

| path | responsibility |
|---|---|
| `brick_icons/rebrickable.py` | Download, parse and join Rebrickable's CSVs. Pure functions plus one fetch. |
| `scripts/import-rebrickable.py` | The CLI around it. |
| `tests/test_rebrickable.py` | The join, the aggregation, the category cleaning. |
| `lab/src/corpus/facts.ts` | Category cleaning, roll-up, and the group key of a cell. |
| `lab/src/corpus/facts.test.ts` | |
| `lab/src/corpus/grouped.ts` | `flowBlocks`, `blockLayout`, `bandedLayout`. |
| `lab/src/corpus/grouped.test.ts` | |
| `lab/src/corpus/tint.ts` | Cell color per tint mode. |
| `lab/src/corpus/tint.test.ts` | |
| `lab/src/corpus/Sidebar.tsx` | Grouping, order, color and the facet list. |
| `lab/src/corpus/Sidebar.css` | |
| `lab/src/corpus/Sidebar.test.tsx` | |

**Modified**

| path | change |
|---|---|
| `brick_icons/db.py` | Three tables in `_SCHEMA`; `import_facts`; `rebuild` calls it. |
| `brick_icons/lab/cells.py` | Facts per cell, category names once. |
| `tests/test_db.py` | The new tables and `import_facts`. |
| `tests/test_lab_cells.py` | Facts in the response. |
| `lab/src/corpus/types.ts` | `Cell` fields, `CellsBody.categories`. |
| `lab/src/corpus/layout.ts` | `Band`, and `bands` in the `Layout` return. |
| `lab/src/corpus/layout.test.ts` | `gridLayout` returns no bands. |
| `lab/src/corpus/paint.ts` | A `label` paint command. |
| `lab/src/corpus/paint.test.ts` | |
| `lab/src/corpus/select.ts` | `Selection` gains grouping, tint, excluded categories. |
| `lab/src/corpus/select.test.ts` | |
| `lab/src/corpus/Wall.tsx` | Draw label commands. |
| `lab/src/corpus/CorpusWall.tsx` | Pick the layout, mount the sidebar. |
| `lab/src/corpus/palette.ts` | An `unmatched` entry and the ramp ends. |

**No schema version bump.** `_SCHEMA` is all `CREATE TABLE IF NOT EXISTS` and
`connect` runs it on every open, so an existing v1 database gains the tables the
next time it is opened. `connect` refuses only a *newer* stamp, so leaving the
stamp at 1 is correct and needs no migration.

---

## Task 1: Clean a category, and roll the tail up

**Files:**
- Create: `brick_icons/rebrickable.py`
- Create: `tests/test_rebrickable.py`

LDraw derives `parts.category` from the first word of the description, so it
carries the description's `~` `=` `_` `|` prefixes and has a long tail.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rebrickable.py
from brick_icons import rebrickable as rb


def test_cleaning_strips_the_description_prefixes():
    assert rb.clean_category("~Moved") == "Moved"
    assert rb.clean_category("=Sticker") == "Sticker"
    assert rb.clean_category("_Figure") == "Figure"
    assert rb.clean_category("~_Plate") == "Plate"
    assert rb.clean_category("Brick") == "Brick"


def test_cleaning_a_bare_marker_or_nothing_gives_the_placeholder():
    assert rb.clean_category("|") == "-"
    assert rb.clean_category(None) == "-"
    assert rb.clean_category("") == "-"


def test_the_roll_up_keeps_big_groups_and_folds_the_tail():
    counts = {"Brick": 40, "Tile": 30, "Dish": 3, "Fence": 1}
    rolled = rb.roll_up(counts, minimum=25)
    assert rolled == {"Brick": "Brick", "Tile": "Tile",
                      "Dish": "Other", "Fence": "Other"}


def test_the_roll_up_leaves_the_placeholder_alone():
    # "-" is already the catch-all for a part with no category; folding it into
    # "Other" would merge two different absences.
    assert rb.roll_up({"-": 2}, minimum=25) == {"-": "-"}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/test_rebrickable.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'brick_icons.rebrickable'`

- [ ] **Step 3: Write the implementation**

```python
# brick_icons/rebrickable.py
"""Rebrickable's public catalog, joined to LDraw part ids.

The CSVs at `cdn.rebrickable.com/media/downloads/` need no account and no key.
Attribution is a condition of use: credit Rebrickable wherever these facts are
shown.
"""
from __future__ import annotations

import csv
import gzip
import io
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

# The catch-all for a part whose description begins with a bare marker, or
# which has no description at all. Distinct from "Other", which is a real
# category too small to label.
NO_CATEGORY = "-"

_PREFIXES = "~=_|"


def clean_category(raw: str | None) -> str:
    return (raw or "").lstrip(_PREFIXES).strip() or NO_CATEGORY


def roll_up(counts: dict[str, int], minimum: int = 25) -> dict[str, str]:
    """Clean category to the group it is drawn under.

    A block of three labeled cells is confetti, so anything under `minimum`
    draws as "Other". `NO_CATEGORY` is exempt: it is already an absence, and
    folding it in would merge two different ones.
    """
    return {name: name if name == NO_CATEGORY or n >= minimum else "Other"
            for name, n in counts.items()}
```

- [ ] **Step 4: Run it and watch it pass**

Run: `.venv/bin/python -m pytest tests/test_rebrickable.py -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/rebrickable.py tests/test_rebrickable.py
git commit -m "clean an LDraw category, and roll its tail into Other"
```

---

## Task 2: Link an LDraw id to a Rebrickable part number

**Files:**
- Modify: `brick_icons/rebrickable.py`
- Modify: `tests/test_rebrickable.py`

Straight across first, then through `elements.design_id` for the modern six-
and seven-digit ids. `matched_by` records which, so a wrong join is findable
later without re-running the match.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rebrickable.py -- append
def test_an_exact_id_matches_directly():
    links = rb.link_ids(["3001"], {"3001"}, {})
    assert links == {"3001": ("3001", "id")}


def test_a_design_id_bridges_the_modern_numbers():
    links = rb.link_ids(["10055"], {"92081"}, {"10055": {"92081"}})
    assert links == {"10055": ("92081", "design")}


def test_a_direct_match_beats_a_design_bridge():
    links = rb.link_ids(["3001"], {"3001", "99999"}, {"3001": {"99999"}})
    assert links == {"3001": ("3001", "id")}


def test_a_design_id_with_several_candidates_takes_the_lowest():
    # Deterministic beats arbitrary: a re-import must not change the join.
    links = rb.link_ids(["10055"], {"b", "a"}, {"10055": {"b", "a"}})
    assert links == {"10055": ("a", "design")}


def test_an_unmatched_id_gets_no_entry():
    # Absence, never a row of Nones -- "we do not know" and "never in a set"
    # are different facts and a null row collapses them.
    assert rb.link_ids(["u9236"], {"3001"}, {}) == {}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/test_rebrickable.py -v`
Expected: FAIL, `AttributeError: module 'brick_icons.rebrickable' has no attribute 'link_ids'`

- [ ] **Step 3: Write the implementation**

```python
# brick_icons/rebrickable.py -- append
def link_ids(ldraw_ids: Iterable[str], part_nums: set[str],
             design_index: dict[str, set[str]]) -> dict[str, tuple[str, str]]:
    """LDraw id -> (Rebrickable part number, how it was matched).

    An id with no match gets no entry at all.
    """
    out: dict[str, tuple[str, str]] = {}
    for pid in ldraw_ids:
        if pid in part_nums:
            out[pid] = (pid, "id")
            continue
        candidates = design_index.get(pid)
        if candidates:
            out[pid] = (min(candidates), "design")
    return out
```

- [ ] **Step 4: Run it and watch it pass**

Run: `.venv/bin/python -m pytest tests/test_rebrickable.py -v`
Expected: PASS, 9 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/rebrickable.py tests/test_rebrickable.py
git commit -m "link LDraw ids to Rebrickable part numbers, directly or by design id"
```

---

## Task 3: Aggregate the inventories into per-part facts

**Files:**
- Modify: `brick_icons/rebrickable.py`
- Modify: `tests/test_rebrickable.py`

`inventory_parts` is 1,557,033 rows. Aggregate it once, in one pass, and store
the result — joining it per request is the version that seems fine on a laptop
and falls over on the wall.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rebrickable.py -- append
def _inventory_rows():
    return [
        {"inventory_id": "1", "part_num": "3001", "color_id": "4", "quantity": "2"},
        {"inventory_id": "2", "part_num": "3001", "color_id": "4", "quantity": "3"},
        {"inventory_id": "2", "part_num": "3001", "color_id": "1", "quantity": "1"},
        {"inventory_id": "9", "part_num": "3001", "color_id": "7", "quantity": "5"},
    ]


def _catalog():
    # inventory 9 belongs to a set with no year -- a real case, and it must not
    # drag year_first to zero.
    return ({"1": "s-1", "2": "s-2", "9": "s-9"}, {"s-1": 1980, "s-2": 1974})


def test_aggregation_sums_quantity_and_counts_distinct_sets():
    inv_set, set_year = _catalog()
    facts = rb.aggregate(_inventory_rows(), inv_set, set_year)
    assert facts["3001"].uses == 11
    assert facts["3001"].sets == {"s-1", "s-2", "s-9"}


def test_aggregation_takes_the_earliest_and_latest_year():
    inv_set, set_year = _catalog()
    facts = rb.aggregate(_inventory_rows(), inv_set, set_year)
    assert facts["3001"].year_first == 1974
    assert facts["3001"].year_last == 1980


def test_aggregation_collects_every_color_the_part_was_made_in():
    inv_set, set_year = _catalog()
    facts = rb.aggregate(_inventory_rows(), inv_set, set_year)
    assert facts["3001"].colors == {1, 4, 7}


def test_a_part_only_in_undated_sets_has_no_year_but_still_has_uses():
    facts = rb.aggregate(
        [{"inventory_id": "9", "part_num": "3001", "color_id": "7", "quantity": "5"}],
        {"9": "s-9"}, {})
    assert facts["3001"].year_first is None
    assert facts["3001"].uses == 5
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/test_rebrickable.py -v`
Expected: FAIL, `AttributeError: module 'brick_icons.rebrickable' has no attribute 'aggregate'`

- [ ] **Step 3: Write the implementation**

```python
# brick_icons/rebrickable.py -- append, above link_ids is fine too
@dataclass
class PartFacts:
    year_first: int | None = None
    year_last: int | None = None
    uses: int = 0
    sets: set[str] = field(default_factory=set)
    colors: set[int] = field(default_factory=set)


def aggregate(inventory_parts: Iterable[dict], inv_set: dict[str, str],
              set_year: dict[str, int]) -> dict[str, PartFacts]:
    """One pass over `inventory_parts`, keyed by Rebrickable part number."""
    out: dict[str, PartFacts] = {}
    for row in inventory_parts:
        part = row["part_num"]
        facts = out.get(part)
        if facts is None:
            facts = out[part] = PartFacts()
        facts.uses += int(row["quantity"])
        facts.colors.add(int(row["color_id"]))
        set_num = inv_set.get(row["inventory_id"])
        if set_num is None:
            continue
        facts.sets.add(set_num)
        year = set_year.get(set_num)
        if year is None:
            continue
        if facts.year_first is None or year < facts.year_first:
            facts.year_first = year
        if facts.year_last is None or year > facts.year_last:
            facts.year_last = year
    return out
```

- [ ] **Step 4: Run it and watch it pass**

Run: `.venv/bin/python -m pytest tests/test_rebrickable.py -v`
Expected: PASS, 13 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/rebrickable.py tests/test_rebrickable.py
git commit -m "aggregate 1.5M inventory rows into per-part year, use and color facts"
```

---

## Task 4: Read a gzipped CSV, and cache the download

**Files:**
- Modify: `brick_icons/rebrickable.py`
- Modify: `tests/test_rebrickable.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rebrickable.py -- append
import gzip


def test_reading_a_gzipped_csv_yields_dicts(tmp_path):
    path = tmp_path / "parts.csv.gz"
    path.write_bytes(gzip.compress(b"part_num,name\n3001,Brick 2 x 4\n"))
    assert list(rb.read_csv(path)) == [{"part_num": "3001", "name": "Brick 2 x 4"}]


def test_a_cached_file_with_a_matching_etag_is_not_downloaded(tmp_path, monkeypatch):
    path = tmp_path / "parts.csv.gz"
    path.write_bytes(gzip.compress(b"part_num\n3001\n"))
    (tmp_path / "parts.csv.gz.etag").write_text('"abc"')

    def explode(*a, **k):
        raise AssertionError("should not have downloaded")

    monkeypatch.setattr(rb, "_head_etag", lambda url: '"abc"')
    monkeypatch.setattr(rb, "_download", explode)
    assert rb.fetch("parts", tmp_path) == path


def test_a_changed_etag_downloads_again(tmp_path, monkeypatch):
    path = tmp_path / "parts.csv.gz"
    path.write_bytes(gzip.compress(b"part_num\n3001\n"))
    (tmp_path / "parts.csv.gz.etag").write_text('"old"')
    calls = []
    monkeypatch.setattr(rb, "_head_etag", lambda url: '"new"')
    monkeypatch.setattr(rb, "_download",
                        lambda url, dest: calls.append(url) or dest.write_bytes(b"x"))
    rb.fetch("parts", tmp_path)
    assert len(calls) == 1
    assert (tmp_path / "parts.csv.gz.etag").read_text() == '"new"'
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/test_rebrickable.py -v`
Expected: FAIL, `AttributeError: module 'brick_icons.rebrickable' has no attribute 'read_csv'`

- [ ] **Step 3: Write the implementation**

```python
# brick_icons/rebrickable.py -- append
BASE = "https://cdn.rebrickable.com/media/downloads"

# Everything the join needs. `part_relationships` is not read yet; it is the
# free oracle for the printed-part-to-base-part rule and is downloaded so that
# work does not need a second fetch path.
FILES = ("parts", "part_categories", "colors", "elements", "sets",
         "inventories", "inventory_parts", "part_relationships")

_UA = "brick-icons (https://github.com/; corpus wall part facts)"


def read_csv(path: Path) -> Iterator[dict]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        yield from csv.DictReader(fh)


def _head_etag(url: str) -> str | None:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.headers.get("ETag")


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=600) as res:
        dest.write_bytes(res.read())


def fetch(name: str, into: Path) -> Path:
    """Download one catalog file unless the cached copy's ETag still matches."""
    into.mkdir(parents=True, exist_ok=True)
    dest = into / f"{name}.csv.gz"
    stamp = into / f"{name}.csv.gz.etag"
    url = f"{BASE}/{name}.csv.gz"
    etag = _head_etag(url)
    if dest.exists() and stamp.exists() and etag and stamp.read_text() == etag:
        return dest
    _download(url, dest)
    if etag:
        stamp.write_text(etag)
    return dest
```

- [ ] **Step 4: Run it and watch it pass**

Run: `.venv/bin/python -m pytest tests/test_rebrickable.py -v`
Expected: PASS, 16 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/rebrickable.py tests/test_rebrickable.py
git commit -m "fetch the catalog CSVs, skipping any whose ETag has not moved"
```

---

## Task 5: The three tables, and writing facts into them

**Files:**
- Modify: `brick_icons/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py -- append
def test_the_fact_tables_are_created(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"part_facts", "part_colors", "colors"} <= names


def test_the_schema_stamp_does_not_move(tmp_path):
    # _SCHEMA is all CREATE TABLE IF NOT EXISTS and connect runs it on every
    # open, so an existing v1 file gains the tables with no migration.
    conn = db.connect(tmp_path / "corpus.db")
    assert conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == "1"


def _seeded(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    conn.executemany(
        "INSERT INTO parts (id, title, printed, obsolete) VALUES (?, ?, 0, 0)",
        [("3001", "Brick  2 x  4"), ("u9236", "Something Unofficial")])
    conn.commit()
    return conn


def test_importing_facts_writes_a_row_per_matched_part(tmp_path):
    conn = _seeded(tmp_path)
    facts = {"3001": {"rb_part": "3001", "matched_by": "id",
                      "year_first": 1974, "year_last": 2026, "uses": 11,
                      "sets": 3, "rb_category": "Bricks", "colors": [1, 4]}}
    n = db.import_facts(conn, facts, colors=[
        {"id": 1, "name": "Blue", "rgb": "0055BF", "is_trans": False},
        {"id": 4, "name": "Red", "rgb": "C91A09", "is_trans": False}])
    assert n == 1
    row = conn.execute("SELECT * FROM part_facts").fetchone()
    assert row["part_id"] == "3001"
    assert row["uses"] == 11
    assert row["matched_by"] == "id"
    assert {r[0] for r in conn.execute(
        "SELECT color_id FROM part_colors WHERE part_id='3001'")} == {1, 4}


def test_an_unmatched_part_gets_no_row(tmp_path):
    conn = _seeded(tmp_path)
    db.import_facts(conn, {}, colors=[])
    assert conn.execute("SELECT COUNT(*) FROM part_facts").fetchone()[0] == 0


def test_importing_twice_replaces_rather_than_duplicates(tmp_path):
    conn = _seeded(tmp_path)
    facts = {"3001": {"rb_part": "3001", "matched_by": "id",
                      "year_first": 1974, "year_last": 2026, "uses": 11,
                      "sets": 3, "rb_category": "Bricks", "colors": [1]}}
    db.import_facts(conn, facts, colors=[
        {"id": 1, "name": "Blue", "rgb": "0055BF", "is_trans": False}])
    facts["3001"]["uses"] = 12
    facts["3001"]["colors"] = [4]
    db.import_facts(conn, facts, colors=[
        {"id": 4, "name": "Red", "rgb": "C91A09", "is_trans": False}])
    assert conn.execute("SELECT uses FROM part_facts").fetchone()[0] == 12
    assert {r[0] for r in conn.execute("SELECT color_id FROM part_colors")} == {4}


def test_a_fact_for_an_unknown_part_is_skipped(tmp_path):
    # The join runs over the LDraw ids, but a stale cache could carry an id the
    # library no longer has; a foreign key error mid-import would lose the rest.
    conn = _seeded(tmp_path)
    db.import_facts(conn, {"9999": {
        "rb_part": "9999", "matched_by": "id", "year_first": None,
        "year_last": None, "uses": 1, "sets": 1, "rb_category": None,
        "colors": []}}, colors=[])
    assert conn.execute("SELECT COUNT(*) FROM part_facts").fetchone()[0] == 0
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/test_db.py -k facts -v`
Expected: FAIL, `AssertionError` on the table names

- [ ] **Step 3: Write the implementation**

Append to `_SCHEMA` in `brick_icons/db.py`, before the closing `"""`:

```sql
CREATE TABLE IF NOT EXISTS part_facts (
  part_id TEXT PRIMARY KEY REFERENCES parts(id),
  rb_part TEXT NOT NULL,
  matched_by TEXT NOT NULL,
  year_first INTEGER,
  year_last INTEGER,
  uses INTEGER NOT NULL DEFAULT 0,
  sets INTEGER NOT NULL DEFAULT 0,
  rb_category TEXT,
  fetched TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS part_colors (
  part_id TEXT NOT NULL REFERENCES parts(id),
  color_id INTEGER NOT NULL,
  PRIMARY KEY (part_id, color_id)
);

CREATE TABLE IF NOT EXISTS colors (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  rgb TEXT NOT NULL,
  is_trans INTEGER NOT NULL DEFAULT 0
);
```

Then append the writer:

```python
# brick_icons/db.py -- append near import_defects
def import_facts(conn: sqlite3.Connection, facts: dict[str, dict],
                 colors: list[dict]) -> int:
    """Replace the outside-fact tables with `facts`.

    Replace, not merge: a part that stopped matching must lose its row, or the
    wall keeps showing a fact the current catalog no longer supports.
    """
    known = {r[0] for r in conn.execute("SELECT id FROM parts")}
    stamp = now()
    conn.execute("DELETE FROM part_colors")
    conn.execute("DELETE FROM part_facts")
    conn.executemany(
        "INSERT OR REPLACE INTO colors (id, name, rgb, is_trans) "
        "VALUES (?, ?, ?, ?)",
        [(c["id"], c["name"], c["rgb"], int(bool(c["is_trans"])))
         for c in colors])
    rows = [(pid, f["rb_part"], f["matched_by"], f["year_first"],
             f["year_last"], f["uses"], f["sets"], f["rb_category"], stamp)
            for pid, f in facts.items() if pid in known]
    conn.executemany(
        "INSERT INTO part_facts (part_id, rb_part, matched_by, year_first, "
        "year_last, uses, sets, rb_category, fetched) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    conn.executemany(
        "INSERT INTO part_colors (part_id, color_id) VALUES (?, ?)",
        [(pid, cid) for pid, f in facts.items() if pid in known
         for cid in f["colors"]])
    conn.commit()
    return len(rows)
```

- [ ] **Step 4: Run it and watch it pass**

Run: `.venv/bin/python -m pytest tests/test_db.py -v`
Expected: PASS, including every pre-existing `test_db` test

- [ ] **Step 5: Commit**

```bash
git add brick_icons/db.py tests/test_db.py
git commit -m "three tables for the outside part facts, replaced whole on import"
```

---

## Task 6: The import CLI

**Files:**
- Create: `scripts/import-rebrickable.py`
- Modify: `brick_icons/rebrickable.py`

A minutes-long job must say where it is: one line per file, and one per
thousand parts joined.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rebrickable.py -- append
def test_the_join_assembles_a_row_per_matched_part(tmp_path):
    catalog = {
        "parts": [{"part_num": "3001", "name": "Brick", "part_cat_id": "11"}],
        "part_categories": [{"id": "11", "name": "Bricks"}],
        "elements": [{"part_num": "3001", "color_id": "4", "design_id": ""}],
        "sets": [{"set_num": "s-1", "year": "1974"}],
        "inventories": [{"id": "1", "set_num": "s-1"}],
        "inventory_parts": [{"inventory_id": "1", "part_num": "3001",
                             "color_id": "4", "quantity": "2"}],
    }
    facts = rb.join(["3001", "u9236"], catalog)
    assert set(facts) == {"3001"}
    assert facts["3001"] == {
        "rb_part": "3001", "matched_by": "id", "year_first": 1974,
        "year_last": 1974, "uses": 2, "sets": 1, "rb_category": "Bricks",
        "colors": [4]}


def test_a_matched_part_never_in_an_inventory_still_gets_a_row(tmp_path):
    # It matched, so we know its category; we just know of no set using it.
    catalog = {
        "parts": [{"part_num": "3001", "name": "Brick", "part_cat_id": "11"}],
        "part_categories": [{"id": "11", "name": "Bricks"}],
        "elements": [], "sets": [], "inventories": [], "inventory_parts": [],
    }
    facts = rb.join(["3001"], catalog)
    assert facts["3001"]["uses"] == 0
    assert facts["3001"]["colors"] == []
    assert facts["3001"]["year_first"] is None
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/test_rebrickable.py -k join -v`
Expected: FAIL, `AttributeError: module 'brick_icons.rebrickable' has no attribute 'join'`

- [ ] **Step 3: Write the implementation**

```python
# brick_icons/rebrickable.py -- append
def join(ldraw_ids: Iterable[str], catalog: dict[str, Iterable[dict]],
         progress=lambda msg: None) -> dict[str, dict]:
    """LDraw id -> the fact row `db.import_facts` wants, for matched ids only.

    `catalog` maps a file name from FILES to its rows; anything the join does
    not need may be omitted.
    """
    ldraw_ids = list(ldraw_ids)
    parts = {r["part_num"]: r for r in catalog.get("parts", ())}
    cats = {r["id"]: r["name"] for r in catalog.get("part_categories", ())}
    design: dict[str, set[str]] = {}
    for row in catalog.get("elements", ()):
        if row.get("design_id"):
            design.setdefault(row["design_id"], set()).add(row["part_num"])
    progress(f"{len(parts)} catalog parts, {len(design)} design ids")

    links = link_ids(ldraw_ids, set(parts), design)
    progress(f"{len(links)} of {len(ldraw_ids)} LDraw ids matched")

    set_year = {r["set_num"]: int(r["year"])
                for r in catalog.get("sets", ()) if r["year"]}
    inv_set = {r["id"]: r["set_num"] for r in catalog.get("inventories", ())}
    facts = aggregate(catalog.get("inventory_parts", ()), inv_set, set_year)
    progress(f"{len(facts)} catalog parts carry inventory facts")

    out: dict[str, dict] = {}
    for n, (pid, (rb_part, how)) in enumerate(sorted(links.items()), 1):
        f = facts.get(rb_part, PartFacts())
        out[pid] = {
            "rb_part": rb_part, "matched_by": how,
            "year_first": f.year_first, "year_last": f.year_last,
            "uses": f.uses, "sets": len(f.sets),
            "rb_category": cats.get(parts[rb_part].get("part_cat_id", ""))
                           if rb_part in parts else None,
            "colors": sorted(f.colors),
        }
        if n % 1000 == 0:
            progress(f"joined {n}/{len(links)}")
    return out
```

```python
#!/usr/bin/env python3
# scripts/import-rebrickable.py
"""Join Rebrickable's public catalog onto the corpus's parts.

    .venv/bin/python scripts/import-rebrickable.py

Downloads eight gzipped CSVs to out/rebrickable/ (skipping any whose ETag has
not moved), joins them onto the LDraw part ids, and replaces the part_facts,
part_colors and colors tables. Safe to re-run.

Data from Rebrickable (https://rebrickable.com/downloads/). Attribution is a
condition of use.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db, rebrickable as rb  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--cache", default=str(ROOT / "out" / "rebrickable"))
    args = ap.parse_args()

    say = lambda m: print(m, flush=True)  # noqa: E731
    cache = Path(args.cache)
    catalog = {}
    for i, name in enumerate(rb.FILES, 1):
        path = rb.fetch(name, cache)
        rows = list(rb.read_csv(path))
        catalog[name] = rows
        say(f"{i}/{len(rb.FILES)} {name}: {len(rows)} rows")

    conn = db.connect(args.db)
    ldraw_ids = [r[0] for r in conn.execute("SELECT id FROM parts ORDER BY id")]
    facts = rb.join(ldraw_ids, catalog, progress=say)
    n = db.import_facts(conn, facts, colors=[
        {"id": int(c["id"]), "name": c["name"], "rgb": c["rgb"],
         "is_trans": c["is_trans"] == "True"}
        for c in catalog["colors"]])
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('rebrickable_rows', ?)",
                 (",".join(f"{k}={len(v)}" for k, v in catalog.items()),))
    conn.commit()
    say(f"{n} of {len(ldraw_ids)} parts carry outside facts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run it and watch it pass**

Run: `.venv/bin/python -m pytest tests/test_rebrickable.py -v`
Expected: PASS, 18 tests

Then run it for real:

Run: `.venv/bin/python scripts/import-rebrickable.py`
Expected: eight progress lines, then a match count. On today's corpus that
number is about 5,500 of 24,591; the drawable subset is about 73%.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/rebrickable.py scripts/import-rebrickable.py tests/test_rebrickable.py
git commit -m "import Rebrickable's catalog: year, uses, sets and colors per part"
```

---

## Task 7: `rebuild` carries the facts through

**Files:**
- Modify: `brick_icons/db.py`
- Modify: `tests/test_db.py`

`rebuild` unlinks the database, so a rebuild drops every fact. It has to
re-import them from the cache it already has.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py -- append
def _facts_cache(tmp_path):
    """A cache directory holding all eight files, minimal but well-formed."""
    from brick_icons import rebrickable as rb
    cache = tmp_path / "rb"
    cache.mkdir()
    headers = {
        "parts": "part_num,name,part_cat_id\n3001,Brick,11\n",
        "part_categories": "id,name\n11,Bricks\n",
        "colors": "id,name,rgb,is_trans\n4,Red,C91A09,False\n",
        "elements": "element_id,part_num,color_id,design_id\n1,3001,4,\n",
        "sets": "set_num,name,year\ns-1,Set,1974\n",
        "inventories": "id,version,set_num\n1,1,s-1\n",
        "inventory_parts": "inventory_id,part_num,color_id,quantity\n1,3001,4,2\n",
        "part_relationships": "rel_type,child_part_num,parent_part_num\n",
    }
    assert set(headers) == set(rb.FILES)
    for name, body in headers.items():
        (cache / f"{name}.csv.gz").write_bytes(gzip.compress(body.encode()))
    return cache


def _rebuild(tmp_path, **over):
    return db.rebuild(tmp_path / "corpus.db", ldraw_dir=_library(tmp_path),
                      root=tmp_path, census_dir=tmp_path / "nope",
                      defects_path=tmp_path / "none.toml",
                      status_path=tmp_path / "none.toml", **over)


def test_rebuild_reimports_facts_from_the_cache(tmp_path):
    counts = _rebuild(tmp_path, facts_cache=_facts_cache(tmp_path))
    assert counts["facts"] == 1
    conn = db.connect(tmp_path / "corpus.db")
    assert conn.execute(
        "SELECT year_first FROM part_facts WHERE part_id='3001'").fetchone()[0] == 1974


def test_rebuild_never_reaches_for_the_network(tmp_path, monkeypatch):
    # A rebuild on a machine with no cache carries no facts rather than
    # downloading 17 MB nobody asked for.
    from brick_icons import rebrickable as rb
    monkeypatch.setattr(rb, "fetch", lambda name, into: pytest.fail("downloaded"))
    assert _rebuild(tmp_path, facts_cache=tmp_path / "absent")["facts"] == 0


def test_rebuild_without_a_facts_cache_is_not_an_error(tmp_path):
    # A fresh clone has no out/rebrickable/.
    assert _rebuild(tmp_path, facts_cache=None)["facts"] == 0


def test_a_half_written_cache_carries_no_facts_rather_than_partial_ones(tmp_path):
    cache = _facts_cache(tmp_path)
    (cache / "sets.csv.gz").unlink()
    assert _rebuild(tmp_path, facts_cache=cache)["facts"] == 0
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/test_db.py -k rebuild -v`
Expected: FAIL, `TypeError: rebuild() got an unexpected keyword argument 'facts_cache'`

`tests/test_db.py` needs `import gzip` at the top if it does not have it.

- [ ] **Step 3: Write the implementation**

In `brick_icons/db.py`, add the parameter to `rebuild`'s signature after
`status_path`:

```python
                facts_cache: Path | str | None = None,
```

and before `conn.close()`:

```python
    counts["facts"] = _reimport_facts(conn, facts_cache, progress)
    progress(f"{counts['facts']} parts carry outside facts")
```

and add, above `rebuild`:

```python
def _reimport_facts(conn: sqlite3.Connection, cache: Path | str | None,
                    progress) -> int:
    """Re-join whatever Rebrickable CSVs are already cached.

    A rebuild deletes the database, so the facts go with it. This never
    downloads: a rebuild on a machine with no cache carries no facts rather
    than reaching for the network.
    """
    from brick_icons import rebrickable as rb
    if cache is None:
        return 0
    cache = Path(cache)
    catalog = {}
    for name in rb.FILES:
        path = cache / f"{name}.csv.gz"
        if not path.exists():
            progress(f"no cached {name}; skipping the outside facts")
            return 0
        catalog[name] = list(rb.read_csv(path))
    ldraw_ids = [r[0] for r in conn.execute("SELECT id FROM parts ORDER BY id")]
    facts = rb.join(ldraw_ids, catalog, progress=progress)
    return import_facts(conn, facts, colors=[
        {"id": int(c["id"]), "name": c["name"], "rgb": c["rgb"],
         "is_trans": c["is_trans"] == "True"} for c in catalog["colors"]])
```

Then in `scripts/build-corpus-db.py`, add the argument and pass it:

```python
    ap.add_argument("--facts-cache", default=str(ROOT / "out" / "rebrickable"))
```

```python
                        commit_sha=sha or "unknown", facts_cache=args.facts_cache,
```

- [ ] **Step 4: Run it and watch it pass**

Run: `.venv/bin/python -m pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brick_icons/db.py scripts/build-corpus-db.py tests/test_db.py
git commit -m "carry the outside facts through a rebuild, from cache and never the network"
```

---

## Task 8: Facts in the cells response

**Files:**
- Modify: `brick_icons/lab/cells.py`
- Modify: `tests/test_lab_cells.py`

The category name goes in the body once and each cell carries an index into it.
24,591 repeated strings for 171 distinct values is most of a megabyte.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lab_cells.py -- append. `_conn` is a seeded connection carrying a
# part with id '3001'; build it exactly the way the tests already in this file
# build theirs rather than adding a second fixture.
def test_a_cell_carries_its_outside_facts(_conn):
    conn = _conn
    conn.execute(
        "INSERT INTO part_facts (part_id, rb_part, matched_by, year_first, "
        "year_last, uses, sets, rb_category, fetched) "
        "VALUES ('3001', '3001', 'id', 1974, 2026, 11, 3, 'Bricks', 'now')")
    conn.executemany("INSERT INTO part_colors VALUES (?, ?)",
                     [("3001", 1), ("3001", 4)])
    conn.commit()
    cell = next(c for c in cells.cells(conn)["cells"] if c["id"] == "3001")
    assert cell["year"] == 1974
    assert cell["year_last"] == 2026
    assert cell["uses"] == 11
    assert cell["sets"] == 3
    assert cell["ncolors"] == 2


def test_a_cell_with_no_facts_carries_nulls_and_no_uses(_conn):
    cell = next(c for c in cells.cells(_conn)["cells"] if c["id"] == "3001")
    assert cell["year"] is None
    assert cell["uses"] is None


def test_categories_are_sent_once_and_indexed(_conn):
    body = cells.cells(_conn)
    cats = body["categories"]
    assert cats == sorted(cats)
    cell = body["cells"][0]
    assert cats[cell["cat"]] is not None


def test_a_part_with_no_category_indexes_the_placeholder(_conn):
    _conn.execute("UPDATE parts SET category = NULL WHERE id = '3001'")
    _conn.commit()
    body = cells.cells(_conn)
    cell = next(c for c in body["cells"] if c["id"] == "3001")
    assert body["categories"][cell["cat"]] == "-"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest tests/test_lab_cells.py -v`
Expected: FAIL, `KeyError: 'year'`

- [ ] **Step 3: Write the implementation**

In `brick_icons/lab/cells.py`, add the import and, inside `cells()` after
`error_elsewhere` is built:

```python
from brick_icons.rebrickable import clean_category
```

```python
    facts = {r["part_id"]: r for r in conn.execute(
        "SELECT part_id, year_first, year_last, uses, sets FROM part_facts")}
    ncolors: dict[str, int] = {}
    for r in conn.execute(
            "SELECT part_id, COUNT(*) AS n FROM part_colors GROUP BY part_id"):
        ncolors[r["part_id"]] = r["n"]
```

Build the category table over every part, not just the page, so a delta's
indices stay valid against the full list:

```python
    names = sorted({clean_category(r["category"])
                    for r in conn.execute("SELECT category FROM parts")})
    cat_index = {name: i for i, name in enumerate(names)}
```

In the row dict, replace nothing and append:

```python
            "cat": cat_index[clean_category(part["category"])],
            "year": fact["year_first"] if fact else None,
            "year_last": fact["year_last"] if fact else None,
            "uses": fact["uses"] if fact else None,
            "sets": fact["sets"] if fact else None,
            "ncolors": ncolors.get(pid, 0) if fact else None,
```

with `fact = facts.get(pid)` beside the existing `render = ...` lookups, and
add `"categories": names` to the returned dict.

- [ ] **Step 4: Run it and watch it pass**

Run: `.venv/bin/python -m pytest tests/test_lab_cells.py tests/test_lab_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/cells.py tests/test_lab_cells.py
git commit -m "carry year, uses and color count per cell, and category names once"
```

---

## Task 9: The client's view of a cell

**Files:**
- Modify: `lab/src/corpus/types.ts`
- Create: `lab/src/corpus/facts.ts`
- Create: `lab/src/corpus/facts.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// lab/src/corpus/facts.test.ts
import { describe, expect, it } from 'vitest';
import {
  UNKNOWN, categoryOf, coverageOf, decadeOf, groupers, rollUp, yearOf,
} from '@lab/corpus/facts';
import type { Cell } from '@lab/corpus/types';

const cell = (over: Partial<Cell> = {}): Cell => ({
  id: '3001', index: 0, title: 'Brick', category: 'Brick', cat: 0,
  printed: false, obsolete: false, status: 'unreviewed', sha: null,
  made_at: null, extra_d99: null, secs: null, error: null,
  open_defects: 0, open_defects_elsewhere: 0, error_elsewhere: false,
  year: null, year_last: null, uses: null, sets: null, ncolors: null,
  ...over,
});

describe('rollUp', () => {
  it('folds anything under the minimum into Other', () => {
    const cells = [...Array(30)].map(() => cell({ cat: 0 }))
      .concat([...Array(3)].map(() => cell({ cat: 1 })));
    const map = rollUp(cells, ['Brick', 'Dish'], 25);
    expect(map.get('Brick')).toBe('Brick');
    expect(map.get('Dish')).toBe('Other');
  });

  it('leaves the no-category placeholder alone', () => {
    const map = rollUp([cell({ cat: 0 })], ['-'], 25);
    expect(map.get('-')).toBe('-');
  });
});

describe('coverageOf', () => {
  it('ranks a defect above a failure and a failure above a timeout', () => {
    expect(coverageOf(cell({ open_defects: 1, error: 'TimeoutError' }))).toBe('defect');
    expect(coverageOf(cell({ error: 'GEOSException' }))).toBe('failed');
    expect(coverageOf(cell({ error: 'TimeoutError' }))).toBe('timeout');
  });

  it('separates a drawn cell from one never attempted', () => {
    expect(coverageOf(cell({ sha: 'abc' }))).toBe('drawn');
    expect(coverageOf(cell())).toBe('untried');
  });
});

describe('decadeOf and yearOf', () => {
  it('names the decade a part first appeared in', () => {
    expect(decadeOf(cell({ year: 1974 }))).toBe('1970s');
    expect(yearOf(cell({ year: 1974 }))).toBe('1974');
  });

  it('calls an undated part unknown at both levels', () => {
    expect(decadeOf(cell())).toBe(UNKNOWN);
    expect(yearOf(cell())).toBe(UNKNOWN);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd lab && npx vitest run src/corpus/facts.test.ts`
Expected: FAIL, cannot resolve `@lab/corpus/facts`

- [ ] **Step 3: Write the implementation**

Add to `Cell` in `lab/src/corpus/types.ts`:

```ts
  /** Index into `CellsBody.categories`. */
  cat: number;
  /** Earliest set year, or null when the part matched nothing outside. */
  year: number | null;
  year_last: number | null;
  uses: number | null;
  sets: number | null;
  ncolors: number | null;
```

and to `CellsBody`:

```ts
  categories: string[];
```

```ts
// lab/src/corpus/facts.ts
import type { Cell } from '@lab/corpus/types';

/** A part that matched nothing outside, at every grouping level. Never the low
 *  end of a ramp: "we do not know" and "1954, never used" are different. */
export const UNKNOWN = 'unknown';

/** A part whose description began with a bare marker. `cells.py` sends this
 *  as a category name, so it arrives already cleaned. */
export const NO_CATEGORY = '-';

export type Coverage = 'defect' | 'failed' | 'timeout' | 'drawn' | 'untried';

const COVERAGE_ORDER: Coverage[] =
  ['defect', 'failed', 'timeout', 'drawn', 'untried'];

export function coverageOf(cell: Cell): Coverage {
  if (cell.open_defects > 0) return 'defect';
  if (cell.error && cell.error !== 'TimeoutError') return 'failed';
  if (cell.error) return 'timeout';
  return cell.sha ? 'drawn' : 'untried';
}

export function categoryOf(cell: Cell, categories: string[]): string {
  return categories[cell.cat] ?? NO_CATEGORY;
}

export function decadeOf(cell: Cell): string {
  return cell.year === null ? UNKNOWN : `${Math.floor(cell.year / 10) * 10}s`;
}

export function yearOf(cell: Cell): string {
  return cell.year === null ? UNKNOWN : String(cell.year);
}

/** Clean category to the group it is drawn under.
 *
 *  Grouping and the facet list use different thresholds on purpose: a labeled
 *  block of three cells is confetti, but a checkbox costs one row. */
export function rollUp(cells: Cell[], categories: string[],
                       minimum = 25): Map<string, string> {
  const counts = new Map<string, number>();
  for (const c of cells) {
    const name = categoryOf(c, categories);
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  const out = new Map<string, string>();
  for (const name of categories) {
    const n = counts.get(name) ?? 0;
    out.set(name, name === NO_CATEGORY || n >= minimum ? name : 'Other');
  }
  return out;
}

export type Grouping = 'none' | 'coverage' | 'category' | 'release';

/** The key functions each grouping needs, outermost first. `release` is the
 *  only two-level one. */
export function groupers(grouping: Grouping, categories: string[],
                         rolled: Map<string, string>):
                         ((c: Cell) => string)[] {
  switch (grouping) {
    case 'none': return [];
    case 'coverage': return [coverageOf];
    case 'category': return [(c) => rolled.get(categoryOf(c, categories)) ?? 'Other'];
    case 'release': return [decadeOf, yearOf];
  }
}

export { COVERAGE_ORDER };
```

- [ ] **Step 4: Run it and watch it pass**

Run: `cd lab && npx vitest run src/corpus/facts.test.ts && npx tsc -b --noEmit`
Expected: PASS, and no type errors

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/facts.ts lab/src/corpus/facts.test.ts lab/src/corpus/types.ts
git commit -m "the group key of a cell: coverage, rolled-up category, decade and year"
```

---

## Task 10: `bands` in the layout contract

**Files:**
- Modify: `lab/src/corpus/layout.ts`
- Modify: `lab/src/corpus/layout.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// lab/src/corpus/layout.test.ts -- append
it('reports no bands, because a dense grid has no groups', () => {
  const out = gridLayout([cell(), cell()], { cell: 32, gap: 4, cols: 2 });
  expect(out.bands).toEqual([]);
});
```

Use whatever `cell()` helper this file already defines.

- [ ] **Step 2: Run it and watch it fail**

Run: `cd lab && npx vitest run src/corpus/layout.test.ts`
Expected: FAIL, `expected undefined to deeply equal []`

- [ ] **Step 3: Write the implementation**

In `lab/src/corpus/layout.ts`:

```ts
/** A group header a layout wants drawn. `depth` 0 is the outer band, 1 an
 *  inner block inside it -- so paint styles the two without a second field,
 *  and a third level costs the type nothing. */
export interface Band {
  key: string;
  label: string;
  count: number;
  rect: Rect;
  depth: 0 | 1;
}

export type Layout = (cells: Cell[], opts: LayoutOptions) =>
  { rects: Rect[]; bands: Band[]; bounds: { w: number; h: number } };
```

and in `gridLayout`'s return, add `bands: [],` beside `rects`.

- [ ] **Step 4: Run it and watch it pass**

Run: `cd lab && npx vitest run src/corpus/layout.test.ts && npx tsc -b --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/layout.ts lab/src/corpus/layout.test.ts
git commit -m "let a layout report the group headers it wants drawn"
```

---

## Task 11: Flow blocks across a width

**Files:**
- Create: `lab/src/corpus/grouped.ts`
- Create: `lab/src/corpus/grouped.test.ts`

The one primitive both grouped layouts are built from: a list of groups packed
as blocks, flowed left to right, wrapping when the next block would overrun.

- [ ] **Step 1: Write the failing test**

```ts
// lab/src/corpus/grouped.test.ts
import { describe, expect, it } from 'vitest';
import { flowBlocks } from '@lab/corpus/grouped';

const opts = { cell: 10, gap: 0, cols: 10 };   // pitch 10, 100 wide

describe('flowBlocks', () => {
  it('places a group\'s cells row-major under its own header', () => {
    const out = flowBlocks([{ key: 'a', items: [0, 1, 2, 3] }], opts, 0, 1);
    // 4 items -> ceil(sqrt(4 * 1.35)) = 3 columns
    expect(out.placed.map((p) => [p.index, p.rect.x, p.rect.y])).toEqual([
      [0, 0, 10], [1, 10, 10], [2, 20, 10], [3, 0, 20],
    ]);
  });

  it('reserves the header rows above each block', () => {
    const out = flowBlocks([{ key: 'a', items: [0] }], opts, 0, 2);
    expect(out.placed[0]!.rect.y).toBe(20);
  });

  it('wraps to a new row when the next block would overrun', () => {
    const wide = { key: 'w', items: [...Array(64).keys()] };       // 10 cols
    const next = { key: 'n', items: [0] };                          // 1 col
    const out = flowBlocks([wide, next], opts, 0, 1);
    const band = out.bands.find((b) => b.key === 'n')!;
    expect(band.rect.x).toBe(0);
    expect(band.rect.y).toBeGreaterThan(0);
  });

  it('never gives a block more columns than the width allows', () => {
    const out = flowBlocks([{ key: 'a', items: [...Array(400).keys()] }],
                           opts, 0, 1);
    expect(Math.max(...out.placed.map((p) => p.rect.x))).toBeLessThan(100);
  });

  it('reports a band per group, with its count and its own box', () => {
    const out = flowBlocks([{ key: 'a', items: [0, 1] }], opts, 0, 1);
    expect(out.bands).toHaveLength(1);
    expect(out.bands[0]).toMatchObject({ key: 'a', count: 2, depth: 1 });
  });

  it('is empty for no groups, and reports no height', () => {
    const out = flowBlocks([], opts, 0, 1);
    expect(out.placed).toEqual([]);
    expect(out.height).toBe(0);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd lab && npx vitest run src/corpus/grouped.test.ts`
Expected: FAIL, cannot resolve `@lab/corpus/grouped`

- [ ] **Step 3: Write the implementation**

```ts
// lab/src/corpus/grouped.ts
import type { Band, LayoutOptions, Rect } from '@lab/corpus/layout';

export interface Group { key: string; label?: string; items: number[] }
export interface Placed { index: number; rect: Rect }
export interface Flowed { placed: Placed[]; bands: Band[]; height: number }

// A block a little wider than tall reads as a block rather than a column, and
// packs more groups per row than a square would.
const BLOCK_ASPECT = 1.35;
// Blocks are separated by two pitches; less and two groups read as one.
const BLOCK_GAP_PITCHES = 2;

export function blockCols(n: number, cols: number): number {
  return Math.min(cols, Math.max(1, Math.ceil(Math.sqrt(n * BLOCK_ASPECT))));
}

/** Pack `groups` as blocks flowed across `cols` cells, starting at `top`.
 *
 *  `headerRows` rows of pitch are reserved above every block for its label.
 *  The caller places cells by index, so this never sees a `Cell`. */
export function flowBlocks(groups: Group[], opts: LayoutOptions, top: number,
                           headerRows: number): Flowed {
  const pitch = opts.cell + opts.gap;
  const width = opts.cols * pitch;
  const gutter = BLOCK_GAP_PITCHES * pitch;
  const placed: Placed[] = [];
  const bands: Band[] = [];
  let x = 0;
  let y = top;
  let rowHeight = 0;

  for (const group of groups) {
    const n = group.items.length;
    const c = blockCols(n, opts.cols);
    const rows = Math.ceil(n / c);
    const w = c * pitch;
    if (x > 0 && x + w > width) {
      x = 0;
      y += rowHeight + gutter;
      rowHeight = 0;
    }
    const cellTop = y + headerRows * pitch;
    group.items.forEach((index, i) => {
      placed.push({
        index,
        rect: { x: x + (i % c) * pitch, y: cellTop + Math.floor(i / c) * pitch,
                w: opts.cell, h: opts.cell },
      });
    });
    const h = headerRows * pitch + rows * pitch - opts.gap;
    bands.push({ key: group.key, label: group.label ?? group.key, count: n,
                 rect: { x, y, w: w - opts.gap, h }, depth: 1 });
    rowHeight = Math.max(rowHeight, h);
    x += w + gutter;
  }

  return { placed, bands, height: groups.length ? y + rowHeight - top : 0 };
}
```

- [ ] **Step 4: Run it and watch it pass**

Run: `cd lab && npx vitest run src/corpus/grouped.test.ts && npx tsc -b --noEmit`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/grouped.ts lab/src/corpus/grouped.test.ts
git commit -m "flow groups as blocks across a width, wrapping when one overruns"
```

---

## Task 12: The two grouped layouts

**Files:**
- Modify: `lab/src/corpus/grouped.ts`
- Modify: `lab/src/corpus/grouped.test.ts`

`blockLayout` for one level, `bandedLayout` for two. Both return a `Layout`, so
`CorpusWall` picks one and nothing downstream changes.

- [ ] **Step 1: Write the failing test**

```ts
// lab/src/corpus/grouped.test.ts -- append
import { bandedLayout, blockLayout } from '@lab/corpus/grouped';
import type { Cell } from '@lab/corpus/types';

const c = (over: Partial<Cell>): Cell => ({
  id: 'x', index: 0, title: '', category: null, cat: 0, printed: false,
  obsolete: false, status: 'unreviewed', sha: null, made_at: null,
  extra_d99: null, secs: null, error: null, open_defects: 0,
  open_defects_elsewhere: 0, error_elsewhere: false, year: null,
  year_last: null, uses: null, sets: null, ncolors: null, ...over,
});

describe('blockLayout', () => {
  it('returns one rect per cell, in the order it was given them', () => {
    const cells = [c({ id: 'a', sha: 'x' }), c({ id: 'b' }), c({ id: 'd', sha: 'x' })];
    const out = blockLayout((x) => (x.sha ? 'drawn' : 'untried'),
                            ['drawn', 'untried'])(cells, opts);
    expect(out.rects).toHaveLength(3);
    // Cell 'b' is in the second block, so it sits right of or below 'a'.
    expect(out.rects[1]!.x + out.rects[1]!.y)
      .toBeGreaterThan(out.rects[0]!.x + out.rects[0]!.y);
  });

  it('orders its blocks by the order it is given, not by size', () => {
    const cells = [c({ id: 'a' }), c({ id: 'b', sha: 'x' }), c({ id: 'd', sha: 'x' })];
    const out = blockLayout((x) => (x.sha ? 'drawn' : 'untried'),
                            ['drawn', 'untried'])(cells, opts);
    expect(out.bands.map((b) => b.key)).toEqual(['drawn', 'untried']);
  });

  it('drops a group nothing falls into', () => {
    const out = blockLayout(() => 'drawn', ['drawn', 'untried'])([c({})], opts);
    expect(out.bands.map((b) => b.key)).toEqual(['drawn']);
  });
});

describe('bandedLayout', () => {
  const byDecade = (x: Cell) => (x.year ? `${Math.floor(x.year / 10) * 10}s` : 'unknown');
  const byYear = (x: Cell) => (x.year ? String(x.year) : 'unknown');

  it('stacks the outer groups and puts the newest first when descending', () => {
    const cells = [c({ year: 1974 }), c({ year: 2011 })];
    const out = bandedLayout(byDecade, byYear, true)(cells, opts);
    const outer = out.bands.filter((b) => b.depth === 0);
    expect(outer.map((b) => b.key)).toEqual(['2010s', '1970s']);
    expect(outer[0]!.rect.y).toBeLessThan(outer[1]!.rect.y);
  });

  it('runs oldest first when ascending', () => {
    const cells = [c({ year: 1974 }), c({ year: 2011 })];
    const out = bandedLayout(byDecade, byYear, false)(cells, opts);
    expect(out.bands.filter((b) => b.depth === 0).map((b) => b.key))
      .toEqual(['1970s', '2010s']);
  });

  it('sorts the undated band last whichever way the rest runs', () => {
    const cells = [c({ year: 1974 }), c({})];
    for (const desc of [true, false]) {
      const out = bandedLayout(byDecade, byYear, desc)(cells, opts);
      const outer = out.bands.filter((b) => b.depth === 0);
      expect(outer[outer.length - 1]!.key).toBe('unknown');
    }
  });

  it('breaks a band into its inner groups at depth 1', () => {
    const cells = [c({ year: 1974 }), c({ year: 1978 })];
    const out = bandedLayout(byDecade, byYear, true)(cells, opts);
    expect(out.bands.filter((b) => b.depth === 1).map((b) => b.key))
      .toEqual(['1978', '1974']);
  });

  it('bounds the whole wall, not just the last band', () => {
    const cells = [c({ year: 1974 }), c({ year: 2011 })];
    const out = bandedLayout(byDecade, byYear, true)(cells, opts);
    const lowest = Math.max(...out.rects.map((r) => r.y + r.h));
    expect(out.bounds.h).toBeGreaterThanOrEqual(lowest);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd lab && npx vitest run src/corpus/grouped.test.ts`
Expected: FAIL, `blockLayout` is not exported

- [ ] **Step 3: Write the implementation**

```ts
// lab/src/corpus/grouped.ts -- append
import { UNKNOWN } from '@lab/corpus/facts';
import type { Layout } from '@lab/corpus/layout';
import type { Cell } from '@lab/corpus/types';

const OUTER_HEADER_ROWS = 2;
const INNER_HEADER_ROWS = 1;
// Between two outer bands. Wider than the gap between blocks inside one, or
// the levels stop reading as levels.
const BAND_GAP_PITCHES = 3;

function bucket(cells: Cell[], key: (c: Cell) => string): Map<string, number[]> {
  const out = new Map<string, number[]>();
  cells.forEach((cell, i) => {
    const k = key(cell);
    const held = out.get(k);
    if (held) held.push(i);
    else out.set(k, [i]);
  });
  return out;
}

function boundsOf(rects: Rect[], bands: Band[]): { w: number; h: number } {
  let w = 0;
  let h = 0;
  for (const r of [...rects, ...bands.map((b) => b.rect)]) {
    w = Math.max(w, r.x + r.w);
    h = Math.max(h, r.y + r.h);
  }
  return { w, h };
}

function rectsInOrder(cells: Cell[], placed: Placed[]): Rect[] {
  // `rects[i]` must address `cells[i]`: paint, hit-testing and the caret all
  // index the two together.
  const out = new Array<Rect>(cells.length);
  for (const p of placed) out[p.index] = p.rect;
  return out;
}

/** One level of grouping, blocks flowed and wrapped. `order` fixes which block
 *  comes first; a key it does not name sorts after the ones it does. */
export function blockLayout(key: (c: Cell) => string, order: string[]): Layout {
  return (cells, opts) => {
    const held = bucket(cells, key);
    const rank = new Map(order.map((k, i) => [k, i]));
    const groups: Group[] = [...held.entries()]
      .sort((a, b) => (rank.get(a[0]) ?? order.length)
                    - (rank.get(b[0]) ?? order.length)
                    || a[0].localeCompare(b[0]))
      .map(([k, items]) => ({ key: k, items }));
    const { placed, bands } = flowBlocks(groups, opts, 0, INNER_HEADER_ROWS);
    const rects = rectsInOrder(cells, placed);
    return { rects, bands, bounds: boundsOf(rects, bands) };
  };
}

// `UNKNOWN` is always last, in both directions: it is an absence, not an
// extreme, and sorting it to one end would read as a date.
function keyOrder(desc: boolean) {
  return (a: string, b: string) => {
    if ((a === UNKNOWN) !== (b === UNKNOWN)) return a === UNKNOWN ? 1 : -1;
    return a.localeCompare(b, undefined, { numeric: true }) * (desc ? -1 : 1);
  };
}

/** Two levels: outer groups stack as bands, inner groups flow inside one. */
export function bandedLayout(outer: (c: Cell) => string,
                             inner: (c: Cell) => string,
                             desc: boolean): Layout {
  return (cells, opts) => {
    const pitch = opts.cell + opts.gap;
    const cmp = keyOrder(desc);
    const outerGroups = [...bucket(cells, outer).entries()]
      .sort((a, b) => cmp(a[0], b[0]));
    const placed: Placed[] = [];
    const bands: Band[] = [];
    let y = 0;

    for (const [key, indices] of outerGroups) {
      const innerGroups: Group[] = [...bucket(
        indices.map((i) => cells[i]!), inner).entries()]
        .sort((a, b) => cmp(a[0], b[0]))
        .map(([k, local]) => ({ key: k, items: local.map((j) => indices[j]!) }));
      const top = y + OUTER_HEADER_ROWS * pitch;
      const flowed = flowBlocks(innerGroups, opts, top, INNER_HEADER_ROWS);
      placed.push(...flowed.placed);
      const h = OUTER_HEADER_ROWS * pitch + flowed.height;
      bands.push({ key, label: key, count: indices.length,
                   rect: { x: 0, y, w: opts.cols * pitch - opts.gap, h },
                   depth: 0 });
      bands.push(...flowed.bands);
      y += h + BAND_GAP_PITCHES * pitch;
    }

    const rects = rectsInOrder(cells, placed);
    return { rects, bands, bounds: boundsOf(rects, bands) };
  };
}
```

- [ ] **Step 4: Run it and watch it pass**

Run: `cd lab && npx vitest run src/corpus/grouped.test.ts && npx tsc -b --noEmit`
Expected: PASS, 14 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/grouped.ts lab/src/corpus/grouped.test.ts
git commit -m "two grouped layouts: blocks flowed, and bands of blocks stacked"
```

---

## Task 13: Draw the band labels

**Files:**
- Modify: `lab/src/corpus/paint.ts`
- Modify: `lab/src/corpus/paint.test.ts`
- Modify: `lab/src/corpus/Wall.tsx`

A label whose band is a few pixels wide is unreadable ink, so it is dropped
rather than drawn small.

- [ ] **Step 1: Write the failing test**

```ts
// lab/src/corpus/paint.test.ts -- append
import type { Band } from '@lab/corpus/layout';

const band = (over: Partial<Band> = {}): Band => ({
  key: '1970s', label: '1970s', count: 12,
  rect: { x: 0, y: 0, w: 400, h: 200 }, depth: 0, ...over,
});

describe('band labels', () => {
  const cam = { x: 0, y: 0, scale: { x: 1, y: 1 } };

  it('emits a label per band, with its count', () => {
    const out = paintCommands({
      cells: [], rects: [], visible: [], cam, manifest: null,
      palette: DEFAULT_PALETTE, bands: [band()],
    });
    const labels = out.filter((c) => c.kind === 'label');
    expect(labels).toHaveLength(1);
    expect(labels[0]).toMatchObject({ text: '1970s', count: 12, depth: 0 });
  });

  it('drops a band too narrow on screen to read', () => {
    const out = paintCommands({
      cells: [], rects: [], visible: [], cam: { ...cam, scale: { x: 0.01, y: 0.01 } },
      manifest: null, palette: DEFAULT_PALETTE, bands: [band()],
    });
    expect(out.filter((c) => c.kind === 'label')).toEqual([]);
  });

  it('emits nothing when there are no bands, as the dense grid has none', () => {
    const out = paintCommands({
      cells: [], rects: [], visible: [], cam, manifest: null,
      palette: DEFAULT_PALETTE,
    });
    expect(out.filter((c) => c.kind === 'label')).toEqual([]);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd lab && npx vitest run src/corpus/paint.test.ts`
Expected: FAIL, `expected [] to have a length of 1`

- [ ] **Step 3: Write the implementation**

In `lab/src/corpus/paint.ts`, add to `PaintCommand`:

```ts
  | { kind: 'label'; text: string; count: number; dx: number; dy: number;
      size: number; depth: 0 | 1 };
```

add to `PaintInput`:

```ts
  /** Group headers the layout asked for. Absent for a dense grid. */
  bands?: Band[];
```

and, after the cell loop in `paintCommands`, before `return out`:

```ts
  for (const b of bands ?? []) {
    const w = b.rect.w * cam.scale.x;
    if (w < MIN_LABEL_PX) continue;
    const [dx, dy] = worldToScreen(b.rect.x, b.rect.y, transform);
    const size = b.depth === 0 ? OUTER_LABEL_PX : INNER_LABEL_PX;
    out.push({ kind: 'label', text: b.label, count: b.count,
               dx, dy: dy + size, size, depth: b.depth });
  }
```

with the constants beside `DIM_ALPHA`:

```ts
// A label narrower than its own text is ink, not a word.
const MIN_LABEL_PX = 40;
const OUTER_LABEL_PX = 18;
const INNER_LABEL_PX = 11;
```

and `bands` destructured out of the input alongside `highlight`.

In `Wall.tsx`, add to `drawPaintCommand`, before the closing brace of the
`else if` chain:

```ts
  } else if (cmd.kind === 'label') {
    ctx.save();
    ctx.fillStyle = cmd.depth === 0 ? palette.label.fill : palette.sublabel.fill;
    ctx.font = `${cmd.depth === 0 ? 700 : 600} ${cmd.size}px ui-sans-serif, system-ui, sans-serif`;
    ctx.textBaseline = 'alphabetic';
    ctx.fillText(cmd.depth === 0 ? `${cmd.text}  ${cmd.count.toLocaleString()}`
                                 : cmd.text, dx, dy);
    ctx.restore();
  }
```

and pass `bands` through both `paintCommands` calls in the two draw effects —
but **not** the one in `hitTest`: a label is not a hit target, and including it
would let a click on a header pick the wrong cell.

Add two entries to `Palette` in `palette.ts`, beside the cell states:

```ts
  /** An outer band's header. */
  label: CellStyle;
  /** An inner block's header, which must not compete with it. */
  sublabel: CellStyle;
```

with defaults `{ fill: '#e8e8ea', border: null, weight: null }` and
`{ fill: '#7e7e88', border: null, weight: null }`, and read in `readPalette`
from `--corpus-label` and `--corpus-sublabel` the same way the state colors are
read. Declare both in `corpus.css` beside the state properties.

- [ ] **Step 4: Run it and watch it pass**

Run: `cd lab && npx vitest run src/corpus && npx tsc -b --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/paint.ts lab/src/corpus/paint.test.ts lab/src/corpus/Wall.tsx lab/src/corpus/palette.ts
git commit -m "draw a band's label, and drop it when the band is too narrow to read"
```

---

## Task 14: Color a cell by a fact

**Files:**
- Create: `lab/src/corpus/tint.ts`
- Create: `lab/src/corpus/tint.test.ts`
- Modify: `lab/src/corpus/palette.ts`

Frequency spans 1 to 140,674, so a linear ramp puts everything but a few
hundred parts at the same value.

- [ ] **Step 1: Write the failing test**

```ts
// lab/src/corpus/tint.test.ts
import { describe, expect, it } from 'vitest';
import { TINT_MODES, ramp, tintFor } from '@lab/corpus/tint';
import { DEFAULT_PALETTE } from '@lab/corpus/palette';
import type { Cell } from '@lab/corpus/types';

const c = (over: Partial<Cell>): Cell => ({
  id: 'x', index: 0, title: '', category: null, cat: 0, printed: false,
  obsolete: false, status: 'unreviewed', sha: null, made_at: null,
  extra_d99: null, secs: null, error: null, open_defects: 0,
  open_defects_elsewhere: 0, error_elsewhere: false, year: null,
  year_last: null, uses: null, sets: null, ncolors: null, ...over,
});

describe('ramp', () => {
  it('clamps at both ends', () => {
    expect(ramp(-1)).toBe(ramp(0));
    expect(ramp(2)).toBe(ramp(1));
  });
});

describe('tintFor', () => {
  it('gives an unmatched part the unmatched style, never the ramp\'s floor', () => {
    const style = tintFor(c({}), 'uses', DEFAULT_PALETTE);
    expect(style).toBe(DEFAULT_PALETTE.unmatched);
    expect(style).not.toBe(tintFor(c({ uses: 1 }), 'uses', DEFAULT_PALETTE));
  });

  it('separates a part used once from one used a hundred thousand times', () => {
    expect(tintFor(c({ uses: 1 }), 'uses', DEFAULT_PALETTE).fill)
      .not.toBe(tintFor(c({ uses: 140674 }), 'uses', DEFAULT_PALETTE).fill);
  });

  it('is logarithmic, so the middle of the range is not the middle of the ramp', () => {
    const mid = tintFor(c({ uses: 70000 }), 'uses', DEFAULT_PALETTE).fill;
    const high = tintFor(c({ uses: 140674 }), 'uses', DEFAULT_PALETTE).fill;
    // Half the maximum is nearly the top of a log ramp, not its middle.
    expect(mid).toBe(high);
  });

  it('falls back to the status palette in status mode', () => {
    expect(tintFor(c({ open_defects: 1 }), 'status', DEFAULT_PALETTE))
      .toBe(DEFAULT_PALETTE.defect);
  });

  it('names every mode it supports', () => {
    expect(TINT_MODES).toEqual(['status', 'year', 'uses', 'colors']);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd lab && npx vitest run src/corpus/tint.test.ts`
Expected: FAIL, cannot resolve `@lab/corpus/tint`

- [ ] **Step 3: Write the implementation**

Add to `palette.ts` a `Palette` entry:

```ts
  /** A part that matched nothing outside. Its own flat tone, so absence never
   *  reads as the low end of a ramp. */
  unmatched: CellStyle;
```

defaulting to `{ fill: '#2a2a2e', border: null, weight: null }`.

```ts
// lab/src/corpus/tint.ts
import { fillFor, type CellStyle, type Palette } from '@lab/corpus/palette';
import type { Cell } from '@lab/corpus/types';

export const TINT_MODES = ['status', 'year', 'uses', 'colors'] as const;
export type TintMode = typeof TINT_MODES[number];

// Quantised, so two cells a few uses apart get the same swatch and a band of
// the ramp reads as a band rather than as noise.
const STEPS = 8;
const LOW = [58, 58, 63];
const HIGH = [232, 196, 120];

export function ramp(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const step = Math.round(clamped * (STEPS - 1)) / (STEPS - 1);
  const rgb = LOW.map((v, i) => Math.round(v + (HIGH[i]! - v) * step));
  return `rgb(${rgb.join(',')})`;
}

// 1954 to 2026, and 140,674 uses -- both from the catalog as it stands, and
// both only affecting where the ramp saturates.
const FIRST_YEAR = 1954;
const YEAR_SPAN = 72;
const MAX_LOG_USES = Math.log10(140674);
const MANY_COLORS = 40;

function value(cell: Cell, mode: TintMode): number | null {
  switch (mode) {
    case 'status': return null;
    case 'year': return cell.year === null ? null
      : (cell.year - FIRST_YEAR) / YEAR_SPAN;
    case 'uses': return cell.uses === null ? null
      : Math.log10(Math.max(1, cell.uses)) / MAX_LOG_USES;
    case 'colors': return cell.ncolors === null ? null
      : cell.ncolors / MANY_COLORS;
  }
}

/** A cell's fill under one tint mode.
 *
 *  Only `status` uses the state palette; the rest are ramps over an outside
 *  fact, and a cell with no fact takes `unmatched` rather than the floor. */
export function tintFor(cell: Cell, mode: TintMode, palette: Palette): CellStyle {
  if (mode === 'status') return fillFor(cell, palette);
  const t = value(cell, mode);
  if (t === null) return palette.unmatched;
  return { fill: ramp(t), border: null, weight: null };
}
```

In `paint.ts`, take a `tint: TintMode` in `PaintInput` (defaulting to
`'status'`) and, in the cell loop, **skip the sprite and image branches when
`tint !== 'status'`** — a thumbnail is opaque, so you cannot read a ramp and
look at the drawings at the same time. Use `tintFor(cell, tint, palette)` in
place of `palette[state]` for the fill command.

- [ ] **Step 4: Run it and watch it pass**

Run: `cd lab && npx vitest run src/corpus && npx tsc -b --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/tint.ts lab/src/corpus/tint.test.ts lab/src/corpus/palette.ts lab/src/corpus/paint.ts lab/src/corpus/paint.test.ts
git commit -m "tint a cell by year, use or color count, on a log ramp for uses"
```

---

## Task 15: Grouping, tint and excluded categories in the selection

**Files:**
- Modify: `lab/src/corpus/select.ts`
- Modify: `lab/src/corpus/select.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// lab/src/corpus/select.test.ts -- append
it('drops a cell whose category is excluded', () => {
  const cells = [cell({ id: 'a', cat: 0 }), cell({ id: 'b', cat: 1 })];
  const out = applySelection(cells, {
    sort: 'id', filter: 'all', grouping: 'none', tint: 'status',
    excluded: ['Duplo'], desc: true,
  }, ['Brick', 'Duplo']);
  expect(out.map((c) => c.id)).toEqual(['a']);
});

it('excludes nothing when the list is empty', () => {
  const cells = [cell({ id: 'a', cat: 0 }), cell({ id: 'b', cat: 1 })];
  const out = applySelection(cells, {
    sort: 'id', filter: 'all', grouping: 'none', tint: 'status',
    excluded: [], desc: true,
  }, ['Brick', 'Duplo']);
  expect(out).toHaveLength(2);
});

it('sorts by uses, worst-informed last', () => {
  const cells = [cell({ id: 'a', uses: 5 }), cell({ id: 'b', uses: null }),
                 cell({ id: 'd', uses: 900 })];
  const out = applySelection(cells, {
    sort: 'uses', filter: 'all', grouping: 'none', tint: 'status',
    excluded: [], desc: true,
  }, ['Brick']);
  expect(out.map((c) => c.id)).toEqual(['d', 'a', 'b']);
});
```

Use whatever `cell()` helper this file already defines, extended with the new
fields.

- [ ] **Step 2: Run it and watch it fail**

Run: `cd lab && npx vitest run src/corpus/select.test.ts`
Expected: FAIL, `applySelection` takes two arguments

- [ ] **Step 3: Write the implementation**

In `lab/src/corpus/select.ts`:

```ts
import { categoryOf, type Grouping } from '@lab/corpus/facts';
import type { TintMode } from '@lab/corpus/tint';

export const SORTS = ['id', 'category', 'status', 'extra_d99', 'secs',
                      'made_at', 'uses', 'year'] as const;
```

```ts
export interface Selection {
  sort: Sort;
  filter: Filter;
  grouping: Grouping;
  tint: TintMode;
  /** Clean category names to leave off the wall entirely. */
  excluded: string[];
  /** Which way `release` runs, and nothing else. */
  desc: boolean;
}
```

Add to `DESCENDING`: `'uses'`. Add to `key()`:

```ts
    case 'uses': return cell.uses;
    case 'year': return cell.year;
```

and change the signature:

```ts
export function applySelection(cells: Cell[], selection: Selection,
                               categories: string[]): Cell[] {
  const off = new Set(selection.excluded);
  const kept = cells.filter((c) => KEEP[selection.filter](c)
                                && !off.has(categoryOf(c, categories)));
```

leaving the sort below unchanged.

- [ ] **Step 4: Run it and watch it pass**

Run: `cd lab && npx vitest run src/corpus/select.test.ts && npx tsc -b --noEmit`
Expected: PASS. `tsc` will name every caller of `applySelection`; Task 16
fixes them.

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/select.ts lab/src/corpus/select.test.ts
git commit -m "carry grouping, tint and the excluded categories in the selection"
```

---

## Task 16: The sidebar

**Files:**
- Create: `lab/src/corpus/Sidebar.tsx`
- Create: `lab/src/corpus/Sidebar.css`
- Create: `lab/src/corpus/Sidebar.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// lab/src/corpus/Sidebar.test.tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Sidebar } from '@lab/corpus/Sidebar';
import type { Selection } from '@lab/corpus/select';

const selection: Selection = {
  sort: 'id', filter: 'all', grouping: 'none', tint: 'status',
  excluded: [], desc: true,
};

const props = {
  selection, categories: ['Brick', 'Duplo'],
  counts: new Map([['Brick', 1332], ['Duplo', 589]]),
  shown: 1332, total: 1921,
};

describe('Sidebar', () => {
  it('lists every category with its count, biggest first', () => {
    render(<Sidebar {...props} onChange={vi.fn()} />);
    const boxes = screen.getAllByRole('checkbox');
    expect(boxes.map((b) => b.getAttribute('name'))).toEqual(['Brick', 'Duplo']);
  });

  it('excludes a category when its box is cleared', () => {
    const onChange = vi.fn();
    render(<Sidebar {...props} onChange={onChange} />);
    fireEvent.click(screen.getByRole('checkbox', { name: /Duplo/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ excluded: ['Duplo'] }));
  });

  it('puts a category back when its box is checked again', () => {
    const onChange = vi.fn();
    render(<Sidebar {...props} selection={{ ...selection, excluded: ['Duplo'] }}
                    onChange={onChange} />);
    fireEvent.click(screen.getByRole('checkbox', { name: /Duplo/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ excluded: [] }));
  });

  it('clears and restores every category at once', () => {
    const onChange = vi.fn();
    render(<Sidebar {...props} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'none' }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ excluded: ['Brick', 'Duplo'] }));
  });

  it('changes the grouping', () => {
    const onChange = vi.fn();
    render(<Sidebar {...props} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Group'), { target: { value: 'release' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ grouping: 'release' }));
  });

  it('offers the direction toggle only where it means something', () => {
    const { rerender } = render(<Sidebar {...props} onChange={vi.fn()} />);
    expect(screen.queryByLabelText('Newest first')).toBeNull();
    rerender(<Sidebar {...props} selection={{ ...selection, grouping: 'release' }}
                      onChange={vi.fn()} />);
    expect(screen.getByLabelText('Newest first')).toBeTruthy();
  });

  it('says how much of the corpus is on the wall', () => {
    render(<Sidebar {...props} onChange={vi.fn()} />);
    expect(screen.getByText('1332 of 1921')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd lab && npx vitest run src/corpus/Sidebar.test.tsx`
Expected: FAIL, cannot resolve `@lab/corpus/Sidebar`

- [ ] **Step 3: Write the implementation**

```tsx
// lab/src/corpus/Sidebar.tsx
import { TINT_MODES } from '@lab/corpus/tint';
import { FILTERS, SORTS, type Selection } from '@lab/corpus/select';
import type { Grouping } from '@lab/corpus/facts';
import '@lab/corpus/Sidebar.css';

const GROUPINGS: { id: Grouping; label: string }[] = [
  { id: 'none', label: 'nothing' },
  { id: 'coverage', label: 'coverage' },
  { id: 'category', label: 'category' },
  { id: 'release', label: 'release year' },
];

export function Sidebar({ selection, categories, counts, shown, total, onChange }: {
  selection: Selection;
  categories: string[];
  counts: Map<string, number>;
  shown: number;
  total: number;
  onChange: (next: Selection) => void;
}) {
  const off = new Set(selection.excluded);
  const ordered = [...categories].sort(
    (a, b) => (counts.get(b) ?? 0) - (counts.get(a) ?? 0) || a.localeCompare(b));

  const toggle = (name: string) => {
    const next = new Set(off);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChange({ ...selection, excluded: ordered.filter((c) => next.has(c)) });
  };

  return (
    <aside className="corpus-side">
      <label>Group
        <select value={selection.grouping}
                onChange={(e) => onChange({ ...selection,
                                            grouping: e.target.value as Grouping })}>
          {GROUPINGS.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
        </select>
      </label>

      {selection.grouping === 'release' && (
        <label className="corpus-side__check">
          <input type="checkbox" checked={selection.desc}
                 onChange={(e) => onChange({ ...selection, desc: e.target.checked })} />
          Newest first
        </label>
      )}

      <label>Order
        <select value={selection.sort}
                onChange={(e) => onChange({ ...selection,
                                            sort: e.target.value as Selection['sort'] })}>
          {SORTS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>

      <label>Color
        <select value={selection.tint}
                onChange={(e) => onChange({ ...selection,
                                            tint: e.target.value as Selection['tint'] })}>
          {TINT_MODES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </label>

      <label>Show
        <select value={selection.filter}
                onChange={(e) => onChange({ ...selection,
                                            filter: e.target.value as Selection['filter'] })}>
          {FILTERS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </label>

      <h3>
        Categories
        <button type="button" onClick={() => onChange({ ...selection, excluded: [] })}>all</button>
        <button type="button"
                onClick={() => onChange({ ...selection, excluded: ordered })}>none</button>
      </h3>
      <ul className="corpus-side__facets">
        {ordered.map((name) => (
          <li key={name}>
            <label>
              <input type="checkbox" name={name} checked={!off.has(name)}
                     onChange={() => toggle(name)} />
              <span>{name}</span>
              <em>{(counts.get(name) ?? 0).toLocaleString()}</em>
            </label>
          </li>
        ))}
      </ul>
      <p className="corpus-side__count">{shown} of {total}</p>
    </aside>
  );
}
```

```css
/* lab/src/corpus/Sidebar.css */
.corpus-side {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 216px;
  padding: 10px 0;
  overflow-y: auto;
  border-right: 1px solid var(--wzl-border);
  background: var(--wzl-surface);
  font-size: 13px;
}
.corpus-side > label { display: flex; flex-direction: column; gap: 3px; padding: 0 12px }
.corpus-side__check { flex-direction: row !important; align-items: center; gap: 6px }
.corpus-side h3 {
  display: flex; align-items: baseline; gap: 8px; margin: 12px 0 2px; padding: 0 12px;
  font-size: 10px; letter-spacing: .09em; text-transform: uppercase;
  color: var(--wzl-text-dim);
}
.corpus-side h3 button {
  border: 0; background: none; padding: 0; cursor: pointer;
  color: var(--wzl-text-dim); font: inherit; text-transform: none; letter-spacing: 0;
}
.corpus-side h3 button:hover { color: var(--wzl-accent) }
.corpus-side__facets { margin: 0; padding: 0; list-style: none }
.corpus-side__facets label {
  display: flex; gap: 7px; align-items: baseline; padding: 2px 12px; cursor: pointer;
}
.corpus-side__facets label:hover { background: var(--wzl-surface-raised) }
.corpus-side__facets span { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap }
.corpus-side__facets em { font-style: normal; font-size: 11px; color: var(--wzl-text-dim);
  font-variant-numeric: tabular-nums }
.corpus-side__count { margin: 8px 12px 0; color: var(--wzl-text-dim) }
```

The `!important` on `.corpus-side__check` is the one place the repo's no-important
rule needs a look: prefer raising the specificity to
`.corpus-side > label.corpus-side__check` and dropping it.

- [ ] **Step 4: Run it and watch it pass**

Run: `cd lab && npx vitest run src/corpus/Sidebar.test.tsx && npx tsc -b --noEmit`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/Sidebar.tsx lab/src/corpus/Sidebar.css lab/src/corpus/Sidebar.test.tsx
git commit -m "a sidebar for grouping, order, color and which categories to drop"
```

---

## Task 17: Wire it into the wall

**Files:**
- Modify: `lab/src/corpus/CorpusWall.tsx`
- Modify: `lab/src/corpus/CorpusWall.test.tsx`
- Modify: `lab/src/corpus/useCells.ts`

- [ ] **Step 1: Write the failing test**

```tsx
// lab/src/corpus/CorpusWall.test.tsx -- append, following this file's
// existing client stub and render helper.
it('regroups without refetching, because layout is a pure function of cells', async () => {
  const client = stubClient();           // this file's existing helper
  render(<CorpusWall client={client} />);
  await screen.findByLabelText('Group');
  const before = client.corpusCells.mock.calls.length;
  fireEvent.change(screen.getByLabelText('Group'), { target: { value: 'category' } });
  expect(client.corpusCells.mock.calls.length).toBe(before);
});

it('drops a category from the wall without refetching', async () => {
  const client = stubClient();
  render(<CorpusWall client={client} />);
  await screen.findByLabelText('Group');
  const before = client.corpusCells.mock.calls.length;
  fireEvent.click(screen.getAllByRole('checkbox')[0]!);
  expect(client.corpusCells.mock.calls.length).toBe(before);
});

it('offers the release direction only when grouping by release year', async () => {
  const client = stubClient();
  render(<CorpusWall client={client} />);
  await screen.findByLabelText('Group');
  expect(screen.queryByLabelText('Newest first')).toBeNull();
  fireEvent.change(screen.getByLabelText('Group'), { target: { value: 'release' } });
  expect(screen.getByLabelText('Newest first')).toBeTruthy();
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd lab && npx vitest run src/corpus/CorpusWall.test.tsx`
Expected: FAIL, no element labeled `Group`

- [ ] **Step 3: Write the implementation**

In `useCells.ts`, keep the whole body rather than just `cells`, so
`categories` reaches the component. In `CorpusWall.tsx`:

```tsx
const [selection, setSelection] = useState<Selection>({
  sort: 'id', filter: 'all', grouping: 'none', tint: 'status',
  excluded: [], desc: true,
});
```

```tsx
const categories = body?.categories ?? [];

const shown = useMemo(
  () => (cells ? applySelection(cells, selection, categories) : []),
  [cells, selection, categories]);

const counts = useMemo(() => {
  const out = new Map<string, number>();
  for (const c of cells ?? []) {
    const name = categoryOf(c, categories);
    out.set(name, (out.get(name) ?? 0) + 1);
  }
  return out;
}, [cells, categories]);

const rolled = useMemo(() => rollUp(shown, categories), [shown, categories]);

const layout = useMemo(() => {
  const keys = groupers(selection.grouping, categories, rolled);
  if (keys.length === 0) return gridLayout;
  if (keys.length === 1) {
    return blockLayout(keys[0]!, selection.grouping === 'coverage'
                                 ? COVERAGE_ORDER : []);
  }
  return bandedLayout(keys[0]!, keys[1]!, selection.desc);
}, [selection.grouping, selection.desc, categories, rolled]);

const laid = useMemo(
  () => layout(shown, { cell: CELL, gap: GAP, cols }),
  [layout, shown, cols]);
```

Pass `bands={laid.bands}` and `tint={selection.tint}` down to `<Wall>`, and
through to both `paintCommands` calls there. Mount the sidebar beside the
stage inside `.corpus-app`, and drop the grouping, sort, color and filter
controls from `FilterBar` — it keeps the slot select alone.

**The refit effect must not re-run on a regroup.** It is already guarded by
`touched.current`, but its dependency array names `laid.bounds`, which changes
on every regroup. Add a ref holding the last grouping and skip the fit when
only the grouping changed.

- [ ] **Step 4: Run it and watch it pass**

Run: `cd lab && npx vitest run src/corpus && npx tsc -b --noEmit`
Expected: PASS

Then drive it. Start the lab, open `/corpus`, and check each by looking:

- Group by **coverage**: five blocks, the timed-out one large.
- Group by **category**: labeled blocks, an `Other` block, no confetti.
- Group by **release year**: decade bands newest first, years across each,
  the undated band last and widest. Clear "Newest first" and it inverts.
- Color by **uses**: thumbnails give way to a ramp; the top-left of the
  frequency sort is the brightest.
- Clear **Duplo**, **Sticker** and **Minifig**: the count drops by about 8,500
  and the wall relays out with no refetch.
- **Arrow across a band gap.** The caret must cross into the next block. If it
  stops at a gap or jumps to the wrong cell, its adjacency is not geometric —
  fix the caret, not the layout.

Slop a screenshot of each grouping to the wall.

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus
git commit -m "wire grouping, tint and the facet sidebar into the corpus wall"
```

---

## Task 18: The full gate

Only now, and only once. Check first that no other session is running a suite —
`ps ax | grep -c '[v]itest'` and the background-process list — because two
concurrent runs manufacture timeouts in files nobody touched.

- [ ] **Step 1: The Python suite**

Run: `.venv/bin/python -m pytest`
Expected: PASS. If something outside `tests/test_rebrickable.py`,
`tests/test_db.py`, `tests/test_lab_cells.py` or `tests/test_lab_app.py` fails,
check for a competing run before treating it as a regression.

- [ ] **Step 2: The lab suite**

Run: `cd lab && npm test`
Expected: PASS, including every pre-existing lab test.

- [ ] **Step 3: Both entries build**

Run: `cd lab && npm run build`
Expected: `dist/index.html` and `dist/corpus.html` both emitted.

- [ ] **Step 4: Credit the source**

Add to `README.md`, in whatever section names the project's data:

```markdown
Part facts — year introduced, how often a part appears in sets, and the colors
it was produced in — come from [Rebrickable](https://rebrickable.com/downloads/),
whose catalog is free to use with attribution.
```

- [ ] **Step 5: Commit whatever the gate turned up**

```bash
git commit -am "fix what the full suite caught"
```

---

## Not in this plan

The Rebrickable API key and the external-id map. Facets on any axis but
category. The printed-part-to-base-part oracle in `part_relationships`, which is
downloaded and unread. Any change to the bake, the sheets or the slots —
regrouping emits different rects against the same baked thumbnails and rebakes
nothing.
