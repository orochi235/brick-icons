# Handoff — printed parts, phase 2 complete

On branch **`decal-uv`**, 6 commits ahead of `main`, clean. 413 tests pass.
Not merged, no PR.

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

## What is still open

- **Strokes still ring `3040bp08`'s lamps and `3941p01`'s buttons.** Both are
  real geometry (analytic discs), not decoration, so they stroke as relief.
  Deciding they should not is a spec question, not a bug in the unwrap.
- **`4740p03`** dies with `shapely.errors.GEOSException: TopologyException`.
- **Linear gradient stops are uncapped** (`shade.py`), so `3960p01` carries 640.
- **Ink pockets** on `30137`, `98283`, `32062` that the user does not want.
- **Spheres** (`3626bp01`) bind to no carrier and pass through unchanged, per
  the spec.

## Traps

- **Regenerating the specimen baseline costs ~8 minutes.** `debug/` is
  gitignored, so `before.sha` does not survive. Rebuild it with a worktree at
  `main` and symlink `vendor/` in. `3649` alone takes 5 of those minutes.
- **`cmd | tail` buffers the whole run**, so a backgrounded suite or render
  looks hung until it exits. Redirect to a log and tail the file.
- **Subagents park on long commands.** Give them only fast targeted tests.
- **`~Moved to` redirect files:** `from_ref` returns None for `48\5-24co10.dat`
  though `flatten` follows the redirect to a real primitive.
- **Whole-dict equality assertions** break when a key is added to `tri_meta` or
  a face dict. Grep before adding one.
- **Test triangles must be wound CCW** or `faces_from_tris` culls them and the
  test dies on an index error rather than its assertion.
