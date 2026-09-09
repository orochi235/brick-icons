# Developing brick-icons

For someone changing the code. `README.md` is the other half — what the tool
does and every CLI flag — and this does not repeat it. The engine's design
rules (why a rule may only ask what LDraw *declared*, why a dihedral angle
across tessellation is never evidence) live in `CLAUDE.md`; read that before
touching `hlr.py`, `occt.py` or `shade.py`.

## The pipeline

A part id becomes an icon in five stages:

1. **Load** — `library.py` resolves the id to a `.dat` under `vendor/ldraw`,
   `hlr.flatten` walks its subfile references into one flat soup of triangles,
   lines, conditional lines and primitive references.
2. **Repair** — `repair.py` fixes what the library gets wrong: winding, welds.
   Library geometry is cracked and inconsistently wound as a matter of course.
3. **Hidden-line removal** — `hlr.py` (the `naive` z-buffer reference) or
   `occt.py` (OpenCASCADE, the one under active work) returns visible segments,
   fill faces and exact-surface occluders. `primitives.py` substitutes analytic
   cylinders, discs and cones for their tessellations so curves stay curves.
4. **Shade and fill** — `shade.py` turns faces into painted regions: paint
   order, gradients, fill merging, residue trimming. `arcfit.py` recovers true
   arcs from hand-faceted rounds; `geom2d.py` is the GEOS layer underneath.
5. **Trace** — `trace.py` writes the SVG. `process.py` handles the raster
   modes.

Projection is orthographic throughout: `hlr.project` is three dot products,
with no perspective divide anywhere.

## Two render paths, and they are not the same renderer

`cli.process_one` forks on `--shading`, and this catches people out:

- **`--shading outline`** (and `--wireframe`) is *our* engine — orthographic,
  shading synthesized from face normals against `--light`.
- **`--shading cel` / `normal` and `--mode color`** shell out to the vendored
  **LDView**, which renders in *perspective*, and derive the vector and the
  tones from that raster. `--ldview` does the same and returns the raw render.

So `--engine occt --shading normal` never reaches the occt engine. When
comparing engines, or judging shading, pass `--shading outline` or you are
measuring LDView against itself.

## Layout

| path | what |
|---|---|
| `brick_icons/` | the library and CLI |
| `brick_icons/lab/` | the lab's HTTP API (FastAPI) |
| `lab/` | the lab's React front end (Vite) |
| `scripts/` | census, fleet, goldens, probes, one-off measurements |
| `tests/` | 49 files, pytest |
| `vendor/ldraw`, `vendor/LDView.app` | the library and the reference renderer |
| `out/` | renders, census results, thumbnails — all untracked |

`shade.py`, `occt.py` and `hlr.py` are the big three (109k, 67k and 59k). Most
engine work lands in one of them.

## The lab

Two processes. The API reads `corpus.db` and drives renders:

    .venv/bin/python -m brick_icons.lab --port 8792

The front end proxies `/api` and `/ldraw` to it:

    cd lab && npm run dev          # :5178

**The lab must not fork the CLI.** It derives its config schema from
`cli.build_parser()` and renders through `_config_from_args` + `process_one`. A
parameter the lab knows and the CLI does not is a bug by construction, and
`tests/test_lab_schema.py` fails on it.

## The corpus database

`corpus.db` holds `parts`, `renders` (one row per part per source slot),
`measurements` (census results) and `attempts` (one row per part a render-store
run tried, drawn or not — the only record of a part that timed out, since it
leaves neither a render nor a measurement). Source slots are `db.SOURCES`.

Adding to it rarely needs a rebuild: `connect()` creates a new table and
ALTERs in a declared column on every open, `scripts/index-slot-renders.py`
indexes a slot's renders where they lie, and `scripts/index-store-attempts.py`
takes up the store's logs — all against a live database. `scripts/snap-corpus.sh`
clones it with `VACUUM INTO` in about a second.

Rebuild it — from scratch, when the file is lost or the schema changes shape —
into a temp file and swap, never in place, because a running lab server reads
it on every request:

    tmp=corpus.db.ingest.$$
    .venv/bin/python scripts/build-corpus-db.py --out "$tmp"
    sqlite3 "$tmp" "PRAGMA wal_checkpoint(TRUNCATE);"
    rm -f corpus.db-wal corpus.db-shm && mv -f "$tmp" corpus.db
    .venv/bin/python scripts/bake-thumbs.py      # the wall's sprite sheets

## The census

A library-scale sweep that renders every part and scores its silhouette against
the part's own polygons — `scripts/compare-silhouette-truth.py` answers "is
this outline real geometry or something the pipeline invented", which looking
at a render cannot. `scripts/census-coverage.py` says what each engine still
owes.

It runs on the fleet through `onto`; see `CLAUDE.md` for the launch form and
the traps. Long jobs go through `onto` even on this Mac.

A node that has never run this repo needs `scripts/provision-node.sh <node>`
first -- uv, the pinned Python, the extras, `resvg`, `potrace`, and the parts
library, which is copied off this checkout rather than downloaded because
complete.zip only ever serves the latest snapshot. A node missing its `.venv`
fails every item in about a second, which reads like the machine refusing the
work.

## Gates

    .venv/bin/python -m pytest tests/test_hlr.py tests/test_occt.py    # engine
    BRICK_GOLDENS=1 .venv/bin/python -m pytest tests/test_goldens.py   # renders

**The goldens gate is an SVG byte diff.** A change that reorders elements
without moving a pixel still fails it, so read a failure as "the output moved",
not "the output broke" — render before and after and look. Re-freezing with
`scripts/freeze-goldens.py` is a deliberate act, not a way to make a red test
green. `BRICK_GOLDENS=1` runs a one-part subset; `=full` runs everything.

Goldens only cover the `iso` pose. A green run says nothing about other angles.

## Traps

**A worktree imports the main tree.** `python scripts/x.py` or
`python -m brick_icons.cli` inside a worktree silently resolves `brick_icons`
from the main checkout, so you measure code you did not change. Always
`PYTHONPATH=$PWD ./.venv/bin/python ...`, and check that a before/after
actually differs before believing it does not.

**Rasterize SVG with `resvg`, not ImageMagick** — `magick` turns shaded SVGs
into black blobs that read as an engine bug.

**A silent `[]` from `occt_faces` is not "unrepresentable".** It returns `[]`
both for "no exact surface exists" and "my tolerance was too tight". Remove the
`except` and look before believing it.

**Stickers and printed parts are in the engine loop, and naive is the one that
still fails them.** occt draws 2,695 of the 2,701 stickers and errors on 397 of
12,429 printed parts; naive errors on 117 stickers. So a sticker that fails
under naive is the known fault, not a finding — reproduce it under occt before
chasing it.
