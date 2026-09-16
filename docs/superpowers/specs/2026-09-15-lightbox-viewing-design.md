# Three lightbox viewing changes

For whoever next touches `lab/src/corpus/Lightbox.tsx`. It covers a header
rework, a toggle that reveals the outlines hiding inside translucent renders,
and a zoomed viewer on a thumbnail.

**Status: designed 2026-09-15, not built.**

These are independent of each other but all land in the same component, so they
go in one at a time.

## The header

Today the title sits on one line and everything else -- id, category, status,
year range, set count -- runs together in one muted sub-line, with the badge
row under it.

- **The year range moves up to the title's line, snapped right.** Title left,
  years right, one row.
- **The part number leads the sub-line in white, bold, `var(--wzl-font-ui)`**,
  so the id is the thing the eye lands on rather than one gray token among six.
- **A token in that line that has a badge is drawn as its badge.** `ALL_BADGES`
  in `paint.ts` maps a name to its artwork; the category is the token that will
  usually hit (`Technic`, `Minifig`). Match case-insensitively. The badge
  replaces the word in the sub-line and does not also appear in the tag row
  below -- the same mark twice, two lines apart, reads as two facts.

`Tags` already knows how to draw a badge with its word (`BadgeSwatch` plus a
visually-hidden label); the sub-line does the same rather than inventing a
second treatment.

## Outlines in translucent views

A checkbox in the lightbox, off by default: **Outlines in translucent views**.

The translucent renders already contain their edges. `translucent-occt`'s
4449-f1 is 149 paths and 41 lines under a `stroke="black"` group, every one
carrying `stroke-width="0.00"` -- the geometry is drawn, the strokes are simply
zero. Nothing needs re-rendering.

**The lab rewrites the widths as it serves the file**, on
`/api/corpus/render/{source}/{part_id}.svg?outline=1`: zero stroke widths
become a visible hairline. Tiles stay plain `<img>`, so nothing about how they
load changes, and the zoomed viewer below gets the same treatment by passing
the same parameter. The checkbox applies to translucent slots only; every other
slot already draws its strokes.

## A zoomed viewer on double-click

Double-clicking a thumbnail opens that slot's render above the lightbox: as
large as fits, then **scroll to zoom and drag to pan**. Escape closes the
viewer and leaves the lightbox open behind it, so the existing Escape handler
must not also fire.

Renders are vector, so zoom costs nothing in fidelity -- which is the point:
this is for judging whether an edge is really missing, on a drawing a 150px
tile cannot settle.

Double-click follows two clicks, so the slot is selected as well. That is
wanted, not a side effect: the viewer opens on the slot you just picked.
Shift-click already opens the raw SVG in a new tab and stays as it is.
