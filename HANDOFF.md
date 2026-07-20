# Handoff — 2026-07-19 (late): condline smooth joints + corner join chaining

Working tree on `main`, clean. 336 tests passing.

## Addendum 2026-07-20: chain miterlimit 5 → 1.5 (corner barbs)

f15fcea's mitered chains grew spikes ("barbs") at interior junctions
sharper than ~46° (miter ratio > 5 never occurred; the visible barbs
were ratio 1.9–3.3 at 35–63° wedges — 98283 ledge corner, 32062 notch
chevrons). miterlimit 1.5 on chains+elbows bevels joins sharper than
~84°; outline corners keep their sharpness via contour_d (still 5).
Census A/B vs census-Z: 6 parts byte-identical, 42 differ ONLY in the
stroke-miterlimit attribute (path data identical); raster delta is
ink-REMOVAL only (985 px @1024 across all 42), all at junction
vertices. 336 tests pass. **census-AA**
(`~/.claude-msb/jobs/0629a9a6/tmp/census-AA/`) is the new baseline;
byte-diff gate hard vs census-AA.

## What this session did (`3f172bc`, `f15fcea`)

- **Condline-declared smooth joints** (`3f172bc`, hlr/primitives):
  4740's "extra concentric seams" were the r=12/r=16 cone-band junction
  circles — the author condlines exactly those circles (smooth joint),
  but `smooth_rim_skips` only suppressed equal-slope wall stacks and the
  dish's bands pitch differently (15.8/21.8/29.9 deg). New
  `primitives.rim_cond_span_bins`: authored type-5 chords lying ON a rim
  circle count as opposite-side coverage UNCONDITIONALLY (real creases
  are type-2 authored — 4740's boss base keeps its ring; guards: chords
  must sit in-plane at radius, span < 30 deg so diameters don't count).
  NOT a regression fix: opaque flat3 has drawn these rings since at
  least census-H; b207e13 removed their translucent hairline cousins,
  which is why they stood out "again". Census diff: 4740 (rings gone) +
  2654a (dome-base seam arcs gone, plus a knock-on: the slit-V weld
  pocket vanished because the seam remnant that triggered it is gone —
  reviewed, cleaner). 30137 spot-checked byte-identical.

- **Corner pinch notches SOLVED by path chaining** (`f15fcea`, trace):
  the QL/WebKit "leaking corners" (real geometry in every renderer, see
  memory corner-pinch-notch) are fixed the sanctioned way —
  `trace._chain_line_ops` chains shared-endpoint same-width line
  strokes into mitered polyline paths (sharpest wedge pairs first,
  cyclic-adjacent pairing per vertex; closed chains emit Z) and covers
  leftover wedges at 3+-degree vertices with 2-segment elbow-join
  paths. GOTCHA: elbow arms are trimmed to 1.5·sw — full-length arms
  double-composite the AA fringe of every junction stroke (first
  attempt showed red edge-length diffs on 2412b). Endpoint keys are the
  emitted 2-dp coords; iteration fully sorted (byte-jitter gate).
  Verified in resvg AND CoreSVG (`sips`): census-Z vs Y is corner-ink
  additions only on 41 boxy parts; 7 pure-round parts byte-identical.

## Baselines

- **census-Z** (`~/.claude-msb/jobs/0629a9a6/tmp/census-Z/`, 48 parts,
  post-f15fcea) is current. Every boxy part byte-differs from census-Y
  (stroke layer restructured into chained paths) — reviewed at PIXEL
  level instead: rasterize + AE + directionality (ink added at corners
  only, none removed).
- census-Y (same dir, post-3f172bc) = condline fix only; diffs vs
  census-X: 4740, 2654a (both reviewed).
- census-X (same dir) and older: see git history of this file.
- Byte-diff gate stays HARD vs census-Z or newer.

## Open items

1. **LDView flags not applying in this environment**: `--mode gray
   --shading normal` renders come back faceted (hex boss) with NO edge
   lines despite `-EdgeLines=1 -CurveQuality=12 -HiResPrimitives=1` —
   observed on direct invocation AND through `render.render_part`. The
   outline path never calls LDView, so current pipeline is unaffected,
   but shaded-reference calibration is broken until diagnosed (prefs
   file? snapshot arg order? Rosetta?).
2. Mike wish list: (b) truncated rim-stud faces as one arc on the
   footprint circle — `primitives.facet_snap_rims` BUILT+TESTED, not
   emitted; needs drawn-chord refit onto known rim circles (hook:
   fit_edge_arcs call site). (c) grow recognized-element
   exact-intersection layer; px-space gates stay fallback.
3. 30137 band-edge raggedness at zoom 8 (invisible at label scale).
4. 3941 translucent bottom notch (pre-existing; verify vs LDView).
5. Performance: suite ~6 min; census ~7 min.
6. LDraw/LDView hosted pinning (upload vendored snapshot on
   renderer-done).

## Verification workflow

- Full suite: `.venv/bin/python -m pytest -q` (336, ~6 min)
- Gallery: `scripts/render-gallery.sh` (16 parts, ~4 min)
- Contact sheet (labeled): `scripts/render-contact-sheet.sh [out-dir]`
- One part: `.venv/bin/python -m brick_icons.cli <id> --format svg
  --shading outline --shade-style flat3 [--part-label] [--opacity 0.55]
  --out <dir>`
- Census A/B: render `--list
  ~/.claude-msb/jobs/eb7c836f/tmp/census-K.parts.txt` (defaults 256×170
  + flat3 match baselines), byte-diff SVGs vs census-Z; where strokes
  restructure, fall back to raster AE + directionality (see this
  session's zcmp workflow in `~/.claude-msb/jobs/0629a9a6/tmp/`).
- WebKit/CoreSVG check for corner-class issues: `sips -s format png -Z
  2048 <svg> --out <png>` (QL preview is WebKit; sips is CoreSVG).
- 1024 stroke parity: `--format both --shading outline --width 1024
  --height 1024`, resvg + `magick compare -metric RMSE`; ~0.019-0.02
  normalized ≈ AA floor. NOTE: outline-mode `.gray.png` is OUR OWN
  rasterized segments, not LDView (cli.py:205) — don't use it as an
  external reference; `--mode gray --shading normal` is the LDView path
  (currently broken, see open item 1).
- Layer-split triage: zero out `stroke-width="0.8"` + `fill` → strokes
  layer; zero out `stroke-width="2.00"` → fills layer.
