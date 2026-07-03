# Scaled SVG library + parameterized shading — design

Date: 2026-07-03

## Goal

Three coordinated additions to the `outline` (pure-Python HLR/vector) renderer:

1. **Physical/real-world scale** for SVG output — a 2×4 brick's SVG is literally
   twice the size of a 1×1, at true LEGO dimensions. The label driver resizes as
   needed.
2. **A parameterized interior-shading system** — pluggable shading styles that
   fill part faces with tone. Flat 3-tone ("iso-diagram") ships first; cel
   (N-level) and gradient styles slot into the same interface later.
3. **Optional highlights** — off by default; any specular is *very diffuse*
   (broad, soft, low-contrast), not a glossy dot.

Plus a **library generator** that batch-renders a filtered, quality-gated subset
of the LDraw catalog to scaled SVGs.

Scope note: these features apply to the `outline` shading path only (the
pure-Python renderer in `hlr.py`/`primitives.py`/`trace.py`). The LDView-backed
`normal`/`cel`/`color` PNG paths are unchanged.

## Constants & facts (verified against current code)

- LDraw unit: **1 LDU = 0.4 mm** exactly.
- The view is **orthographic isometric**, so projection preserves scale (only the
  inherent iso foreshortening applies). No perspective correction needed.
- `hlr._visible_segments_*` compute an LDU→px scale factor `s` (via
  `_fit_params`) used to project geometry into a `render_px`-square space. Segment
  coordinates are therefore linear in LDU: `px = LDU_proj * s + offset`. Hence
  physical size is recoverable: **`mm = px_extent / s * 0.4`**.
- `flatten()` populates `out["tri"]` (flat triangles, BFC-wound → normals
  derivable), `out["2"]` (edges), `out["5"]` (conditional/silhouette edges), and
  `out["analytic"]` (recognized curved primitives: `cyli`, `disc`, `ring`,
  `edge`).
- `parts/*.dat` ≈ 24,214 files. `!LDRAW_ORG` type is `Part` (19,248) or
  `Shortcut` (4,966). Title line 0 gives a human category as its leading word(s)
  (e.g. `Brick 2 x 4`, `Technic Brick 1 x 2 with Hole`, `Slope Brick 45 2 x 1`).

## 1. Physical scale (SVG)

### Behavior

Add a `scale_mode`: `fit` (current behavior, default) | `physical`.

- **`fit`** — unchanged. `fit_segments` scales each part to fill the `width`×
  `height` canvas; SVG `viewBox="0 0 W H"`.
- **`physical`** — no per-part rescale. Emit segments in px-space, set
  `viewBox` to the projected bounding box (plus a margin), and set the SVG's
  physical size attributes:
  - `width  = (bbox_px_w / s) * 0.4` mm
  - `height = (bbox_px_h / s) * 0.4` mm

  Stroke widths in `physical` mode are specified in **mm** (config
  `line_mm` / `silhouette_mm`, defaults e.g. `0.20` / `0.30`) so they render at
  a fixed physical weight regardless of part size, rather than scaling with the
  part. In `fit` mode the existing px stroke widths continue to apply.

### Implementation

- `hlr.visible_segments` already returns `(segs, bbox)` in px-space and can also
  return `s` (the LDU→px factor). Extend it (or add a sibling) to surface `s`
  so the SVG writer can convert to mm. Keep `segs` in px-space; only the SVG
  `width`/`height` attributes and stroke units change.
- `trace.segments_to_svg` gains parameters for physical output: an optional
  `physical=(width_mm, height_mm)` and mm stroke widths. When present it writes
  `width="{w}mm" height="{h}mm"` and a `viewBox` equal to the px bbox, and uses
  `stroke-width` values in the viewBox's px units that correspond to the desired
  mm (converted via the same `s`).
- The library generator always uses `scale_mode = physical`.

PNG outputs are out of scope for physical scale (they remain fit-to-canvas);
this feature targets SVG, per the request.

## 2. Shading architecture

### Faces producer

New function (in `primitives.py` or a new `shade.py`) that yields **fillable
faces** with a normal and a representative depth:

- **Flat faces** from `out["tri"]`: group/emit triangles (and coplanar quads
  where cheap) as filled polygons; face normal from BFC winding; depth from face
  centroid along the view forward vector.
- **Analytic surfaces** from `out["analytic"]`:
  - `disc` → filled ellipse (single fill; normal = disc axis).
  - `ring` → filled annulus.
  - `cyli` (wall) → split the visible angular range into **K angular bands**
    (config `cyl_bands`, default e.g. 6); each band is a quad-ish fill with the
    band's mid-angle surface normal. This is what gives curved walls their tone
    gradient in a flat-fill style.

Each face = `{ outline_ops, normal, depth, kind }`, where `outline_ops` are the
same op vocabulary (`line`/`arc`) used for strokes, closed into a fill path.

### Compositing — painter's algorithm

Fills do **not** use HLR clipping. Instead:

1. Sort faces **back-to-front** by depth.
2. Fill each solid; nearer faces overpaint farther ones (correct for opaque
   parts, and cheap).
3. Draw the existing crisp analytic **outline strokes last, on top** — so edges
   stay exact vector regardless of fill overdraw.
4. If highlights are enabled, draw the highlight overlay between fills and
   strokes (see §3).

Rationale: the outline renderer tracks *edges*, not *face visibility*. Painter's
order gives correct opaque shading without building a second visibility solver.

### `ShadingStyle` interface

```
class ShadingStyle:
    def tone(self, normal, light) -> str            # fill color for a face
    def curve_bands(self, kind) -> int              # angular bands for cyli walls
    # gradient style overrides fill emission to attach an SVG gradient instead
```

- **`flat3`** (first): map each face to one of three tones by dominant
  orientation relative to light — top (lightest), left (mid), right (dark).
  Cylinder walls use `curve_bands` sectors, each snapped to the nearest of the
  three tones (or a small fixed ramp). Tiny SVGs, dithers cleanly.
- **`cel`**: `tone = quantize(max(0, normal·light), N)` with `N = cel_levels`;
  more bands on curves.
- **`gradient`**: curved faces emit an SVG `linearGradient`/`radialGradient`
  approximating continuous `normal·light`; flat faces stay solid.

### Palette

Fill tones are shades of `--part-color` (default a mid-gray). All tones are
grayscale-derived so they dither to 1-bit cleanly. `--shade-style none` (default)
emits no fills — identical to today's pure outline.

Light direction: default standard upper-front (a fixed vector in view space);
`--light LAT,LONG` overrides.

## 3. Highlights (off by default)

- Opt-in via `--highlights`; separate from `--shade-style` (can combine or use
  independently).
- Specular is **very diffuse**: a broad, low-opacity soft **radial gradient**
  blob centered on up-facing curved tops (primarily stud top discs), with wide
  falloff — no hard rim. Rendered as an overlay layer above fills (and below or
  above strokes; default below strokes so edges stay crisp).
- `--highlight-strength` (0–1, small default) controls peak opacity.
- On 1-bit output the highlight may wash out; that is acceptable since it is
  opt-in. It is primarily for grayscale/screen SVG.

## 4. Library generator

New module `library.py` + CLI entry (`python -m brick_icons.library`, and/or
`cli --library`).

### Filter ("intersection of curated ∩ category")

1. Enumerate `vendor/ldraw/parts/*.dat` (top-level only; `parts/s/` subparts are
   already excluded by the glob).
2. Keep only `!LDRAW_ORG … Part` (drop `Shortcut`, subpart, primitive,
   `~Moved to` redirects).
3. Title leading category ∈ **configurable allowlist**:
   `Brick, Plate, Tile, Slope, Technic, Wedge, Panel, Cylinder, Cone, Dish, Bar,
   Bracket, Hinge, Wing, Baseplate`.
4. Exclude noise: titles containing `Sticker`, `Pattern`/`with Pattern`; titles
   beginning with `~` or `_` (obsolete/subpart markers); `Moved` redirects.
5. Result ≈ a few thousand clean, sortable parts (exact count reported at run
   time). Allowlist and exclusions live in `labels.toml` so they are easy to
   tune.

### Output & manifest

- SVGs to `out/library/<category>/<id>.svg`, rendered with
  `scale_mode = physical` and the configured shade style.
- A **manifest** `out/library/manifest.json`: one record per attempted part
  `{ id, title, category, width_mm, height_mm, status }` where `status ∈
  {ok, skipped-empty, error:<msg>}`. Errors/empties are logged, not fatal — noise
  self-prunes.

### Execution

- **Resumable**: skip parts whose SVG already exists (unless `--force`).
- **Parallel**: `concurrent.futures.ProcessPoolExecutor` across parts; each
  worker renders one part. Progress printed periodically.
- `--limit N` and `--category X` for partial/targeted runs (useful for the
  sign-off sample).

## 5. CLI / config surface

New CLI flags (all mirrored as `labels.toml` defaults):

- `--scale-mode {fit,physical}` (default `fit`).
- `--shade-style {none,flat3,cel,gradient}` (default `none`).
- `--highlights` (flag, default off) and `--highlight-strength FLOAT`.
- `--light LAT,LONG`.
- `--cyl-bands N`, `--line-mm`, `--silhouette-mm` (physical stroke weights).

Library-specific: `--library`, `--limit`, `--category`, `--force`.

Back-compat: with defaults (`scale_mode=fit`, `shade-style=none`, no highlights),
output is byte-for-byte the current pure-outline behavior.

## 6. Testing

Unit tests (pytest, no LDView dependency):

- **mm sizing**: given a known `s` and px bbox, `physical` width/height math is
  correct; a 2×4 brick's SVG mm-size is 2× a 1×1's in the long axis.
- **faces producer**: a unit cube's 3 visible faces have expected normals and
  depth ordering; a cylinder yields `cyl_bands` wall bands + a top disc.
- **painter order**: faces sorted back-to-front; a known occluding face is
  emitted after (over) the one it hides.
- **`flat3` tones**: top/left/right faces map to the three expected tones.
- **library filter**: allowlist accept (`Brick 2 x 4`), category reject
  (`Sticker …`, `Minifig …`), pattern/`~`/`Moved` exclusion, `Shortcut` type
  exclusion.
- **manifest shape**: records carry the documented fields and statuses.

Plus a **visual sign-off gate**: the first implementation step renders a sample
sheet of ~6 representative parts (2×4 brick, round 2×2, tile, slope, technic
beam, stud-heavy plate) in `flat3` at physical scale, shown inline for approval
before the full batch runs.

## Non-goals / YAGNI

- No physical scaling of PNG outputs.
- No new shading on the LDView (`normal`/`cel`/`color`) paths.
- No per-face HLR clipping of fills (painter's algorithm instead).
- `gradient` and `cel` styles are designed-for but `flat3` is the only style
  built in the first implementation pass.
