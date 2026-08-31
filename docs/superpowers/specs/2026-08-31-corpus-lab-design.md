# Corpus Lab — design

A local web app for inspecting brick-icons renders and tracking corpus defects.
For whoever implements it: you know brick-icons, you have not used labkit.

Today, comparing two engines on a part means typing two CLI invocations and
opening two files, and a defect found by eye becomes a paragraph in
`HANDOFF.md` that nothing can query, count, or re-check. The lab replaces both:
renders sit side by side at a shared zoom, and a defect is a box you drag on the
render, stored as data.

## What labkit gives us

`@weasel-js/labkit` (npm, 1.3.0, alongside the other `@weasel-js/*` packages at
the same version) is a React toolkit for lab pages. Its vocabulary:

- an **instrument** is one kind of experiment, declared once with
  `defineInstrument({ config, initialState, render, ... })`;
- a **trial** is one running instance of an instrument, with its own config,
  state, and view (pan/zoom or orbit — labkit persists the view opaquely);
- the **workspace** is the grid of open trials;
- **capabilities** an instrument declares — `job`, `layers`, `canvas`, `undo` —
  make the trial provide the matching chrome without further wiring.

This app is one lab with two instruments: **Part Inspector** and **Contact
Sheet**.

## The constraint everything else answers to

The app must never drift from the CLI. So it does not define a parameter set:

1. `cli.py` splits `_parse_args` into `build_parser()` and `_parse_args(argv)`,
   which calls it. No behavior change.
2. `GET /api/schema` introspects that parser — each option's `dest`, type,
   `choices` and `help` — and emits a labkit `ConfigSchema`. Adding a CLI flag
   puts a control in the panel with no frontend change.
3. A trial's config **is** argv. The trial chrome always shows the command,
   click-to-copy: `brick-icons 3941 --engine occt --shading outline
   --shade-style flat3 --angle 30,25`.
4. The server runs that argv through `build_parser().parse_args(argv)` →
   `_config_from_args` → `process_one`, in-process. Same path as the CLI.

Two tests hold it: every parser option appears in the emitted schema, and
argv → `Config` round-trips to what the CLI produces for a sample command.

## Server — `brick_icons/lab/`

FastAPI + uvicorn, behind a `lab` optional-dependency extra. Started with
`python -m brick_icons.lab`; it serves the API and, when built, the frontend.
In development, Vite serves the frontend and proxies `/api` and `/ldraw`.

| route | does |
|---|---|
| `GET /api/schema` | argparse-derived config schema |
| `GET /api/lists` | `parts.txt`, `specimens.txt`, `manifest.toml` combos, `decal-corpus.txt` |
| `GET /api/parts?q=` | search all 24,591 library files by id and description line |
| `POST /api/render` | `{argv}` → job id |
| `GET /api/jobs/{id}` | SSE: progress, then artifacts |
| `GET /api/artifact/{key}` | cached output, keyed by sha of argv, under `out/lab/` |
| `GET /api/reference` | LDView PNG via `render.render_part` at a lat/long |
| `GET /api/diff` | raster diff of two artifacts |
| `GET`/`POST`/`PATCH` `/api/defects` | `tests/goldens/defects.toml` |
| `GET /api/goldens` | frozen hash vs. fresh hash, per part |
| `POST /api/batch` | render a whole list as one job |
| `/ldraw/*` | static mount of `vendor/ldraw` |

The part index (id → description line) is built once at startup and cached.

`/api/diff` reports **connected-component count**, not a pixel count. Antialias
fringe scatters into hundreds of tiny components and a real defect is a handful
of chunky ones, so a pixel total cannot tell the two apart.

Every job emits one progress line per item, with position when the work list is
known up front.

## Part Inspector

**Config** is the argv schema, plus two fields the CLI has no equivalent for:

- `sources` — which of `naive`, `occt`, `reference`, `3d`, `diff` are on;
- `layout` — `split` (panes side by side) or `stack` (one pane, sources drawn
  over each other and toggled).

Both layouts show the same enabled sources; the toggle changes only whether
they sit beside each other or on top of each other. Pan and zoom are shared
across panes either way, so a difference lands in the same place on screen.

**State** holds, per source, the artifact URL, the render duration and the op
counts, plus that part's defect marks.

**Capabilities:** `job` (render progress and cancel in the chrome, free) and
`layers` (the source toggles). The view holds pan/zoom for the 2D panes and the
orbit for the 3D one.

**`render(ctx)`** returns the panes as DOM under one shared transform:

- engine output as **inline SVG**. The SVG is the artifact under test;
  displaying a raster of it would mean inspecting a proxy, and it stays sharp
  at any zoom.
- reference and diff as `<img>`.
- the 3D pane as a three.js canvas.

Pan and zoom drive a CSS transform through labkit's surface hooks
(`@weasel-js/labkit/surface`), which exist for exactly this — driving a
renderer labkit does not own. `CanvasStack` is not used.

Two things the panes must say out loud, because otherwise they read as defects:

- `occt` returns no faces, so every filled mode degrades to an outline. The
  pane labels that rather than looking broken.
- The 3D pane is `LDrawLoader`'s parse — neither the engine's geometry nor
  LDView's renderer.

### The 3D pane

three.js `LDrawLoader` with `@react-three/fiber` and `drei`'s OrbitControls,
loading the `.dat` from `/ldraw/*`. The orbit lives in the trial view via
`useOrbit`. Orbiting sets `--angle` for every other pane; when the orbit
settles, the reference source re-renders through LDView at that exact lat/long.

Panes are **sources** behind one interface — id, label, how to fetch, how to
draw — so a second 3D implementation drops in beside this one rather than
replacing it. See Deferred.

## Contact Sheet

A second instrument. Config is a corpus list plus the same argv schema; it runs
`POST /api/batch` as a job and grids every part in the list at those
parameters. Clicking a cell opens a Part Inspector trial for that part with the
same argv. This replaces `scripts/render-contact-sheet.sh`; cells carry the
part id, as that script's `--part-label` already does.

## Defects

Drag a box over any pane, give it a title and a status, and it is written to
`tests/goldens/defects.toml` — git-tracked, beside `manifest.toml`, and part
ids stay out of `brick_icons/`.

```toml
[[defect]]
id = "3941-occt-borehole"
part = "3941"
engines = ["occt"]
status = "open"        # open | fixed | wontfix | notabug
title = "borehole rim not drawn"
mark = { x = 0.42, y = 0.55, w = 0.11, h = 0.09 }   # fractions of the render box
seen = { angle = "30,25", shading = "outline", shade_style = "flat3" }
filed = 2026-08-31
notes = """…"""
```

`mark` is fractional so it survives a change of `--render-px`. It does **not**
survive a change of `--angle`, which is why `seen` records the parameters the
defect was found at; a mark viewed at other parameters is drawn dimmed.

A lab-level panel lists every defect, filters by status, engine and part, and
opens the part's trial with the mark selected.

`scripts/defects-to-handoff.py` regenerates `HANDOFF.md`'s defect list from the
TOML, so the two cannot disagree.

## Golden status

`GET /api/goldens` compares each part's frozen hashes in
`tests/goldens/hashes.txt` against a fresh render, and the trial's status bar
says `goldens: match` or `goldens: 2 moved`.

## Title-bar search

A field in the workspace title bar: type a part id, press Enter, get a new
trial for that part. Typeahead runs against `/api/parts`, which searches
description lines too, so `slope 45` finds parts by name.

labkit's `addTrial(instrumentName)` takes no initial config. **Upstream ask:
`addTrial(name, { config })`.** Until it lands, the app adds the trial and then
sets its config; the first render is gated on a non-empty part id so the
default-config trial never renders anything.

## Layout

```
lab/                    Vite + React + TS frontend
  src/instruments/      partInspector, contactSheet
  src/sources/          one module per pane source
  src/api/              typed client over /api
brick_icons/lab/        FastAPI server
tests/goldens/defects.toml
scripts/defects-to-handoff.py
```

## Testing

Server, under pytest: the schema covers every parser option; argv → `Config`
round-trips against the CLI; defects round-trip through TOML without losing
fields; the artifact cache key is stable across equivalent argv orderings.

Frontend, under vitest: the config ↔ argv builder, which is where divergence
would appear, and the mark coordinate math. No browser tests in v1.

## Deferred

**An engine-mesh 3D source.** `hlr.flatten` already yields triangles, type-2
edges, type-5 conditional lines and analytic surfaces, and
`scripts/export-mesh.py` already dumps the repaired mesh. Serving that and
drawing it with bare three.js would show what no LDraw viewer can, because it
is the engine's own input: unpaired edges, type-2 against type-5, BFC winding,
which faces `occt` found an exact surface for against which fell back to
facets, and raw against repaired. It arrives as another source, not a rewrite.

**Corpus membership editing.** Curating which parts sit in which list is a
separate job from inspection; the lab reads the lists and does not write them.

## Risks

`3649` (40-tooth gear) renders slowly enough that the job's cancel control is
load-bearing rather than decorative.
