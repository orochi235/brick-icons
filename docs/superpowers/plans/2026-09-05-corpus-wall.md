# Corpus wall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pan/zoom wall at `/corpus` showing all 24,591 LDraw parts as one cell each, thumbnails where a render exists, filling in as the render job lands more.

**Architecture:** Python bakes thumbnails from the render store into two whole-corpus sprite sheets (8 px, 32 px) plus loose 128 px files, per slot — a slot being one `db.SOURCES` entry, i.e. an engine crossed with a style — all addressed by slot and part number. FastAPI serves the cell list, a delta since a version, and the images. The React app computes layout and camera as pure functions and paints one `<canvas>`; that canvas is the only place weasel's mega view will ever need to replace.

**Tech Stack:** Python 3.11, SQLite, FastAPI, Pillow, resvg; React 19, TypeScript, Vite, vitest.

**Spec:** `docs/superpowers/specs/2026-09-05-corpus-wall-design.md`

**Run Python tests as `.venv/bin/python -m pytest`, never `.venv/bin/pytest`.**
The venv is shared with the main checkout and its editable install maps
`brick_icons` to the main checkout's copy. The console script puts its own
`bin/` on `sys.path[0]` and so imports *that* tree; `-m` puts the working
directory first and imports this one. Both forms pass for a module that exists
unchanged in both trees, which is how the wrong one goes unnoticed.

---

## File structure

**Python**

| File | Responsibility |
|---|---|
| `scripts/index-census-renders.py` | Index the census's kept SVGs in place, as `census-naive`. Takes a count. |
| `brick_icons/thumbs.py` | Sheet geometry, per-part rasterizing, sheet composition, manifest. No I/O policy, no CLI. |
| `scripts/bake-thumbs.py` | CLI over `thumbs.py`, with per-item progress. |
| `brick_icons/lab/cells.py` | The cell list and the delta since a version, read from `corpus.db`. |
| `brick_icons/lab/app.py` | Four new routes. Routes only, as the module's docstring requires. |

**TypeScript** — all under `lab/src/corpus/`, none of it importing from `lab/src/instruments/` or `lab/src/panes/`.

| File | Responsibility |
|---|---|
| `layout.ts` | `Layout` strategy type and the dense grid strategy. Pure. |
| `camera.ts` | Pan/zoom state, `zoomAt`, and level selection with hysteresis. Pure. |
| `sheet.ts` | Sheet manifest → source rect for a cell index. Pure. |
| `visible.ts` | Which placements intersect the viewport. Pure. |
| `useCells.ts` | Fetch the cell list, poll for deltas, merge. |
| `Wall.tsx` | The canvas. The weasel seam — everything above it is layout and data. |
| `FilterBar.tsx` | Sort key and filter controls. |
| `Lightbox.tsx` | Full-screen detail for a selected part. |
| `CorpusWall.tsx` | Composes the above. The component a labkit instrument will import. |
| `main.tsx` | Standalone mount for `/corpus`. |

---

### Task 1: Index the census's kept renders

The census keeps its renders under `out/census-naive/renders/naive/` — 2,539 of
them, growing as it runs. They are **not** the store's drawing: the oracle
renders with `--line-width 0 --silhouette-width 0` so its fills carry the
silhouette, while `db.canonical_argv("...", "naive")` names the ordinary stroked
drawing. Filing one under the other's source records a drawing under a key
describing a different drawing, and was reverted once already in `5cbcd4e`.

So this indexes them **in place**, as source `census-naive`, with
`db.record_render`. Nothing is copied and nothing new enters git —
`db.rebuild` already treats census renders exactly this way, under the comment
"The census's renders stay out of git but are indexed all the same."

**Files:**
- Create: `scripts/index-census-renders.py`
- Test: `tests/test_index_census.py`

- [ ] **Step 1: Write the failing test**

```python
"""Indexing the census's kept renders, in place."""
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from brick_icons import db

index_census = importlib.import_module("index-census-renders")

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
       '<path d="M0 0h10v10H0z"/></svg>')


@pytest.fixture
def tree(tmp_path):
    kept = tmp_path / "out" / "census-naive" / "renders" / "naive"
    kept.mkdir(parents=True)
    for pid in ("3001", "3004", "nosuchpart"):
        (kept / f"{pid}.svg").write_text(SVG)
    conn = db.connect(tmp_path / "corpus.db")
    for pid in ("3001", "3004"):
        conn.execute("INSERT INTO parts (id, title, printed, obsolete) "
                     "VALUES (?, 'Brick', 0, 0)", (pid,))
    conn.commit()
    yield tmp_path, conn
    conn.close()


def test_it_indexes_under_the_census_source(tree):
    root, conn = tree
    assert index_census.index(conn, root=root, limit=10) == 2
    rows = conn.execute("SELECT part_id, source FROM renders").fetchall()
    assert {(r["part_id"], r["source"]) for r in rows} == {
        ("3001", "census-naive"), ("3004", "census-naive")}


def test_it_leaves_the_svg_where_the_census_put_it(tree):
    root, conn = tree
    index_census.index(conn, root=root, limit=10)
    assert not (root / "renders" / "census-naive").exists()
    assert (root / "out" / "census-naive" / "renders" / "naive" / "3001.svg").is_file()


def test_the_recorded_path_points_at_the_census_file(tree):
    root, conn = tree
    index_census.index(conn, root=root, limit=10)
    path = conn.execute("SELECT path FROM renders WHERE part_id='3001'").fetchone()[0]
    assert path == "out/census-naive/renders/naive/3001.svg"


def test_it_skips_ids_that_are_not_parts(tree):
    root, conn = tree
    index_census.index(conn, root=root, limit=10)
    assert conn.execute(
        "SELECT count(*) FROM renders WHERE part_id='nosuchpart'"
    ).fetchone()[0] == 0


def test_the_limit_caps_the_work(tree):
    root, conn = tree
    assert index_census.index(conn, root=root, limit=1) == 1


def test_it_skips_what_is_already_indexed(tree):
    root, conn = tree
    index_census.index(conn, root=root, limit=10)
    assert index_census.index(conn, root=root, limit=10) == 0


def test_a_missing_kept_directory_is_an_error_not_a_zero(tree):
    # A wrong --root and a finished backfill must not look identical.
    _, conn = tree
    with pytest.raises(FileNotFoundError):
        index_census.index(conn, root=tree[0] / "nowhere", limit=10)


def test_one_unreadable_svg_does_not_abandon_the_rest(tree):
    root, conn = tree
    (root / "out" / "census-naive" / "renders" / "naive" / "3001.svg").write_text("")
    assert index_census.index(conn, root=root, limit=10) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_index_census.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'index-census-renders'`

- [ ] **Step 3: Write the script**

```python
#!/usr/bin/env python3
"""Index the renders the census kept, where they lie.

    .venv/bin/python scripts/index-census-renders.py --limit 100

The census's drawing is strokeless -- its fills carry the silhouette -- so it is
not the store's `naive` render and is never recorded as one. It is indexed under
`census-naive` and left in `out/`, which is what `db.rebuild` does with it too.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402

ENGINE = "naive"
SOURCE = f"census-{ENGINE}"
KEPT = Path("out") / SOURCE / "renders" / ENGINE


def index(conn: sqlite3.Connection, root: Path | str = ".",
          limit: int = 100) -> int:
    """Record up to `limit` kept census renders. Returns how many it recorded."""
    root = Path(root)
    kept = root / KEPT
    if not kept.is_dir():
        raise FileNotFoundError(f"no census renders at {kept}")

    known = {r["id"] for r in conn.execute("SELECT id FROM parts")}
    have = {r["part_id"] for r in conn.execute(
        "SELECT part_id FROM renders WHERE source = ?", (SOURCE,))}
    recorded = 0
    for svg in sorted(kept.glob("*.svg")):
        if recorded >= limit:
            break
        pid = svg.stem
        if pid not in known or pid in have:
            continue
        try:
            db.record_render(conn, pid, SOURCE, svg, root=root)
        except Exception as e:  # noqa: BLE001
            # The census is still running and kills shards mid-write, so a
            # truncated SVG is expected traffic, not a reason to stop.
            print(f"skipped {pid}: {type(e).__name__} {e}", flush=True)
            continue
        recorded += 1
        print(f"{recorded}/{limit} {pid}", flush=True)
    return recorded


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()
    conn = db.connect(args.db)
    try:
        n = index(conn, root=args.root, limit=args.limit)
    finally:
        conn.close()
    print(f"recorded {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_index_census.py -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Run it for real**

Run: `.venv/bin/python scripts/index-census-renders.py --limit 100`
Expected: 100 progress lines, then `recorded 100`.

Confirm the sources are separate:
`sqlite3 corpus.db "select source, count(*) from renders group by source"`
Expected: `census-naive|100` and `naive|49`.

Confirm nothing was copied into git:
`git status --porcelain` — expected: only the two new files, no `renders/` changes.

- [ ] **Step 6: Commit**

```bash
git add scripts/index-census-renders.py tests/test_index_census.py
git commit -m "index the census's kept renders under their own source"
```

`corpus.db` is gitignored and must NOT be committed. Neither should anything
under `renders/` change — if it did, the script copied when it should have
recorded.

---

### Task 2: Sheet geometry

Where a part's cell sits on a sprite sheet, from nothing but its index and the level. Pure arithmetic, so it is settled before any image is touched.

**Files:**
- Create: `brick_icons/thumbs.py`
- Test: `tests/test_thumbs.py`

- [ ] **Step 1: Write the failing test**

```python
"""Thumbnail baking: geometry, freshness, sheets."""
import pytest

from brick_icons import thumbs


def test_levels_are_the_two_sheets_and_the_loose_one():
    assert thumbs.SHEET_LEVELS == (8, 32)
    assert thumbs.LOOSE_LEVEL == 128


def test_the_grid_is_square_enough_to_hold_every_part():
    g = thumbs.geometry(24591, level=32)
    assert g.cols == 157
    assert g.rows == 157
    assert g.cols * g.rows >= 24591


def test_the_coarsest_level_has_no_gutter():
    assert thumbs.geometry(100, level=8).gutter == 0
    assert thumbs.geometry(100, level=32).gutter == 2


def test_pitch_is_the_cell_plus_both_gutters():
    g = thumbs.geometry(100, level=32)
    assert g.pitch == 36
    assert g.size == g.cols * 36


def test_a_cell_lands_row_major_inside_its_gutter():
    g = thumbs.geometry(100, level=32)  # cols == 10
    assert g.cell_box(0) == (2, 2, 34, 34)
    assert g.cell_box(1) == (38, 2, 70, 34)
    assert g.cell_box(10) == (2, 38, 34, 70)


def test_an_index_past_the_grid_is_an_error():
    g = thumbs.geometry(4, level=8)
    with pytest.raises(IndexError):
        g.cell_box(g.cols * g.rows)


def test_the_loose_level_is_not_a_sheet():
    # 128 px is served as loose files. Sheeting it would silently produce a
    # 12800px page nothing asks for.
    with pytest.raises(ValueError):
        thumbs.geometry(100, level=thumbs.LOOSE_LEVEL)


def test_a_square_sheet_never_crops_an_uneven_grid():
    g = thumbs.geometry(82, level=32)   # cols 10, rows 9
    assert (g.cols, g.rows) == (10, 9)
    assert g.size >= g.rows * g.pitch
    assert g.cell_box(81)[3] <= g.size


def test_a_tiny_corpus_still_has_a_grid():
    for count in (0, 1):
        g = thumbs.geometry(count, level=8)
        assert g.cols == 1 and g.rows == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_thumbs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brick_icons.thumbs'`

- [ ] **Step 3: Write the module**

```python
"""Thumbnails for the corpus wall: per-part rasters and the sheets holding them.

A cell's index is its position in part-id order over every part, so a render
landing later writes one cell rather than renumbering the sheet.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

SHEET_LEVELS = (8, 32)
LOOSE_LEVEL = 128
# The mip chain stops at the coarsest level, so it cannot bleed and needs no
# padding. Every finer sheet does.
GUTTER = 2


@dataclass(frozen=True)
class Geometry:
    count: int
    level: int
    cols: int
    rows: int
    gutter: int

    @property
    def pitch(self) -> int:
        return self.level + 2 * self.gutter

    @property
    def size(self) -> int:
        return self.cols * self.pitch

    def cell_box(self, index: int) -> tuple[int, int, int, int]:
        """The cell's (left, top, right, bottom) on the sheet, gutters excluded."""
        if not 0 <= index < self.cols * self.rows:
            raise IndexError(f"cell {index} is outside a {self.cols}x{self.rows} grid")
        col, row = index % self.cols, index // self.cols
        x = col * self.pitch + self.gutter
        y = row * self.pitch + self.gutter
        return (x, y, x + self.level, y + self.level)


def geometry(count: int, level: int) -> Geometry:
    if level not in SHEET_LEVELS:
        raise ValueError(f"{level} is not a sheet level; sheets are {SHEET_LEVELS}")
    cols = max(1, math.ceil(math.sqrt(count)))
    # cols >= sqrt(count) makes cols*cols >= count, so rows <= cols always and
    # a square `size` is never a crop -- only ever some dead rows at the bottom.
    rows = max(1, math.ceil(count / cols))
    gutter = 0 if level == min(SHEET_LEVELS) else GUTTER
    return Geometry(count=count, level=level, cols=cols, rows=rows, gutter=gutter)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_thumbs.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/thumbs.py tests/test_thumbs.py
git commit -m "sheet geometry for corpus thumbnails"
```

---

### Task 3: Rasterize one part, and skip it when it is fresh

**Files:**
- Modify: `brick_icons/thumbs.py`
- Modify: `tests/test_thumbs.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_thumbs.py`:

```python
from pathlib import Path

from PIL import Image

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
       '<rect x="0" y="0" width="256" height="170" fill="black"/></svg>')


def test_it_rasterizes_every_level_for_one_part(tmp_path):
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    made = thumbs.bake_part("3001", svg, out, sha="abc123")
    assert sorted(made) == [8, 32, 128]
    for level in (8, 32, 128):
        with Image.open(out / str(level) / "3001.png") as img:
            assert img.size == (level, level)


def test_a_wide_render_is_padded_square_not_stretched(tmp_path):
    # Every stored render is 256x170. resvg cannot letterbox, so squaring is
    # this module's job -- and stretching would make every part the wrong shape.
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    thumbs.bake_part("3001", svg, out, sha="abc123")
    with Image.open(out / "128" / "3001.png") as img:
        assert img.size == (128, 128)
        assert img.getpixel((2, 2)) == (255, 255, 255, 255)


def test_a_baked_cell_is_opaque_so_the_ink_is_visible(tmp_path):
    # Renders are black ink on transparency and the lab's surface follows the
    # weasel theme, so a transparent thumbnail disappears in dark mode.
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    thumbs.bake_part("3001", svg, out, sha="abc123")
    with Image.open(out / "8" / "3001.png") as img:
        assert img.convert("RGBA").getextrema()[3] == (255, 255)


def test_it_skips_a_part_whose_sha_is_unchanged(tmp_path):
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    thumbs.bake_part("3001", svg, out, sha="abc123")
    assert thumbs.bake_part("3001", svg, out, sha="abc123") == []
    assert thumbs.bake_part("3001", svg, out, sha="different") != []


def test_the_baked_sha_is_readable_back(tmp_path):
    svg = tmp_path / "3001.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    thumbs.bake_part("3001", svg, out, sha="abc123")
    assert thumbs.baked_shas(out) == {"3001": "abc123"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_thumbs.py -v`
Expected: FAIL — `AttributeError: module 'brick_icons.thumbs' has no attribute 'bake_part'`

- [ ] **Step 3: Implement**

Add to `brick_icons/thumbs.py`:

```python
import json
import subprocess
from pathlib import Path

from PIL import Image

LEVELS = (*SHEET_LEVELS, LOOSE_LEVEL)
BAKED = "baked.json"


def baked_shas(out: Path | str) -> dict[str, str]:
    path = Path(out) / BAKED
    return json.loads(path.read_text()) if path.is_file() else {}


def _write_baked(out: Path, shas: dict[str, str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / BAKED).write_text(json.dumps(shas, sort_keys=True))


def bake_part(part_id: str, svg: Path | str, out: Path | str,
              sha: str) -> list[int]:
    """Rasterize one part at every level. Returns the levels written.

    An unchanged sha writes nothing: this runs after every batch of renders,
    and the corpus it has already baked is the overwhelming majority of it.
    """
    out = Path(out)
    shas = baked_shas(out)
    if shas.get(part_id) == sha:
        return []
    # resvg is the project's antialias reference -- the same rasterizer the
    # census, the contact sheet and the differ use. It has no letterbox flag
    # (`-w`, `-h`, `-z` only) and passing both -w and -h stretches a 256x170
    # render, so it is asked for a width and squared here.
    out.mkdir(parents=True, exist_ok=True)
    wide = out / f".{part_id}.wide.png"
    proc = subprocess.run(
        ["resvg", "--width", str(LOOSE_LEVEL), str(svg), str(wide)],
        capture_output=True, text=True)
    if proc.returncode != 0 or not wide.is_file():
        raise RuntimeError(f"resvg failed on {part_id}: "
                           f"{(proc.stderr or proc.stdout).strip()[:200]}")
    try:
        with Image.open(wide) as img:
            drawn = img.convert("RGBA")
        for level in LEVELS:
            path = out / str(level) / f"{part_id}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            _square(drawn, level).save(path)
    finally:
        wide.unlink(missing_ok=True)
    _write_baked(out, {**shas, part_id: sha})
    return list(LEVELS)


def _square(drawn: Image.Image, level: int) -> Image.Image:
    """Fit a render inside an opaque white square of `level` px.

    Opaque, because a render is black ink on transparency and the wall's
    background follows the weasel theme -- a transparent thumbnail is invisible
    in dark mode. A cell that was never baked stays fully transparent on the
    sheet, so alpha still separates "drawn" from "not drawn".
    """
    scale = level / max(drawn.size)
    size = (max(1, round(drawn.width * scale)), max(1, round(drawn.height * scale)))
    cell = Image.new("RGBA", (level, level), (255, 255, 255, 255))
    fitted = drawn.resize(size, Image.LANCZOS)
    cell.paste(fitted, ((level - size[0]) // 2, (level - size[1]) // 2), fitted)
    return cell
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_thumbs.py -v`
Expected: PASS, 9 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/thumbs.py tests/test_thumbs.py
git commit -m "bake one part's thumbnails, skipping an unchanged sha"
```

---

### Task 4: Compose the sheets and their manifest

**Files:**
- Modify: `brick_icons/thumbs.py`
- Modify: `tests/test_thumbs.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_thumbs.py`:

```python
def _baked(tmp_path, ids):
    svg = tmp_path / "src.svg"
    svg.write_text(SVG)
    out = tmp_path / "thumbs"
    for pid in ids:
        thumbs.bake_part(pid, svg, out, sha=f"sha-{pid}")
    return out


def test_the_sheet_is_one_page_sized_from_the_part_count(tmp_path):
    out = _baked(tmp_path, ["a", "b", "c"])
    thumbs.compose(out, order=["a", "b", "c", "d"])
    for level in (8, 32):
        g = thumbs.geometry(4, level)
        with Image.open(out / f"sheet-{level}.png") as img:
            assert img.size == (g.size, g.size)


def test_the_manifest_names_the_geometry_and_what_is_baked(tmp_path):
    out = _baked(tmp_path, ["a", "c"])
    thumbs.compose(out, order=["a", "b", "c", "d"])
    m = json.loads((out / "sheet-32.json").read_text())
    assert m["level"] == 32 and m["gutter"] == 2 and m["pitch"] == 36
    assert m["cols"] == 2 and m["count"] == 4
    assert m["baked"] == {"a": "sha-a", "c": "sha-c"}


def test_a_part_with_no_thumbnail_leaves_its_cell_empty(tmp_path):
    out = _baked(tmp_path, ["a"])
    thumbs.compose(out, order=["a", "b"])
    g = thumbs.geometry(2, 32)
    with Image.open(out / "sheet-32.png") as img:
        assert img.crop(g.cell_box(0)).getextrema()[3][1] > 0   # a is drawn
        assert img.crop(g.cell_box(1)).getextrema()[3][1] == 0  # b is empty


def test_the_gutter_replicates_the_cell_edge(tmp_path):
    out = _baked(tmp_path, ["a"])
    thumbs.compose(out, order=["a", "b"])
    with Image.open(out / "sheet-32.png") as img:
        x0, y0, _, _ = thumbs.geometry(2, 32).cell_box(0)
        assert img.getpixel((x0 - 1, y0)) == img.getpixel((x0, y0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_thumbs.py -v`
Expected: FAIL — `AttributeError: module 'brick_icons.thumbs' has no attribute 'compose'`

- [ ] **Step 3: Implement**

Add to `brick_icons/thumbs.py`:

```python
def compose(out: Path | str, order: list[str]) -> list[Path]:
    """Paste every baked thumbnail onto its sheet, in `order`'s index order.

    `order` is every part, not only the drawn ones: an index is a position in
    the corpus, so a part gaining a render later fills the cell it already had.
    """
    out = Path(out)
    shas = baked_shas(out)
    written = []
    for level in SHEET_LEVELS:
        g = geometry(len(order), level)
        sheet = Image.new("RGBA", (g.size, g.size), (0, 0, 0, 0))
        for index, part_id in enumerate(order):
            tile = out / str(level) / f"{part_id}.png"
            if not tile.is_file():
                continue
            with Image.open(tile) as img:
                cell = img.convert("RGBA")
            x0, y0, _, _ = g.cell_box(index)
            sheet.paste(cell, (x0, y0))
            if g.gutter:
                _replicate_edges(sheet, cell, x0, y0, g.gutter)
        path = out / f"sheet-{level}.png"
        sheet.save(path)
        (out / f"sheet-{level}.json").write_text(json.dumps({
            "level": level, "gutter": g.gutter, "pitch": g.pitch,
            "cols": g.cols, "rows": g.rows, "count": len(order),
            "size": g.size, "baked": shas,
        }, sort_keys=True))
        written.append(path)
    return written


def _replicate_edges(sheet: Image.Image, cell: Image.Image,
                     x0: int, y0: int, gutter: int) -> None:
    """Pad a cell with its own edge pixels.

    Without this each mip reduction averages a cell against its neighbour and
    the wall reads as halos -- a rendering fault that looks like a data fault.
    """
    w, h = cell.size
    for d in range(1, gutter + 1):
        sheet.paste(cell.crop((0, 0, w, 1)), (x0, y0 - d))
        sheet.paste(cell.crop((0, h - 1, w, h)), (x0, y0 + h + d - 1))
        sheet.paste(cell.crop((0, 0, 1, h)), (x0 - d, y0))
        sheet.paste(cell.crop((w - 1, 0, w, h)), (x0 + w + d - 1, y0))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_thumbs.py -v`
Expected: PASS, 13 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/thumbs.py tests/test_thumbs.py
git commit -m "compose the corpus sprite sheets with edge-replicated gutters"
```

---

### Task 5: The bake CLI

One slot at a time, into that slot's own directory. A slot is a `db.SOURCES`
entry — `naive`, `census-naive`, and any other with renders. `thumbs.py` needs
no knowledge of slots: it is handed `out/thumbs/<source>` as its output root.

**Files:**
- Create: `scripts/bake-thumbs.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Bake the corpus wall's thumbnails and sprite sheets, one slot at a time.

    .venv/bin/python scripts/bake-thumbs.py
    .venv/bin/python scripts/bake-thumbs.py --source naive

A slot is one `db.SOURCES` entry -- an engine crossed with a style. Each gets
its own thumbnails and its own sheets under `out/thumbs/<source>/`. Idempotent:
a part whose render sha has not changed is skipped, so running this after each
batch of renders costs only the new ones.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db, thumbs  # noqa: E402

DEFAULT_OUT = Path("out") / "thumbs"


def bake_source(conn, source: str, root: Path, out: Path,
                order: list[str]) -> tuple[int, int]:
    """Bake one slot. Returns (baked, total)."""
    rows = conn.execute(
        "SELECT part_id, path, sha256 FROM renders WHERE source = ? "
        "ORDER BY part_id", (source,)).fetchall()
    slot = out / source
    total, baked = len(rows), 0
    for i, row in enumerate(rows, 1):
        svg = root / row["path"]
        if not svg.is_file():
            print(f"  {source} {i}/{total} {row['part_id']} MISSING {row['path']}",
                  flush=True)
            continue
        made = thumbs.bake_part(row["part_id"], svg, slot, sha=row["sha256"])
        baked += bool(made)
        print(f"  {source} {i}/{total} {row['part_id']} "
              f"{'baked' if made else 'fresh'}", flush=True)
    for path in thumbs.compose(slot, order):
        print(f"  wrote {path}", flush=True)
    return baked, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--out", default=str(ROOT / DEFAULT_OUT))
    ap.add_argument("--source", action="append",
                    help="slot to bake; repeatable. Default: every slot with renders.")
    args = ap.parse_args()

    root, out = Path(args.root), Path(args.out)
    conn = db.connect(args.db)
    try:
        order = [r["id"] for r in conn.execute("SELECT id FROM parts ORDER BY id")]
        sources = args.source or [
            r["source"] for r in conn.execute(
                "SELECT DISTINCT source FROM renders ORDER BY source")]
        print(f"{len(sources)} slot(s) over {len(order)} cells: "
              f"{', '.join(sources)}", flush=True)
        for n, source in enumerate(sources, 1):
            print(f"[{n}/{len(sources)}] {source}", flush=True)
            baked, total = bake_source(conn, source, root, out, order)
            print(f"[{n}/{len(sources)}] {source}: baked {baked} of {total}",
                  flush=True)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it for real**

Run: `.venv/bin/python scripts/bake-thumbs.py`
Expected: two slots — `census-naive` (200 renders) and `naive` (49) — each
printing one line per part and then two `wrote .../sheet-*.png` lines. Both
slots' sheets land under `out/thumbs/<source>/`.

- [ ] **Step 3: Verify it is idempotent**

Run: `.venv/bin/python scripts/bake-thumbs.py`
Expected: every part line reads `fresh`, and each slot reports `baked 0 of N`.

- [ ] **Step 4: Look at both slots**

```bash
~/src/slopboard/bin/slop out/thumbs/census-naive/sheet-32.png
~/src/slopboard/bin/slop out/thumbs/naive/sheet-32.png
```

Expected: two 5652 px squares, almost entirely transparent, with small drawings
scattered through them in part-id order. The `naive` sheet's drawings carry
black outline strokes; the `census-naive` sheet's do not — that difference is
the whole point of keeping the slots apart. Confirm both are recognisable parts
and not black blobs.

- [ ] **Step 5: Commit**

```bash
git add scripts/bake-thumbs.py
git commit -m "bake each slot's thumbnails and sheets from the render store"
```

---

### Task 6: The cell list and its delta

**Files:**
- Create: `brick_icons/lab/cells.py`
- Test: `tests/test_lab_cells.py`

- [ ] **Step 1: Write the failing test**

```python
"""The corpus wall's cell list."""
import pytest

from brick_icons import db
from brick_icons.lab import cells


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "corpus.db")
    yield c
    c.close()


def _part(conn, pid, title="Brick", category="Brick", status="unreviewed"):
    conn.execute("INSERT INTO parts (id, title, category, printed, obsolete, "
                 "status) VALUES (?, ?, ?, 0, 0, ?)",
                 (pid, title, category, status))


def _render(conn, pid, sha, made_at, source="naive"):
    conn.execute("INSERT INTO renders (part_id, source, config_key, made_at, "
                 "path, sha256) VALUES (?, ?, 'k', ?, ?, ?)",
                 (pid, source, made_at, f"renders/{source}/{pid}.svg", sha))


def test_every_part_is_a_cell_in_id_order(conn):
    for pid in ("3004", "3001", "3005"):
        _part(conn, pid)
    conn.commit()
    body = cells.cells(conn)
    assert [c["id"] for c in body["cells"]] == ["3001", "3004", "3005"]
    assert body["count"] == 3


def test_a_cell_index_is_its_position_in_that_order(conn):
    for pid in ("3004", "3001"):
        _part(conn, pid)
    conn.commit()
    assert [c["index"] for c in cells.cells(conn)["cells"]] == [0, 1]


def test_a_rendered_cell_carries_its_sha(conn):
    _part(conn, "3001")
    _render(conn, "3001", "deadbeef", "2026-09-05T10:00:00+00:00")
    conn.commit()
    cell = cells.cells(conn)["cells"][0]
    assert cell["sha"] == "deadbeef"
    assert cell["made_at"] == "2026-09-05T10:00:00+00:00"


def test_an_unrendered_cell_has_no_sha(conn):
    _part(conn, "3001")
    conn.commit()
    assert cells.cells(conn)["cells"][0]["sha"] is None


def test_the_version_is_the_newest_render(conn):
    _part(conn, "3001")
    _part(conn, "3004")
    _render(conn, "3001", "a", "2026-09-05T10:00:00+00:00")
    _render(conn, "3004", "b", "2026-09-05T11:00:00+00:00")
    conn.commit()
    assert cells.cells(conn)["version"] == "2026-09-05T11:00:00+00:00"


def test_the_version_is_empty_with_no_renders(conn):
    _part(conn, "3001")
    conn.commit()
    assert cells.cells(conn)["version"] == ""


def test_since_returns_only_what_was_rendered_after_it(conn):
    _part(conn, "3001")
    _part(conn, "3004")
    _render(conn, "3001", "a", "2026-09-05T10:00:00+00:00")
    _render(conn, "3004", "b", "2026-09-05T11:00:00+00:00")
    conn.commit()
    body = cells.cells(conn, since="2026-09-05T10:30:00+00:00")
    assert [c["id"] for c in body["cells"]] == ["3004"]
    assert body["count"] == 2  # the corpus size, not the delta's


def test_a_delta_cell_keeps_the_index_it_has_on_the_wall(conn):
    for pid in ("3001", "3004", "3005"):
        _part(conn, pid)
    _render(conn, "3005", "c", "2026-09-05T11:00:00+00:00")
    conn.commit()
    body = cells.cells(conn, since="2026-09-05T10:00:00+00:00")
    assert body["cells"][0]["index"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_lab_cells.py -v`
Expected: FAIL — `ImportError: cannot import name 'cells'`

- [ ] **Step 3: Implement**

```python
"""The corpus wall's cells: one per part, in the order the sheets are baked in.

A cell's index is its position in part-id order over every part. The sprite
sheet is baked in that same order, so index is the only thing that has to agree
between this and `brick_icons.thumbs` -- and both take it from `ORDER BY id`.
"""
from __future__ import annotations

import sqlite3

_LATEST_MEASURE = """
SELECT m.part_id, m.extra_d99, m.secs, m.error FROM measurements m
JOIN (SELECT part_id, MAX(run_id) AS run_id FROM measurements
      WHERE engine = ? GROUP BY part_id) latest
  ON m.part_id = latest.part_id AND m.run_id = latest.run_id
WHERE m.engine = ?
"""


def engine_for(source: str) -> str:
    """The engine a slot's measurements are filed under.

    `renders.source` names a slot and `measurements.engine` names an engine, so
    the census slots have to drop their prefix or every metric joins to nothing
    and the wall sorts an unsorted column without erroring.
    """
    return source[len("census-"):] if source.startswith("census-") else source


def cells(conn: sqlite3.Connection, source: str = "census-naive",
          since: str | None = None) -> dict:
    """Every cell, or only those whose render landed after `since`.

    `count` is always the corpus size: the wall lays out every part whether or
    not this response mentions it, and a delta must not shrink the grid.
    """
    order = [r["id"] for r in conn.execute("SELECT id FROM parts ORDER BY id")]
    index = {pid: i for i, pid in enumerate(order)}

    renders = {r["part_id"]: r for r in conn.execute(
        "SELECT part_id, sha256, made_at FROM renders WHERE source = ?",
        (source,))}
    engine = engine_for(source)
    measures = {r["part_id"]: r for r in conn.execute(
        _LATEST_MEASURE, (engine, engine))}

    version = max((r["made_at"] for r in renders.values()), default="")
    wanted = order
    if since is not None:
        wanted = sorted(pid for pid, r in renders.items()
                        if r["made_at"] > since)

    rows = []
    marks = ",".join("?" * len(wanted)) if wanted else "NULL"
    for part in conn.execute(
            f"SELECT id, title, category, printed, obsolete, status FROM parts "
            f"WHERE id IN ({marks}) ORDER BY id", wanted):
        pid = part["id"]
        render = renders.get(pid)
        measure = measures.get(pid)
        rows.append({
            "id": pid,
            "index": index[pid],
            "title": part["title"],
            "category": part["category"],
            "printed": bool(part["printed"]),
            "obsolete": bool(part["obsolete"]),
            "status": part["status"],
            "sha": render["sha256"] if render else None,
            "made_at": render["made_at"] if render else None,
            "extra_d99": measure["extra_d99"] if measure else None,
            "secs": measure["secs"] if measure else None,
            "error": measure["error"] if measure else None,
        })
    return {"cells": rows, "count": len(order), "version": version,
            "source": source}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_lab_cells.py -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/cells.py tests/test_lab_cells.py
git commit -m "the corpus wall's cell list, with a delta since a version"
```

---

### Task 7: The routes

**Files:**
- Modify: `brick_icons/lab/app.py`
- Modify: `tests/test_lab_app.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lab_app.py`:

```python
def _corpus_client(tmp_path):
    from brick_icons import db
    conn = db.connect(tmp_path / "corpus.db")
    conn.execute("INSERT INTO parts (id, title, category, printed, obsolete, "
                 "status) VALUES ('3001', 'Brick 2 x 4', 'Brick', 0, 0, 'good')")
    conn.commit()
    conn.close()
    thumbs = tmp_path / "thumbs"
    (thumbs / "naive" / "128").mkdir(parents=True)
    (thumbs / "naive" / "128" / "3001.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (thumbs / "naive" / "sheet-8.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return TestClient(lab_app.create_app(
        cache_root=tmp_path / "cache",
        corpus_db=tmp_path / "corpus.db",
        thumbs_root=thumbs))


def test_cells_route_returns_every_part(tmp_path):
    body = _corpus_client(tmp_path).get("/api/corpus/cells").json()
    assert body["cells"][0]["id"] == "3001"
    assert body["count"] == 1


def test_cells_route_takes_a_since(tmp_path):
    body = _corpus_client(tmp_path).get(
        "/api/corpus/cells", params={"since": "2030-01-01T00:00:00+00:00"}).json()
    assert body["cells"] == []
    assert body["count"] == 1


def test_summary_route_counts_the_corpus(tmp_path):
    body = _corpus_client(tmp_path).get("/api/corpus/summary").json()
    assert body["parts"] == 1


def test_part_route_carries_measurements_and_defects(tmp_path):
    body = _corpus_client(tmp_path).get("/api/corpus/part/3001").json()
    assert body["part"]["title"] == "Brick 2 x 4"
    assert body["findings"] == []
    assert body["defects"] == []


def test_part_route_404s_on_an_unknown_part(tmp_path):
    assert _corpus_client(tmp_path).get("/api/corpus/part/nope").status_code == 404


def test_thumb_route_serves_a_loose_level(tmp_path):
    r = _corpus_client(tmp_path).get("/api/thumbs/naive/128/3001.png")
    assert r.status_code == 200


def test_thumb_route_serves_a_sheet(tmp_path):
    assert _corpus_client(tmp_path).get(
        "/api/thumbs/naive/sheet-8.png").status_code == 200


def test_thumb_route_refuses_an_unknown_slot(tmp_path):
    assert _corpus_client(tmp_path).get(
        "/api/thumbs/nonsense/128/3001.png").status_code == 400


def test_thumb_route_refuses_traversal(tmp_path):
    assert _corpus_client(tmp_path).get(
        "/api/thumbs/naive/128/..%2F..%2Fcorpus.db").status_code in (400, 404)


def test_sources_route_lists_the_slots_that_have_renders(tmp_path):
    body = _corpus_client(tmp_path).get("/api/corpus/sources").json()
    assert body["sources"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_lab_app.py -k corpus -v`
Expected: FAIL — `TypeError: create_app() got an unexpected keyword argument 'corpus_db'`

- [ ] **Step 3: Implement**

The cell list is ~6.5MB of JSON for the whole corpus, so the app gzips. Add the
import and one line inside `create_app`, right after the `FastAPI(...)` call:

```python
from fastapi.middleware.gzip import GZipMiddleware
```

```python
    # 24,591 cells is ~6.5MB of JSON and highly repetitive; gzip takes it under
    # a megabyte for the cost of one line.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
```

In `brick_icons/lab/app.py`, extend the import line and the signature:

```python
from . import (cache, cells, corpus, decal, defects, diff, findings,
               goldens_status, jobs, partindex, reference, runner, schema)
from .. import db as corpus_db_module
```

```python
def create_app(root: Path | str = ".",
               cache_root: Path | str = cache.DEFAULT_ROOT,
               defects_path: Path | str | None = None,
               corpus_db: Path | str | None = None,
               thumbs_root: Path | str | None = None) -> FastAPI:
```

and inside it, beside the other `app.state` assignments:

```python
    app.state.corpus_db = Path(corpus_db) if corpus_db else (
        root / corpus_db_module.DEFAULT_PATH)
    app.state.thumbs_root = Path(thumbs_root) if thumbs_root else (
        root / "out" / "thumbs")
```

Then add the routes, next to the other artifact routes:

```python
    def corpus_conn():
        if not Path(app.state.corpus_db).is_file():
            raise HTTPException(503, "no corpus database; run "
                                     "scripts/build-corpus-db.py")
        return corpus_db_module.connect(app.state.corpus_db)

    @app.get("/api/corpus/cells")
    def get_cells(source: str = "census-naive", since: str | None = None):
        conn = corpus_conn()
        try:
            return cells.cells(conn, source=source, since=since)
        finally:
            conn.close()

    @app.get("/api/corpus/summary")
    def get_corpus_summary():
        conn = corpus_conn()
        try:
            return findings.summary(conn)
        finally:
            conn.close()

    @app.get("/api/corpus/part/{part_id}")
    def get_corpus_part(part_id: str):
        conn = corpus_conn()
        try:
            row = conn.execute("SELECT * FROM parts WHERE id = ?",
                               (part_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "no such part")
            # `findings` matches `part` with LIKE, so 3001 would drag in
            # 3001a. The detail view is about one part.
            found = [f for f in findings.findings(conn, part=part_id,
                                                  limit=50)["rows"]
                     if f["part_id"] == part_id]
            runs = [dict(r) for r in conn.execute(
                "SELECT r.id, r.kind, r.started, r.commit_sha, m.engine, "
                "m.extra_d99, m.missing_px, m.secs, m.error "
                "FROM measurements m JOIN runs r ON r.id = m.run_id "
                "WHERE m.part_id = ? ORDER BY r.started DESC LIMIT 20",
                (part_id,))]
        finally:
            conn.close()
        return {"part": dict(row), "findings": found, "runs": runs,
                "defects": [d for d in defects.load(app.state.defects_path)
                            if d["part"] == part_id]}

    def _slot(source: str) -> Path:
        if source not in corpus_db_module.SOURCES:
            raise HTTPException(400, f"no such slot: {source}")
        return Path(app.state.thumbs_root) / source

    @app.get("/api/corpus/sources")
    def get_sources():
        """The slots that have renders, worst-populated last."""
        conn = corpus_conn()
        try:
            return {"sources": [dict(r) for r in conn.execute(
                "SELECT source, count(*) AS n FROM renders "
                "GROUP BY source ORDER BY n DESC")]}
        finally:
            conn.close()

    @app.get("/api/thumbs/{source}/sheet-{level}.png")
    def get_sheet(source: str, level: int):
        path = _slot(source) / f"sheet-{level}.png"
        if not path.is_file():
            raise HTTPException(404, "no such sheet; run scripts/bake-thumbs.py")
        return FileResponse(path)

    @app.get("/api/thumbs/{source}/sheet-{level}.json")
    def get_sheet_manifest(source: str, level: int):
        path = _slot(source) / f"sheet-{level}.json"
        if not path.is_file():
            raise HTTPException(404, "no such sheet manifest")
        return FileResponse(path)

    @app.get("/api/thumbs/{source}/{level}/{name}")
    def get_thumb(source: str, level: int, name: str):
        if "/" in name or ".." in name or not name.endswith(".png"):
            raise HTTPException(400, "bad thumbnail path")
        path = _slot(source) / str(level) / name
        if not path.is_file():
            raise HTTPException(404, "no such thumbnail")
        return FileResponse(path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_lab_app.py -v`
Expected: PASS, including the 8 new corpus tests and every route test that
already passed.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/app.py tests/test_lab_app.py
git commit -m "serve the corpus wall's cells, summary, part detail and thumbnails"
```

---

### Task 8: A second Vite entry that mounts

**Files:**
- Create: `lab/corpus.html`
- Create: `lab/src/corpus/main.tsx`
- Create: `lab/src/corpus/CorpusWall.tsx`
- Create: `lab/src/corpus/corpus.css`
- Modify: `lab/vite.config.ts`
- Test: `lab/src/corpus/CorpusWall.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from '@testing-library/react';
import { CorpusWall } from '@lab/corpus/CorpusWall';

it('says it is loading before the cells arrive', () => {
  render(<CorpusWall client={{ cells: () => new Promise(() => {}),
                               corpusSources: () => new Promise(() => {}) } as any} />);
  expect(screen.getByText(/loading the corpus/i)).toBeTruthy();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/corpus/CorpusWall.test.tsx`
Expected: FAIL — cannot resolve `@lab/corpus/CorpusWall`

- [ ] **Step 3: Write the files**

`lab/corpus.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>brick-icons corpus</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/corpus/main.tsx"></script>
  </body>
</html>
```

`lab/src/corpus/CorpusWall.tsx`:

```tsx
import { useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { CellsBody } from '@lab/corpus/types';
import '@lab/corpus/corpus.css';

/** The whole app, minus its mount. Exported so a labkit instrument can host it
 *  without the standalone page. */
export function CorpusWall({ client }: { client: LabClient }) {
  const [body, setBody] = useState<CellsBody | null>(null);

  useEffect(() => {
    void client.cells('census-naive').then(setBody);
  }, [client]);

  if (!body) return <p className="corpus-loading">loading the corpus…</p>;
  return <p className="corpus-loading">{body.count} parts</p>;
}
```

`lab/src/corpus/types.ts`:

```ts
export interface Cell {
  id: string;
  index: number;
  title: string;
  category: string | null;
  printed: boolean;
  obsolete: boolean;
  status: string;
  sha: string | null;
  made_at: string | null;
  extra_d99: number | null;
  secs: number | null;
  error: string | null;
}

export interface CellsBody {
  cells: Cell[];
  count: number;
  version: string;
  source: string;
}

export interface SheetManifest {
  level: number;
  gutter: number;
  pitch: number;
  cols: number;
  rows: number;
  count: number;
  size: number;
  baked: Record<string, string>;
}
```

`lab/src/corpus/main.tsx`:

```tsx
import { createRoot } from 'react-dom/client';
import { createClient } from '@lab/api/client';
import { CorpusWall } from '@lab/corpus/CorpusWall';

createRoot(document.getElementById('root')!).render(
  <CorpusWall client={createClient()} />,
);
```

`lab/src/corpus/corpus.css`:

```css
.corpus-loading {
  padding: 1rem;
  font: 13px/1.4 ui-monospace, monospace;
}
```

In `lab/vite.config.ts`, replace `build: { outDir: 'dist' },` with:

```ts
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        corpus: fileURLToPath(new URL('./corpus.html', import.meta.url)),
      },
    },
  },
```

Add to `lab/src/api/client.ts`, beside the other methods:

```ts
  cells: (source: string, since?: string): Promise<CellsBody> => {
    const q = new URLSearchParams({ source });
    if (since) q.set('since', since);
    return get(`/api/corpus/cells?${q}`);
  },
  corpusSources: (): Promise<{ sources: { source: string; n: number }[] }> =>
    get('/api/corpus/sources'),
```

Import `CellsBody` from `@lab/corpus/types` at the top of `client.ts`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/corpus/CorpusWall.test.tsx`
Expected: PASS

- [ ] **Step 5: See it in a browser**

Run the server and the dev page:

```bash
.venv/bin/python -m brick_icons.lab &
cd lab && npm run dev
```

Open `http://localhost:5178/corpus.html`. Expected: `24591 parts`.

- [ ] **Step 6: Commit**

```bash
git add lab/corpus.html lab/vite.config.ts lab/src/corpus lab/src/api/client.ts
git commit -m "a second lab entry that mounts the corpus wall"
```

---

### Task 9: The layout strategy

**Files:**
- Create: `lab/src/corpus/layout.ts`
- Test: `lab/src/corpus/layout.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { gridLayout } from '@lab/corpus/layout';
import type { Cell } from '@lab/corpus/types';

const cell = (id: string, index: number): Cell => ({
  id, index, title: id, category: 'Brick', printed: false, obsolete: false,
  status: 'unreviewed', sha: null, made_at: null, extra_d99: null,
  secs: null, error: null,
});

const cells = [cell('a', 0), cell('b', 1), cell('c', 2), cell('d', 3)];

it('fills row-major at the given pitch', () => {
  const { rects } = gridLayout(cells, { cell: 10, gap: 2, cols: 2 });
  expect(rects[0]).toEqual({ x: 0, y: 0, w: 10, h: 10 });
  expect(rects[1]).toEqual({ x: 12, y: 0, w: 10, h: 10 });
  expect(rects[2]).toEqual({ x: 0, y: 12, w: 10, h: 10 });
});

it('reports bounds that contain every rect', () => {
  const { bounds } = gridLayout(cells, { cell: 10, gap: 2, cols: 2 });
  expect(bounds).toEqual({ w: 22, h: 22 });
});

it('is a function of the array order, not of cell.index', () => {
  const reversed = [...cells].reverse();
  const { rects } = gridLayout(reversed, { cell: 10, gap: 2, cols: 2 });
  expect(rects[0]).toEqual({ x: 0, y: 0, w: 10, h: 10 });
});

it('lays out an empty corpus without dividing by zero', () => {
  expect(gridLayout([], { cell: 10, gap: 2, cols: 2 }))
    .toEqual({ rects: [], bounds: { w: 0, h: 0 } });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/corpus/layout.test.ts`
Expected: FAIL — cannot resolve `@lab/corpus/layout`

- [ ] **Step 3: Implement**

```ts
import type { Cell } from '@lab/corpus/types';

export interface Rect { x: number; y: number; w: number; h: number }

export interface LayoutOptions {
  /** Edge of one cell in world units. */
  cell: number;
  /** Space between cells in world units. */
  gap: number;
  cols: number;
}

/** A layout answers where each cell sits, and nothing else. It never touches
 *  the atlas, so re-sorting or regrouping the wall rebakes nothing. */
export type Layout = (cells: Cell[], opts: LayoutOptions) =>
  { rects: Rect[]; bounds: { w: number; h: number } };

export const gridLayout: Layout = (cells, { cell, gap, cols }) => {
  const pitch = cell + gap;
  const rects = cells.map((_, i) => ({
    x: (i % cols) * pitch,
    y: Math.floor(i / cols) * pitch,
    w: cell,
    h: cell,
  }));
  const rows = Math.ceil(cells.length / cols);
  return {
    rects,
    bounds: cells.length
      ? { w: Math.min(cells.length, cols) * pitch - gap, h: rows * pitch - gap }
      : { w: 0, h: 0 },
  };
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/corpus/layout.test.ts`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/layout.ts lab/src/corpus/layout.test.ts
git commit -m "the corpus wall's grid layout strategy"
```

---

### Task 10: Camera and level selection

**Files:**
- Create: `lab/src/corpus/camera.ts`
- Test: `lab/src/corpus/camera.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { fitBounds, levelFor, pickLevel, toScreen, toWorld, zoomAt }
  from '@lab/corpus/camera';

const cam = { x: 0, y: 0, scale: 2 };

it('maps world to screen and back', () => {
  expect(toScreen(cam, 10, 20)).toEqual({ x: 20, y: 40 });
  expect(toWorld(cam, 20, 40)).toEqual({ x: 10, y: 20 });
});

it('keeps the point under the cursor fixed while zooming', () => {
  const next = zoomAt(cam, 100, 100, 2);
  expect(toScreen(next, toWorld(cam, 100, 100).x, toWorld(cam, 100, 100).y))
    .toEqual({ x: 100, y: 100 });
});

it('clamps zoom to the allowed range', () => {
  expect(zoomAt(cam, 0, 0, 1e6).scale).toBeLessThanOrEqual(64);
  expect(zoomAt(cam, 0, 0, 1e-6).scale).toBeGreaterThanOrEqual(0.01);
});

it('fits bounds inside a viewport', () => {
  const fitted = fitBounds({ w: 100, h: 50 }, { width: 200, height: 200 });
  expect(fitted.scale).toBe(2);
});

it('does not hand back Infinity for an empty wall', () => {
  expect(fitBounds({ w: 0, h: 0 }, { width: 200, height: 200 }).scale).toBe(1);
});

it('picks the coarsest level that covers the on-screen cell size', () => {
  expect(levelFor(4)).toBe(8);
  expect(levelFor(20)).toBe(32);
  expect(levelFor(200)).toBe(128);
});

it('holds the current level across the whole hysteresis dead zone', () => {
  // The 8/32 boundary is 16px, so the dead zone is [16*0.67, 16*1.5] = [10.7, 24].
  // Inside it the level in hand wins, whichever one that is -- which is the
  // entire point: a zoom parked on 16px would otherwise re-upload every frame.
  expect(pickLevel(8, 20)).toBe(8);    // wants 32, not past 24 yet
  expect(pickLevel(32, 12)).toBe(32);  // wants 8, not below 10.7 yet
});

it('swaps once the zoom is clearly past the dead zone', () => {
  expect(pickLevel(8, 30)).toBe(32);
  expect(pickLevel(32, 5)).toBe(8);
});

it('leaves the level alone when it is already the right one', () => {
  expect(pickLevel(8, 10)).toBe(8);
  expect(pickLevel(32, 40)).toBe(32);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/corpus/camera.test.ts`
Expected: FAIL — cannot resolve `@lab/corpus/camera`

- [ ] **Step 3: Implement**

```ts
export interface Camera { x: number; y: number; scale: number }

export const MIN_SCALE = 0.01;
export const MAX_SCALE = 64;

/** The on-screen cell size each baked level is meant to cover. */
const BANDS: readonly [number, number][] = [[8, 16], [32, 64], [128, Infinity]];

export function toScreen(cam: Camera, x: number, y: number) {
  return { x: (x - cam.x) * cam.scale, y: (y - cam.y) * cam.scale };
}

export function toWorld(cam: Camera, sx: number, sy: number) {
  return { x: sx / cam.scale + cam.x, y: sy / cam.scale + cam.y };
}

export function zoomAt(cam: Camera, sx: number, sy: number,
                       factor: number): Camera {
  const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, cam.scale * factor));
  const before = toWorld(cam, sx, sy);
  const after = toWorld({ ...cam, scale }, sx, sy);
  return { x: cam.x + before.x - after.x, y: cam.y + before.y - after.y, scale };
}

export function fitBounds(bounds: { w: number; h: number },
                          viewport: { width: number; height: number }): Camera {
  // An empty wall has zero bounds, and the unguarded division hands back
  // Infinity -- which multiplies every coordinate into NaN with nothing
  // downstream to catch it.
  if (bounds.w <= 0 || bounds.h <= 0) return { x: 0, y: 0, scale: 1 };
  const scale = Math.min(viewport.width / bounds.w, viewport.height / bounds.h);
  return { x: 0, y: 0, scale };
}

/** The level a cell of `px` on screen wants, ignoring what is loaded. */
export function levelFor(px: number): number {
  for (const [level, top] of BANDS) if (px < top) return level;
  return BANDS[BANDS.length - 1]![0];
}

/** The level to actually use, given the one in hand.
 *
 *  Straight thresholds re-upload every frame when a zoom parks on a boundary,
 *  so a level is kept until the cell size is half again past its band. */
export function pickLevel(current: number, px: number): number {
  const wanted = levelFor(px);
  if (wanted === current) return current;
  return wanted > current
    ? (levelFor(px / 1.5) > current ? wanted : current)
    : (levelFor(px / 0.67) < current ? wanted : current);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/corpus/camera.test.ts`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/camera.ts lab/src/corpus/camera.test.ts
git commit -m "camera and hysteresis-guarded level selection for the wall"
```

---

### Task 11: Sheet lookup and the visible set

**Files:**
- Create: `lab/src/corpus/sheet.ts`
- Create: `lab/src/corpus/visible.ts`
- Test: `lab/src/corpus/sheet.test.ts`
- Test: `lab/src/corpus/visible.test.ts`

- [ ] **Step 1: Write the failing tests**

`lab/src/corpus/sheet.test.ts`:

```ts
import { sourceBox, isStale } from '@lab/corpus/sheet';
import type { SheetManifest } from '@lab/corpus/types';

const manifest: SheetManifest = {
  level: 32, gutter: 2, pitch: 36, cols: 2, rows: 2, count: 4, size: 72,
  baked: { a: 'sha-a', b: 'sha-b' },
};

it('finds a cell row-major inside its gutter', () => {
  expect(sourceBox(manifest, 0)).toEqual({ sx: 2, sy: 2, sw: 32, sh: 32 });
  expect(sourceBox(manifest, 1)).toEqual({ sx: 38, sy: 2, sw: 32, sh: 32 });
  expect(sourceBox(manifest, 2)).toEqual({ sx: 2, sy: 38, sw: 32, sh: 32 });
});

it('has no box for an index outside the sheet', () => {
  expect(sourceBox(manifest, 4)).toBeNull();
});

it('calls a cell stale when the store has moved past the bake', () => {
  expect(isStale(manifest, { id: 'a', sha: 'sha-a' })).toBe(false);
  expect(isStale(manifest, { id: 'a', sha: 'sha-new' })).toBe(true);
  expect(isStale(manifest, { id: 'c', sha: 'sha-c' })).toBe(true);
});

it('does not call an unrendered cell stale', () => {
  expect(isStale(manifest, { id: 'c', sha: null })).toBe(false);
});
```

`lab/src/corpus/visible.test.ts`:

```ts
import { visibleRange } from '@lab/corpus/visible';

const rects = [
  { x: 0, y: 0, w: 10, h: 10 },
  { x: 20, y: 0, w: 10, h: 10 },
  { x: 0, y: 20, w: 10, h: 10 },
];

it('returns the indices intersecting the viewport', () => {
  expect(visibleRange(rects, { x: 0, y: 0, scale: 1 },
                      { width: 15, height: 15 })).toEqual([0]);
});

it('includes a rect only partly on screen', () => {
  expect(visibleRange(rects, { x: 5, y: 0, scale: 1 },
                      { width: 20, height: 15 })).toEqual([0, 1]);
});

it('returns nothing when the camera is off the wall', () => {
  expect(visibleRange(rects, { x: 500, y: 500, scale: 1 },
                      { width: 20, height: 20 })).toEqual([]);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd lab && npx vitest run src/corpus/sheet.test.ts src/corpus/visible.test.ts`
Expected: FAIL — cannot resolve either module

- [ ] **Step 3: Implement**

`lab/src/corpus/sheet.ts`:

```ts
import type { SheetManifest } from '@lab/corpus/types';

export interface SourceBox { sx: number; sy: number; sw: number; sh: number }

export function sourceBox(m: SheetManifest, index: number): SourceBox | null {
  if (index < 0 || index >= m.cols * m.rows) return null;
  return {
    sx: (index % m.cols) * m.pitch + m.gutter,
    sy: Math.floor(index / m.cols) * m.pitch + m.gutter,
    sw: m.level,
    sh: m.level,
  };
}

/** Whether the sheet's picture of this cell is behind the store's.
 *
 *  A cell with no render is not stale -- it is a placeholder, which is the
 *  common case on a wall the render job is still filling. */
export function isStale(m: SheetManifest,
                        cell: { id: string; sha: string | null }): boolean {
  if (cell.sha === null) return false;
  return m.baked[cell.id] !== cell.sha;
}
```

`lab/src/corpus/visible.ts`:

```ts
import type { Camera } from '@lab/corpus/camera';
import { toWorld } from '@lab/corpus/camera';
import type { Rect } from '@lab/corpus/layout';

/** Indices of the rects touching the viewport.
 *
 *  A linear scan, deliberately: it is layout-agnostic, and 24,591 rects cost
 *  well under a millisecond. A spatial index is what a non-uniform layout
 *  would need, not what this scale needs. */
export function visibleRange(rects: readonly Rect[], cam: Camera,
                             viewport: { width: number; height: number }):
                             number[] {
  const tl = toWorld(cam, 0, 0);
  const br = toWorld(cam, viewport.width, viewport.height);
  const out: number[] = [];
  for (let i = 0; i < rects.length; i++) {
    const r = rects[i]!;
    if (r.x < br.x && r.x + r.w > tl.x && r.y < br.y && r.y + r.h > tl.y) {
      out.push(i);
    }
  }
  return out;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd lab && npx vitest run src/corpus/sheet.test.ts src/corpus/visible.test.ts`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/sheet.ts lab/src/corpus/visible.ts \
        lab/src/corpus/sheet.test.ts lab/src/corpus/visible.test.ts
git commit -m "sheet cell lookup and the wall's visible set"
```

---

### Task 12: Fetch, poll and merge the cells

**Files:**
- Create: `lab/src/corpus/useCells.ts`
- Test: `lab/src/corpus/useCells.test.ts`
- Modify: `lab/src/api/client.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { mergeCells } from '@lab/corpus/useCells';
import type { Cell } from '@lab/corpus/types';

const cell = (id: string, index: number, sha: string | null = null): Cell => ({
  id, index, title: id, category: null, printed: false, obsolete: false,
  status: 'unreviewed', sha, made_at: null, extra_d99: null, secs: null,
  error: null,
});

it('replaces a cell the delta names', () => {
  const merged = mergeCells([cell('a', 0), cell('b', 1)],
                            [cell('b', 1, 'sha-b')]);
  expect(merged[1]!.sha).toBe('sha-b');
});

it('leaves untouched cells alone, by identity', () => {
  const a = cell('a', 0);
  const merged = mergeCells([a, cell('b', 1)], [cell('b', 1, 'sha-b')]);
  expect(merged[0]).toBe(a);
});

it('keeps the array in index order', () => {
  const merged = mergeCells([cell('a', 0), cell('b', 1), cell('c', 2)],
                            [cell('c', 2, 'sha-c'), cell('a', 0, 'sha-a')]);
  expect(merged.map((c) => c.id)).toEqual(['a', 'b', 'c']);
});

it('ignores a delta cell that is not on the wall', () => {
  const merged = mergeCells([cell('a', 0)], [cell('zz', 99)]);
  expect(merged.map((c) => c.id)).toEqual(['a']);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/corpus/useCells.test.ts`
Expected: FAIL — cannot resolve `@lab/corpus/useCells`

- [ ] **Step 3: Implement**

```ts
import { useEffect, useRef, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { Cell, CellsBody } from '@lab/corpus/types';

export const POLL_MS = 10_000;

/** Fold a delta into the wall's cells.
 *
 *  Identity of untouched cells is preserved so React and the paint loop can
 *  tell what actually changed when the render job lands a batch. */
export function mergeCells(current: Cell[], delta: Cell[]): Cell[] {
  if (delta.length === 0) return current;
  const byId = new Map(delta.map((c) => [c.id, c]));
  return current.map((c) => byId.get(c.id) ?? c);
}

export function useCells(client: LabClient, source: string) {
  const [cells, setCells] = useState<Cell[] | null>(null);
  const version = useRef('');

  useEffect(() => {
    let live = true;
    // A slot change is a different set of drawings for the same parts, so the
    // version resets with it -- polling the old one would merge the wrong shas.
    version.current = '';
    setCells(null);
    void client.cells(source).then((body: CellsBody) => {
      if (!live) return;
      version.current = body.version;
      setCells(body.cells);
    });
    const timer = setInterval(() => {
      void client.cells(source, version.current).then((body: CellsBody) => {
        if (!live || body.cells.length === 0) return;
        version.current = body.version;
        setCells((prev) => (prev ? mergeCells(prev, body.cells) : prev));
      });
    }, POLL_MS);
    return () => { live = false; clearInterval(timer); };
  }, [client, source]);

  return cells;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/corpus/useCells.test.ts`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/useCells.ts lab/src/corpus/useCells.test.ts
git commit -m "poll the corpus for renders and merge them into the wall"
```

---

### Task 13: The canvas

This is the weasel seam. Everything it needs is already a tested pure function; this file only draws.

**Files:**
- Create: `lab/src/corpus/paint.ts`
- Create: `lab/src/corpus/Wall.tsx`
- Test: `lab/src/corpus/paint.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { paintCommands, STATUS_FILL } from '@lab/corpus/paint';
import type { Cell, SheetManifest } from '@lab/corpus/types';

const cell = (id: string, index: number, sha: string | null,
              status = 'unreviewed'): Cell => ({
  id, index, title: id, category: null, printed: false, obsolete: false,
  status, sha, made_at: null, extra_d99: null, secs: null, error: null,
});

const manifest: SheetManifest = {
  level: 32, gutter: 2, pitch: 36, cols: 2, rows: 2, count: 4, size: 72,
  baked: { a: 'sha-a' },
};

const rects = [
  { x: 0, y: 0, w: 10, h: 10 },
  { x: 20, y: 0, w: 10, h: 10 },
];

it('draws a baked cell from the sheet', () => {
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: 1 }, manifest,
  });
  expect(cmd).toMatchObject({ kind: 'sprite', dx: 0, dy: 0, dw: 10, dh: 10,
                              sx: 2, sy: 2 });
});

it('draws an unrendered cell as its status color', () => {
  const [cmd] = paintCommands({
    cells: [cell('b', 1, null, 'broken')], rects: [rects[1]!], visible: [0],
    cam: { x: 0, y: 0, scale: 1 }, manifest,
  });
  expect(cmd).toEqual({ kind: 'fill', dx: 20, dy: 0, dw: 10, dh: 10,
                        fill: STATUS_FILL.broken });
});

it('draws a stale cell as a fill, not as last week’s picture', () => {
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-newer')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: 1 }, manifest,
  });
  expect(cmd!.kind).toBe('fill');
});

it('applies the camera to every command', () => {
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: -5, y: -5, scale: 2 }, manifest,
  });
  expect(cmd).toMatchObject({ dx: 10, dy: 10, dw: 20, dh: 20 });
});

it('emits nothing for an empty visible set', () => {
  expect(paintCommands({
    cells: [], rects: [], visible: [], cam: { x: 0, y: 0, scale: 1 }, manifest,
  })).toEqual([]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/corpus/paint.test.ts`
Expected: FAIL — cannot resolve `@lab/corpus/paint`

- [ ] **Step 3: Implement**

`lab/src/corpus/paint.ts`:

```ts
import type { Camera } from '@lab/corpus/camera';
import { toScreen } from '@lab/corpus/camera';
import type { Rect } from '@lab/corpus/layout';
import { isStale, sourceBox } from '@lab/corpus/sheet';
import type { Cell, SheetManifest } from '@lab/corpus/types';

export const STATUS_FILL: Record<string, string> = {
  unreviewed: '#2a2a2e',
  good: '#1f3a24',
  suspect: '#4a3a12',
  broken: '#4a1c1c',
  wontfix: '#232326',
};

export type PaintCommand =
  | { kind: 'sprite'; dx: number; dy: number; dw: number; dh: number;
      sx: number; sy: number; sw: number; sh: number }
  | { kind: 'fill'; dx: number; dy: number; dw: number; dh: number;
      fill: string };

export interface PaintInput {
  cells: Cell[];
  rects: Rect[];
  visible: number[];
  cam: Camera;
  manifest: SheetManifest | null;
}

/** What to draw this frame, as data.
 *
 *  Kept separate from the canvas so the decisions -- which cells, from where,
 *  in what colour -- are testable without a rendering context, and so the
 *  drawing itself is the only thing weasel's mega view has to replace. */
export function paintCommands({ cells, rects, visible, cam, manifest }:
                              PaintInput): PaintCommand[] {
  const out: PaintCommand[] = [];
  for (const i of visible) {
    const cell = cells[i];
    const rect = rects[i];
    if (!cell || !rect) continue;
    const { x: dx, y: dy } = toScreen(cam, rect.x, rect.y);
    const dw = rect.w * cam.scale;
    const dh = rect.h * cam.scale;
    const box = manifest && cell.sha && !isStale(manifest, cell)
      ? sourceBox(manifest, cell.index)
      : null;
    out.push(box
      ? { kind: 'sprite', dx, dy, dw, dh, ...box }
      : { kind: 'fill', dx, dy, dw, dh,
          fill: STATUS_FILL[cell.status] ?? STATUS_FILL.unreviewed! });
  }
  return out;
}
```

`lab/src/corpus/Wall.tsx`:

```tsx
import { useEffect, useRef } from 'react';
import type { Camera } from '@lab/corpus/camera';
import type { Rect } from '@lab/corpus/layout';
import { paintCommands } from '@lab/corpus/paint';
import type { Cell, SheetManifest } from '@lab/corpus/types';
import { visibleRange } from '@lab/corpus/visible';

export interface WallProps {
  cells: Cell[];
  rects: Rect[];
  cam: Camera;
  sheet: HTMLImageElement | null;
  manifest: SheetManifest | null;
  width: number;
  height: number;
  onPick: (cell: Cell) => void;
}

/** The wall's only rendering surface.
 *
 *  Canvas2D holds today's corpus. When weasel's mega view exists this body is
 *  what it replaces; nothing above it knows what an atlas page is. */
export function Wall({ cells, rects, cam, sheet, manifest, width, height,
                       onPick }: WallProps) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.imageSmoothingEnabled = true;
    const visible = visibleRange(rects, cam, { width, height });
    for (const cmd of paintCommands({ cells, rects, visible, cam, manifest })) {
      if (cmd.kind === 'sprite' && sheet) {
        ctx.drawImage(sheet, cmd.sx, cmd.sy, cmd.sw, cmd.sh,
                      cmd.dx, cmd.dy, cmd.dw, cmd.dh);
      } else if (cmd.kind === 'fill') {
        ctx.fillStyle = cmd.fill;
        ctx.fillRect(cmd.dx, cmd.dy, cmd.dw, cmd.dh);
      }
    }
  }, [cells, rects, cam, sheet, manifest, width, height]);

  return (
    <canvas
      ref={ref}
      className="corpus-canvas"
      style={{ width, height }}
      onClick={(e) => {
        const box = e.currentTarget.getBoundingClientRect();
        const sx = e.clientX - box.left;
        const sy = e.clientY - box.top;
        const hit = visibleRange(rects, cam, { width, height }).find((i) => {
          const r = rects[i]!;
          const p = { x: (r.x - cam.x) * cam.scale, y: (r.y - cam.y) * cam.scale };
          return sx >= p.x && sx <= p.x + r.w * cam.scale
              && sy >= p.y && sy <= p.y + r.h * cam.scale;
        });
        if (hit !== undefined && cells[hit]) onPick(cells[hit]!);
      }}
    />
  );
}
```

Create `lab/src/corpus/Wall.css` and import it from `Wall.tsx`
(`import '@lab/corpus/Wall.css';`) — the lab keeps CSS per component
(`ColorRow.css`, `DefectCard.css`, `SourcePane.css`), not in one sheet:

```css
.corpus-canvas { display: block; cursor: crosshair; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/corpus/paint.test.ts`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/paint.ts lab/src/corpus/paint.test.ts \
        lab/src/corpus/Wall.tsx lab/src/corpus/corpus.css
git commit -m "paint the corpus wall onto one canvas"
```

---

### Task 14: Sort and filter

**Files:**
- Create: `lab/src/corpus/select.ts`
- Create: `lab/src/corpus/FilterBar.tsx`
- Test: `lab/src/corpus/select.test.ts`
- Test: `lab/src/corpus/FilterBar.test.tsx`

- [ ] **Step 1: Write the failing tests**

`lab/src/corpus/select.test.ts`:

```ts
import { applySelection } from '@lab/corpus/select';
import type { Cell } from '@lab/corpus/types';

const cell = (over: Partial<Cell> & { id: string; index: number }): Cell => ({
  title: over.id, category: 'Brick', printed: false, obsolete: false,
  status: 'unreviewed', sha: null, made_at: null, extra_d99: null,
  secs: null, error: null, ...over,
});

const cells = [
  cell({ id: 'a', index: 0, sha: 'x', extra_d99: 1 }),
  cell({ id: 'b', index: 1, extra_d99: 9 }),
  cell({ id: 'c', index: 2, sha: 'y', extra_d99: 5, error: 'boom' }),
];

it('sorts by part id ascending by default', () => {
  expect(applySelection(cells, { sort: 'id', filter: 'all' })
    .map((c) => c.id)).toEqual(['a', 'b', 'c']);
});

it('sorts a metric worst-first', () => {
  expect(applySelection(cells, { sort: 'extra_d99', filter: 'all' })
    .map((c) => c.id)).toEqual(['b', 'c', 'a']);
});

it('puts cells with no measurement last', () => {
  const withNull = [...cells, cell({ id: 'd', index: 3 })];
  expect(applySelection(withNull, { sort: 'extra_d99', filter: 'all' })
    .at(-1)!.id).toBe('d');
});

it('filters to what has no render', () => {
  expect(applySelection(cells, { sort: 'id', filter: 'unrendered' })
    .map((c) => c.id)).toEqual(['b']);
});

it('filters to errors', () => {
  expect(applySelection(cells, { sort: 'id', filter: 'errors' })
    .map((c) => c.id)).toEqual(['c']);
});

it('never mutates the input', () => {
  const before = cells.map((c) => c.id);
  applySelection(cells, { sort: 'extra_d99', filter: 'all' });
  expect(cells.map((c) => c.id)).toEqual(before);
});
```

`lab/src/corpus/FilterBar.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { FilterBar } from '@lab/corpus/FilterBar';

const SLOTS = [{ source: 'census-naive', n: 200 }, { source: 'naive', n: 49 }];
const bar = (props: Record<string, unknown> = {}) => (
  <FilterBar selection={{ sort: 'id', filter: 'all' }} onChange={() => {}}
             shown={10} total={100} sources={SLOTS} source="census-naive"
             onSource={() => {}} {...props} />
);

it('lists the slots that have renders, with their counts', () => {
  render(bar());
  expect(screen.getByRole('option', { name: 'census-naive (200)' })).toBeTruthy();
  expect(screen.getByRole('option', { name: 'naive (49)' })).toBeTruthy();
});

it('reports a slot change', () => {
  const onSource = vi.fn();
  render(bar({ onSource }));
  fireEvent.change(screen.getByLabelText('Slot'), { target: { value: 'naive' } });
  expect(onSource).toHaveBeenCalledWith('naive');
});

it('reports a sort change', () => {
  const onChange = vi.fn();
  render(bar({ onChange }));
  fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'secs' } });
  expect(onChange).toHaveBeenCalledWith({ sort: 'secs', filter: 'all' });
});

it('reports a filter change', () => {
  const onChange = vi.fn();
  render(bar({ onChange }));
  fireEvent.change(screen.getByLabelText('Show'),
                   { target: { value: 'unrendered' } });
  expect(onChange).toHaveBeenCalledWith({ sort: 'id', filter: 'unrendered' });
});

it('says how much of the corpus is on the wall', () => {
  render(bar());
  expect(screen.getByText('10 of 100')).toBeTruthy();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd lab && npx vitest run src/corpus/select.test.ts src/corpus/FilterBar.test.tsx`
Expected: FAIL — cannot resolve either module

- [ ] **Step 3: Implement**

`lab/src/corpus/select.ts`:

```ts
import type { Cell } from '@lab/corpus/types';

export const SORTS = ['id', 'category', 'status', 'extra_d99', 'secs',
                      'made_at'] as const;
export const FILTERS = ['all', 'rendered', 'unrendered', 'errors', 'printed',
                        'obsolete'] as const;

export type Sort = typeof SORTS[number];
export type Filter = typeof FILTERS[number];
export interface Selection { sort: Sort; filter: Filter }

const KEEP: Record<Filter, (c: Cell) => boolean> = {
  all: () => true,
  rendered: (c) => c.sha !== null,
  unrendered: (c) => c.sha === null,
  errors: (c) => c.error !== null,
  printed: (c) => c.printed,
  obsolete: (c) => c.obsolete,
};

// Metrics read worst-first; the descriptive keys read alphabetically. Both put
// "no answer" last, so an unmeasured part never displaces a bad one.
const DESCENDING: ReadonlySet<Sort> = new Set(['extra_d99', 'secs', 'made_at']);

function key(cell: Cell, sort: Sort): string | number | null {
  switch (sort) {
    case 'id': return cell.id;
    case 'category': return cell.category;
    case 'status': return cell.status;
    case 'extra_d99': return cell.extra_d99;
    case 'secs': return cell.secs;
    case 'made_at': return cell.made_at;
  }
}

export function applySelection(cells: Cell[], selection: Selection): Cell[] {
  const kept = cells.filter(KEEP[selection.filter]);
  const desc = DESCENDING.has(selection.sort);
  return kept.slice().sort((a, b) => {
    const ka = key(a, selection.sort);
    const kb = key(b, selection.sort);
    if (ka === null || ka === undefined) return kb === null ? 0 : 1;
    if (kb === null || kb === undefined) return -1;
    if (ka === kb) return a.id < b.id ? -1 : 1;
    return (ka < kb ? -1 : 1) * (desc ? -1 : 1);
  });
}
```

`lab/src/corpus/FilterBar.tsx`:

```tsx
import { FILTERS, SORTS, type Selection } from '@lab/corpus/select';

export function FilterBar({ selection, onChange, shown, total,
                            sources, source, onSource }: {
  selection: Selection;
  onChange: (next: Selection) => void;
  shown: number;
  total: number;
  sources: { source: string; n: number }[];
  source: string;
  onSource: (next: string) => void;
}) {
  return (
    <div className="corpus-bar">
      <label>
        Slot
        <select value={source} onChange={(e) => onSource(e.target.value)}>
          {sources.map((s) => (
            <option key={s.source} value={s.source}>{s.source} ({s.n})</option>
          ))}
        </select>
      </label>
      <label>
        Sort
        <select value={selection.sort}
                onChange={(e) => onChange({ ...selection,
                                            sort: e.target.value as Selection['sort'] })}>
          {SORTS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      <label>
        Show
        <select value={selection.filter}
                onChange={(e) => onChange({ ...selection,
                                            filter: e.target.value as Selection['filter'] })}>
          {FILTERS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </label>
      <span className="corpus-count">{shown} of {total}</span>
    </div>
  );
}
```

Create `lab/src/corpus/FilterBar.css` and import it from `FilterBar.tsx`:

```css
.corpus-bar {
  display: flex;
  gap: 1rem;
  align-items: center;
  padding: 0.4rem 0.6rem;
  font: 12px/1.4 ui-monospace, monospace;
}
.corpus-bar label { display: flex; gap: 0.3rem; align-items: center; }
.corpus-count { margin-left: auto; opacity: 0.7; }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd lab && npx vitest run src/corpus/select.test.ts src/corpus/FilterBar.test.tsx`
Expected: PASS, 9 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/select.ts lab/src/corpus/select.test.ts \
        lab/src/corpus/FilterBar.tsx lab/src/corpus/FilterBar.test.tsx \
        lab/src/corpus/corpus.css
git commit -m "sort and filter controls for the corpus wall"
```

---

### Task 15: The lightbox

**Files:**
- Create: `lab/src/corpus/Lightbox.tsx`
- Test: `lab/src/corpus/Lightbox.test.tsx`
- Modify: `lab/src/api/client.ts`

- [ ] **Step 1: Write the failing test**

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Lightbox } from '@lab/corpus/Lightbox';

const detail = {
  part: { id: '3001', title: 'Brick 2 x 4', category: 'Brick',
          status: 'good', status_note: null },
  findings: [{ part_id: '3001', engine: 'naive', extra_d99: 1.5,
               missing_px: 3, secs: 12.0, error: null }],
  runs: [{ id: 7, kind: 'census', started: '2026-09-05T10:00:00+00:00',
           commit_sha: 'abc1234', engine: 'naive', extra_d99: 1.5,
           missing_px: 3, secs: 12.0, error: null }],
  defects: [{ id: 'd1', part: '3001', title: 'rim nubs', status: 'open' }],
};

const client = { corpusPart: () => Promise.resolve(detail) } as any;
const box = (props: Record<string, unknown> = {}) => (
  <Lightbox partId="3001" source="naive" client={client} onClose={() => {}}
            {...props} />
);

it('shows the part title and the render for the slot being viewed', async () => {
  render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  expect(screen.getByRole('img', { name: /3001/ })
    .getAttribute('src')).toContain('/api/thumbs/naive/128/3001.png');
});

it('lists each engine measurement', async () => {
  render(box());
  await waitFor(() => screen.getByText('naive'));
  expect(screen.getByText('1.5')).toBeTruthy();
});

it('lists open defects', async () => {
  render(box());
  await waitFor(() => screen.getByText('rim nubs'));
});

it('closes on the button', async () => {
  const onClose = vi.fn();
  render(box({ onClose }));
  await waitFor(() => screen.getByLabelText('Close'));
  fireEvent.click(screen.getByLabelText('Close'));
  expect(onClose).toHaveBeenCalled();
});

it('closes on Escape', async () => {
  const onClose = vi.fn();
  render(box({ onClose }));
  await waitFor(() => screen.getByLabelText('Close'));
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(onClose).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/corpus/Lightbox.test.tsx`
Expected: FAIL — cannot resolve `@lab/corpus/Lightbox`

- [ ] **Step 3: Implement**

Add to `lab/src/api/client.ts`:

```ts
  corpusPart: (id: string): Promise<PartDetail> =>
    get(`/api/corpus/part/${encodeURIComponent(id)}`),
```

Add to `lab/src/corpus/types.ts`:

```ts
export interface PartDetail {
  part: { id: string; title: string; category: string | null;
          status: string; status_note: string | null };
  findings: { part_id: string; engine: string; extra_d99: number | null;
              missing_px: number | null; secs: number | null;
              error: string | null }[];
  runs: { id: number; kind: string; started: string; commit_sha: string;
          engine: string; extra_d99: number | null; missing_px: number | null;
          secs: number | null; error: string | null }[];
  defects: { id: string; part: string; title: string; status: string }[];
}
```

`lab/src/corpus/Lightbox.tsx`:

```tsx
import { useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { PartDetail } from '@lab/corpus/types';

export function Lightbox({ partId, source, client, onClose }: {
  partId: string;
  source: string;
  client: LabClient;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<PartDetail | null>(null);

  useEffect(() => {
    let live = true;
    void client.corpusPart(partId).then((d) => { if (live) setDetail(d); });
    return () => { live = false; };
  }, [partId, client]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="corpus-lightbox" role="dialog" aria-label={`Part ${partId}`}>
      <button type="button" className="corpus-close" aria-label="Close"
              onClick={onClose}>x</button>
      {!detail ? <p>loading {partId}…</p> : (
        <>
          <h2>{detail.part.title}</h2>
          <p className="corpus-sub">
            {detail.part.id} · {detail.part.category ?? 'uncategorised'} ·
            {' '}{detail.part.status}
            {detail.part.status_note ? ` · ${detail.part.status_note}` : ''}
          </p>
          <img className="corpus-big" alt={`${detail.part.id} render`}
               src={`/api/thumbs/${source}/128/${detail.part.id}.png`} />
          <h3>Measurements</h3>
          <table>
            <thead>
              <tr><th>engine</th><th>extra d99</th><th>missing px</th>
                  <th>secs</th><th>error</th></tr>
            </thead>
            <tbody>
              {detail.findings.map((f) => (
                <tr key={f.engine}>
                  <td>{f.engine}</td>
                  <td>{f.extra_d99 ?? '—'}</td>
                  <td>{f.missing_px ?? '—'}</td>
                  <td>{f.secs ?? '—'}</td>
                  <td>{f.error ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>Defects</h3>
          {detail.defects.length === 0 ? <p>none</p> : (
            <ul>
              {detail.defects.map((d) => (
                <li key={d.id}>{d.title} <em>{d.status}</em></li>
              ))}
            </ul>
          )}
          <h3>Runs</h3>
          <ul>
            {detail.runs.map((r) => (
              <li key={`${r.id}-${r.engine}`}>
                {r.started.slice(0, 10)} · {r.kind} · {r.commit_sha.slice(0, 7)}
                {' '}· {r.engine} · d99 {r.extra_d99 ?? '—'}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
```

Create `lab/src/corpus/Lightbox.css` and import it from `Lightbox.tsx`:

```css
.corpus-lightbox {
  position: fixed;
  inset: 0;
  overflow: auto;
  padding: 2rem;
  background: #131316;
  font: 13px/1.5 ui-monospace, monospace;
}
.corpus-close { position: absolute; top: 1rem; right: 1rem; }
.corpus-big { width: 256px; height: 256px; image-rendering: pixelated; }
.corpus-sub { opacity: 0.7; }
.corpus-lightbox td, .corpus-lightbox th {
  padding: 0.1rem 0.8rem 0.1rem 0;
  text-align: left;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/corpus/Lightbox.test.tsx`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/Lightbox.tsx lab/src/corpus/Lightbox.test.tsx \
        lab/src/corpus/types.ts lab/src/api/client.ts lab/src/corpus/corpus.css
git commit -m "the corpus wall's part lightbox"
```

---

### Task 16: Wire it together

**Files:**
- Modify: `lab/src/corpus/CorpusWall.tsx`
- Modify: `lab/src/corpus/CorpusWall.test.tsx`

- [ ] **Step 1: Write the failing test**

Replace `lab/src/corpus/CorpusWall.test.tsx` with:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CorpusWall } from '@lab/corpus/CorpusWall';
import type { Cell } from '@lab/corpus/types';

const cell = (id: string, index: number, sha: string | null = null): Cell => ({
  id, index, title: `Part ${id}`, category: 'Brick', printed: false,
  obsolete: false, status: 'unreviewed', sha, made_at: null,
  extra_d99: null, secs: null, error: null,
});

const client = {
  corpusSources: () => Promise.resolve({
    sources: [{ source: 'census-naive', n: 2 }],
  }),
  cells: () => Promise.resolve({
    cells: [cell('a', 0, 'sha-a'), cell('b', 1)], count: 2,
    version: '2026-09-05T10:00:00+00:00', source: 'census-naive',
  }),
  sheetManifest: () => Promise.resolve({
    level: 32, gutter: 2, pitch: 36, cols: 2, rows: 1, count: 2, size: 72,
    baked: { a: 'sha-a' },
  }),
  corpusPart: () => new Promise(() => {}),
} as any;

it('says it is loading before the cells arrive', () => {
  render(<CorpusWall client={{ cells: () => new Promise(() => {}),
                               corpusSources: () => new Promise(() => {}),
                               sheetManifest: () => new Promise(() => {}) } as any} />);
  expect(screen.getByText(/loading the corpus/i)).toBeTruthy();
});

it('draws a canvas once the cells arrive', async () => {
  const { container } = render(<CorpusWall client={client} />);
  await waitFor(() => expect(container.querySelector('canvas')).toBeTruthy());
});

it('reports how much of the corpus the filter is showing', async () => {
  render(<CorpusWall client={client} />);
  await waitFor(() => screen.getByText('2 of 2'));
  fireEvent.change(screen.getByLabelText('Show'),
                   { target: { value: 'unrendered' } });
  await waitFor(() => screen.getByText('1 of 2'));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/corpus/CorpusWall.test.tsx`
Expected: FAIL — no canvas, no `2 of 2`

- [ ] **Step 3: Implement**

Add to `lab/src/api/client.ts`:

```ts
  sheetManifest: (source: string, level: number): Promise<SheetManifest> =>
    get(`/api/thumbs/${source}/sheet-${level}.json`),
```

Replace `lab/src/corpus/CorpusWall.tsx`:

```tsx
import { useEffect, useMemo, useRef, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import { fitBounds, zoomAt, type Camera } from '@lab/corpus/camera';
import { FilterBar } from '@lab/corpus/FilterBar';
import { gridLayout } from '@lab/corpus/layout';
import { Lightbox } from '@lab/corpus/Lightbox';
import { applySelection, type Selection } from '@lab/corpus/select';
import { useCells } from '@lab/corpus/useCells';
import type { SheetManifest } from '@lab/corpus/types';
import { Wall } from '@lab/corpus/Wall';
import '@lab/corpus/corpus.css';

const SHEET_LEVEL = 32;
const CELL = 32;
const GAP = 4;

/** The whole app, minus its mount. Exported so a labkit instrument can host it
 *  without the standalone page. */
export function CorpusWall({ client }: { client: LabClient }) {
  const [sources, setSources] = useState<{ source: string; n: number }[]>([]);
  const [source, setSource] = useState('census-naive');
  const cells = useCells(client, source);
  const [manifest, setManifest] = useState<SheetManifest | null>(null);
  const [sheet, setSheet] = useState<HTMLImageElement | null>(null);
  const [selection, setSelection] = useState<Selection>(
    { sort: 'id', filter: 'all' });
  const [cam, setCam] = useState<Camera | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 800, height: 600 });

  // The most-populated slot is the one worth opening on; the route already
  // orders them that way.
  useEffect(() => {
    void client.corpusSources().then(({ sources: got }) => {
      setSources(got);
      if (got[0]) setSource(got[0].source);
    }).catch(() => {});
  }, [client]);

  useEffect(() => {
    setSheet(null);
    void client.sheetManifest(source, SHEET_LEVEL).then(setManifest).catch(() => {});
    const img = new Image();
    img.onload = () => setSheet(img);
    img.src = `/api/thumbs/${source}/sheet-${SHEET_LEVEL}.png`;
  }, [client, source]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setSize({ width: entry.contentRect.width,
                           height: entry.contentRect.height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [cells]);

  const shown = useMemo(
    () => (cells ? applySelection(cells, selection) : []),
    [cells, selection]);

  const cols = Math.max(1, Math.ceil(Math.sqrt(shown.length)));
  const laid = useMemo(
    () => gridLayout(shown, { cell: CELL, gap: GAP, cols }),
    [shown, cols]);

  useEffect(() => {
    if (cam === null && laid.bounds.w > 0) setCam(fitBounds(laid.bounds, size));
  }, [cam, laid.bounds, size]);

  if (!cells) return <p className="corpus-loading">loading the corpus…</p>;

  return (
    <div className="corpus-app">
      <FilterBar selection={selection} onChange={setSelection}
                 shown={shown.length} total={cells.length}
                 sources={sources} source={source} onSource={setSource} />
      <div className="corpus-stage" ref={box}
           onWheel={(e) => {
             if (!cam) return;
             const r = e.currentTarget.getBoundingClientRect();
             setCam(zoomAt(cam, e.clientX - r.left, e.clientY - r.top,
                           e.deltaY < 0 ? 1.1 : 1 / 1.1));
           }}>
        {cam && (
          <Wall cells={shown} rects={laid.rects} cam={cam} sheet={sheet}
                manifest={manifest} width={size.width} height={size.height}
                onPick={(c) => setPicked(c.id)} />
        )}
      </div>
      {picked && (
        <Lightbox partId={picked} source={source} client={client}
                  onClose={() => setPicked(null)} />
      )}
    </div>
  );
}
```

Add to `lab/src/corpus/corpus.css` (the shell's own sheet, already imported by
`CorpusWall.tsx`):

```css
.corpus-app { display: flex; flex-direction: column; height: 100vh; }
.corpus-stage { flex: 1; overflow: hidden; }
```

- [ ] **Step 3b: Move focus into the lightbox when it opens**

The lightbox is `role="dialog"` with an Escape handler and a real `<button>`
Close, but nothing moves focus into it — so a keyboard user lands wherever the
canvas left them and has to tab through the page to reach it. No single
component can fix that; the one that mounts the dialog has to.

In `Lightbox.tsx`, focus the close button on mount:

```tsx
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { closeRef.current?.focus(); }, []);
```

and put `ref={closeRef}` on the Close button. Add a test asserting
`document.activeElement` is the Close button after the dialog renders.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/corpus/CorpusWall.test.tsx`
Expected: PASS, 3 tests

- [ ] **Step 5: Typecheck and run the corpus tests**

Run: `cd lab && npx tsc -b --noEmit && npx vitest run src/corpus`
Expected: no type errors; every corpus test passes.

- [ ] **Step 6: Look at it**

```bash
.venv/bin/python -m brick_icons.lab &
cd lab && npm run dev
```

Open `http://localhost:5178/corpus.html`. Expected: a wall of 24,591 cells,
100 of them white tiles carrying a part drawing and the rest flat placeholders.
Scroll to zoom. Click a drawn cell and the lightbox opens on that part. Change
Sort to `extra_d99` and the drawn cells move to the top-left.

Check it in both themes before moving on: the placeholder colours in
`STATUS_FILL` are a first guess, and the drawn tiles have to stay legible
against whichever surface the theme paints.

Screenshot it and put it on the wall:

```bash
~/src/slopboard/bin/slop <screenshot>
```

- [ ] **Step 7: Commit**

```bash
git add lab/src/corpus lab/src/api/client.ts
git commit -m "wire the corpus wall: cells, layout, camera, filter, lightbox"
```

---

### Task 17: Level of detail

`camera.ts` grew `levelFor` and `pickLevel` in Task 10 and nothing has used them
yet. This is the spec's rule that a cell shows the coarse sheet when it is
small, the fine sheet when it is bigger, and its own 128 px file when it is
large enough that the sheet would look soft.

**Files:**
- Modify: `lab/src/corpus/paint.ts`
- Modify: `lab/src/corpus/paint.test.ts`
- Create: `lab/src/corpus/useSheets.ts`
- Create: `lab/src/corpus/useLooseThumbs.ts`
- Test: `lab/src/corpus/useLooseThumbs.test.ts`
- Modify: `lab/src/corpus/Wall.tsx`
- Modify: `lab/src/corpus/CorpusWall.tsx`

- [ ] **Step 1: Write the failing tests**

Append to `lab/src/corpus/paint.test.ts`:

```ts
it('draws a whole loose image when one is loaded for the cell', () => {
  const img = {} as HTMLImageElement;
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: 1 }, manifest, loose: new Map([['a', img]]),
  });
  expect(cmd).toEqual({ kind: 'image', dx: 0, dy: 0, dw: 10, dh: 10, image: img });
});

it('prefers the loose image over the sheet', () => {
  const img = {} as HTMLImageElement;
  const sheetOnly = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: 1 }, manifest, loose: new Map(),
  });
  expect(sheetOnly[0]!.kind).toBe('sprite');
  const withLoose = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: 1 }, manifest, loose: new Map([['a', img]]),
  });
  expect(withLoose[0]!.kind).toBe('image');
});

it('falls back to the sheet while a loose image is still loading', () => {
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: 1 }, manifest, loose: new Map(),
  });
  expect(cmd!.kind).toBe('sprite');
});
```

`lab/src/corpus/useLooseThumbs.test.ts`:

```ts
import { thumbUrl, wanted } from '@lab/corpus/useLooseThumbs';
import type { Cell } from '@lab/corpus/types';

const cell = (id: string, index: number, sha: string | null): Cell => ({
  id, index, title: id, category: null, printed: false, obsolete: false,
  status: 'unreviewed', sha, made_at: null, extra_d99: null, secs: null,
  error: null,
});

it('names the slot and cache-busts on the render sha', () => {
  expect(thumbUrl(cell('3001', 0, 'deadbeefcafe'), 'naive'))
    .toBe('/api/thumbs/naive/128/3001.png?v=deadbeef');
});

it('wants nothing below the loose level', () => {
  expect(wanted([cell('a', 0, 'x')], [0], 32)).toEqual([]);
});

it('wants only visible cells that have a render', () => {
  const cells = [cell('a', 0, 'x'), cell('b', 1, null)];
  expect(wanted(cells, [0, 1], 128).map((c) => c.id)).toEqual(['a']);
});

it('caps how many it asks for at once', () => {
  const many = Array.from({ length: 300 }, (_, i) => cell(`p${i}`, i, 'x'));
  expect(wanted(many, many.map((_, i) => i), 128).length).toBe(200);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd lab && npx vitest run src/corpus/paint.test.ts src/corpus/useLooseThumbs.test.ts`
Expected: FAIL — `paintCommands` rejects `loose`; `@lab/corpus/useLooseThumbs` unresolved.

- [ ] **Step 3: Implement**

In `lab/src/corpus/paint.ts`, add the command variant, the input field and the
branch:

```ts
export type PaintCommand =
  | { kind: 'sprite'; dx: number; dy: number; dw: number; dh: number;
      sx: number; sy: number; sw: number; sh: number }
  | { kind: 'image'; dx: number; dy: number; dw: number; dh: number;
      image: HTMLImageElement }
  | { kind: 'fill'; dx: number; dy: number; dw: number; dh: number;
      fill: string };

export interface PaintInput {
  cells: Cell[];
  rects: Rect[];
  visible: number[];
  cam: Camera;
  manifest: SheetManifest | null;
  /** Full-size thumbnails already loaded, by part id. */
  loose?: Map<string, HTMLImageElement>;
}
```

and inside the loop in `paintCommands`, replace the `out.push(...)` with:

```ts
    const image = loose?.get(cell.id);
    if (image) {
      out.push({ kind: 'image', dx, dy, dw, dh, image });
      continue;
    }
    const box = manifest && cell.sha && !isStale(manifest, cell)
      ? sourceBox(manifest, cell.index)
      : null;
    out.push(box
      ? { kind: 'sprite', dx, dy, dw, dh, ...box }
      : { kind: 'fill', dx, dy, dw, dh,
          fill: STATUS_FILL[cell.status] ?? STATUS_FILL.unreviewed! });
```

(and destructure `loose` out of the argument alongside `manifest`.)

`lab/src/corpus/useLooseThumbs.ts`:

```ts
import { useEffect, useState } from 'react';
import { LOOSE_LEVEL } from '@lab/corpus/useSheets';
import type { Cell } from '@lab/corpus/types';

/** How many full-size thumbnails to have in flight. At the zoom that asks for
 *  them only a few dozen cells are on screen; the cap is for the moment a
 *  filter change puts many large cells in view at once. */
export const MAX_IN_FLIGHT = 200;

export function thumbUrl(cell: Cell, source: string): string {
  return `/api/thumbs/${source}/${LOOSE_LEVEL}/${cell.id}.png`
       + `?v=${cell.sha!.slice(0, 8)}`;
}

/** Which visible cells deserve their own image at this level. */
export function wanted(cells: Cell[], visible: number[],
                       level: number): Cell[] {
  if (level < LOOSE_LEVEL) return [];
  const out: Cell[] = [];
  for (const i of visible) {
    const cell = cells[i];
    if (cell && cell.sha !== null) out.push(cell);
    if (out.length === MAX_IN_FLIGHT) break;
  }
  return out;
}

export function useLooseThumbs(cells: Cell[], visible: number[], level: number,
                               source: string) {
  const [loaded, setLoaded] = useState(new Map<string, HTMLImageElement>());

  useEffect(() => { setLoaded(new Map()); }, [source]);

  useEffect(() => {
    const want = wanted(cells, visible, level);
    const missing = want.filter((c) => !loaded.has(c.id));
    if (missing.length === 0) return;
    let live = true;
    for (const cell of missing) {
      const img = new Image();
      img.onload = () => {
        if (!live) return;
        setLoaded((prev) => new Map(prev).set(cell.id, img));
      };
      img.src = thumbUrl(cell, source);
    }
    return () => { live = false; };
  }, [cells, visible, level, source, loaded]);

  return level >= LOOSE_LEVEL ? loaded : undefined;
}
```

`lab/src/corpus/useSheets.ts`:

```ts
import { useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { SheetManifest } from '@lab/corpus/types';

export const SHEET_LEVELS = [8, 32] as const;
export const LOOSE_LEVEL = 128;

export interface Sheet {
  image: HTMLImageElement | null;
  manifest: SheetManifest | null;
}

/** Both sprite sheets, loaded once. They are one small texture each and never
 *  change during a session, so there is nothing to evict. */
export function useSheets(client: LabClient, source: string): Record<number, Sheet> {
  const [sheets, setSheets] = useState<Record<number, Sheet>>({});

  useEffect(() => {
    setSheets({});
    for (const level of SHEET_LEVELS) {
      void client.sheetManifest(source, level).then((manifest) => {
        setSheets((prev) => ({ ...prev,
          [level]: { ...(prev[level] ?? { image: null }), manifest } }));
      }).catch(() => {});
      const img = new Image();
      img.onload = () => setSheets((prev) => ({ ...prev,
        [level]: { ...(prev[level] ?? { manifest: null }), image: img } }));
      img.src = `/api/thumbs/${source}/sheet-${level}.png`;
    }
  }, [client, source]);

  return sheets;
}
```

In `lab/src/corpus/Wall.tsx`, take `loose` and draw the new command kind. Change
the props and the paint loop:

```tsx
export interface WallProps {
  cells: Cell[];
  rects: Rect[];
  cam: Camera;
  sheet: HTMLImageElement | null;
  manifest: SheetManifest | null;
  loose?: Map<string, HTMLImageElement>;
  width: number;
  height: number;
  onPick: (cell: Cell) => void;
}
```

```tsx
    for (const cmd of paintCommands({ cells, rects, visible, cam, manifest,
                                      loose })) {
      if (cmd.kind === 'sprite' && sheet) {
        ctx.drawImage(sheet, cmd.sx, cmd.sy, cmd.sw, cmd.sh,
                      cmd.dx, cmd.dy, cmd.dw, cmd.dh);
      } else if (cmd.kind === 'image') {
        ctx.drawImage(cmd.image, cmd.dx, cmd.dy, cmd.dw, cmd.dh);
      } else if (cmd.kind === 'fill') {
        ctx.fillStyle = cmd.fill;
        ctx.fillRect(cmd.dx, cmd.dy, cmd.dw, cmd.dh);
      }
    }
```

and add `loose` to that effect's dependency array.

In `lab/src/corpus/CorpusWall.tsx`, replace the single-sheet state with the
level ladder. Delete the `SHEET_LEVEL` constant, the `manifest`/`sheet` state
and the effect that loaded them, and use:

```tsx
import { pickLevel } from '@lab/corpus/camera';
import { useLooseThumbs } from '@lab/corpus/useLooseThumbs';
import { useSheets } from '@lab/corpus/useSheets';
import { visibleRange } from '@lab/corpus/visible';
```

```tsx
  const sheets = useSheets(client, source);
  const [level, setLevel] = useState(8);

  useEffect(() => {
    if (cam) setLevel((current) => pickLevel(current, CELL * cam.scale));
  }, [cam]);

  const visible = useMemo(
    () => (cam ? visibleRange(laid.rects, cam, size) : []),
    [laid.rects, cam, size]);
  const loose = useLooseThumbs(shown, visible, level, source);
  const sheet = sheets[level === 128 ? 32 : level] ?? { image: null, manifest: null };
```

and pass them down:

```tsx
          <Wall cells={shown} rects={laid.rects} cam={cam} sheet={sheet.image}
                manifest={sheet.manifest} loose={loose} width={size.width}
                height={size.height} onPick={(c) => setPicked(c.id)} />
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd lab && npx vitest run src/corpus`
Expected: PASS, including the 3 new paint tests and the 4 new loose-thumb tests.

- [ ] **Step 5: See the ladder work**

With the server and dev page running, open `http://localhost:5178/corpus.html`.
Zoom all the way out: cells are a few pixels and come from `sheet-8.png` — check
the network panel shows it fetched. Zoom in: `sheet-32.png` takes over. Zoom
until a cell is bigger than 128 px: individual
`/api/thumbs/<slot>/128/<part>.png` requests appear and the drawing sharpens.

Then switch the Slot control from `census-naive` to `naive`. The wall keeps its
camera and its sort, the sheets swap, and far fewer cells are drawn — 49 against
200. The drawings that do appear carry black outline strokes the census ones
lack.

Park the zoom exactly on a threshold and jiggle it. Expected: the level does not
flip back and forth — that is what `pickLevel`'s hysteresis is for. If the
network panel shows a sheet being refetched every frame, the hysteresis is
broken.

- [ ] **Step 6: Commit**

```bash
git add lab/src/corpus
git commit -m "swap the corpus wall between both sheets and the loose thumbnails"
```

---

### Task 18: The part card

Clicking a cell should not jump straight to a full-screen takeover. A single
click raises a **business-card-sized popup** beside the cell — id, title,
category, status, the sorted metric, its thumbnail, and a button that opens the
full lightbox. A **double click** skips the card and opens the lightbox
directly.

Everything the card shows is already in the `Cell` the wall holds, so the card
costs no fetch and appears instantly; only the lightbox goes to the server.

**Files:**
- Create: `lab/src/corpus/PartCard.tsx`, `PartCard.test.tsx`, `PartCard.css`
- Modify: `lab/src/corpus/Wall.tsx` (report the click point and the cell)
- Modify: `lab/src/corpus/CorpusWall.tsx` (card state, double-click to lightbox)
- Modify: `lab/src/corpus/CorpusWall.test.tsx`

Two repo rules bind this:

**No inline `style={...}`.** The card is positioned at the click point, which is
genuinely dynamic — so set CSS custom properties on the element from a ref in an
effect (`el.style.setProperty('--card-x', `${x}px`)`) and let the stylesheet
consume them. The JSX stays free of a `style` prop.

**Single vs double click needs no timer.** A click event carries `detail` — the
click count. `onClick` returns early when `e.detail === 2` and lets
`onDoubleClick` handle it, so the card never flashes before the lightbox.

- [ ] **Step 0: Fix the camera, which fits once at the wrong size**

Seen in the browser: the wall draws at half the scale it should, filling about
half the canvas. `cam` is fitted only when it is `null`, and that happens on the
first render with `size` still at its 800x600 default — the `ResizeObserver`
reports the real 1184x1443 a moment later and nothing re-fits.

Refit while the camera is still the automatic one, and stop as soon as the user
moves it. Track that explicitly rather than guessing from the values:

```tsx
  const touched = useRef(false);
  useEffect(() => {
    if (touched.current || laid.bounds.w <= 0) return;
    setCam(fitBounds(laid.bounds, size));
  }, [laid.bounds, size]);
```

and set `touched.current = true` in the wheel handler. That also fixes filtering
to a small set leaving the camera on the old bounds, since the refit follows
`laid.bounds`.

Add a test asserting the camera re-fits when the observed size changes but not
after a wheel event.

- [ ] **Step 1: Write `lab/src/corpus/PartCard.test.tsx`**

```tsx
import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { PartCard } from '@lab/corpus/PartCard';
import type { Cell } from '@lab/corpus/types';

const cell: Cell = {
  id: '3001', index: 0, title: 'Brick 2 x 4', category: 'Brick',
  printed: false, obsolete: false, status: 'good', sha: 'deadbeefcafe',
  made_at: '2026-09-05T10:00:00+00:00', extra_d99: 4.5, secs: 12, error: null,
};

const card = (props: Record<string, unknown> = {}) => (
  <PartCard cell={cell} source="naive" at={{ x: 100, y: 100 }}
            viewport={{ width: 1000, height: 800 }}
            onOpen={() => {}} onClose={() => {}} {...props} />
);

it('shows what the wall already knows, without fetching', () => {
  render(card());
  expect(screen.getByText('Brick 2 x 4')).toBeTruthy();
  expect(screen.getByText(/3001/)).toBeTruthy();
  expect(screen.getByText(/good/)).toBeTruthy();
});

it('shows the thumbnail for the slot being viewed', () => {
  render(card());
  expect(screen.getByRole('img', { name: /3001/ })
    .getAttribute('src')).toContain('/api/thumbs/naive/128/3001.png');
});

it('says so when a part has no render rather than showing a broken image', () => {
  render(card({ cell: { ...cell, sha: null } }));
  expect(screen.queryByRole('img')).toBeNull();
  expect(screen.getByText(/not rendered/i)).toBeTruthy();
});

it('opens the lightbox from its button', () => {
  const onOpen = vi.fn();
  render(card({ onOpen }));
  fireEvent.click(screen.getByRole('button', { name: /open/i }));
  expect(onOpen).toHaveBeenCalledWith('3001');
});

it('closes on Escape', () => {
  const onClose = vi.fn();
  render(card({ onClose }));
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(onClose).toHaveBeenCalled();
});

it('stays inside the viewport when clicked near the right edge', () => {
  const { container } = render(card({ at: { x: 990, y: 790 } }));
  const el = container.querySelector('.corpus-card') as HTMLElement;
  expect(parseInt(el.style.getPropertyValue('--card-x'), 10))
    .toBeLessThan(990);
});
```

- [ ] **Step 2: Run to verify it fails**

`cd lab && npx vitest run src/corpus/PartCard.test.tsx`

- [ ] **Step 3: Implement the card**

Write `PartCard.tsx` yourself against those tests. It takes
`{ cell, source, at, viewport, onOpen, onClose }`, renders a small panel with
the part's identity, its status, `extra_d99`/`secs` where present, the thumbnail
when `cell.sha` is set, and an Open button. It clamps `--card-x`/`--card-y` so
the card never leaves the viewport, and it listens for Escape.

`PartCard.css` sizes it like a business card (about 320x190) and positions it
absolutely from the two custom properties.

- [ ] **Step 4: Report the click point from `Wall.tsx`**

`onPick` currently receives only the cell. Widen it to
`onPick(cell, at: {x, y})`, passing the click's position within the canvas —
the hit-test already computes it. Update `Wall`'s own callers and tests.

- [ ] **Step 5: Wire both gestures in `CorpusWall.tsx`**

Hold `carded: {cell, at} | null` beside `picked`. `onPick` sets `carded`;
`onDoubleClick` on the stage sets `picked` and clears `carded`. Opening the
lightbox from the card's button clears the card. Add tests to
`CorpusWall.test.tsx` for: a single click showing the card, the card's Open
button raising the lightbox, and a double click going straight to the lightbox
without the card appearing.

- [ ] **Step 6: Run, look, and commit**

`npx vitest run src/corpus` and `npx tsc -b --noEmit` must both be clean.

Then run it and drive it in a browser, as Task 16 did: single-click a drawn
cell and confirm the card appears beside it rather than over it; press its Open
button; double-click another cell and confirm the lightbox opens with no card
flash; click a placeholder cell and confirm the card says the part is not
rendered. Screenshot the card and put it on the slopboard.

```bash
git add lab/src/corpus/PartCard.tsx lab/src/corpus/PartCard.test.tsx \
        lab/src/corpus/PartCard.css lab/src/corpus/Wall.tsx \
        lab/src/corpus/CorpusWall.tsx lab/src/corpus/CorpusWall.test.tsx
git commit -m "raise a part card on click, and the lightbox on double click"
```

---

### Task 19b: Two bugs the level ladder exposed

- [ ] **Pick the opening level from the zoom, not from a default**

`fitBounds` lands the default view at a cell size of about 11px. The 8/32 dead
zone is 10.7-24, and `level` initialises to 32 — so `pickLevel` correctly holds
32, and the wall opens drawing 32px art at 11px, which is the banding this whole
ladder exists to remove.

Hysteresis governs *transitions*; the first pick has nothing to be hysteretic
about. Initialise `level` from `levelFor(CELL * cam.scale)` at the moment the
camera first fits, and only run it through `pickLevel` thereafter.

Test that a wall opening at an 11px cell size starts on level 8, and that a
later small jiggle does not move it.

- [ ] **Stop requesting old-slot ids against the new slot**

Switching slots fires a burst of 404s: `useCells` clears its cells in an effect,
so for one commit `useLooseThumbs` sees the previous slot's `cells` alongside
the new `source` and builds URLs that cannot exist. It self-heals and never
shows wrong content — a 404 never fires `onload`, so nothing enters the map —
but the console is not clean, and a reader cannot tell this 404 from a real one.

Clear during render rather than in an effect, so the child never observes the
mismatched pair:

```ts
  const [fetchedFor, setFetchedFor] = useState(source);
  if (fetchedFor !== source) {
    setFetchedFor(source);
    setCells(null);
    version.current = '';
  }
```

Test that changing `source` yields `null` cells on the very next render, before
any effect runs.

- [ ] **Verify and commit**

`npx vitest run src/corpus` and `npx tsc -b --noEmit` clean. In the browser:
the wall opens on `sheet-8` with no banding, and switching slots produces no
404s in the network log.

```bash
git add lab/src/corpus/CorpusWall.tsx lab/src/corpus/CorpusWall.test.tsx \
        lab/src/corpus/useCells.ts lab/src/corpus/useCells.test.ts
git commit -m "open on the level the zoom asks for, and stop 404ing on a slot switch"
```

---

### Task 20: Colour a cell by what is known about it

Most of the wall has no thumbnail, so a cell's colour is the only thing it can
say. Today `STATUS_FILL` keys off `parts.status`, which is a review verdict —
not what a viewer needs to see. Replace it with four states:

| state | colour | source |
|---|---|---|
| an open defect against this slot | bright ochre `#c8860d` | `defects.engines` includes this engine |
| cannot be drawn here — GEOS, dead process, type error | red `#8c2020` | `measurements.error` |
| timed out here | dim rust `#5a3326` | `measurements.error` |
| an open defect against another slot | muted ochre `#6b5220` | `defects.engines` excludes it |
| a failure or timeout under another engine | muted red `#4a2a2a` | other engines' measurements |
| nothing is known | gray `#3a3a3f` | absence |

`defects.engines` is a JSON array of engine names, so a defect knows which
permutations it applies to. Parts are measured under both `naive` and `occt`,
and 1,313 of them error under at least one — so "a problem exists in another
permutation of this part" is real data, not a hypothetical. What is wrong here
always outranks what is wrong elsewhere.

**A timeout is not a defect.** 1,420 of the 1,428 recorded errors are
`TimeoutError`; the eight that genuinely failed would be invisible among them
under one colour. That is why these are two states.

**An open defect outranks a failure** — it is the newer fact, and someone acted
on it. It also applies to cells that *are* drawn: the thumbnail is an opaque
tile, so a background colour would sit behind it unseen. Those get an ochre ring
around the tile instead.

`cells.py` does not return defect counts yet; that is the first half of this
task. `findings.py`'s `_attach_defects` already does this in one query for a
page of rows rather than one query per row — follow it rather than inventing a
second approach.

**Files:**
- Modify: `brick_icons/lab/cells.py`, `tests/test_lab_cells.py`
- Modify: `lab/src/corpus/types.ts` (add `open_defects: number`)
- Modify: `lab/src/corpus/paint.ts`, `paint.test.ts`
- Modify: `lab/src/corpus/PartCard.tsx` (say why a cell is the colour it is)

- [ ] **Step 1: Return the four problem counts from `cells.py`**

Test first. A cell gains four fields, all counting only what is open (status not
`fixed`, not `notabug`) or erroring:

- `open_defects` — defects whose `engines` includes this slot's engine
- `open_defects_elsewhere` — defects on this part naming only other engines
- `error` — this engine's latest error, as today
- `error_elsewhere` — true when another engine's latest measurement errored

`engines` is stored as a JSON array string, so parse it rather than pattern
matching the text. `cells.engine_for(source)` already maps a slot to its engine.

Tests to write: a part with no defects reports 0 and 0; a defect naming this
engine counts in `open_defects` only; a defect naming a different engine counts
in `open_defects_elsewhere` only; a `fixed` defect counts in neither; a part
erroring under `occt` while clean under `naive` sets `error_elsewhere` and not
`error`. One query per response for each, not one per cell.

- [ ] **Step 2: Decide the fill in `paint.ts`**

Replace `STATUS_FILL` with a `CELL_FILL` table and a `fillFor(cell)` function.
Write the tests first — they are the specification:

```ts
it('flags a part with an open defect in ochre, whatever else is true', () => {
  expect(fillFor({ ...base, open_defects: 1, error: 'GEOSException' }))
    .toBe(CELL_FILL.defect);
});

it('separates a part that cannot be drawn from one that timed out', () => {
  expect(fillFor({ ...base, error: 'GEOSException' })).toBe(CELL_FILL.failed);
  expect(fillFor({ ...base, error: 'ProcessDied' })).toBe(CELL_FILL.failed);
  expect(fillFor({ ...base, error: 'TimeoutError' })).toBe(CELL_FILL.timeout);
});

it('mutes a problem that belongs to another permutation', () => {
  expect(fillFor({ ...base, open_defects_elsewhere: 1 }))
    .toBe(CELL_FILL.defectElsewhere);
  expect(fillFor({ ...base, error_elsewhere: true }))
    .toBe(CELL_FILL.problemElsewhere);
});

it('lets what is wrong here outrank what is wrong elsewhere', () => {
  expect(fillFor({ ...base, error: 'TimeoutError', open_defects_elsewhere: 3 }))
    .toBe(CELL_FILL.timeout);
});

it('says nothing is known when nothing is known', () => {
  expect(fillFor(base)).toBe(CELL_FILL.unknown);
});
```

`base` is a `Cell` with no sha, no error and no defects. Classify the error by
whether it *is* `TimeoutError`, not by a list of the failures — a new failure
mode should read as a failure, not fall through to gray.

- [ ] **Step 3: Ring a drawn cell that has an open defect**

Add a `ring` field to the sprite and image paint commands, set when
`open_defects > 0`, and have `Wall.tsx` stroke that rect after drawing the
image. Test that a drawn cell with a defect emits a command carrying the ring
and one without does not.

- [ ] **Step 4: Say it in the card**

`PartCard` should name the state in words — "not rendered", "render timed out",
"cannot be drawn: GEOSException", "2 open defects" — so the colour is legible
rather than something to memorise. Test each.

- [ ] **Step 5: Run, look, commit**

`npx vitest run src/corpus`, `.venv/bin/python -m pytest tests/test_lab_cells.py`
and `npx tsc -b --noEmit` all clean.

Then look at the wall: with 24,591 cells and 1,428 errors, the rust band should
be plainly visible and the eight red cells findable. Sort by `extra_d99` and by
`id` and confirm the colours travel with the cells. Screenshot and slop it.

```bash
git add brick_icons/lab/cells.py tests/test_lab_cells.py \
        lab/src/corpus/types.ts lab/src/corpus/paint.ts \
        lab/src/corpus/paint.test.ts lab/src/corpus/PartCard.tsx \
        lab/src/corpus/PartCard.test.tsx lab/src/corpus/Wall.tsx
git commit -m "colour a cell by what is known about it"
```

---

### Task 20b: Replace the hand-rolled camera with weasel's viewport

`lab/src/corpus/camera.ts` reimplements, worse, a module `@weasel-js/core`
already ships with tests. Two bugs have already come out of it — `fitBounds`
handing back `Infinity` on an empty wall, and an opening level chosen inside the
hysteresis dead zone. Neither would have existed in the tested version.

What core has, all under `packages/core/src/core/viewport/` with a `.test.ts`
each, and exported from `@weasel-js/core`:

| the wall's hand-rolled version | core's |
|---|---|
| `toScreen` / `toWorld` | `clientToCanvas`, `clientToWorld`, `viewTransform` |
| `zoomAt` | `zoomAt` |
| `fitBounds` | `fitToBounds`, `fitViewToBounds` |
| `MIN_SCALE` / `MAX_SCALE` | `DEFAULT_MIN_ZOOM`, `DEFAULT_MAX_ZOOM`, `clampView` |
| the `ResizeObserver` effect in `CorpusWall` | `useCanvasSize` |
| nothing — this is new | `viewportDragPanAction`, `wheelHandler`, `usePinchGesture`, `useVelocityTracker`, `useDecayLoop` |

**What stays.** `levelFor` and `pickLevel` are about which baked thumbnail to
sample and have nothing to do with a viewport — core knows nothing of the 8/32/128
ladder. They move into their own module rather than being deleted with the rest.

**Files:**
- Delete: `lab/src/corpus/camera.ts`, `camera.test.ts`
- Create: `lab/src/corpus/levels.ts`, `levels.test.ts` (`levelFor`, `pickLevel`,
  moved verbatim with their passing tests)
- Modify: `lab/src/corpus/CorpusWall.tsx`, `Wall.tsx`, `paint.ts`, `visible.ts`,
  `caret.ts` if it exists yet, and their tests
- Modify: `lab/src/corpus/Wall.css`

**All of it is in the version already installed.** `@weasel-js/core` 1.4.0 is in
`lab/node_modules` and its `.d.ts` exports every symbol above. Nothing needs
releasing, upgrading, or asking for.

The one real gap is packaging: `lab/package.json` depends on `@weasel-js/labkit`
only, so core is present transitively and invisible to anyone reading the
manifest. **Add `@weasel-js/core` as a direct dependency at the version already
resolved** — that omission is the likeliest reason a previous agent hand-rolled
a camera instead of finding this.

- [ ] **Step 1: Read core's viewport before writing anything**

Read `packages/core/src/core/viewport/` in `~/src/weasel` — at minimum `view.ts`,
`viewTransform.ts`, `zoomAt.ts`, `fitToBounds.ts`, `fitViewToBounds.ts`,
`clampView.ts`, `useCanvasSize.ts`, and `interactions/actions/defaults/viewportDragPan.ts`.
Their tests are the documentation.

The wall's `Camera` is `{x, y, scale}`; core's is a `View`. Report what the shape
actually is and how it converts, rather than assuming they match.

- [ ] **Step 2: Move the level ladder out**

`levelFor` and `pickLevel` and their tests move to `levels.ts`/`levels.test.ts`
unchanged. They pass today; they must still pass after the move, and that is the
whole check.

- [ ] **Step 3: Swap the viewport**

Replace every use of the wall's camera with core's equivalents. `visible.ts`,
`paint.ts` and `Wall.tsx` all convert world to screen; they take core's transform
instead. `CorpusWall`'s `ResizeObserver` effect gives way to `useCanvasSize`.

Every existing test must still pass, adjusted only where the type changed. **A
test that has to be weakened to accommodate the swap is a finding — report it
rather than weakening it.**

- [ ] **Step 4: Open fitted to the width, and drag to pan**

Two behaviours, both now core's rather than hand-written:

**Fit to width on load** — the wall fills the viewport's width and runs off the
bottom, rather than shrinking to fit both axes. `fitToBounds`/`fitViewToBounds`
take options; find the one that fits a single axis rather than computing it
yourself. Note that on a window taller than it is wide the two answers coincide,
so verify on a landscape window or you are testing nothing.

**Drag to pan** via `viewportDragPanAction`, with whatever inertia core gives by
default. A drag must not fire the click that raises a part card — track movement
between down and up and suppress the click past a few pixels, or use whatever
core provides for that. `cursor: grab`/`grabbing` in `Wall.css`.

Panning and zooming both count as touching the camera and stop the automatic
refit, as the wheel already does.

- [ ] **Step 5: Run, drive it, commit**

`npx vitest run src/corpus` and `npx tsc -b --noEmit` clean.

In the browser, on a window **wider than it is tall**: the wall opens filling the
width and running off the bottom; drag pans it to the last row and back; a drag
does not open a card and a click still does; zoom still anchors under the cursor;
the level ladder still switches. Screenshot and slop it.

```bash
git add lab/src/corpus
git commit -m "take weasel's viewport instead of a hand-rolled camera"
```

Report how much code the swap deleted — that number is the point of the task.

---

### Task 20c: Make the problem states actually read

The six cell colours were chosen as dark fills and four of them do not separate
at cell size. `#5a3326` rust against `#3a3a3f` gray is two dark, low-chroma
colours a few pixels across; the two muted "elsewhere" states are worse. Only
the bright ochre and the red carry.

**Pale fill, thick coloured border.** At five pixels the border is most of the
cell and carries the identity; at a hundred it reads as a labelled empty slot.
The dark gray unknown stays a plain fill with no border — it is the field
everything else has to separate from, and it should recede.

Starting point, to be corrected by looking rather than trusted:

| state | fill | border |
|---|---|---|
| unknown | `#3a3a3f` | none |
| timed out here | `#e8d5cc` | `#8a4a32`, thick |
| cannot be drawn here | `#f0d0d0` | `#b02020`, thick |
| open defect here | `#f5e3b8` | `#c8860d`, thick |
| problem in another slot | `#e8d5cc` | `#8a4a32`, thin |
| defect in another slot | `#f5e3b8` | `#c8860d`, thin |

"Elsewhere" reads as lower priority through border weight, not a duller hue —
duller hues are what failed.

**Scale the border with the cell**, `max(1, cell * 0.18)` or similar, capped so
a large cell does not become a picture frame. A fixed pixel width disappears
when zoomed out, which is the case that matters most.

**Files:**
- Modify: `lab/src/corpus/paint.ts`, `paint.test.ts`
- Modify: `lab/src/corpus/Wall.tsx`
- Modify: `lab/src/corpus/Legend.tsx` if it exists by now

- [ ] **Step 0: Clamp the pan, so the wall cannot be lost**

Adopting core's viewport brought drag-panning with inertia but **not** clamping —
`clampView` exists in core and is opt-in, and nothing calls it. So a flick now
sends the wall off into blank space with no way back except reloading. Wheel-zoom
alone made that hard; inertia makes it easy.

Apply `clampView` to panning. Read its signature and its test in
`~/src/weasel/packages/core/src/core/viewport/clampView.ts` first.

The bound is not "keep the whole wall on screen" — the wall deliberately
overflows vertically once fitted to the width. Something like "at least one
row and column of cells stays in view" is the shape to aim for. Say what rule
you chose and why.

- [ ] **Step 1: A fill command that carries a border**

`CELL_FILL` becomes a table of `{ fill, border, weight }`. The `fill` paint
command gains `border` and `borderWidth`, computed from the cell size. `unknown`
has no border and must emit none — not a transparent one.

Test: each state emits its fill and border; unknown emits no border; the border
width scales with the drawn cell size and never goes below 1.

- [ ] **Step 2: Stroke it**

`Wall.tsx` strokes the border inside the cell rect after filling, so adjacent
cells do not bleed into each other. Mind that a stroke straddles its path —
inset by half the width or neighbouring borders will overlap and read as a grid.

- [ ] **Step 3: LOOK AT IT, then correct the palette**

This is a task whose output is judged by eye, and the palette above is a first
guess by someone who already guessed wrong once.

Screenshot the wall zoomed fully out, at mid zoom, and zoomed in, and put all
three on the slopboard. Then answer, from the images and not from the hex
values: can you find the eight `cannot be drawn` cells at a glance? Do the ~1,260
timeouts read as a distinct population from the gray field? Do the pale fills
compete with the white drawn thumbnails, and if so say so — that is the most
likely thing to be wrong with this scheme.

Adjust the palette until those answers are yes, and report what you changed and
why.

```bash
git add lab/src/corpus
git commit -m "give the problem states pale fills and weighted borders"
```

---

### Task 21: Put the wall in its own labkit shell

The corpus wall gets labkit's **UI** — the shell, the theme, the loupe, the
panel primitives — and none of its **ontology**. It is its own lab, not an
instrument inside the existing one.

**Read `~/src/weasel/docs/handoffs/2026-08-30-labkit-consumer-asks.md` first.**
This repo already filed five asks against labkit, and one of them is a direct
warning about the pattern this task reaches for: labkit's README shows
`<LabShell><Workspace>…</Workspace></LabShell>` as the way to build a lab, and
following it *inside* a `<Lab>` lays the whole app out as one header item with
every trial rendered twice, because `<Lab>` owns its own shell.

The wall is standalone and wants no trials, so `LabShell` may well be right here
— but confirm that against the docs rather than against my say-so, and report
what you find. If `LabShell` alone turns out not to be a supported way to build a
non-trial app, say so and stop; that is a finding, not an obstacle to work
around.

**Use:** the interstellar theme and its `--wzl-*` tokens, the loupe, and
labkit's panel primitives, with whatever shell the docs actually sanction.

**Do not use:** `Lab`, `defineInstrument`, trials, snapshots, the job model, or
the CLI-derived config schema. The wall's Slot/Sort/Show are view state, not
render parameters, and they stay the wall's own controls — rendered in the
shell's header rather than a generated config panel.

Nothing in `lab/src/corpus/` may import from `lab/src/instruments/` or
`lab/src/panes/`; that rule does not change.

**Files:**
- Modify: `lab/src/corpus/main.tsx` (mount the shell around `<CorpusWall/>`)
- Modify: `lab/src/corpus/CorpusWall.tsx`, `corpus.css`, `FilterBar.css`,
  `PartCard.css`, `Lightbox.css`, `Wall.css`
- Modify: `lab/src/corpus/paint.ts`, `paint.test.ts`
- Create: `lab/src/corpus/palette.ts`, `palette.test.ts`

- [ ] **Step 1: Read the theme's colours instead of hardcoding them**

The six cell colours are **canvas fills**, so CSS cannot style them — they have
to be read at paint time or the wall keeps its own palette while everything
around it follows the theme.

Create `palette.ts`: a `readPalette(el: Element)` that pulls each cell state's
colour from a CSS custom property via `getComputedStyle`, with the current hex
values as fallbacks so a missing token degrades rather than paints nothing.
Declare the properties in `corpus.css` against the `--wzl-*` tokens where one
fits, and as literal values where none does.

Test it against a stubbed `getComputedStyle`: each state resolves from its
property, and a missing property falls back rather than yielding `""`.

Then have `paint.ts` take the palette as input rather than owning `CELL_FILL`,
and `Wall.tsx` read it once per theme change rather than per frame.

- [ ] **Step 2: Mount `LabShell` in `main.tsx`**

Read `LabShellProps` and `lab/src/App.tsx` for how the existing app parameterises
the shell — then take only the shell. The wall is full-bleed: it wants the whole
viewport under the header, so whatever the shell offers for a maximised content
region is what it uses.

Put `<FilterBar/>` in the shell's header slot beside the title, where
`PartSearch` sits in the existing lab.

- [ ] **Step 3: Restyle against the theme**

Replace the hardcoded colours in `corpus.css`, `FilterBar.css`, `PartCard.css`,
`Lightbox.css` and `Wall.css` with `--wzl-*` tokens. The lightbox's `#131316`
and the card's background are the obvious ones. No inline `style`, no
`!important` — the standing rules still hold.

- [ ] **Step 4: Add the loupe**

A wall of 5px cells is the case the loupe exists for: magnify a region without
disturbing the camera. Wire labkit's loupe over the canvas. Read
`lab/src/panes/useLoupe.ts` for how the existing lab drives it — **read it, do
not import it**; that file belongs to the lab.

- [ ] **Step 5: Run, look, commit**

`npx vitest run src/corpus` and `npx tsc -b --noEmit` clean.

Then look at it in both themes — that is the point of this task. Confirm the
cell colours change with the theme rather than staying fixed, the card and
lightbox follow it, and the loupe magnifies without moving the camera.
Screenshot both themes and the loupe, and slop them.

```bash
git add lab/src/corpus
git commit -m "give the corpus wall its own labkit shell, theme and loupe"
```

---

### Task 21b: A floating legend that highlights what it names

Six cell colours are six things to memorise. A legend makes them readable, and
hovering one should pick those cells out of the wall.

It comes after the labkit shell so it can be a `FloatingPanel` — the existing
lab already uses one for its defect list (see `lab/src/App.tsx`), including the
detail that `FloatingPanel` is a positioned box and nothing else, so its title
and dismissal are written as its first child.

**Files:**
- Create: `lab/src/corpus/Legend.tsx`, `Legend.test.tsx`, `Legend.css`
- Modify: `lab/src/corpus/paint.ts`, `paint.test.ts`
- Modify: `lab/src/corpus/CorpusWall.tsx`, `CorpusWall.test.tsx`

- [ ] **Step 1: Name the states once**

`paint.ts` currently decides a colour inside `fillFor`. Split out the state
itself — `cellState(cell)` returning the state name — so the legend and the
painter agree by construction rather than by two parallel tables. `fillFor`
becomes a lookup on that.

Test that every state `cellState` can return has an entry in `CELL_FILL`, so a
seventh state cannot be added without a colour.

- [ ] **Step 2: Count them**

The legend shows a count per state, which makes it a summary of the corpus and
not merely a key. Count from the cells already in hand — no request. A pure
`tally(cells)` returning a count per state, tested against a handful of cells.

- [ ] **Step 3: Dim what is not hovered**

Hovering a legend row highlights those cells. **Dim the others rather than
brightening the matches** — on a wall this dense, changing the matching cells'
colour destroys the thing the legend is teaching, while dropping everything else
back makes them pop and keeps their colour honest.

`paintCommands` takes a `highlight: CellState | null`; when set, cells of other
states get a dimmed fill and drawn cells a reduced alpha. Test that the
highlighted state's cells keep their exact colour and the rest do not.

- [ ] **Step 4: The panel**

`Legend.tsx` renders one row per state: swatch, name, count. Hovering a row
raises the highlight; leaving it clears. Rows are not buttons — they are hover
targets — but they must be reachable, so give each a `tabIndex` and raise the
highlight on focus too, which is the same behaviour for a keyboard.

Test: rows render with their counts; hovering reports the state; leaving reports
null; focusing does what hovering does.

- [ ] **Step 5: Run, drive it, commit**

`npx vitest run src/corpus` and `npx tsc -b --noEmit` clean.

In the browser: confirm the counts match what the wall shows, hover "timed out"
and confirm about 6% of the wall stays lit while the rest recedes, hover
"cannot be drawn" and confirm the eight cells are findable. Tab to a row and
confirm focus highlights the same way. Screenshot a highlight and slop it.

```bash
git add lab/src/corpus/Legend.tsx lab/src/corpus/Legend.test.tsx \
        lab/src/corpus/Legend.css lab/src/corpus/paint.ts \
        lab/src/corpus/paint.test.ts lab/src/corpus/CorpusWall.tsx \
        lab/src/corpus/CorpusWall.test.tsx
git commit -m "a floating legend that dims the wall around what it names"
```

---

### Task 20d: Spread the status hues around the wheel

The three signal colours sit inside a 38-degree wedge: `#e03030` is hue 0,
`#c86a42` is 18, `#e8a020` is 38. Red, orange and amber are the hardest triple
to tell apart at five pixels, and the one that collapses outright under the
common colour-vision deficiencies.

**The structure is right and stays:** hue means *what kind of problem*, border
weight means *here or in another slot*, and lightness stays reserved for "this
part has a render". Only the hue assignments change.

There are three signal hues to place. Spread them:

| state | border | hue |
|---|---|---|
| cannot be drawn here | `#e03030` | 0 — red keeps the hard-failure convention |
| timed out here | `#30b0d0` | 193 — cool reads as waiting, not broken |
| open defect here | `#c050e0` | 285 — distinct from both |

Fills stay dark and near-neutral, tinted toward their border's hue just enough to
group: roughly `#4a2626`, `#26383f`, `#3a2a42`. Unknown stays `#3a3a3f` with no
border.

**This moves the defect colour off the ochre that was originally asked for.**
Ochre sat 38 degrees from red, and those two states — eight hard failures and
eleven filed defects — are precisely the pair you most need to tell apart once
you have found them. Say so in the report; it is a deliberate trade and worth
being overruled on.

**Files:** `lab/src/corpus/palette.ts`, `palette.test.ts`, and the CSS custom
properties declaring them.

- [ ] **Step 1: Change the values, nothing else**

The palette pipeline already exists — `readPalette` resolves each state from a
CSS custom property with a fallback. This changes those values in one place.

Check `PartCard.css` and `Legend.css` for any swatch or accent that hardcodes one
of the old hues rather than reading the property.

- [ ] **Step 2: Look at it, and check the separation properly**

Screenshot zoomed fully out and answer from the image:

1. Are the ~1,260 timeouts, the eight failures and the eleven defects three
   visibly different populations, or do any two still merge?
2. Does the cyan read as a problem state rather than as decoration? Cool colours
   can look informational rather than wrong.
3. Do the thin "elsewhere" borders still read as quieter than the thick ones now
   that the hues carry more of the load?

Then check it under a colour-vision simulation. Chrome DevTools has
`Rendering → Emulate vision deficiencies` — run protanopia and deuteranopia and
confirm the three stay distinguishable. That is the failure this task exists to
fix, so verifying it by eye in normal vision only would miss the point.

Screenshot normal and one simulated deficiency, and slop both.

```bash
git add lab/src/corpus
git commit -m "spread the status hues so red, amber and orange stop colliding"
```

---

### Task 22: The caret

The wall is mouse-only. Give it a caret: an implied focus when there is no
explicit one, arrow keys to move it, `Enter` to raise the card.

**Files:**
- Create: `lab/src/corpus/caret.ts`, `caret.test.ts`
- Modify: `lab/src/corpus/paint.ts`, `paint.test.ts` (draw it)
- Modify: `lab/src/corpus/Wall.tsx`, `CorpusWall.tsx`, and their tests

- [ ] **Step 1: `caret.ts` — two pure functions, tests first**

`impliedCaret(rects, visible, cam, viewport)` returns the index of the cell
holding the most on-screen area, breaking ties by distance from the viewport
centre. Area is what separates a clipped edge cell from a whole one; zoomed out
every whole cell has identical area, so the tie-break is what actually picks.
Returns `null` for an empty visible set.

`adjacent(rects, from, direction)` returns the index of the nearest cell whose
centre lies in that direction (`'left' | 'right' | 'up' | 'down'`). **Geometric,
not `index ± 1`** — grid arithmetic works today and breaks the moment a grouped
layout inserts whitespace, which is the whole reason layout is a strategy.
Prefer a cell close to the same row or column: score by distance along the
direction plus a penalty for drifting across it, so pressing right from the end
of a row does not leap diagonally.

**When geometry finds nothing, left and right fall back to sequence order;
up and down return `null`.** Wrapping is an ordering idea, not a geometric one,
so it applies only where a single reading exists: off the end of a row, the next
cell in sequence is the only continuation anyone would mean. Off the bottom
there is none — stopping and moving to the next column are equally arguable, so
the caret stays put. The last cell of the array has nothing after it and the
first has nothing before it, so those still return `null`.

Tests to write: the implied caret prefers a whole cell over a clipped one;
prefers the centre among equals; is null when nothing is visible. `adjacent`
finds the neighbour in each of the four directions; picks the same-row neighbour
over a nearer diagonal one; **wraps from the end of a row to the start of the
next and back**; returns `null` going up from the top row, down from the bottom
row, right from the very last cell and left from the very first.

- [ ] **Step 2: Draw it**

Add a `caret` flag to the paint commands, set for the caret's index, and have
`Wall.tsx` stroke it distinctly from the ochre defect ring — the two can be on
the same cell. Test that exactly one command carries it and that a cell can
carry both.

- [ ] **Step 3: Keys**

The canvas takes `tabIndex={0}`. Arrow keys move the caret and make it explicit;
`Enter` raises the card for it; `Escape` drops back to the implied caret.
Arrowing to a cell that is off screen pans the camera to bring it in — reuse the
camera rather than adding a second notion of position.

Announce the caret's part through an `aria-live="polite"` region. A canvas
cannot expose 24,591 focusable children, so the canvas holds focus and the live
region carries the name — that is keyboard operability and a programmatically
determinable name without inventing DOM nodes for pixels.

- [ ] **Step 4: Run, drive it, commit**

`npx vitest run src/corpus` and `npx tsc -b --noEmit` clean.

In the browser: tab to the canvas, confirm a caret appears on a central cell,
arrow around and confirm it moves one cell at a time in the direction pressed,
arrow to the edge of the viewport and confirm the camera follows, press Enter
and confirm the card opens for the carated cell. Screenshot the caret and slop
it.

```bash
git add lab/src/corpus/caret.ts lab/src/corpus/caret.test.ts \
        lab/src/corpus/paint.ts lab/src/corpus/paint.test.ts \
        lab/src/corpus/Wall.tsx lab/src/corpus/CorpusWall.tsx \
        lab/src/corpus/CorpusWall.test.tsx
git commit -m "give the wall a caret, moved by the arrow keys"
```

---

### Task 22d: A "base parts only" filter

Most of the wall is not a part anyone is trying to render. Of 24,591 cells:
13,083 are printed, 4,046 obsolete, 2,152 composites, 1,931 stickers, 878
unofficial. **6,891 are base parts** — and 175 of the 200 census renders are
among them, so the filter takes the wall from 0.8% drawn to 2.5% drawn.

`FILTERS` in `lab/src/corpus/select.ts` already has `printed` and `obsolete`,
which *show* only those. This adds `base`, which hides all of them at once.

**The classification lives in `cells.py`, as one `base` boolean.** Do not
re-derive it in TypeScript from id shapes: the id-shape knowledge belongs beside
the seeding logic and the repo's own guidance on part numbering, not in two
places that can disagree.

`base` is true when a part is none of:

- **printed** — `parts.printed`, already stored. Set from the description line,
  which the repo's CLAUDE.md is emphatic about: `^\d{3,}p\d+$` catches only
  3,254 of 13,081, a plain letter suffix is ambiguous, and 132 bare-numeric ids
  are patterned. **Use the column; never pattern-match the id for this.**
- **obsolete** — `parts.obsolete`, already stored, set from a `~` or `_` title.
- **composite** — id matching `%c__`, 2,152 of them.
- **sticker** — id matching `%d__`, 1,931.
- **unofficial** — id matching `u9*`, 878.

**Mould variants like `3068b` stay in.** A plain letter suffix is ambiguous per
the same guidance, and excluding on it would drop real base parts.

**Files:**
- Modify: `brick_icons/lab/cells.py`, `tests/test_lab_cells.py`
- Modify: `lab/src/corpus/types.ts`, `select.ts`, `select.test.ts`

- [ ] **Step 1: `base` on the cell**

Add the field, computed in SQL alongside the existing per-cell query rather than
in a second pass. Tests: a plain part is base; a printed one is not; an obsolete
one is not; `1234c01`, `1234d01` and `u9123` are not; `3068b` **is**.

- [ ] **Step 2: The filter**

Add `base` to `FILTERS` and `KEEP` in `select.ts`. Test that it keeps only base
cells and that the existing filters are unchanged.

- [ ] **Step 3: Check the real numbers**

Restart the backend so the new `cells.py` is live, then select `base` and
confirm the count reads **6,891 of 24,591**, and that the drawn cells drop to
around 175 rather than 200. If either number is off, the classification
disagrees with the database and that is worth reporting rather than adjusting
the expectation.

Screenshot the filtered wall and slop it — a wall at 2.5% coverage should look
materially less empty than the full one.

```bash
git add brick_icons/lab/cells.py tests/test_lab_cells.py lab/src/corpus
git commit -m "a base-parts filter, hiding printed, obsolete and variant parts"
```

---

### Task 22c: A params panel

Every tuning constant in the wall is a literal in a source file, and the palette
alone has taken four rounds of hand-editing hex and reloading. A panel turns
that into seconds.

**Use labkit's `ControlPanel`.** It takes a `ConfigField[]` and a config object —
it is not coupled to `defineInstrument`, and it builds on `@weasel-js/ui`'s rows
including `ColorRow`, `SliderRow`, `NumberRow` and `SelectRow`. Same call as
`LabShell`: take the widget, define the wall's own schema. **Do not** reach for
the CLI-derived schema; these are view parameters, not render flags.

**The palette needs no new plumbing.** `readPalette` already resolves each state
from a CSS custom property, and `Wall.tsx` already re-reads on a mutation. So a
colour row writes `--corpus-cell-<state>-<fill|border>` on the root element and
the wall follows. Wiring colours through React state instead would fork that
pipeline — do not.

**Files:**
- Create: `lab/src/corpus/params.ts`, `params.test.ts`, `ParamsPanel.tsx`,
  `ParamsPanel.test.tsx`
- Modify: `lab/src/corpus/CorpusWall.tsx`, `paint.ts`, `Wall.tsx`, `levels.ts`,
  and the modules holding the constants below

- [ ] **Step 1: Gather the constants that earn a knob**

These exist today as literals. Group them:

*Layout* — `CELL` 32 and `GAP` 4 (`CorpusWall.tsx`), and the column count,
currently `ceil(sqrt(n))` with no way to override.

*Appearance* — the twelve palette values (six states x fill/border);
`THICK_BORDER_FACTOR` 0.18, `THIN_BORDER_FACTOR` 0.09, `MAX_BORDER_PX` 6 and
`DIM_ALPHA` 0.25 (`paint.ts`).

*Feel* — `DRAG_THRESHOLD_PX` 4 (`Wall.tsx`) and the 1.5 / 0.67 hysteresis
factors (`levels.ts`), which are currently inline numbers rather than named
constants.

Leave out and say why in the report: `PartCard`'s geometry, `caret.ts`'s
`CROSS_PENALTY`, and `MAX_IN_FLIGHT` — all things nobody tunes by eye. Include
`POLL_MS` only if it is cheap; it is useful for exercising the trickle-in path.

- [ ] **Step 2: `params.ts` — the schema and its defaults**

A `ConfigField[]` describing the above, with the current literals as defaults, and
a `Params` type. Every constant it replaces must import its default **from here**,
so there is one source of truth rather than a literal and a schema that drift.

Test that every field has a default and that the defaults match the values the
code used before this task — a param panel that silently changes the wall's
appearance on first load is worse than no panel.

- [ ] **Step 3: Persist and reset**

Params survive a reload (`localStorage`), and the panel has a reset that restores
defaults. Test both.

- [ ] **Step 4: The panel**

`ParamsPanel.tsx` renders `ControlPanel` in a `FloatingPanel`, as `Legend` does.
Colour rows write CSS custom properties on the root; everything else feeds the
wall through props.

- [ ] **Step 5: Run, drive it, commit**

`npx vitest run src/corpus` and `npx tsc -b --noEmit` clean.

In the browser: change a cell colour and confirm the wall repaints without a
reload; change `CELL` and confirm the grid re-flows and the level ladder still
picks sensibly; reload and confirm the changes survived; reset and confirm the
wall returns to what it looks like today. Screenshot the panel and slop it.

```bash
git add lab/src/corpus
git commit -m "a params panel for the wall's own tuning constants"
```

---

### Task 22b: A search box that goes to the part

The wall needs the lab's part search. It is nearly shareable already — `client`
and `onOpen` are both injected — so this promotes it rather than copying it.

**One coupling to lift.** `PartSearch` calls `setPendingPart` from
`@lab/config/pending`: a module-level one-slot box that exists because labkit's
`addTrial` takes only an instrument name and has nowhere to put the subject.
That is the first entry in `~/src/weasel/docs/handoffs/2026-08-30-labkit-consumer-asks.md`,
filed by this repo. The wall has no trials, so the call is dead weight for it —
and the component should not carry a workaround for a gap it has nothing to do
with. Move that line into the lab's own `onOpen` handler.

**Files:**
- Move: `lab/src/chrome/PartSearch.tsx` and `.test.tsx` → `lab/src/shared/`
- Modify: `lab/src/App.tsx` (import from the new home; call `setPendingPart` in
  its `onOpen`)
- Modify: `lab/src/corpus/CorpusWall.tsx`, `CorpusWall.test.tsx`
- Modify: `lab/src/corpus/corpus.css` or the shell's stylesheet as needed

- [ ] **Step 1: Promote it, unchanged except for the coupling**

Move the component and its test to `lab/src/shared/`, delete the `setPendingPart`
import and call, and put that call in `App.tsx`'s `onOpen` so the lab behaves
exactly as before. Its existing tests must pass unmodified except for the import
path — **a test that needs its assertions changed means the move altered
behaviour, which is a finding.**

- [ ] **Step 2: Point it at the wall**

`CorpusWall` renders `<PartSearch/>` in the header beside the filter bar. Its
`onOpen(partId)`:

- finds that part's index in the currently shown cells
- moves the camera so the cell is centred, using core's view animation rather
  than jumping — `interpolateView`/`useViewAnimation` exist for this
- sets the caret to it
- raises its card

**The part may not be on the wall.** `/api/parts` searches the whole LDraw
index, so a hit can be filtered out by the current `Show`, or absent from the
slot. Say so rather than silently doing nothing or jumping to a cell that is not
drawn — "3001 is hidden by the current filter" is the useful answer. Test both
the found and the filtered-out cases.

- [ ] **Step 3: Run, drive it, commit**

`npx vitest run src` — the lab's own tests too this time, since `App.tsx` and a
moved component are in scope.
`npx tsc -b --noEmit` clean.

In the browser: search a part id, confirm the camera glides to it, the caret
lands on it and its card opens. Search something filtered out and confirm it
says so. Confirm the lab at `/` still opens a part into a trial exactly as
before — that is the regression this move risks. Screenshot and slop it.

```bash
git add lab/src/shared lab/src/chrome lab/src/App.tsx lab/src/corpus
git commit -m "share the part search, and let it fly the wall to a part"
```

---

### Task 19: The full gate

Only now, and only once.

- [ ] **Step 1: Run the Python suite**

Run: `.venv/bin/python -m pytest`
Expected: PASS. If something outside `tests/test_thumbs.py`,
`tests/test_lab_cells.py`, `tests/test_lab_app.py` or
`tests/test_index_census.py` fails, check whether another suite is running on
the box before treating it as a regression.

- [ ] **Step 2: Run the lab suite**

Run: `cd lab && npm test`
Expected: PASS, including every pre-existing lab test.

- [ ] **Step 3: Build both entries**

Run: `cd lab && npm run build`
Expected: `dist/index.html` and `dist/corpus.html` both emitted.

- [ ] **Step 4: Commit anything the gate turned up**

```bash
git commit -am "fix what the full suite caught"
```
