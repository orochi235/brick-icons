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

**Carriers.** Cylinders and cones only — the surfaces already modeled as
`Cylinder` and `Cone` primitives. Flat carriers (tile prints) pass through
untouched: they are coplanar with their face already and have no seam. Spheres
(minifig heads) are out of scope.

**Assignment.** A decal facet group binds to a carrier when its vertices lie
within tolerance of an existing analytic surface in the same part — same axis,
radius within tolerance. On no match, the geometry is left as authored, so an
unrecognized construction degrades to today's output rather than breaking.

**Unwrap and re-emit.** For a cylinder of radius `r`, each vertex maps to
(θ, h) in the primitive's local frame; the exact `R^-1` local frame built for
elliptical primitives is reused rather than recomputed. The boundary is
re-projected onto the carrier at the *carrier's* radius, closing the sagitta
gap, and fed through arcfit so the buttons emit consistent `A` commands instead
of the current arc/polygon mix.

**Painting.** Each unwrapped region carries its LDraw code from phase 1 and
fills flat, with interior facet edges inside a region suppressed — otherwise
every facet boundary inks and the print reads as a mesh.

**Rejected: raster textures.** LDraw ships bitmaps only for the 124 `!TEXMAP`
parts (PNGs vendored in `parts/textures/`); the other ~4,750 printed parts have
geometry alone, so there is nothing to apply. Laying a bitmap on a curved wall
in SVG also needs per-strip `<image>` elements with seams between them, against
the one-element-per-surface rule. TEXMAP parts already degrade safely — the
parser skips `0 !:` lines and takes the `!TEXMAP FALLBACK` geometry.

## Incidental fix

`--line-width 0 --silhouette-width 0` on `3941p01` raises `ValueError: not
enough values to unpack (expected 2, got 0)` at `shade.py:1230`, where
`_ink_lens_pockets` returns empty instead of a 2-tuple. `4740` with the same
flags still renders, so it is the pattern geometry reaching an unguarded
return, not a general regression.

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
