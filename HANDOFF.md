# Handoff — 2026-07-17: stud10 truncation rendered; 4032a rim item closed

Working tree on `main`, clean. 296 tests passing. All commits pushed
through `ecf771e`.

## What this session did

- `36e2280` — committed the 2026-07-16 handoff doc.
- `ecf771e` — **stud10 alias removed** (was `ALIAS_REFS = {"stud10.dat":
  "stud.dat"}`, from 0ad7e47). Mike flagged that studs on round parts
  (4032a, 3941, cones) rendered as full cylinders where the real part
  clips them at the body's r=20 boundary. stud10 now recurses: its
  3-4cyli/3-4edge/3-4disc substitute at true 270°, the faceted truncation
  quads shade as facets. The stripes/tone-band artifacts that motivated
  the alias no longer appear (absorbed by plane-merge, angular-coverage
  seam suppression, orphan cull). Verified clean on 4032a/3941/3943b/6233
  at 512–4200 px. Test `test_flatten_recurses_stud10_truncation` pins it.
  Memory: `stud10-truncation-rendered`.

- **Open item 1 (4032a side-wall rim faceted) CLOSED — no defect.**
  Characterization: the y=4 rim is the grip-groove top edge (4 straight
  70.7° chords + notch-corner chord pairs — already arc-fitted where
  appropriate); the y=0 top-face rim mixes exact 1-8cylo 45° arcs with
  authored planar notch-chamfer cut edges (r 20→19.66→20). LDView draws
  those same chords. Post-fix 1024 stroke parity: RMSE 0.0193 (4032a) /
  0.0198 (3941) — at the AA floor. The old "faceted vs smooth master"
  impression came from the aliased full-cylinder studs + comparing crisp
  vector strokes against blurry upscaled raster masters. A
  mixed-chain/near-circle arcfit would be stylization DIVERGING from the
  reference (the fabrication-guard phantom-arc class) — only revisit if
  Mike asks for smoother-than-LDView styling.

## Baselines

- **census-L** (`~/.claude-msb/jobs/eb7c836f/tmp/census-L/`, 48 parts,
  256 flat3, post-ecf771e) is current. vs census-K: byte-diffs on exactly
  3941 + 4032a (the stud10 fix), all 46 others byte-equal.
- census-K = post-2fc12a0 (pre-stud10), census-J = post-bbf584b.
- Byte-diff gate is HARD (2fc12a0): byte-diff ⇒ real change, vs census-K
  or newer.

## Open items

1. **Residual light-on-light seam** at 3941's pinches (~0.07 px² stroke
   reach, e3/e23 wedge): needs seam-following, not donation. Unchanged.
2. **Performance**: donation pass still doubles fill_ops on hole-heavy
   parts; suite ~17 min loaded (~8 min quiet), census ~12 min.
   Determinism test adds ~65s.
3. **Stock-render comparison (07-07)**: 3700 stock image never arrived.
4. **LDraw/LDView hosted pinning**: when renderer is declared done,
   upload the vendored snapshot as a release asset + hash-verify in
   setup-ldview.sh.

## Verification workflow

- Full suite: `.venv/bin/python -m pytest -q` (296, ~8 min quiet machine)
- Contact sheet (labeled): `scripts/render-contact-sheet.sh [out-dir]`
- One part: `.venv/bin/python -m brick_icons.cli <id> --format svg
  --shading outline --shade-style flat3 [--part-label] --out <dir>`
- Census A/B: render `--list parts.txt` twice (defaults 256×170 + flat3
  match baselines), byte-diff SVGs vs census-L.
- 1024 stroke parity: `--format both --shading outline --width 1024
  --height 1024` (NO flat3, NO --mode gray — outline mode's .gray.png is
  the LDView line-art reference; `--mode gray` gives the SHADED
  reference), then resvg at 1024 + `magick compare -metric RMSE`;
  ~0.019-0.02 normalized ≈ AA floor. Script: `tmp/parity_compare_h.sh`.
- Layer-split triage: zero out `stroke-width="0.8"` + `fill` → strokes
  layer; zero out `stroke-width="2.00"` → fills layer.
- Probe scripts in `~/.claude-msb/jobs/eb7c836f/tmp/`: probe33/36 (cull
  reports), probe34 (op-graph), probe37 (4032a rim chain anatomy),
  probe39/40 (emitted arc spans / analytic op dump per part).
