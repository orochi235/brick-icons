# Handoff: the wall's UI pass (brick-icons + pezlie)

**Written 2026-09-15. Live work, several threads. Nothing here is pushed.**

Two repos move together: `~/src/pezlie` (the `wall/` library, branch `main`) and
brick-icons' `lab/`. brick-icons pins pezlie by sha in `lab/package.json`, so a
pezlie change lands in brick-icons only after a push and a pin bump.

**Another session is working in both trees.** In the main brick-icons checkout it holds
`lab/src/corpus/paint.ts`, `lab/src/corpus/draw2d.ts`, `HANDOFF.md`,
`pyproject.toml`, `uv.lock`, `tests/test_occt.py`, `tests/test_cqsvg.py` and
`tests/goldens/defects.toml` (as of 2026-09-15 23:57); and in pezlie
(`bakery/**`, `levels.ts`, `useSheets.ts`, `useLooseThumbs.ts`,
`useVectorThumbs.ts`, `WallView.tsx`, `cacheReport.ts`, `urls.ts`,
`wall/README.md`). Stage per file, and read `git diff --cached` before every
commit: a README hunk of theirs was caught mid-staging once already.

## Merged, and the trap that came with it

`wall-header` is merged into local `main` (unpushed): the `/wall` header
controls, the lab in every page's title menu, and the printed/sticker badges at
top left. **After any merge that moves the pezlie pin, run `npm install` in that
checkout before believing its tests or its dev server.** The merge left the
shared checkout's `node_modules` on the old pezlie, so `WallView` took the
host's `header` FUNCTION as a child node — React's "Functions are not valid as a
React child" — and three `BrickWall` tests failed with the engine toggle absent.
Reinstalling fixed all three; 92 lab tests pass.

`replaces-both-ways` is **merged** -- `9e16bb7` on local `main`, unpushed:
`predecessors` per cell, a `replaces` tag and `tr` badge beside `replaced`, a
badge that jumps back for a single predecessor and falls through to the card for
several, a `Lineage` line in the card and lightbox, `replaces` on its OWN axis
("What it replaced") so the 24 chains stay askable, the legacy wall's corner-row
placement, and one shared `linkedPart` in `paint.ts` for both walls.

The one conflict, `lab/src/corpus/Lightbox.tsx`, resolved as this doc planned:
the tag row keeps main's `subTags`, which drops the category tag now drawn as a
badge above it -- the branch's `detail.part.tags` would have drawn it twice.

Gated on a **stationary copy** of the merge result, not the shared checkout: a
peer edits this tree live and contaminated two earlier runs, the failure set
changing between consecutive runs of the same tree. lab 1195 passed, pytest 1423
passed.

**Four failure classes, none of them this merge. Expect each again:**

- `tests/test_lab_tally.py` (5) reads git, so it fails in any tree that is not a
  real git repo. A `git archive` extraction scores 5 failures where a real
  worktree scores 34/34. Never gate on it from a materialized tree.
- `lab/src/corpus/CorpusWall.test.tsx` is **flaky**. Four different tests in it
  have failed across runs of unchanged trees, all `waitFor` canvas tests. In the
  decisive alternated A/B the branch tip failed while the merge result passed
  36/36 twice. It will keep producing red runs that look like regressions.
- `tests/test_occt.py::test_a_sticker_is_not_clipped_by_the_slope_it_is_stuck_to`
  fails on `bc592f0` as well, at 5.12% against its 5% bound. Pre-existing.
- `src/instruments/partInspector.test.ts` expects `['naive','occt']`, but
  `7080ca3` (Sep 10) narrowed `DEFAULT_SOURCES` to `['occt']`. A stale test on
  `main`: its lab suite is not green on its own.

The `agent-ad4ead163d4041051` worktree can go whenever; its branch is in `main`.
Its `lab/node_modules` and `vendor` are symlinks to the main checkout.

Still the user's call: the `replaces` badge's color and its mirrored `redoBack`
mark. Below about 20px the arrow's direction stops reading and hue alone
separates it from `replaced`, at a hue near the sticker badge's navy. A render
of the pair at badge sizes is on the slopboard, zone `tn-backfill`.

## Done

- **Lightbox title row** (`161156e`, unpushed) -- the title and the year share a
  face and a size. Both had to be stated in `Lightbox.css`: the panel is
  portaled to `.lk-root`, OUTSIDE `.lk-lab`, so the kit's `.lk-lab h1, h2, h3`
  rule never reaches it and its own `font: 13px/1.5 ui-monospace` won for the
  title too. `1.5em` on the panel's 13px is the 19.5px the title already had, so
  the title does not move and only the year rises. Measured headless before and
  after; labeled pair on the slopboard, zone `tn-backfill`.

- **`/corpus` retired from the menu** (`897e91b`, unpushed) -- the menu lists one
  wall: the `/corpus` entry goes and `/wall` takes the plain name `Wall`. The
  dashboard's wall link points at `/wall`, which reads the same query through
  `readWallLink`. `DEFAULT_SOURCE` moved from `CorpusWall.tsx` to `wallHash.ts`.
  **Unlisted, not removed** -- `corpus.html` and its vite entry still answer, so
  old links work, and `lab/src/corpus/` stays because `/wall`, `/bench` and
  pezlie's tests import from it. The user chose unlist-over-delete.

- **part-themes** — merged to brick-icons `main` (`eab2259`). 4,838 printed and
  sticker parts carry a dominant Rebrickable theme (≥80% of their own sets).
- **wall-header** — merged into local `main` (unpushed). `/wall` gets the engine
  toggle, style dropdown and part search; the render lab joins every page's
  title menu.
- **pezlie `f51fd1a`** — badges sized 0.063 × cell with a 0.06 × cell edge gap,
  hidden below 80px cells, and badges sharing a corner drawn as a row (hit test
  included). Review fixes are in flight, see below.

## In flight

- **pezlie badge fixes** (implementer running): strip discs move to the badge
  geometry (not the caption's), rows and pushed captions clamp at the cell's
  midline, plus small test and comment fixes. Then: commit, re-review, push.
- **brick-icons badge data** (not started, needs the pezlie push): move
  `printed` and `sticker` from `STRIP_BADGES` to `CORNER_BADGES` at `tl`, after
  `popular`, in `lab/src/corpus/paint.ts`; bump the pin; check `/wall` headless.

## Half-built: the card as a frame

pezlie has the library half, pushed (`origin/main` at `e4d545b`): `ItemCard`
takes a `cell` rect and draws an opaque frame with an opening over it, details
column flipping side, and `Wall`'s `onPick` hands up the clicked position.
Reviewed twice; the second pass re-measured it in a headless browser (opening
offset 0,0, clicks in the opening reach the canvas). The review's minors landed
in `0deb887`: the opening's rect is cached rather than measured per pointermove,
and both the hover and press rules require the wall's own canvas as the target,
so a panel overlapping the cell no longer counts as the cell.

**The browser pass is the gate this work keeps missing.** jsdom does no layout
and no hit testing, so the unit suite passed while the frame sat 7px off its
cell with its opening sealed. When the wiring lands, run the spec's check at
1280×720 and put the labeled before/after on the slopboard: that is the only
thing that shows the frame following the cell through the glide.

**Wiring `WallView` is blocked**: the other session's uncommitted ladder refactor there
deleted `LOOSE_LEVEL`, and the card's glide was written against its
`ladder.loose`. Wait for their commit, or rewrite the hunks against
`LOOSE_LEVEL`. Until then `wall/test/WallViewFrame.test.tsx` stays uncommitted
in the working tree — it tests the wiring, so it fails without it. The
brick-icons half (`PartCardBody` gaining `thumb`, `BrickWall` passing
`thumb={false}`) is not started.

## Designed, not built

- **Card as a frame** — spec `~/src/pezlie/docs/superpowers/specs/2026-09-15-wall-card-frame-design.md`
  (`1ca1dca`, unpushed). Approved in conversation; awaiting the user's read of
  the written spec before a plan.

## Traps

- `part-years.csv` is not reproducible: a tie on the `design` route makes row
  `6567` flip between runs. Predates this work; nothing records it.
- pezlie's differential test replays the legacy wall's 56px badge threshold via
  `badgeMinPx` in `hosts/brick-icons/test/legacy.ts`. Don't "fix" that to 80.
- This session's brick-icons work lives in the `wall-header` worktree; git from
  a worktree-pinned session refuses to touch the shared checkout.
