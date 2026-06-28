# Design: HLR conditional-line outline (replaces LDView raster outline)

Status: proposed (2026-06-28). Supersedes the outline portion of
`2026-06-27-lego-bin-labels-design.md`.

## Why

`--shading outline` currently renders the part in LDView, then derives line art
from the raster (silhouette dilate/erode + `FIND_EDGES`, traced by potrace). The
calibration pass (high-res gray masters) showed this is the wrong tool:

- curved surfaces are faceted / low-poly looking;
- the stud-top "LEGO" logo becomes black smudges (`FIND_EDGES` noise);
- raster tracing adds fuzz and loses crisp geometry.

A spike (`scratchpad/hlr_spike.py`) rendering **hidden-line removal directly from
LDraw geometry** produced clean technical-drawing line art: mathematically smooth
studs/holes (no faceting), no logo noise, uniform strokes. See
`out/hlr-vs-ldview.png`. This reverses the original design's "HLR/POV-Ray out of
scope" call (made before we looked at gray masters).

## Decision

Reimplement `--shading outline` as a pure-Python LDraw HLR renderer. Retire the
LDView raster-trace outline path entirely (`make_outline`, `outline_masks`,
`outline_mono`, `_compose_lines`, `trace.outline_svg`). Keep `--line-width` /
`--silhouette-width` (HLR honors them) and the cel/normal/color paths unchanged.

Key consequence: **outline shading no longer invokes LDView/Rosetta** — it reads
`vendor/ldraw/**.dat` directly. Faster, deterministic, one fewer moving part.
cel/normal/color still use LDView.

## How it works

1. **Parse + flatten** (`hlr.py`): recursively resolve type-1 sub-file references,
   composing 3×3+translation transforms; prefer `p/48/` primitives (hi-res).
   Collect type-2 edges, type-5 conditional lines, type-3/4 faces (occluders).
   Parse cache keyed by resolved path.
2. **Camera**: `--angle` preset or `LAT,LONG` → look-at basis matching LDView's
   convention (so angles agree across shadings). Orthographic projection.
3. **Hidden-line removal**: z-buffer the faces (per-triangle bbox rasterization).
   A line sample is kept only if not behind a face (depth bias).
4. **Conditional lines**: draw a type-5 segment only when its two control points
   project to the same side of the segment — yields smooth curve silhouettes.
5. **Output**:
   - SVG: visible segments as polylines, `stroke-width` from line/silhouette width.
   - mono PNG: rasterize the segments at label size (line widths in output px),
     centered/contained like the other modes; `--mode mono`/`both`.
   - gray master: the line art at render resolution (`--mode gray`/`both`).

## Fixes vs the spike

- **Silhouette self-occlusion**: conditional silhouette lines sit *on* the curved
  surface, so a tight z-test culls them intermittently (3941 mid-body dropout +
  stray line). Use a larger relative depth bias for type-5 lines so the surface
  they lie on can't self-occlude, while genuinely-nearer surfaces (studs in front
  of the body) still hide them.
- **Stud-apex nub**: skip near-degenerate conditionals (control-point cross
  products near zero / zero-length projected segment).

## Modules / boundaries

- `hlr.py` — LDraw parse+flatten, camera, z-buffer HLR → list of 2D segments
  (each tagged edge vs silhouette). One responsibility: geometry → visible lines.
- `trace.py` — gains `segments_to_svg`; reuses existing SVG writer style.
- `process.py` — gains a raster step: segments → mono/gray bitmap at given widths
  (can reuse `_dilate`/canvas helpers). Drops the retired outline helpers.
- `cli.py` — for `--shading outline`, skip `render_part`; run hlr → trace/process.
- `config.py` — no new fields (reuses `ldraw_dir`, `line_width`, `silhouette_width`,
  `angle`, `scale`, `margin`, `width/height`, `render_px`).

## Testing (TDD)

Pure-geometry, so unit-testable without the full library:
- flatten a tiny inline `.dat` (type-1 ref + 2/3/5) → expected world coords;
- conditional same-side predicate (true/false cases);
- z-buffer occlusion: a face in front removes a segment behind it;
- camera presets: `top` and `front` project to expected axes;
- SVG has expected element count and rasterizes non-blank;
- end-to-end on a real part (3701) **skips if `vendor/ldraw` absent**, like the
  existing render/trace tests.

## Out of scope

- POV-Ray (povray now installed but not used here).
- HLR for cel/normal (those stay LDView raster).
- Analytic (non-z-buffer) exact HLR — z-buffer visibility is sufficient at icon
  sizes; revisit only if artifacts persist.
