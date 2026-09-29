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

Or hand both to launchd, which keeps them up and restarts the API when
`brick_icons/` changes:

    scripts/lab-agents.sh install     # from the main checkout, once
    brick-lab stat | up | down | cycle | log

`perch install` adds the menu bar item that drives the same verbs, from
`menubar.yaml`. Logs are in `~/.local/state/brick-icons/` and are emptied on
every `up`, `cycle` and `install`. A lab started by hand on 8792 or 5178 is
stopped by `install`; a worktree that wants its own lab still starts one by
hand on another port.

**The lab must not fork the CLI.** It derives its config schema from
`cli.build_parser()` and renders through `_config_from_args` + `process_one`. A
parameter the lab knows and the CLI does not is a bug by construction, and
`tests/test_lab_schema.py` fails on it.

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

The cloned `.venv` still imports `brick_icons` from the `brick-icons` tree
until a `uv sync` in `brick-icons-spot` repoints its editable install;
`scripts/spot-worker.sh` does that on every start, so run the worker only
through it.

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
