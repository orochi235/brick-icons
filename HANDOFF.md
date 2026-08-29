# Handoff — printed parts, mid phase 2

On branch **`decal-unwrap`**, 19 commits ahead of `main`, clean. 378 tests pass.
Not merged, no PR.

**Read these, in order — they carry the design and the task list:**
- `docs/superpowers/plans/2026-08-28-decal-unwrap.md` — its Status block says
  which tasks are done and with which commit. **Start at Task 8.**
- `docs/superpowers/specs/2026-08-28-printed-parts-design.md` — both phases

## What works now

All four printed specimens paint their print in the right LDraw colours, on flat
and curved carriers alike. The 18 unprinted specimens are byte-identical to
`debug/unwrap/before.sha`; every change is gated on `color != 16`, which is why.

`scripts/proof-decals.py` builds the proofing PDF — each part's decal laid flat
beside LDView's own colour render, labelled, in a grid. It caches per part,
takes `--jobs`, and `--list` accepts a long file. `scripts/render-references.py`
does the same comparison for icon output rather than the flat decal.

## What is still wrong, and why it is one thing

Buttons and stripes are ringed with strokes that a print should not have; the
panel's corners are square where the part rounds them; the panel still emits as
six paths rather than one; stray spurs sit below it. These look like four bugs
and are one: the union, the shape recovery and the stroking all still happen in
PROJECTED space, where a panel is 36 mutually non-coplanar facets seen through a
camera. In UV it is a rounded rectangle with eight holes.

That is what Tasks 8-13 do, and it is why the projected-space fixes each landed
only partly. Do not keep patching there.

## Decisions from conversation that the code does not show

- **Every printed part goes through the unwrap — no bypass for flat carriers**,
  whose map is the identity. One path means flat cannot drift, and unwrapping
  dissolves authored faceting rather than inheriting it.
- **Fit rounded rectangles before circles.** It is the commonest decal shape and
  collapses dozens of facets plus four corner fans to one `rect` with an `rx`.
- **Subtract enclosed regions; do not tile around them.** The buttons and a
  frame's interior are holes, not gaps between neighbours. Letting them split a
  region is what produced the strips of separately stroked fragments.
- **Decoration is ink, not relief:** no shading ramp, and its boundary is not a
  crease, so it should not stroke. The no-stroke half is NOT implemented.
- **A decal is a stack of nested regions in different colours** — border, solid
  background, shape — confirmed in the data (`3068bd0f` carries 10 black facets
  under 12 white). They are coplanar, so paint order cannot come from depth;
  authored order is the only ordering available, and `out["tri"]` preserves it.
- **LDView is the reference, structurally not numerically.** It renders one part
  at two fidelities (smooth where a stock primitive was referenced, faceted
  where the author wrote quads), so never pixel-gate against it.
- **Raster/texture scraping is rejected.** LDView gives a projected view, not an
  unwrapped texture; a cylinder's wrap cannot be recovered from one render. The
  spec separately rejected raster decals with measurements.

## Traps that cost time here

- **Subagents park on long commands.** Three ended their turn waiting on a
  backgrounded pytest whose notification reaches the controller, not them. Give
  them only fast targeted tests; run the full suite and renders as controller.
- **`~Moved to` redirect files.** `from_ref` returns None for
  `48\5-24co10.dat`, but `flatten` follows the redirect and the target IS a
  primitive. Testing `from_ref` alone will mislead you about which geometry path
  a part takes — it misled me into a wrong diagnosis of the cone.
- **Whole-dict equality assertions** break when a key is added to `tri_meta` or
  a face dict. Grep before adding one.
- **Test triangles must be wound CCW** or `faces_from_tris` culls them and the
  test dies on an index error rather than its assertion.

## Open, unplanned

- **`3040bp08`'s lamps and `3941p01`'s buttons stroke** where they should not.
- **`absorb_wall_facets` is a fourth colour-blind merge**, unguarded. No part is
  known to hit it; add the guard only with a part that demonstrates it.
- **`4740p03`** dies with `shapely.errors.GEOSException: TopologyException`.
- **Linear gradient stops are uncapped** (`shade.py`), so `3960p01` carries 640.
- **Ink pockets** on `30137`, `98283`, `32062` that the user does not want.
