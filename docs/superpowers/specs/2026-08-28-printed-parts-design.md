# Printed parts: color codes and decal unwrap — design

**Date:** 2026-08-28
**Status:** proposed
**Predecessors:** 2026-06-28-primitive-substitution-design.md,
2026-07-05-primitive-classes-design.md

Two phases, built in order. Phase 1 is a prerequisite: a printed part cannot be
painted at all until the renderer can resolve an LDraw color code.

## Problem

**Phase 1.** `--part-color` accepts only `0xRRGGBB`. LDraw's palette — 322
`!COLOUR` entries in the vendored `vendor/ldraw/LDConfig.ldr` — is present but
nothing reads it.

**Phase 2.** Printed parts (4,764 `pNN`, 92 `pb`, 20 `pr` in the vendored
library) render as embossed outlines rather than print, and their decal
geometry does not sit flush on curved walls. Measured on `3941p01` (Brick 2x2
Round with Black Panels with Buttons):

- `hlr.flatten` never reads the color code — `tri_meta` carries only
  `certified` and `invert`. The black panel is filled in body color, so the
  print reads as engraving.
- The decal is built from **flat** primitives (16 `4-4ndis`, 16 `4-4disc`, 8
  `1-4ndis`, 8 `1-4chrd`) lying against a **curved** wall (2 `4-4cyli`, 2
  `1-4cyli`). The sagitta between the flat chords and the true cylinder opens a
  white seam along the panel's lower edge. The LDView reference render shows
  the same gap, so it is authored into the part, not introduced by the tracer.
- Arcfit catches most decal circles but not all: 74 of 111 paths carry arcs, 37
  are pure polylines, and one 25-segment polygon button sits among neighbors
  that came out as clean 5-arc ellipses.
- The only black in the output is 6 `_ink_lens_pockets` paths — ink artifacts
  sitting where the print should be.

`library.py` also excludes `"Pattern"` and `"Sticker"` titles from the sweep,
so printed parts never enter the census today.

## Phase 1 — LDraw color codes

New module `brick_icons/colors.py`, the only code that knows LDConfig exists.

Parses `!COLOUR` lines into `Color(code, name, rgb, alpha)`, cached per path.

`resolve(spec, ldraw_dir) -> (hex_str, alpha | None)` applies an explicit
precedence rule, because `--part-color 16` is already valid hex today:

1. `0x…`, `#…`, or six hex digits → hex passthrough, unchanged behavior
2. all digits, three characters or fewer → LDraw code
3. otherwise → name, normalized on case, `_`/`-`/space, and `gray` ≡ `grey`
4. no match → `ValueError` naming the spec

`shade.parse_hex_color` currently falls back to gray on garbage input. Codes and
names raise instead; the hex path keeps its silent fallback so existing configs
behave identically.

**Wiring.** Resolve once in `load_config`, writing canonical `0xRRGGBB` back
into `part_color`. Both consumers — the LDView `-DefaultColor3=` flag in
`render.py` and `shade.parse_hex_color` in `cli.py` — then see exactly what they
see today. Nothing downstream changes.

**Opacity.** `load_config` tracks which keys were explicitly set (toml keys ∪
non-`None` overrides). If `opacity` was not among them and the resolved color
carries `ALPHA`, set `opacity = alpha / 255`. So `--part-color 36` yields trans
red at 0.5 and an explicit `--opacity` always wins.

**`--list-colors`** prints `code  name  #hex  [alpha]` and exits.

## Phase 2 — decal unwrap

The decal's carrier polygons are flat; the wall is curved. Rather than render
the decal where the part author placed it, map it into the carrier surface's
own parameter space and re-emit it on the exact analytic surface the wall
already uses. The two are then coincident by construction and the seam cannot
open.

**Carriers.** Cylinders and cones for the unwrap — the surfaces already modeled
as `Cylinder` and `Cone` primitives. Spheres (minifig heads) are out of scope.

Flat carriers need no unwrap, but they are not free, and they are the worst case
today: a flat decal is coplanar with its face, so the coplanar plane-merge
unions it into the face and the print vanishes outright. Measured across a
13-part sample, `3001p01`, `3004p01`, `3068bp00`, `3069bp01`, `3960p01`,
`4740p01` and `6141p01` render pixel-identical to undecorated bricks, while only
the curved carriers show anything at all. Keying that merge by (carrier, color)
rather than by plane alone is therefore what makes flat prints appear, and it is
the single highest-value piece of phase 2 by part count.

**Assignment.** A decal facet group binds to a carrier when its vertices lie
within tolerance of an existing analytic surface in the same part — same axis,
radius within tolerance. On no match, the geometry is left as authored, so an
unrecognized construction degrades to today's output rather than breaking.

`scripts/measure-decal-offsets.py` settles the tolerance. Across curved
carriers the decal sits essentially *on* its surface: `3960p01` 0.001,
`3062bp01` 0.006, `3626bp01` 0.011, `3941p01` 0.074, `4740p01` 0.150,
`3040bp08` 0.345 LDU. **0.5 LDU binds every observed case** with an order of
magnitude of headroom under the smallest real feature (a stud is 12 LDU
across). No bimodality, so one tolerance suffices.

This also corrects an earlier reading of `3941p01` as a decal at radius 19.65
against a wall at 20, which implied the unwrap must snap geometry outward.
19.65 is a *body* radius too; decal and carrier are already co-radial to within
0.074 LDU. There is no snap, and consequently no risk of the snap pushing a
near-limb region across the silhouette.

The flat-carrier case needs a different measurement. Distance from the part
axis records position *along* a flat face rather than offset *from* it, which
is why `6141p01` and `3001p01` report 6.5 and 2.0 LDU. Those are artifacts of
the metric, not standoffs; a plane-offset measure is needed before the flat
path is tuned.

**Unwrap and re-emit.** For a cylinder of radius `r`, each vertex maps to
(θ, h) in the primitive's local frame; the exact `R^-1` local frame built for
elliptical primitives is reused rather than recomputed. The boundary is
re-projected onto the carrier at the *carrier's* radius, closing the sagitta
gap, and fed through arcfit so the buttons emit consistent `A` commands instead
of the current arc/polygon mix.

**Painting.** Each unwrapped region carries its LDraw code from phase 1 and
fills flat, with interior facet edges inside a region suppressed — otherwise
every facet boundary inks and the print reads as a mesh.

**Dump the unwrap as its own stage.** The unwrapped decal — the decal laid flat
in (θ, h) before re-projection — is written as an SVG under `--debug-dir`,
alongside the existing per-stage PNGs that `cli._stage` emits. It earns its
place twice over: it is the only way to see whether a carrier bound correctly
without reading projected output, and being 2-D and camera-independent it is
far easier to assert on in tests than a rendered view. Test the unwrap against
this artifact; test the projection separately.

**Clipping is mostly not needed.** Decal facets are ordinary geometry, so the
existing HLR occlusion pass already clips them at the silhouette and behind
studs — visible today in `3941p01`, whose leftmost buttons are cut by the
brick's contour with no decal-specific code.

The one case the unwrap itself creates: snapping a decal from its authored
radius to the carrier's (19.65 → 20 on `3941p01`) moves it outward, which near
the limb can push a region across a silhouette it previously sat inside. The
limb is an exact θ, so this clips as a half-plane in UV before projection — for
a decal circle, a restriction of the parameter interval to `cos t <=
(θ_limb - θc)·R/ρ`, closed with a chord at constant θ that projects to a
straight generator line. It emits pre-clipped path data, needing no
`<clipPath>` and no extra elements. Treat it as a guard, not a phase.

**Rejected: raster textures via affine strips.** Under orthographic projection
the cylinder map is separable — the axial direction is a pure translation
independent of θ — so a strip's quad is an exact parallelogram (measured corner
closure 0.000000 px) and SVG's affine `matrix()` lands all four corners with no
geometric seam. The approach is therefore viable on cylinders, with interior
error falling as Δθ²: 7.01 px at 4 strips, 0.44 px at 16, 0.11 px at 32.

It fails on cones. Separability requires constant radius; once radius varies
with height the quad is no longer a parallelogram and one 29° strip mismatches
by 44 px on a 20→12 taper, 88 px on 20→4. Printed cones (`3942bp01`) are in
scope. On the same decal the vector route also measures better on every axis —
16 elements, 7.0 KB, 0.023 px max curve error, against 16 `<image>` elements,
28.9 KB and 0.44 px — and stays resolution-independent.

Independently, there is nothing to apply: LDraw ships bitmaps only for the 124
`!TEXMAP` parts (vendored in `parts/textures/`), and the other ~4,750 printed
parts have geometry alone. TEXMAP parts already degrade safely — the parser
skips `0 !:` lines and takes the `!TEXMAP FALLBACK` geometry.

## Incidental fix

`--line-width 0 --silhouette-width 0` on `3941p01` raises `ValueError: not
enough values to unpack (expected 2, got 0)` at `shade.py:1230`, where
`_ink_lens_pockets` returns empty instead of a 2-tuple. `4740` with the same
flags still renders, so it is the pattern geometry reaching an unguarded
return, not a general regression.

A second crash, unfixed and not yet diagnosed: `4740p03` dies with
`shapely.errors.GEOSException: TopologyException: side location conflict`
during a normal outline render. It was the only failure in a 13-part printed
sample, so it is rare rather than systemic, but printed geometry evidently
reaches states the fill pipeline does not.

## Testing

- **Phase 1:** `tests/test_colors.py` — LDConfig parsing, code lookup, name
  normalization, the `16` vs `000016` precedence rule, unknown spec raises.
  `tests/test_config.py` — trans alpha sets opacity, explicit opacity wins.
- **Phase 2:** the specimen byte-diff gate must stay hard. Unprinted parts are
  byte-identical after phase 2; only printed parts may change. A new printed
  specimen set covers a cylinder carrier (`3941p01`), a cone carrier
  (`3942bp01`) and a flat carrier (a `3068`-family print).
- A seam regression test asserting no background-colored region inside the
  decal boundary on `3941p01`.

## Open question, deferred to implementation

At 150px the `3941p01` buttons collapse into a dark mass — the print is finer
than the format's resolution. Whether printed parts need a minimum feature size,
or a flag that drops decoration below some scale, should be settled against
rendered output rather than decided now.
