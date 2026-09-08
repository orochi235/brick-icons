# Corpus dashboard

**Status: built**, on branch `corpus-dashboard` (`65b08ac`), over the coverage
move on `corpus-coverage-server-side` (`4aeb2d6`). Neither is merged.

A third lab page, beside the wall and the badge sheet, that tallies what the
corpus database holds: how far each slot's census got, how long the engines
took, what the runs were, and what the corpus is made of. Every tally is
scoped to a working set you choose, and links into the wall filtered to the
same parts.

For whoever builds it, and for the next person who wants a number that
`CENSUS-RUN2.md` currently states by hand.

## The one architectural move

Coverage is already classified twice, both times in the browser, both times
from one slot's full `cells` fetch: `coverageOf` in `lab/src/corpus/facts.ts`
labels a cell `defect | failed | timeout | drawn | untried`, and `Legend`
tallies the eight `CellState` values. The dashboard wants those tallies for
every slot at once. Computing them a third time, in Python, is how the three
drift apart.

So the label moves to `brick_icons/lab/cells.py`, which already reads
everything `coverageOf` looks at — `error`, `sha`, `open_defects`. Each cell
row gains a `coverage` field; `coverageOf` becomes a field read; the wall's
coverage grouping is unchanged and its existing tests hold it in place. The
stats endpoint is then a `GROUP BY` over the same labels rather than a second
opinion.

`tests/test_lab_cells.py` gets the cases `facts.test.ts` currently owns, and
`facts.test.ts` keeps only what remains client-side.

## The endpoint

`GET /api/corpus/stats` takes the membership half of the wall's `Selection` —
`kind`, `moved`, `out_of_scope`, `excluded`, `badges` — and returns, for that
working set:

The wall's `rendered` / `unrendered` / `errors` filters are not among them.
Each is a statement about one slot, and the coverage chart already breaks
every slot out that way.

- `coverage`: per slot, a count per label, plus the set's own size
- `speed`: per engine, `n`, total, median, p95, max `secs`, and a fixed-bin
  histogram
- `error`: per engine, distribution of `extra_d99` and `missing_px`
- `runs`: each row of `runs` with the parts it measured and whether it is open
- `shape`: parts by category, by printed/obsolete/base, and how many carry
  year/set/color facts
- `as_of`: when the numbers were read

The display half of `Selection` — `sort`, `grouping`, `tint`, `desc` — is not
sent. It changes how the wall draws, not which parts are in.

## Working sets

The dashboard carries the wall's own membership controls: the category
checklist, the class toggles, the tag badges, the show dropdown. State lives
in the query string, so a working set is a link you can keep, and "open in the
wall" hands `corpus.html` the identical filter.

The default is the wall's default — `moved` hidden, `outOfScope` shown, no
category excluded, no badge required — so both pages agree on first load, at
23,432 of 24,591 parts.

Coverage percentages are against the chosen set's own size, never a fixed
denominator, and the page states that size beside them. A set that hides
out-of-scope parts is 20,638; the full corpus is 24,591; neither is
privileged.

## The page

Coverage first: a stacked bar per slot across `drawn / defect / failed /
timeout / untried`. Then a tile row — renders, measurements, parts, defects,
and the open run if there is one. Then speed as a `secs` histogram per engine
with median and tail called out, then the run table, then corpus shape.

Charts where the shape carries something a number cannot — the timing tail,
the error distribution — and tables everywhere else. Colors come from the
dataviz palette, so the page reads as one system rather than five.

Every tally is a link into `corpus.html` with the filter that selects those
parts.

## Freshness

The page polls while `runs` holds an unfinished row and stops when it does
not, so coverage climbing during a census is visible without a reload. An
"as of HH:MM" line says which read the numbers came from.

## Testing

The Python tallies are tested against a fixture database, one test per
returned section, in the manner of the existing lab API tests. The frontend
tests cover the working-set round trip through the query string, the poll
starting and stopping on an open run, and the link a tally hands to the wall.
Chart rendering is not tested beyond the data it is given.

## Not in this

No comparison of two working sets side by side, no saved and named sets, no
export. Presets and saved sets can sit on top of the URL state later without
changing anything here.

## What the build added that this did not ask for

`vite.config.ts` reads `LAB_API` for its proxy target, so a worktree can run
its own lab server on its own port without editing the committed config.
`brick_icons/tags.py` gained `clean_category`, the display-cased sibling of
`normalize_category` and the mirror of `cleanCategory` in `facts.ts` — the
wall's category checklist names categories in that spelling on the way back
in.
