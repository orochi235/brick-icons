# Handoff — 2026-07-17b: 3941 ring-floor chips donated; stranded-spur fallback

Working tree on `main`, clean. 298 tests passing. All commits pushed
through `dcceaf2`.

## What this session did

- `dcceaf2` — **stranded single-seam spur donation.** The stud10 fix
  (ecf771e) had exposed two ~1.2 px² light chips on 3941's rim ink band
  between the front studs: the front ends of the y=4 ring-floor strip
  (Ring r8→16 annulus, real surface — LDView shows it as a tapered
  lens), previously buried under the bogus full-cylinder stud ink.
  census-K→L comparison proved they appeared exactly at ecf771e. They
  passed every `_donate_escaped_spurs` gate but their only seam
  neighbor (the axle-boss wall, `('g',368)`) paints LATER, and the pass
  only donated later→earlier. New fallback: a later-painting receiver
  is allowed when the piece has no open link to its own core and its
  uncovered seam (esc − raw ink, length ≥0.5) runs ≥95% along that one
  receiver. Under-ink escapes stay put. Tests:
  `test_stranded_spur_donated_to_later_single_seam_neighbor` (unit),
  `test_3941_ring_floor_chips_donated` (integration, chip windows).

## Baselines

- **census-M** (`~/.claude-msb/jobs/0bc8b81a/tmp/census-M/`, 48 parts,
  256 flat3, post-dcceaf2) is current. vs census-L: 11 byte-diffs, all
  inspected — 3941 (chips donated, the fix), 2654a/4589 (small dark
  wedge notches removed, improvement), 3001/3660b/3673/87580
  (sub-canvas-pixel neutral sliver tone swaps), 15573/32062/3713/4740
  (AE=0 at zoom 8 — invisible under-ink ownership moves).
- census-L = post-ecf771e (stud10), census-K = post-2fc12a0.
- Byte-diff gate is HARD (2fc12a0): byte-diff ⇒ real change, vs
  census-M or newer.

## Open items

1. **Light-on-light pinch hairlines** (3941 e3/e23 wedge, ~0.07 px²):
   still benign/unpinned — invisible at every inspected zoom. The
   visible artifact previously filed under this item turned out to be
   the ring-floor chips (now fixed). Only revisit if a part shows a
   VISIBLE uncovered light seam.
2. **Performance**: donation pass still doubles fill_ops on hole-heavy
   parts; suite ran 4.5 min this session (loaded), census ~10 min.
   Determinism test adds ~65s.
3. **Stock-render comparison (07-07)**: 3700 stock image never arrived.
4. **LDraw/LDView hosted pinning**: when renderer is declared done,
   upload the vendored snapshot as a release asset + hash-verify in
   setup-ldview.sh.

## Verification workflow

- Full suite: `.venv/bin/python -m pytest -q` (298, ~4.5 min)
- Contact sheet (labeled): `scripts/render-contact-sheet.sh [out-dir]`
- One part: `.venv/bin/python -m brick_icons.cli <id> --format svg
  --shading outline --shade-style flat3 [--part-label] --out <dir>`
- Census A/B: render `--list parts.txt` twice (defaults 256×170 + flat3
  match baselines), byte-diff SVGs vs census-M.
- 1024 stroke parity: `--format both --shading outline --width 1024
  --height 1024` (NO flat3, NO --mode gray — outline mode's .gray.png is
  the LDView line-art reference; `--mode gray` gives the SHADED
  reference), then resvg at 1024 + `magick compare -metric RMSE`;
  ~0.019-0.02 normalized ≈ AA floor (3941 0.0198, 4032a 0.0193
  post-fix). Script: `~/.claude-msb/jobs/eb7c836f/tmp/parity_compare_h.sh`.
- Layer-split triage: zero out `stroke-width="0.8"` + `fill` → strokes
  layer; zero out `stroke-width="2.00"` → fills layer.
- Probe scripts: `~/.claude-msb/jobs/eb7c836f/tmp/` probe33/36/34/37/
  39/40 (see 07-17a handoff); `~/.claude-msb/jobs/0bc8b81a/tmp/`
  probe_gate*.py (donation-gate trace), probe_plot.py (fill boundaries
  vs true-width strokes overlay), probe_members.py (emitted element →
  source faces).
