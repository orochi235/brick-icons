# Grouping the corpus wall, and the part facts it groups by

**Unbuilt. Nothing in this document exists yet**, and it is gated on the
`corpus-wall` branch merging first — it extends that wall's layout seam and its
cells route rather than standing alone.

For whoever picks it up after that merge. It assumes the corpus wall exists:
24,591 cells, one per part, drawn on a canvas through a `Layout` strategy, with
a caret, a slot control and a lightbox.

The question it answers: **what does the wall group by, given that part id and
category are the only keys the corpus knows about today, and neither says
anything about whether a part matters?**

## What it adds

Three groupings — coverage, category, release year — a DOM sidebar to switch
between them and switch categories off, and the outside facts two of them need.

## The facts, and where they come from

Rebrickable publishes its whole catalogue as gzipped CSVs at
`cdn.rebrickable.com/media/downloads/`. No account, no key, no rate limit, and
re-downloadable in CI. Eight files matter:

| file | what it gives |
|---|---|
| `parts` | 64,616 part numbers, names, and a curated category |
| `part_categories` | 77 categories, against LDraw's 336 |
| `sets` | a year per set |
| `inventories` + `inventory_parts` | 1,557,033 rows of part × colour × set |
| `elements` | part × colour → LEGO element number, and a `design_id` |
| `colors` | 276 colours with RGB and a transparency flag |
| `part_relationships` | 37,391 print / mould / alternate edges |

From those, per part: the earliest and latest set year it appears in, total
quantity across every set, how many distinct sets, and the set of colours it was
produced in.

**Attribution is a condition of use.** Credit Rebrickable in the README and in
the wall's about text.

### Matching LDraw ids to Rebrickable part numbers

Straight across, then through `elements.design_id` for the modern six- and
seven-digit ids:

| set | matched |
|---|---|
| all 24,591 parts | 5,547 — 22.6% |
| the 7,373 unprinted, current, official, non-alias parts | 5,051 direct, **72.8%** with the `design_id` bridge |
| of those, with inventory facts | 4,876 |

The overall figure is low because most of what it misses is not a part: `~Moved`
aliases, `u9…` unofficials, subparts, and 13,083 printed parts and stickers that
Rebrickable files under their base. The 2,004 genuine drawable misses skew to
Minifig, Technic and Electric.

**Rebrickable's API would close most of that gap** — `/api/v3/lego/parts/` pages
1,000 at a time with `external_ids` inline, so about 65 calls gets the
authoritative LDraw↔Rebrickable map. It needs a free key, which means a secret
in the pipeline. Not in this build: ship the keyless join, let the wall show
which cells are unmatched, and spend the key only if that band turns out to hold
parts worth caring about.

### Where the facts live

`db.rebuild` opens with `path.unlink(missing_ok=True)` — it deletes `corpus.db`
and reseeds `parts` from the LDraw library. So facts cannot be columns on
`parts`; a rebuild would drop them. Three tables of their own, and `rebuild`
calls the importer last:

```sql
part_facts(part_id PRIMARY KEY REFERENCES parts(id), rb_part, matched_by,
           year_first, year_last, uses, sets, rb_category, fetched)
part_colors(part_id, color_id, PRIMARY KEY (part_id, color_id))
colors(id PRIMARY KEY, name, rgb, is_trans)
```

`matched_by` is `id` or `design`, so a wrong join is findable later without
re-running the match.

**An unmatched part gets no row, never a row of nulls.** A null `uses` and a
`uses` of zero are different facts — "we don't know" against "it was never in a
set" — and a row of nulls collapses them. The wall draws absence as its own
state rather than as the bottom of a ramp, which is the difference between a
cell reading *unknown* and reading *1954, never used*.

### The importer

`scripts/import-rebrickable.py`, re-runnable and idempotent:

- Downloads the eight files to `out/rebrickable/`, skipping any whose ETag matches
  what it last saw. `out/` is gitignored — 17 MB of gzip does not belong in git.
- Prints a line per file and per thousand parts joined, per the repo's rule that
  a minutes-long job must say where it is.
- Records the download date and each file's row count in `meta`, so a stale
  import is visible rather than inferred.

## What rides in the cells response

The cells route gains `year`, `uses`, `sets`, `ncolors` and `cat` per cell.
`cat` is an index into a `categories` array carried once in the body — 24,591
repeated category strings is most of a megabyte for 171 distinct values.

**The colour list stays out of the cells response.** It is per-part detail, it
is what the lightbox wants, and the lightbox already has a route.

## The layout seam grows bands

Today:

```ts
type Layout = (cells: Cell[], opts: LayoutOptions) => { rects: Rect[]; bounds: Size }
```

Grouping needs headers, and release year needs two levels of them:

```ts
interface Band { key: string; label: string; count: number; rect: Rect; depth: 0 | 1 }
type Layout = (cells, opts) => { rects: Rect[]; bands: Band[]; bounds: Size }
```

`gridLayout` returns `bands: []` and is otherwise untouched. `depth` is what
separates a decade from a year inside it, so paint styles the two without a
second field and a third level costs the type nothing.

**The caret needs no change, and that is the point.** Adjacency is already
geometric and wrapping already falls back to sequence, chosen so that inserted
whitespace could not break it. Grouping is the first thing that tests the claim.

## The three strategies

One builder, three configurations.

**Coverage** — one level: has a defect, failed, timed out, drawn, never
attempted. Ordered within each block by `uses` descending, so the top-left of
the timed-out block is the part it hurts most to be missing. This is the wall as
a work queue.

**Category** — one level, the rolled-up category. This is the wall as a
catalogue: where the dish family is.

**Release year** — two levels. Decade bands stack vertically, and each band
breaks left to right into its actual years. Direction is a parameter and applies
to both levels together; **descending by default**, newest decade at the top.

Undated parts are 76% of the corpus, so their band would set the cell pitch for
the whole wall on its own. It takes the width the dated bands settled on instead
of choosing its own, and sorts last in both directions.

## Rolling up the category

LDraw derives `category` from the first word of a part's description, which
gives 336 values with a median of 5 parts and a thicket of `~` `=` `_` `|`
prefixes. Stripping the prefixes gives 171.

**Grouping and the facet list use different thresholds, on purpose.** For
grouping, anything under 25 parts rolls into `Other`: 58 labelled blocks
covering 97.4% of the corpus, because a labelled block of three cells is
confetti. For the facet list, all 171 stay listed — a checkbox costs one row,
and a category the layout declined to name is still one you should be able to
switch off.

Rebrickable's 77 curated categories are cleaner but reach only 6,348 cells, so
they are a display alternative rather than the grouping key.

## The sidebar

DOM, beside the canvas, not drawn into it. Four sections: grouping, order
within a group, cell colour, and the category facets — every category with its
count, sorted by size, with all/none. Switching off Sticker, Minifig and Duplo
removes 8,527 cells in three clicks.

Colour modes are status, release year, frequency on a log scale, and colours
produced. **Frequency must be logarithmic**: it spans 1 to 140,674, and a linear
ramp puts every part except a few hundred at the same value.

## Traps

**Frequency is not popularity.** `uses` counts a part across every set
Rebrickable knows, which is weighted by how well documented an era is, not by
how many were moulded. It ranks well and should never be quoted as a number of
bricks.

**A part with no facts is not a part with zero facts.** See above; it is the
single easiest way to make the wall confidently wrong.

**`inventory_parts` is 1.5M rows.** Aggregate it in one pass in the importer and
store the result. Joining it live, per request, is the version that seems fine
on a laptop and falls over on the wall.

**Rebrickable ids are not stable forever.** They get merged and renamed as the
catalogue is curated. `fetched` and the row counts in `meta` are what let a
later reader tell a changed catalogue from a broken join.

## Rejected

| Considered | Verdict |
|---|---|
| Facts as columns on `parts` | Rejected. `db.rebuild` unlinks the database and reseeds `parts`; the facts would vanish on every rebuild. |
| A separate `facts.db` | Rejected. Two connections and a cross-database join for data that is one row per part. Own tables in `corpus.db`, repopulated by the importer, is less machinery. |
| One column per year rather than decade bands | Rejected on looking at it. 73 columns across a monitor is one cell wide; the year label does not fit and the eye cannot follow a column. |
| A squarified treemap of categories | Rejected. Every group fits on screen with no wrapping, but cell size stops being comparable between groups, and a coverage map whose cells are different sizes is not a coverage map. |
| Committing the render corpus to git | Rejected, and it does not work: 200,000 SVGs at a 77 KB mean is 15.4 GB raw and ~3.7 GB packed, against an enforced 2 GB push limit and a recommended 3,000 entries per directory. The census's renders already sit in `out/` and are indexed in place by `db.record_render`; that pattern holds at 200,000 unchanged. |

## Not in this build

The Rebrickable API key and the external-id map. Filtering by any axis other
than category. Writing facts back to Rebrickable. Any change to the bake, the
sheets or the slots — re-sorting and regrouping emit different rects against the
same baked thumbnails, and rebake nothing.
