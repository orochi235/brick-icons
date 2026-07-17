# Handoff — 2026-07-16: fill-layer byte determinism fixed, pushed

Working tree on `main`, clean once this file is deleted (untracked scratch —
delete once absorbed). 296 tests passing. All commits pushed through
`2fc12a0`.

## What this session did (1 commit)

`2fc12a0` — **fill-layer byte nondeterminism SOLVED** (was open item 6).
Root cause: `shade._loop_cut_merged` iterated its `interior` SET of
merge-root keys — tuples with a string tag (`("g", n)`/`("i", n)`/
`("p", plane)`) — so iteration followed the per-process string hash seed,
and the absorb step unioned spill pieces in seed-dependent order, rotating
shapely ring start vertices in the emitted fill `d`. Fix: iterate in
`merged`'s insertion order. Verified: pixel-identical to census-J (AE=0
at 2400px); seeds 1 vs 2 byte-equal on 3941/3713/4032a/6541/2654a/60474/
3001; new regression test `test_svg_bytes_deterministic_across_hash_seeds`
(subprocess renders, ~65s, needs LDraw lib). Diagnostic that cracked it:
`PYTHONHASHSEED=0` twice → byte-equal ⇒ string-hash-order bug, not id().
Swept the emission path: `kinds`/`emitted`/`seam_keys`/`ks_set` are
membership-only; no other hash-ordered iteration found. Memory:
`fill-byte-jitter-fixed`.

## Byte-diff gate is HARD again

Byte-diff ⇒ real change; byte-equal ⇒ no change — for renders made
post-2fc12a0. Baselines cut PRE-fix (census-J and earlier) byte-differ vs
post-fix renders on loop-cut parts with zero pixel change: compare against
census-K or newer only.

## Baselines

- **census-K** (`~/.claude-msb/jobs/eb7c836f/tmp/census-K/`, 48 parts,
  256 flat3, post-2fc12a0) is current — parts list at `census-K.parts.txt`.
  Expected byte-diffs vs census-J on loop-cut parts are the fix
  canonicalizing ring starts, not regressions (3941 confirmed AE=0).
- census-J = post-bbf584b (pre-fix), census-H = post-724ab8b.
- 1024 parity: parity-H (pre-724ab8b) in job tmp; parity-2654a has the
  post-cull 2654a pair (RMSE 1500 ≈ AA floor).

## Open items

1. **4032a side-wall rim faceted — CHARACTERIZED**, outer contour smooth
   (724ab8b); interior stroke chain still faceted. Full fix needs
   mixed-chain/near-circle arcfit extension. Bigger design task; unpinned.
2. **Residual light-on-light seam** at 3941's pinches (~0.07 px² stroke
   reach, e3/e23 wedge): needs seam-following, not donation. Unchanged.
3. **Performance**: donation pass still doubles fill_ops on hole-heavy
   parts; suite ~17 min on a loaded machine (~8 min quiet), census ~12 min.
   New determinism test adds ~65s (two subprocess renders of 3941).
4. **Stock-render comparison (07-07)**: 3700 stock image never arrived.
5. **LDraw/LDView hosted pinning**: when renderer is declared done, upload
   the vendored snapshot as a release asset + hash-verify in
   setup-ldview.sh.

## Verification workflow

- Full suite: `.venv/bin/python -m pytest -q` (296, ~8 min quiet machine)
- Contact sheet (labeled): `scripts/render-contact-sheet.sh [out-dir]`
- One part: `.venv/bin/python -m brick_icons.cli <id> --format svg
  --shading outline --shade-style flat3 [--part-label] --out <dir>`
- Census A/B: render `--list parts.txt` twice (defaults 256×170 + flat3
  match baselines), byte-diff SVGs — post-2fc12a0 a byte-diff is a REAL
  change (no more rasterize-to-confirm step against post-fix baselines).
- 1024 parity: `--format both --mode gray --width 1024 --height 1024`
  WITHOUT flat3 (gray masters are stroke-only; flat3 fills blow up RMSE),
  then `parity_compare_h.sh` pattern in job tmp.
- Layer-split triage: zero out `stroke-width="0.8"` + `fill` → strokes
  layer; zero out `stroke-width="2.00"` → fills layer.
- Probe scripts in `~/.claude-msb/jobs/eb7c836f/tmp/`: probe30/31 (2654a
  crumb triage), probe33 (cull report + dash status), probe34 (op-graph
  neighborhood), probe36 (production-matching cull report, any parts).
  Hash-seed determinism probe: `tmp/nondet/probe_interior.py`.
