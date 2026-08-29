# Handoff — printed parts, phase 2

Working tree on `main`, clean. 363 tests passing.

**Read these first, in order — they carry the design, not this file:**
- `docs/superpowers/specs/2026-08-28-printed-parts-design.md` — both phases
- `docs/superpowers/plans/2026-08-28-ldraw-color-codes.md` — phase 1 tasks

## Phase 1 is done

Every task in the plan is committed, including the byte-diff gate and the
printed specimens. `--part-color` takes hex, an LDraw code, or a color name.

The gate now baselines to `debug/colorcodes/baseline-v2.sha` (22 specimens),
which supersedes the 18-part Task 1 baseline. Regenerate it with the render
command in the plan's header, into `debug/colorcodes/specimens-new`.

## Decisions the code does not show

- **Codes and names raise; hex keeps its silent gray fallback.** Deliberate:
  a malformed hex string stays backward-compatible, a typo'd name should not
  silently render gray.
- **Hex is canonicalized to lowercase**, which changed the `-DefaultColor3`
  flag's case and required updating `test_build_argv_part_color_optional`.
  LDView hex is case-insensitive, so renders are unaffected.
- **The four printed specimens are a baseline, not a demo.** None of them
  renders its print. `hlr.py:62` `flatten()` never reads column 2, the LDraw
  colour code, so decoration reaches the pipeline geometrically identical to
  its carrier. What little shows is accidental: the cone's stripes are
  `5-24co*` patches at the carrier's own radii, so only their seams survive;
  the flat prints are coplanar and the plane-merge unions them away; the three
  circles on `3040bp08` survive only as `4-4disc` primitives; and `3941p01`'s
  black dots are ink-pocket fill, not the panel — the real part is the inverse
  (black panel, white buttons). Keep them out of `docs/gallery/` and the README
  until phase 2 lands.
- **LDView renders the same parts in LDraw's own colours**, at the same angle,
  with no new dependency — `render.py` already drives it. That is the phase-2
  target, and it is cheaper and more diffable than a photograph.
- **Raster textures were considered and rejected for phase 2** — see the spec.
  Affine strips work on cylinders (the map is separable) but fail on cones by
  44–88 px, and no texture asset exists for the ~4,750 non-TEXMAP printed parts.

## Phase 2 is ready to plan

Its plan was deliberately held until real carrier-offset numbers existed. They
do now — 0.5 LDU binds every curved carrier (`scripts/measure-decal-offsets.py`).
The spec's phase 2 section can be turned into tasks as-is.

One thing has to land before any of it: `flatten()` must carry the LDraw colour
code (`tri_meta` is the natural place), and the coplanar plane-merge must re-key
on (plane, colour). Until then decoration is indistinguishable from its carrier
and there is nothing to unwrap.

**Every printed part goes through the unwrap stage — no bypass for flat
carriers.** A planar carrier's unwrap is the identity map, a degenerate case of
the general one, not a shortcut around it. Two reasons: one code path means flat
cannot drift into a special case, and the standalone texture the stage emits is
the artifact worth testing, being 2-D and camera-independent.

Flat prints are the largest class by part count and the one
`scripts/measure-decal-offsets.py` cannot size, because distance-from-axis is
the wrong metric for a flat face. A planar carrier binds by plane distance
instead; that tolerance still needs picking.

## Open, none of it planned

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
