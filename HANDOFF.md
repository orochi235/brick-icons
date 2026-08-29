# Handoff — 2026-08-28: LDraw color codes + printed parts

Working tree on `main`, clean. 359 tests passing.

**Read these first, in order — they carry the design, not this file:**
- `docs/superpowers/specs/2026-08-28-printed-parts-design.md` — both phases
- `docs/superpowers/plans/2026-08-28-ldraw-color-codes.md` — phase 1 tasks

## Where phase 1 stands

Done and committed (Tasks 2–6, 8–10): `brick_icons/colors.py` resolves
`--part-color` as hex, LDraw code, or color name against the vendored
LDConfig; `load_config` resolves once so nothing downstream changed;
`--list-colors`; README; the `_ink_lens_pockets` crash fix; and
`scripts/measure-decal-offsets.py`.

**Task 7 (byte-diff gate) was in flight when this was written** and is the one
thing to confirm before trusting the phase. A true pre-change baseline renders
from a worktree at `28f895e` (the last docs-only commit), because the in-repo
`debug/colorcodes/baseline` was regenerated *after* the code changes and is an
after-shot. Compare that worktree's specimen SVGs against
`debug/colorcodes/baseline`; expect byte-identical, since specimens pass no
`--part-color`.

Task 11 (adding printed parts to `specimens.txt`) is deliberately unstarted —
it needs a human to pick which of the 12 rendered samples to carry.

## Decisions made in conversation that the code does not show

- **Codes and names raise; hex keeps its silent gray fallback.** Deliberate:
  a malformed hex string stays backward-compatible, a typo'd name should not
  silently render gray.
- **Hex is canonicalized to lowercase**, which changed the `-DefaultColor3`
  flag's case and required updating `test_build_argv_part_color_optional`.
  LDView hex is case-insensitive, so renders are unaffected.
- **Raster textures were considered and rejected for phase 2** — see the spec.
  The short version is that affine strips work on cylinders (the map is
  separable) but fail on cones by 44–88 px, and no texture asset exists for the
  ~4,750 non-TEXMAP printed parts anyway.

## Open, none of it planned yet

- **Ink pockets the user does not want** in `docs/gallery`: `30137` (4 black
  paths, three of them one-per-log-top), `98283` (5, reading as ragged
  corners), `32062` (1). Cannot simply be disabled — that inking is what closed
  the graze-shard and pinhole classes. Needs its own task with a byte-diff gate.
- **Linear gradient stops are uncapped.** `shade.py:1313` emits one stop per
  `grad_sample`; radial gradients bin to 8 via `_radial_focal_stops`. Hence
  `3960p01` carrying twelve 48-stop linear gradients (640 stops against the
  plain dish's 28). Binning linear stops the same way would shrink every part.
- **`4740p03`** dies with `shapely.errors.GEOSException: TopologyException:
  side location conflict` on a normal outline render. Undiagnosed.
- **Flat prints render as nothing at all** — the largest phase 2 item by part
  count, and the measurement script cannot yet size its tolerance because
  distance-from-axis is the wrong metric for a flat face.

## Phase 2

Not planned yet, by choice: its plan was to wait on real carrier-offset
numbers, which now exist (0.5 LDU binds every curved carrier). The spec's
phase 2 section is ready to turn into tasks.
