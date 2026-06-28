# Handoff: brick-icons — HLR landed (faceted), next = analytic primitive substitution (path B)

## TL;DR / next task
The pure-Python **HLR outline renderer is built, reviewed merge-ready, and on branch
`hlr-outline`**. It produces clean vector line-art icons from LDraw geometry (no LDView).
Remaining polish artifacts on *curved* parts trace to z-buffer edge-occlusion fuzz on
**faceted** LDraw geometry. **Decision: implement path B — analytic primitive
substitution** (swap LDraw's named curved primitives for exact cylinders/discs/tori) to
get geometrically-correct continuous curves and likely fix those artifacts.

**Start by brainstorming + writing a spec for path B** (superpowers brainstorming →
writing-plans). Don't dive into code first.

## Repo / branch state
- Branch **`hlr-outline`** (NOT merged). `main` still has the old LDView raster outline.
- HLR feature fully implemented across 9 TDD tasks + reviews; **final review verdict: "ready
  to merge, yes-with-minors."** `.venv/bin/pytest -q` → **50 passed**.
- Last commit `f3251d0` = WIP resolution-relative edge-occlusion dilation (partial — see below).
- Design doc: `docs/superpowers/specs/2026-06-28-hlr-outline-design.md`.
  Plan: `docs/superpowers/plans/2026-06-28-hlr-outline.md`.
- GitHub remote exists: **public `orochi235/brick-icons`** (`main` pushed; `hlr-outline` is
  local-only, not pushed).

### Open decision for next session
Merge `hlr-outline` to `main` first (it's a big win; faceting isn't the outline blocker),
then do path B as a new feature — OR continue path B on the same branch before merging.
Recommend **merge first**, then path B branch. Confirm with Mike.

## Why path B (the architectural finding)
LDraw geometry is **polygonal, not curve patches** (verified in the source): a cylinder =
4× quarter-cylinder = **48 flat quads** (`p/48/`, hi-res) or 16 (`p/`); vertices are samples
on the ideal circle. **Type-5 conditional lines** are authored silhouette markers (drawn only
when their control points project to the same side) — that's why our outlines already have
*smooth silhouettes* despite faceting.

Key nuance: **for the outline deliverable, faceting is NOT the blocker** (conditionals give
smooth curves). The artifacts below are **edge-occlusion fuzz on faceted surfaces**. Faceting
mainly degrades **cel** shading (facet bands). Path B helps both, and should clean up the
occlusion artifacts because analytic primitives have exact, fuzz-free depth at silhouettes.

## Path B design sketch (to be brainstormed into a real spec)
- During `hlr.flatten` (in `brick_icons/hlr.py`), the recursion resolves type-1 sub-file refs.
  Add a **substitution layer**: when a referenced file is a known curved **primitive**
  (`p/48/4-4cyli.dat`, `4-4disc`, `1-4cyli`, ring/torus `t??o????`, `4-4cyli`, `4-4edge`,
  cones `*con*`, etc.), instead of recursing into its polygons, emit an **analytic surface
  record** (cylinder/disc/cone/torus) carrying the accumulated transform + radius/height.
- Project & render analytic silhouettes exactly: a transformed cylinder's silhouette is two
  true lines + elliptical caps; a disc/torus → exact ellipse. Occlude against an exact (or
  high-res analytic) depth buffer. This removes the tangent quantization that causes the
  3941 base gap / tails.
- Brick *bodies* (boxes, non-primitive geometry) are already exact flat polygons — keep as is.
- Reference prior art: **LGEO** (LDraw→POV primitive substitution) for the name→shape mapping.
- Scope: cover the standard curved primitives used by the curated `parts.txt` set first.

## Open artifacts (current faceted HLR) — for reference / validation targets
1. **3941 (round 2×2) base gap**: body vertical silhouette doesn't connect to the bottom-rim
   arc. ROOT CAUSE (diagnosed): bottom-rim *type-2 edges* self-occlude against the faceted
   front wall; z-buffer quantization at the silhouette tangent. A flat `EDGE_BIAS` bump fixes
   the gap but **leaks extraneous lines** (Mike rejected 0.05). The committed **dilated
   z-buffer** approach (`dilate_zbuffer`, neighborhood-max for edges) fixes it at render_px≈900
   without leak, but is **resolution-fragile** — does NOT fully connect at the production
   `render_px=2048` even with radius scaling. Path B should make this moot.
2. **Top-corner stud-area spurs**: "the topmost corner of each brick has line segments that
   extend a little too far into the stud area." **NOT yet diagnosed.** Likely a conditional
   line or edge near the back-top corner; investigate independently (may be unrelated to
   faceting/occlusion — could be a clean fix).
3. Minor "tails" around 3941's center notch at high EDGE_BIAS (gone with the dilation approach).

## Review minors still open (from final review, not yet done)
- Dead **`--outline-interior` / `--no-outline-interior` flag + `config.outline_interior`**:
  HLR ignores it (always emits interior edges). Mike dislikes misleading public surface —
  **remove the flag + field** (design doc intentionally dropped it from the kept-flags list).
- `hlr.visible_segments` gives a **cryptic error** on an unresolvable part id and on
  `.ldr`/`.mpd` inputs (only `.dat` special-cased) — add a clean `FileNotFoundError` and
  `.ldr`/`.mpd` parity with `render.resolve_part`.

## How it works now (faceted HLR pipeline)
`brick_icons/hlr.py`: `flatten` (recursive LDraw parse, prefers `p/48`) → `view_basis`/`project`
(look-at, iso) → `rasterize_zbuffer` + `clip_visible` (+ `dilate_zbuffer` for edges) →
`visible_segments(part, ldraw_dir, lat, long, render_px)` returns `[(x1,y1,x2,y2,kind)]`
(`kind` ∈ `edge`|`sil`) + bbox; `fit_segments` contains/centers into a label box.
`brick_icons/trace.py`: `segments_to_svg`. `brick_icons/process.py`: `draw_segments`/
`segments_mono` (raster). `brick_icons/cli.py`: `--shading outline` routes through HLR (skips
LDView); cel/normal/color still use LDView (`render.py`).

## Run / verify
```sh
cd ~/src/brick-icons
.venv/bin/pytest -q                       # 50 passed
.venv/bin/python -m brick_icons.cli 3941 3701 3001 --shading outline --format both --mode both --out out/x
# faceting reference: vendor/ldraw/p/48/1-4cyli.dat  (12 quads + 13 conditional lines per quadrant)
```
- **Calibrate on the high-res GRAY masters (`*.gray.png`), not the 1bpp mono** (see memory
  `calibrate-with-gray-masters`). Always `open` generated images for Mike.
- Persistent reference renders on disk (gitignored `out/`): `out/hlr-batch-sheet.png` (24-part
  HLR sheet), `out/hlr-vs-ldview.png`, `out/hlr-final/3941.gray.png`. (Scratchpad diagnostic
  images from this session will NOT persist across `/clear`.)

## Env gotchas
- `.venv` has pillow/numpy/pytest. **`pip` is blocked** — use `uv pip install --python .venv/bin/python`.
- HLR is pure Python from `vendor/ldraw/*.dat` (no LDView/Rosetta). LDView (cel/normal/color)
  is x86_64 under Rosetta via `config.ldview_launcher`. `vendor/` gitignored, locally populated.
- povray IS installed (brew) but unused — was for the abandoned POV-Ray spike.

## House rules (Mike)
US English, concise, no sycophancy. Never put his name in committed files (commits use
`git -c user.name='Michael Baker' -c user.email='devnull17@gmail.com'`). Branch before
committing on `main`; confirm before `gh pr create`. `gh` account for this repo = `orochi235`.
