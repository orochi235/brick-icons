# Handoff — printed parts, phase 2 complete

Phase 2 and the decal orientation fix are both on **`main`**. Nothing is
unmerged. 432 tests pass. `6372ffd`'s message and `tests/test_orientation.py`
carry the orientation diagnosis; only flat carriers moved, so the 18 unprinted
specimens stayed byte-identical.

**The durable record is the plan:**
`docs/superpowers/plans/2026-08-28-decal-unwrap.md`. Its Status block lists
every task with its commit, and a section on where the plan was wrong — read
that before trusting any instruction in the task bodies, which are historical.
The spec is `docs/superpowers/specs/2026-08-28-printed-parts-design.md`.

## What works now

Decoration binds to the analytic carrier it lies on, unwraps into that
carrier's parameter space, unions and recovers its shape there, and
re-projects onto the exact surface. `3941p01`'s panel is one path with eight
holes and round corners; `3068bp00`'s arrow is one path; `3040bp08`'s border
is one frame with an interior ring; `3942bp01`'s stripes ride the cone.

Gates, all green: 18 unprinted specimens byte-identical to `main`, four
printed specimens structurally matching LDView, `3941p01` emitting exactly one
`#1b2a34` path. `<part>.unwrap.svg` in `--debug-dir` shows the decal laid flat
— the only way to check a bind without reading projected output.

## Open, and diagnosed but unfixed

The cone's stripes read correctly once the rim seams went: the horizontal
arcs were cutting across them, not the stripe geometry. `_wall_span_face`
samples any span with 40 points (1.9 deg for a 75 deg stripe), so
under-sampling was never in it.

What remains is two artifacts on the cone's top stud, **both present on the
UNPRINTED `3942b`** and absent on `4589`, so neither has anything to do with
decoration:

- **Ragged bore.** The bore wall is an analytic `cyli r=4` (an exact circle);
  the bore floor is 56 flat triangles at y=4 spanning r=3.536-6.0 (a polygon).
  The wall's fill is bounded by the true circle and the floor's by chords, so
  where a chord falls inside the circle the floor does not reach the wall and
  the wall's darker fill shows through as a tab. This is the ring-floor chip
  class. `facet_snap_rims` exists for exactly this but the note at
  `hlr.py`'s `_visible_segments_analytic` says emitting those candidates is
  NOT safe alone: fills snap to the circle while drawn chords stay put, which
  opens slivers. A fix needs the drawn-chord refit too.
- **Debris on the stud's bottom seam**, same region, not separately diagnosed.

- **White decals are invisible** in the proof sheet — the cell background is
  also white (`10049p01`, `26603p01`). The prints may be fine; nobody can
  tell.
- **Organic bodies have no single carrier.** Fixed in the proof sheet: it
  binds per facet and labels what fell off (`3/672 facets · 669
  off-carrier`), so the old slivers are gone. But 183 of the 189 plane cells
  in `out/proof-300.pdf` put under half their facets on the dominant plane —
  a Friends leg is faceted into thousands of one-facet planes and is neither
  a plane nor one curve. The renders are fine; it is the sheet's
  one-carrier-per-part model that cannot describe this class.
- **`4740p03`** dies with `shapely.errors.GEOSException: TopologyException`.
- **Linear gradient stops are uncapped** (`shade.py`), so `3960p01` carries 640.
- **Ink pockets** on `30137`, `98283`, `32062` that the user does not want.
- **Spheres** (`3626bp01`) bind to no carrier and pass through unchanged, per
  the spec.

## Traps

- **The proof sheet is not the renderer.** `scripts/proof-decals.py` fits its
  own carrier from raw geometry; `brick_icons/` binds per facet against
  analytic primitives and `shade._body_planes`. A wrong cell is a sheet bug
  until an actual render disagrees — every minifig torso read as a squashed
  cylinder in the sheet while `--shading outline --shade-style flat3` drew
  them correctly. Render before believing the sheet.
- **Decoration only reaches SVG with a shade style.** Plain
  `--shading outline` emits strokes and no fills, so two differently printed
  parts come out byte-identical and it looks like binding failed. Add
  `--shade-style flat3`.

- **Rendering with `--line-width 0 --silhouette-width 0` is the fastest way to
  tell a stroke artifact from a fill artifact.** It is what proved 3942bp01's
  horizontal band lines were strokes rather than tonal steps, and it surfaces
  ragged fill boundaries the outline would hide.
- **Regenerating the specimen baseline costs ~8 minutes.** `debug/` is
  gitignored, so `before.sha` does not survive. Rebuild it with a worktree at
  `main` and symlink `vendor/` in. `3649` alone takes 5 of those minutes.
- **LDView's colour output is not evidence.** `6636p0c` uses code 85, which
  `LDConfig.ldr` defines as `Medium_Lilac #441A91`; LDView, pointed at that
  same file, paints `#f53193` — a value that appears nowhere in the palette,
  so its internal table is overriding the file it was given. Our colour is
  the one that matches LDraw. (The real Friends tile probably is pink, so
  upstream LDraw is likely the wrong one — but that is not something to
  resolve by reading pixels.) "LDView is structural, not numerical" covers
  colour too.
- **No part IDs live in `brick_icons/`** — they appear only as comment
  witnesses and test fixtures. Every fix so far generalized; a part number
  reaching library code means one did not.
- **`cmd | tail` buffers the whole run**, so a backgrounded suite or render
  looks hung until it exits. Redirect to a log and tail the file.
- **Subagents park on long commands.** Give them only fast targeted tests.
- **`~Moved to` redirect files:** `from_ref` returns None for `48\5-24co10.dat`
  though `flatten` follows the redirect to a real primitive.
- **Whole-dict equality assertions** break when a key is added to `tri_meta` or
  a face dict. Grep before adding one.
- **Test triangles must be wound CCW** or `faces_from_tris` culls them and the
  test dies on an index error rather than its assertion.
