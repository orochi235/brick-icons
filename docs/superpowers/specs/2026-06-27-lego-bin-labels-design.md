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

## Decisions made

- **Python, not Node** — image-processing-centric; Pillow already present.
- **New sibling repo**, not a subdirectory of `lbx-editor` — decoupled batch tool.

## Out of scope

- LBX file assembly / printing (handled by the user's separate stack).
- Fetching part images from the web; rendering is always local from LDraw.
- A GUI; this is a CLI batch tool.
