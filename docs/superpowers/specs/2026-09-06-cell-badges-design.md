# Cell badges on the corpus wall

What a wall cell wears besides its drawing: a run of small discs saying what
kind of part it is. For whoever implements it in `lab/src/corpus/`; assumes the
wall as it stands at `a6b059e`.

**Nothing here is built.** The wall today draws two badges — a gold star for
`popular` at top-left, a gray `R` for `retired` at bottom-right — and this
replaces the corner model with a strip.

The question it answers: **when the outline doesn't tell you what the part is,
what does the cell say instead?**

## Two families

**System** — which building system the part belongs to. A part has one
`!CATEGORY`, so at most one system badge ever shows, and each carries its own
livery rather than a shared palette.

**Property** — what is true of the drawing regardless of system. These stack,
and share one field color so a run of them reads as a group.

The families exist because the two behave differently in layout, not as
taxonomy for its own sake.

## The badges

| | glyph | family | n |
|---|---|---|---|
| technic | `T`, white on navy | system | 1366 |
| duplo | `d`, red on white, stroked | system | 142 |
| minifig | head silhouette — barrel and stud, no face | system | 4723 |
| weird | `Ψ` | system | 658 |
| electric | lightning bolt | property | 1280 |
| magnet | thick `U` — arc with two square feet | property | 23 |
| printed | brush tip — tapered diagonal with a ferrule band | property | 8639 |
| composite | `+` | property | 2033 |

`popular` keeps its present disc and corner and is in neither family.
`retired` splits — see below — and keeps its slot.

The minifig head carries no face: 70% of minifig parts are also printed, so a
face would sit beside the printed badge in the same strip reading as a
duplicate.

Counts are from the vendored library, 24,591 part files.

## Retired splits into retired and updated

A part that stopped and a part that was replaced are not the same thing, and
today they wear the same gray `R`. 2780 is the case: 2,492 sets, last seen in
2021, and still made — as 61332.

Both keep the bottom-right slot, so at most one shows and nothing else moves.

| | glyph | n |
|---|---|---|
| retired | as today | 3550 |
| updated | its own mark, clickable | 456 |

**Clicking an updated badge goes to the successor.** The wall draws to canvas,
so the badge has no DOM node to carry a link: this needs hit-testing the badge's
rect in canvas coordinates. `select.ts` selects a cell, not a mark within one.

### Where a successor comes from

Not from LDraw. `~Moved to` is a file rename, not a supersession — 2780 has no
such record because 2780 and 61332 are genuinely different parts.

Rebrickable publishes `part_relationships.csv.gz` (37,390 rows, six types).
`fetch-part-years.py` pulls `parts`, `sets`, `inventories` and
`inventory_parts`; this adds a fifth dump and a table beside `part_years`.

A retired part is *updated* when a relation names a partner with a later last
year. **Mould (`M`) outranks alternate (`A`)**, or 2780 resolves to 3673, the
frictionless pin — a part that fits the same hole, not a replacement.

Measured: 456 of the 4,006 retired parts qualify — 310 by mould, 146 by
alternate. Every successor is an LDraw part; 312 are still current. The other
3,550 stay plain retired, so updated is the minority badge.

### The moved target is already free and discarded

Separately: `cells.py` computes `moved` as `title LIKE '~Moved to%'` and throws
the target away. All 1,159 moved parts name one, the header agrees with the
type-1 body reference in every case, and 1,153 resolve to a file. A redirect is
not a supersession, but the edge costs nothing to keep.

## The strip

Badges run right along the bottom edge from the part number: `4761 T ⚡ ✎`.

Corners do not scale. Two already hold captions (years top-right, part id
bottom-left), `popular` and `retired`/`updated` hold the other two, and this
adds eight — eleven discs into two corners. Nothing moves: `popular` keeps top-left,
`retired`/`updated` bottom-right, years top-right, and the part id keeps bottom-left with
the strip growing rightward from it.

Glyphs show from `BADGE_MIN_PX` (56); the id text joins them at `LABEL_MIN_PX`
(110).

**Badges stack; they are not exclusive.** 70% of Minifig parts are printed, 93%
of Tile, 61% of Brick. One-glyph-per-part collapses the two most common badges
into one.

## Where each comes from

`technic`, `duplo`, `minifig` and `printed` are already emitted by
`tags_for` and need only a table entry.

**`electric`, `magnet` and `composite` are new tags.** Electric and magnet are
`normalize_category` matches like the existing four; composite is the id
pattern `…c01`, which `cells.py` already computes for `base`.

**`weird` is a split, and a fix.** `tags.py` currently jams two meanings into
`obscure`: a part from a non-mainline theme, and a part in two sets or fewer.
Weird takes the first, `obscure` keeps the second — otherwise "Modulex" and
"only ever in two sets" wear the same badge.

The theme half is also broken today. Six of the eleven entries in
`OBSCURE_CATEGORIES` — `fabuland`, `quatro`, `galidor`, `primo`, `mursten`,
`cloud` — match no part at all, because those themes have no LDraw category:
411 Fabuland parts sit under `Figure` and elsewhere, named only in the
description line. Category catches 117 of the 658 parts that qualify.

**So weird matches the description, not the category** — the same authority
CLAUDE.md already gives for printed parts. Word-boundary match on the theme
names against line 1 of the `.dat`.

`Figure` is not weird: 519 of its 944 parts are Friends minidolls, which are
current mainline, and 30 more are Technic action figures.

## Drawing

A letter is drawn at the full badge `size`, a mark at `radius × 0.66` — which is
`size × 0.475`. **A picture is half the height of a letter in the same disc.**
`size` is `clamp(cell × 0.14, 9, 20)`, so a mark runs 4.3px at the 56px badge
floor up to 9.5px, capping once cells pass 143px. Every mark here has to survive
its floor by degrading to a distinct blob rather than into another badge: a
zigzag, a closed arc, a diagonal, a cross.

**`CellBadge` gains `stroke`.** Duplo's field is white and `THUMB_GROUND` is
`#ffffff`, so it is the first badge that would otherwise be invisible.

`mark` grows from `'star'` to `'star' | 'sticker' | 'bolt' | 'magnet' | 'brush'
| 'minifig'`. Technic, duplo, weird and composite go through `text`.

Paint order in `Wall.tsx` is already right — wash, then captions, then badges —
so a retired part's badges stay full color over the gray rather than fading into
it.

**`Ψ` needs confirming on screen.** The badge font is `ui-monospace, monospace`;
Menlo carries Greek, but a missing glyph renders as tofu.

## Watch on screen, don't pre-solve

- **The brush at the strip's floor.** If it doesn't hold, the fallback is a
  halftone dot cluster — a 2×2 or 3×3 of dots, which names the actual process
  and is the most robust primitive at small size.
- **The minifig head at 4.3px.** It is the only system badge paying the mark
  budget; the others are letters at double the height. If the stud vanishes,
  `F` is no worse.
- **`+` reading as an affordance.** A cross in a disc is the universal "add"
  control and wall cells are clickable.

## Decided against

**Keywords as a second source for technic.** A Power Functions motor is
`!CATEGORY Electric`, so it gets the bolt and no `T`. `!KEYWORDS` does not close
the gap: 185 files carry a technic keyword, 5 of them overlap the category, and
68 of the rest are stickers. Category alone stays the authority, matching the
existing tag.

**One shared color for the system family.** Technic navy and Duplo red are those
systems' own colors and read better than an arbitrary palette. The shared field
belongs to the property family, which is what makes it scan as a group.
