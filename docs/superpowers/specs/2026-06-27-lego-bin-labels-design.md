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

2. **Render** (LDView, headless `-SaveSnapshot`) — render at **2048px**
   supersample, **max curve fidelity** (`-CurveQuality=12 -HiResPrimitives=1
   -AllowPrimitiveSubstitution=1` → 48-segment primitives, re-tessellated),
   **contrast lighting** (`-Lighting=1 -UseQualityLighting=1
   -LightVector=-1,1,2`), edge lines on, transparent background. Output: a
   high-resolution anti-aliased **RGBA** PNG (alpha preserved for silhouette
   extraction and flatten-on-white).

3. **Normalize / style** (Pillow) — flatten onto white, then apply the chosen
   **shading** (see Rendering parameters), optional levels/gamma, autocrop is
   already done by LDView, then fit to the label with margin and scale.

4. **Output** — two orthogonal axes: **format** (`--format png|svg|both`) and,
   for PNG, **mode** (`--mode gray|mono|color|both`):
   - PNG `gray` → high-resolution **grayscale** (or styled) PNG; the Brother
     driver does the scaling and dithering.
   - PNG `mono` → **dither to 1-bit** at the target pixel size; 1-bit PNG.
   - PNG `color` → high-resolution **RGB** render flattened on white, no
     dithering (preview only — the printer itself is 1-bit).
   - PNG `both` → gray + mono.
   - **SVG** → vector output via potrace; requires `--shading outline` or `cel`
     (continuous-tone `normal` has nothing clean to vectorize). See SVG output.

## Rendering parameters

The render stage exposes camera, fidelity, shading, and color controls so the
same part can be shot the way that reads best on a tiny label:

- **`--angle`** — viewing angle, mapped to LDView `-DefaultLatLong=LAT,LONG`:
  - `iso` (**default**, 45° isometric: lat 30, long 45)
  - `front` (0,0), `back` (0,180), `left` (0,-90), `right` (0,90),
    `top` (90,0), `bottom` (-90,0)
  - or an explicit `LAT,LONG` pair for anything else.
- **`--shading`** — how the part's tone is produced (validated against real
  renders, see Smoke-test results):
  - `normal` (**default**) — lit grayscale with the contrast lighting above.
  - `cel` — the lit grayscale **posterized** to `--cel-levels` flat bands
    (default 4); crisp, reads cleanly when dithered.
  - `outline` — **line art** derived in Pillow: the part's silhouette contour
    (from the alpha channel) plus, by default, interior structural edges
    (`--outline-interior/--no-outline-interior`). Black lines on white.
- **`--part-color`** — recolor the part via LDView `-DefaultColor3=0xRRGGBB`
  (hex). Affects the gray tone after desaturation; mainly visible in
  `--mode color`. Default: the part's own LDraw color.
- **`--curve-quality`** — LDView curve subdivision (default `12`, its max).
- **`--render-px`** — supersample size before downscaling (default `2048`).
- **`--scale`** — how much of the label's view area the part fills, `0`–`1`
  (default `1.0`). Applied in Pillow during the fit step (the render is always
  auto-cropped first), so it composes with `--margin`. `0.8` leaves extra
  breathing room around the part.

LDView's tessellation ceiling is 48-segment hi-res primitives; at label sizes
this is visually smooth (confirmed). True mathematically-exact curves would
require a ray-tracer (l3p + POV-Ray) — explicitly out of scope per design review.

## SVG output

Vector output (`--format svg`), validated against real renders, via the
`potrace` CLI (external dependency, installed by the setup script):

- **`outline`** — the Pillow line-art image (silhouette + optional interior
  edges) is traced in one potrace pass into smooth Bézier paths: a crisp,
  scalable line drawing.
- **`cel`** — the lit render is posterized to `--cel-levels` bands; each band's
  cumulative mask (pixels that dark or darker, within the silhouette) is traced
  separately and the resulting filled paths are **stacked lightest→darkest**,
  all sharing potrace's single y-flip/scale transform group. Produces flat
  vector tonal regions.

Implementation notes (learned during prototyping): potrace emits paths inside a
`<g transform="translate(0,H) scale(0.1,-0.1)">`; the assembled multi-band SVG
must preserve that transform or paths render off-canvas. ImageMagick's internal
renderer rasterizes the result for previews/tests.

## Sizing

Target pixel dimensions come from either:
- explicit `--width` / `--height` in pixels, or
- `--label-mm` + `--dpi`, computing pixels from physical label size. P-touch
  printers are typically 180 or 360 dpi; default `--dpi 180`.

## Dithering (mono mode)

`--dither floyd|atkinson|ordered|threshold`. Atkinson tends to look best on
small 3D renders and is hand-rolled (Pillow lacks it); Floyd–Steinberg uses
Pillow's `convert('1')`; ordered (Bayer) and plain threshold are implemented
directly. Additional knobs: `--threshold`, `--margin`. (Camera, fidelity,
shading, and color knobs are listed under Rendering parameters.)

## Batch & debugging

- Multiple parts (CLI args or a list file) → one output file each in an output
  directory.
- `--debug-dir <dir>` saves every intermediate stage in its own subfolder
  (`render/`, `cropped/`, `gray/`, `mono/`) so the divergence between
  tool-side dithering and driver-side scaling can be eyeballed directly. This
  serves the primary "try both approaches" goal.

## Modules

- `config.py` — load `labels.toml` + merge CLI overrides into a `Config`.
- `render.py` — resolve part, build the LDView argv (fidelity/lighting/angle/
  color), run the snapshot → hi-res RGBA PNG.
- `process.py` — flatten, grayscale, levels, posterize (cel), line-art outline,
  fit, and the four dither algorithms.
- `trace.py` — potrace-backed vector output: `outline_svg` and `cel_svg`.
- `cli.py` — argparse, batch handling, format/mode/shading wiring.
- `labels.toml` — default config values, overridable by flags.

Each module has one clear responsibility and a small interface: `render.py`
turns a part file into a hi-res RGBA PNG, `process.py` turns that into the
requested raster image(s), `trace.py` turns it into SVG, `cli.py` wires inputs
to outputs.

## Setup (prerequisites, validated as the first implementation task)

1. Install LDView (x86_64, runs under Rosetta): SourceForge
   `LDView_4.2.1_Universal.dmg` (not in Homebrew). The setup script handles it.
2. Install the LDraw parts library: `complete.zip` from ldraw.org.
3. Install `potrace` (`brew install potrace`) for SVG output.

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
the silhouette and the dithers come out dark/dense. This drove the render-tuning
investigation below.

## Render tuning + SVG investigation (2026-06-27 — VALIDATED)

A settings matrix on a curvy part (2×2 round brick 3941) and a 2×4 (3001),
viewed as contact sheets, settled the render-stage design:

- **Curve fidelity:** baseline `-CurveQuality=2` is visibly faceted on round
  parts. `-CurveQuality=12 -HiResPrimitives=1 -AllowPrimitiveSubstitution=1`
  (48-segment hi-res primitives) plus 2048px supersample is smooth at label
  size. This is LDView's ceiling — confirmed acceptable; POV-Ray true curves
  ruled out.
- **Contrast:** default lighting gives part-pixel stddev ~15 (dithers to a gray
  blob). `-Lighting=1 -UseQualityLighting=1 -LightVector=-1,1,2` raises it to
  ~40 with distinct face tones — the dither finally reads as a 3D brick. Adopted
  as the default lighting.
- **Shading modes:** `normal` (lit gray), `cel` (posterize to N bands — crisp,
  reads great), `outline` (Pillow line-art: silhouette from alpha + interior
  edges via `FIND_EDGES`). LDView's own flat+thick-edge "outline" path FAILED
  (renders near-white) — the Pillow-derived outline is used instead.
- **Color:** `-DefaultColor3=0xRRGGBB` recolors correctly (verified red/blue).
- **SVG:** potrace traces both outline (one pass) and cel (per-band, stacked)
  into clean vector output. Verified by rasterizing with ImageMagick.

Comparison sheets from this investigation are archived in the session scratchpad
(`keep/sheet_*.png`).

## Decisions made

- **Python, not Node** — image-processing-centric; Pillow already present.
- **New sibling repo**, not a subdirectory of `lbx-editor` — decoupled batch tool.

## Portability

macOS is the development platform, but the design keeps platform specifics out of
the code so a later port is a config change, not a rewrite. The only OS-specific
piece is the LDView invocation: `config.ldview` (binary path) and
`config.ldview_launcher` (prefix args, default `["arch","-x86_64"]` on Apple
Silicon, `[]` elsewhere via `default_ldview_launcher()`). LDView's `-Flags` are
identical across its macOS/Linux/Windows builds; potrace, ImageMagick, Pillow,
and NumPy are cross-platform. The `setup-ldview.sh` convenience script is
macOS-only (dmg/hdiutil/brew); on Linux you install ldview + potrace via the
package manager and set the two config values in `labels.toml`.

## Out of scope

- LBX file assembly / printing (handled by the user's separate stack).
- Fetching part images from the web; rendering is always local from LDraw.
- A GUI; this is a CLI batch tool.
- True mathematically-exact curved surfaces (l3p + POV-Ray); LDView's 48-segment
  tessellation is sufficient at label size.
- Color/multi-band raster tracing tools beyond potrace (e.g. vtracer); cel SVG
  is built by stacking per-band potrace passes.
