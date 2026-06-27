# lego-bin-labels — design

**Date:** 2026-06-27
**Status:** Approved (design); pending implementation plan

## Purpose

Generate small monochrome bitmaps of LEGO parts for printing bin labels on a
Brother P-touch (LBX) printer. Each part is rendered from the LDraw parts
library, normalized to grayscale, and emitted either as a 1-bit dithered bitmap
sized for the label or as a higher-resolution grayscale image that the Brother
driver scales and dithers itself. The downstream LBX assembly/printing stack is
handled separately; this tool produces the image assets it consumes.

## Form

Standalone Python CLI in its own repo at `~/src/lego-bin-labels`. Python because
the work is overwhelmingly image processing and Pillow (already installed,
v11.3.0) gives the cleanest control over dithering. Decoupled from `lbx-editor`
(a TS/React app) because this is a batch-oriented asset generator, not editor UI.
Add a one-line entry to `~/src/PROJECTS.md` once it exists.

Existing local tooling to lean on: Pillow 11.3, ImageMagick (`magick`/`convert`),
Node 26 (not used here). No LDraw renderer or parts library is installed yet —
both are setup prerequisites (see Setup).

## Pipeline (per part)

1. **Resolve** — input is one of:
   - a part id (e.g. `3001`),
   - a path to a `.dat`/`.ldr` file, or
   - a batch list file: one part per line, with optional `color` and
     `output-name` columns.

   A part id resolves to `<ldraw-lib>/parts/<id>.dat`.

2. **Render** (LDView, headless `-SaveSnapshot`) — render at high resolution
   (supersampled for clean downscaling), edge lines on, a neutral part color on
   a white background, auto-framed to the part. Output: a high-resolution
   anti-aliased PNG.

3. **Normalize** (Pillow) — autocrop to the part bounds, add a configurable
   margin, desaturate to grayscale (`L`), apply optional contrast/levels.

4. **Output** (customizable — the experimentation surface):
   - `--mode gray` → emit the high-resolution **grayscale** PNG; the Brother
     driver does the scaling and dithering.
   - `--mode mono` → **dither to 1-bit** at the target pixel size; emit a 1-bit
     PNG (and optionally a BMP).
   - `--mode both` → emit both.

## Rendering parameters

The render stage exposes camera and shading controls (LDView flags), so the same
part can be shot the way that reads best on a tiny label:

- **`--angle`** — viewing angle, mapped to LDView `-DefaultLatLong=LAT,LONG`:
  - `iso` (**default**, 45° isometric: lat 30, long 45)
  - `front` (0,0), `back` (0,180), `left` (0,-90), `right` (0,90),
    `top` (90,0), `bottom` (-90,0)
  - or an explicit `LAT,LONG` pair for anything else.
- **`--shading`** — `normal` (lit 3D, default), `flat` (`-Lighting=0`, even fill
  — pairs well with `threshold` for clean line art), `subdued`
  (`-SubduedLighting=1`, softer for dithering).
- **`--scale`** — how much of the label's view area the part fills, `0`–`1`
  (default `1.0`). Applied in Pillow during the fit step (the render is always
  auto-cropped first), so it composes with `--margin`. `0.8` leaves extra
  breathing room around the part.

## Sizing

Target pixel dimensions come from either:
- explicit `--width` / `--height` in pixels, or
- `--label-mm` + `--dpi`, computing pixels from physical label size. P-touch
  printers are typically 180 or 360 dpi; default `--dpi 180`.

## Dithering (mono mode)

`--dither floyd|atkinson|ordered|threshold`. Atkinson tends to look best on
small 3D renders and is hand-rolled (Pillow lacks it); Floyd–Steinberg uses
Pillow's `convert('1')`; ordered (Bayer) and plain threshold are implemented
directly. Additional knobs: `--threshold`, `--part-color`, `--bg`, `--margin`,
`--angle` (camera latitude/longitude).

## Batch & debugging

- Multiple parts (CLI args or a list file) → one output file each in an output
  directory.
- `--debug-dir <dir>` saves every intermediate stage in its own subfolder
  (`render/`, `cropped/`, `gray/`, `mono/`) so the divergence between
  tool-side dithering and driver-side scaling can be eyeballed directly. This
  serves the primary "try both approaches" goal.

## Modules

- `render.py` — LDView invocation and snapshot handling.
- `process.py` — crop, grayscale, resize, dither algorithms.
- `cli.py` — argparse, batch handling, output modes.
- `labels.toml` — default config values, overridable by flags.

Each module has one clear responsibility and a small interface: `render.py`
turns a part file into a hi-res PNG, `process.py` turns a PNG into the requested
output image(s), `cli.py` wires inputs to outputs.

## Setup (prerequisites, validated as the first implementation task)

1. Install LDView: `brew install --cask ldview` if available, otherwise the
   SourceForge build.
2. Install the LDraw parts library: `complete.zip` from ldraw.org, unpacked to
   `~/ldraw` (configurable).

**Primary risk:** LDView headless snapshotting on macOS. The first
implementation task is a focused smoke test confirming `-SaveSnapshot` writes a
file from the command line without stealing window focus (per the user's
foreground-focus preference). If LDView cannot run cleanly headless, fall back
to LeoCAD's CLI image export before building the rest of the pipeline.

## Smoke-test results (2026-06-27 — VALIDATED)

The risky assumption was tested up front and the full chain works end-to-end:

- **LDView distribution:** not in Homebrew. Latest macOS build is
  `LDView_4.2.1_Universal.dmg` from SourceForge
  (`/projects/ldview/files/01.%20LDView/LDView%204.2/`). "Universal" means
  **i386 + x86_64 only — no arm64 slice.** On Apple Silicon it runs via
  **Rosetta 2** (`arch -x86_64 LDView.app/Contents/MacOS/LDView ...`), which is
  already installed on this machine. Strip quarantine (`xattr -dr
  com.apple.quarantine LDView.app`) before first run to avoid a Gatekeeper
  dialog.
- **Headless render confirmed:** `-SaveSnapshot=out.png -SaveWidth=W
  -SaveHeight=H -AutoCrop=1 -SaveAlpha=1 -EdgeLines=1` produced a correct,
  auto-cropped, anti-aliased RGBA render of part 3001 with no blocking dialog,
  no hang, clean stderr. Focus-steal was not observed (confirm on a real run).
- **LDraw library:** `complete.zip` (~140 MB) from
  `library.ldraw.org/library/updates/complete.zip` unpacks to a `ldraw/`
  tree; `-LDrawDir=<...>/ldraw` resolves `parts/3001.dat` etc.
- **Background:** render with `-SaveAlpha=1` (transparent) and flatten onto
  white in Pillow — gives full control instead of LDView's default gray bg.
- **Dither stage validated:** threshold / Floyd–Steinberg / ordered (Bayer) /
  Atkinson all implemented and run against the render at a 256×170 label size.

**Tuning need surfaced by the test (feeds the experimentation knobs):** with
LDView's default lighting the part renders mid-gray, so naive threshold collapses
the silhouette and the dithers come out dark/dense. The pipeline should expose
**levels/contrast** and **lighting** controls, and likely composite **solid
black edge lines over a lightened, dithered interior** for legible small labels.
This is the first thing to dial in during implementation.

## Decisions made

- **Python, not Node** — image-processing-centric; Pillow already present.
- **New sibling repo**, not a subdirectory of `lbx-editor` — decoupled batch tool.

## Out of scope

- LBX file assembly / printing (handled by the user's separate stack).
- Fetching part images from the web; rendering is always local from LDraw.
- A GUI; this is a CLI batch tool.
