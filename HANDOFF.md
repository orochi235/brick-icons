# Handoff — 2026-07-19: per-bin seams + facet coverage + weld gates

Working tree on `main`, clean. 323 tests passing.

## Addendum (later session, `1f46740`)

- **Interior-landing weld gate**: V-join check is now "landing point ≥
  2.0·sw from the landed-on stroke's endpoints" (was endpoint-to-
  endpoint 0.5·sw). Kills 2654a's boss-lip ink knuckles; 30137
  byte-identical (its stubs land on closed rim circles). Census-W
  (`~/.claude-msb/jobs/0629a9a6/tmp/census-W/`) is the new baseline —
  vs census-V: 2654a, 32062, 98283, all reviewed. 324 tests.
- **Corner pinch notches are real geometry, not a Quick Look bug**
  (Mike-flagged via QL/Safari): the face-colored wedge past the shared
  cap disc at every 3-stroke corner appears in resvg/WebKit/CoreSVG
  alike. If fixed, fix by chaining shared-endpoint strokes into
  polyline paths (real SVG joins) — corner ink-welding is vetoed.
- **Wide-pass contour arc recovery** (geom2d, contour_d-only): edges
  missing the strict gates get a second offer at 0.25 px / 27° with a
  ≥3-edge run gate. 2654a's dome horizon + 3941's truncated rear-stud
  rims collapse to arcs; census contour L-commands 1229 → 557 over 48
  parts, 9 round parts diff at AE < 0.16%. **census-X**
  (`~/.claude-msb/jobs/0629a9a6/tmp/census-X/`) is the current
  baseline (current tree verified byte-identical to it on 2654a/3941).
- Mike wish list remaining: (b) truncated rim-stud faces as one arc on
  the footprint circle — `primitives.facet_snap_rims` + one-sided snap
  candidates are BUILT+TESTED but deliberately not emitted: fills snap
  while chord strokes stay, opening paint slivers (3941 front-stud
  crescent). Needs an arcfit-style drawn-chord refit onto known rim
  circles (hook: fit_edge_arcs call site) emitted together with the
  candidates. (c) architecture direction: grow recognized-element
  (studs/footprint) exact-intersection layer; px-space gates stay as
  fallback.

## What this session did (`9318e5e`)

Four interlocking changes, all verified against census-R with Mike
reviewing renders live:

- **Per-bin wall-rim seam suppression.** `hlr.smooth_rim_skips` +
  `primitives.rim_span_bins` / `rim_uncovered_spans` /
  `_rim_emit_spans`: a sectored wall suppresses a shared rim circle
  only over its covered angles; arc emission splits per rim into the
  uncovered spans. 60474's side-wall seam ring, 3941/6143's base-lip
  seams gone; true bite/cutout gaps keep their edges. The 3941 sil-base
  test now accepts the sil ending on the part outline (the seam it used
  to land on is no longer drawn mid-cutout).

- **Facet-authored walls count as seam coverage.**
  `primitives.rim_facet_span_bins`: LDraw resumes primitive-tiled walls
  as raw quads (60474's outer wall beside each bite; HALF its
  center-hole lower wall — the leftover seam stubs there read as nubs
  on the front-center stud's top edge, Mike-flagged). Gates: asymmetric
  radial band (up to 16-gon chord inset INWARD — stitching vertices sit
  at 5.885/5.946 on the r=6 hole wall — jitter only outward), must abut
  the rim plane, extend away from it, span < 25 deg.

- **absorb_wall_facets** (shade.py, wired in
  `_visible_segments_analytic`): facet-authored wall stretches join the
  abutting analytic band's gradient instead of flat-toning (60474's
  bite flanks). `faces_from_tris` keeps `_verts` for it. GOTCHA: the
  25-deg angular-span cap is load-bearing — 30136's flat END face is a
  chord plane whose 4 corners lie exactly ON the lobe cylinder (author
  clipped it to the log profile) and whose normal equals the radial
  direction at mid-angle; only the span betrays it. Without the cap it
  absorbed and re-toned the whole face (gray 94 -> 129).

- **Weld false-junction gates** (`_weld_junction_notches`): (1)
  collinear twin — a stub lying >= 75% inside the landed-on band is
  duplicate/split authoring of the same edge (60474's bite flank: two
  short pieces OVER a full-length twin; internal split points read as
  T-grazes), skip; a genuine graze only pokes its tip in. (2)
  shared-vertex tolerance is now 0.5·sw of the landed-on stroke (was
  absolute 0.3 px; 60474's rim chord ends 0.79 px from the flank end).
  Kills the corner ink blobs at 60474's bites (Mike-flagged) and
  3713's slit-end nibbles; 2654a boss-graze welds also un-weld (clean
  Y-junctions now, reviewed OK). **30137 byte-identical** — the
  beaked-Y weld survives all of it. Do NOT relax the containment
  fraction or V-tolerance without re-rendering 30137 + 3713 + 60474.
  The vetoed broad weld ships as opt-in `--weld-corners` (cli/config).

## Baselines

- **census-V** (`~/.claude-msb/jobs/0629a9a6/tmp/census-V/`, 48 parts,
  post-9318e5e) is current. vs census-R: 7 byte-diffs, all reviewed —
  2654a (boss-base seams + un-welded boss grazes), 3660b (tube-rim
  seam tick), 3673 (collar seam arcs), 3713 (slit-end weld gone),
  3941/6143 (base seam per-bin), 60474 (seam ring + hole stubs +
  corner welds). 30137 spot-checked byte-identical (not in census
  list).
- census-R (`~/.claude-msb/jobs/0bc8b81a/tmp/census-R/`) = pre-session;
  census-P/O/N/M older, same dir (P is the vetoed broad weld — never
  baseline against it).
- Byte-diff gate is HARD (2fc12a0): byte-diff ⇒ real change, vs
  census-V or newer.

## Open items

1. **30137 band-edge raggedness**: lens-pocket inner edge ragged at
   zoom 8, invisible at label scale. Revisit only if a part shows it
   at ≤2x.
2. **3941 translucent bottom notch**: pre-existing black rectangle in
   transparent renders; verify vs LDView if it comes up.
3. **Light-on-light pinch hairlines** (3941 e3/e23): benign/unpinned.
4. **Performance**: suite ~6 min; census ~7 min; facet coverage adds
   per-key tri scans (vectorized, negligible so far).
5. **Stock-render comparison (07-07)**: 3700 stock image never arrived.
6. **LDraw/LDView hosted pinning**: on renderer-done, upload vendored
   snapshot as release asset + hash-verify in setup-ldview.sh.

## Verification workflow

- Full suite: `.venv/bin/python -m pytest -q` (323, ~6 min)
- Gallery: `scripts/render-gallery.sh` (16 parts, ~4 min)
- Contact sheet (labeled): `scripts/render-contact-sheet.sh [out-dir]`
- One part: `.venv/bin/python -m brick_icons.cli <id> --format svg
  --shading outline --shade-style flat3 [--part-label] [--opacity 0.55]
  --out <dir>`
- Census A/B: render `--list <parts>` (defaults 256×170 + flat3 match
  baselines), byte-diff SVGs vs census-V; parts list at
  `~/.claude-msb/jobs/eb7c836f/tmp/census-K.parts.txt`.
- 1024 stroke parity: `--format both --shading outline --width 1024
  --height 1024` (NO flat3, NO --mode gray — outline mode's .gray.png is
  the LDView line-art reference; `--mode gray` gives the SHADED
  reference), then resvg at 1024 + `magick compare -metric RMSE`;
  ~0.019-0.02 normalized ≈ AA floor. Script:
  `~/.claude-msb/jobs/eb7c836f/tmp/parity_compare_h.sh`.
- Layer-split triage: zero out `stroke-width="0.8"` + `fill` → strokes
  layer; zero out `stroke-width="2.00"` → fills layer.
- Probe scripts: durable ones in `~/.claude-msb/jobs/0bc8b81a/tmp/`
  (probe_gate*, probe_plot, probe_members) and
  `~/.claude-msb/jobs/eb7c836f/tmp/` (probe33-40); this session's
  weld/seam probes in `~/.claude-msb/jobs/0629a9a6/tmp/`.
