# Slot materials, and the lightbox's measurements as a chart

For whoever builds or next touches the lightbox's Measurements section or any
place a render slot is drawn as a swatch. It answers: what each slot looks like
when it is not a render, and how the lightbox shows what a slot cost.

**Status: built 2026-09-15** (`fa32e98`..`14f0312`). The code is in
`lab/src/shared/materials.ts`, `lab/src/shared/MaterialBar.tsx` and
`lab/src/corpus/Measurements.tsx`.

## A material per slot

A slot's material is what a chart bar or a chip is made of. Each one resembles
the render setting it stands for: a plain slot is shaded plastic with the
engine's 2px strokes, silhouette is the same plastic with no strokes, white is
white, translucent is see-through, reference is metallic gold, decal is a flat
print. occt is LEGO Blue and naive is LEGO Orange, and every family member takes
its family's color.

| slot | color | finish | opacity | stroke |
|---|---|---|---|---|
| `occt` | `#0055BF` | solid | 1 | `#000000` |
| `white-occt` | `#F2F3F2` | solid | 1 | `#0055BF` |
| `silhouette-occt` | `#0055BF` | solid | 1 | none |
| `translucent-occt` | `#0055BF` | trans | 0.45 | none |
| `naive` | `#FE8A18` | solid | 1 | `#000000` |
| `white-naive` | `#F2F3F2` | solid | 1 | `#FE8A18` |
| `silhouette-naive` | `#FE8A18` | solid | 1 | none |
| `translucent-naive` | `#FF8A00` | trans | 0.7 | none |
| `reference` | `#DBAC34` | metallic | 1 | `#000000` |
| `decal` | `#C870A0` | print | 1 | `#8E4570` |

A stroke is 1px. A slot missing from the table gets a gray solid with a black
stroke, so a new slot draws before anyone picks its material.

The table lives in `lab/src/shared/materials.ts`, and `MaterialBar`
(`lab/src/shared/MaterialBar.tsx`) is the one component that draws a material,
at any size. Both the lightbox and the stats page import from `@lab/shared`.

## Drawing a bar

A bar is seen slightly from above: a front face, and a 3px top face above it
whose far end steps in 2px. The near end is square, because a bar grows out of
its axis already in progress. Shades below are HLS lightness offsets from the
material's color, top of the front face to bottom.

- **solid:** front `+.08`, `+.03` at 30%, the color at 60%, `-.18`; top face `+.34`.
- **trans:** the solid ramp at the material's opacity, brightened in the middle
  by opacity rather than lightness (`+.08` at 45% with opacity `+.3`) -- lightening
  turns orange to cream, and on the lightbox's dark surface a low opacity turns
  it brown. A thin white line sits 2px under the top edge; a white wash fades
  down from it over 60% of the front; a glow in the color `+.3` sits between 55%
  and 93%. Wash and glow are blurred (σ 1.4), clipped to the front face, and run
  off the near end so it shows no edge.
- **metallic:** one soft band: `+.02`, `+.14` at 40%, `-.06` at 75%, `-.16`.
- **print:** flat. A white ground with 9px stripes every 16px in the color `+.2`,
  at 45° on the front. Each top-face stripe starts where its front stripe meets
  the edge and narrows toward the far end with the top face, so the hatching
  reads as one surface wrapping the edge.

A chip is a `MaterialBar` at 34×14.

## The Measurements section

The table and the chart are one: a row per slot, in chart order -- `occt`,
`naive`, `reference`, then `translucent-occt`, `translucent-naive`,
`silhouette-occt`, `silhouette-naive`, `white-occt`, `white-naive`, and `decal`
last. The order lives beside the materials table; a slot it does not list goes
before `decal`.

| slot | extra d99 | missing px | missing comps | secs |
|---|---|---|---|---|
| chip + name | number | number | number | bar, then its value |

- secs is a bar scaled to this part's slowest slot, with the value just past the
  bar's end. The other three stay numbers, right-aligned, in tabular figures.
- Column headers may wrap, which keeps the number columns narrow.
- A number at or above the corpus 90th percentile gets a warm cell, at or above
  the 99th a hot one. Cutoffs, from the latest measurement per part and slot in
  `corpus.db` on 2026-09-15:

  | measure | p90 | p99 |
  |---|---|---|
  | extra d99 | 1.41 | 7.44 |
  | missing px | 724 | 61,026 |
  | missing comps | 1 | 6 |

  A low extra d99 is not shaded: every silhouette slot sits near 0.45.
- A slot that errored shows its error across the three number cells. A timed-out
  slot's bar is a dashed outline in its family color with no fill, and its value
  is dimmed -- the bar stops at the time limit, not at what the render would have
  cost, and a faded bar would read as translucent.
- All text is `var(--wzl-font-ui)`.

Declared edges stays a table.

## Slot tiles

The render tiles follow the same chart order as the Measurements rows. Each
tile gets a chip in front of the slot name, the chip
and the name both top-aligned so a name that wraps keeps its chip on the first
line. The tile's background still carries the wall's state color.

## Not using materials: the stats failure chart

`SlotLines` draws one line per slot and needs a hue per slot. Three occt slots
share one material color, so the chart keeps its own palette (`--slot-*` in
`stats/stats.css`). `SLOT_COLOR` in `stats/charts.tsx` mirrors those variables
and nothing reads it; delete it.

## Tests

- `MaterialBar`: each finish emits its parts (top face, front, trans wash and
  glow, print stripes on both faces), and two bars on one page never share a
  gradient, clip or filter id.
- Lightbox: rows follow chart order, decal last; cells at each cutoff get the warm and hot
  classes and one below does not; an error spans the three cells; a timeout
  draws the dashed bar.
- A headless screenshot of the lightbox on 4449-f1 and 30298, which between them
  hit both shading tiers, a timeout in each family and every material but decal.
