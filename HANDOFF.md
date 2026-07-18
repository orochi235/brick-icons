# Handoff — 2026-07-18b: T-graze junction weld (30137 beaked-Y fixed)

Working tree on `main`, clean. 315 tests passing.

## What this session did

- `349cf85` + `6a78dc4` — **stub-bridged junction weld.** The 30137
  rear-scallop cap junction (open item 1, Mike-flagged, diagnosis in
  the previous handoff below) is fixed per the junction directive: new
  `_weld_junction_notches` in shade.py inks the thin notch pinched
  between converging stroke bands at a beak junction. Weld =
  closing(op bands, 0.5·line_px) − bands, clipped to the arc-grown
  part region; pieces must be thin under opening(0.5·line_px), 0.02 <
  area ≤ SPUR_MAX_AREA, and within 3·line_px of a junction point.
  `349cf85` welded EVERY T-graze — 46/48 census parts, inking stud
  cylinder limb/rim corners library-wide. Mike VETOED that; `6a78dc4`
  narrowed it with two gates: the dying stroke must be a STUB
  (< 3×sw — 30137's 6.7° bridge between scallop V and cap rim; limbs
  and seams are long and keep their corners), and the notch must touch
  ≥ 3 distinct stroke bands (arc + stub + rim pile-up). Shared-vertex
  (V) joins never count — every ordinary face corner is one. Census
  impact: 13 parts, AE 0–399 at zoom 4, all verified ticks at genuine
  pile-ups (3941 boss pinch slivers, 2654a boss grazes, 32062 axle
  flats); stud corners byte-identical or AE ≤ 1. 30137's junction
  reads as a clean solid Y at zoom 8. NOTE: do not loosen the stub or
  band-count gates without re-checking stud corners across the census
  — the veto was specifically about those.

## Previous session (2026-07-18a)

- `4b621f4` — **partial-disc phantom triangle.** A sectored analytic
  `Disc` (stud10's 270° 3-4disc cap) built its fill polygon from the arc
  samples alone; the implicit closure chord covered a phantom triangle
  over the quarter tiled by the primitive's hand-authored fan tris.
  Invisible opaque (same tone painted twice), a lighter wedge on every
  stud cap at opacity < 1 — the "weird triangle" Mike reported on
  transparent 3941. Partial sectors now close the pie through the
  center. NOTE: this artifact class is invisible in opaque renders —
  verify translucent when touching sectored flat prims.
- `03ed533` — **residue-trim laundering.** Mike's second report: white
  needle on 30137's top face where the back-edge arc grazes stud 3 (and
  a worse one behind stud 2). Root cause was NOT the fill sagging off
  the arc (densify was fine): the residue rounds bared the strip in two
  locally-sound steps (top tris → column wall → background). Fixes:
  `_trim_safe` claimant retention (a piece that shows outside drawn-ops
  ink may only be trimmed if it fuses thickly with the claimant's
  fragment under opening), and the whites absorption generalized to any
  thin bare piece of base − fills − ink (graze voids leak past the
  0.15 channel sever, so enclosed-holes detection missed them).
  Ops-only ink for the show test is load-bearing — a contour term
  phantom-covers the very strip being laundered.
- `28a45f9` — gallery regenerated (30137, 3941, 3649 visibly improved;
  3960/54200 AE=0 jitter).

## Baselines

- **census-R** (`~/.claude-msb/jobs/0bc8b81a/tmp/census-R/`, 48 parts,
  post-6a78dc4) is current. vs census-O: 13 byte-diffs, all stub-weld
  ticks, AE 0–399 at zoom 4, reviewed above.
- census-P (same dir) = post-349cf85 (the vetoed broad weld — do NOT
  baseline against it); census-O = post-03ed533; census-N =
  post-b207e13; census-M = post-dcceaf2.
- Byte-diff gate is HARD (2fc12a0): byte-diff ⇒ real change, vs
  census-R or newer.

## Open items

1. **30137 band-edge raggedness**: with the needles gone, the black
   lens-pocket inking along the back-edge band's inner edge reads
   ragged at zoom 8 (invisible at label scale). Only revisit if a part
   shows it at ≤2x.
2. **3941 translucent bottom notch**: solid black rectangle at the
   bottom center of the transparent render (pre-existing, not
   flagged). Verify against LDView translucent reference if it comes
   up.
3. **Light-on-light pinch hairlines** (3941 e3/e23 wedge): still
   benign/unpinned.
4. **Performance**: suite now ~5 min loaded; census ~10 min; donation
   pass still doubles fill_ops on hole-heavy parts.
5. **Stock-render comparison (07-07)**: 3700 stock image never arrived.
6. **LDraw/LDView hosted pinning**: when renderer is declared done,
   upload the vendored snapshot as a release asset + hash-verify in
   setup-ldview.sh.

## Verification workflow

- Full suite: `.venv/bin/python -m pytest -q` (315, ~5 min)
- Gallery: `scripts/render-gallery.sh` (16 parts, ~4 min)
- Contact sheet (labeled): `scripts/render-contact-sheet.sh [out-dir]`
- One part: `.venv/bin/python -m brick_icons.cli <id> --format svg
  --shading outline --shade-style flat3 [--part-label] [--opacity 0.55]
  --out <dir>`
- Census A/B: render `--list parts.txt` twice (defaults 256×170 + flat3
  match baselines), byte-diff SVGs vs census-R; parts list at
  `~/.claude-msb/jobs/eb7c836f/tmp/census-K.parts.txt`.
- 1024 stroke parity: `--format both --shading outline --width 1024
  --height 1024` (NO flat3, NO --mode gray — outline mode's .gray.png is
  the LDView line-art reference; `--mode gray` gives the SHADED
  reference), then resvg at 1024 + `magick compare -metric RMSE`;
  ~0.019-0.02 normalized ≈ AA floor. Script:
  `~/.claude-msb/jobs/eb7c836f/tmp/parity_compare_h.sh`.
- Layer-split triage: zero out `stroke-width="0.8"` + `fill` → strokes
  layer; zero out `stroke-width="2.00"` → fills layer.
- Probe scripts: this session's in scratchpad (gone on reboot); durable
  ones in `~/.claude-msb/jobs/0bc8b81a/tmp/` (probe_gate*, probe_plot,
  probe_members) and `~/.claude-msb/jobs/eb7c836f/tmp/` (probe33-40).
