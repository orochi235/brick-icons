# Declared-edge oracle

**Status: designed 2026-09-13, not built.** Remove this line when it lands.

For whoever builds or reads the scores. Answers: does a stroked drawing draw
the edges the part file declares, where they are visible?

The silhouette oracle (`scripts/compare-silhouette-truth.py`) scores only the
outline, so a dropped interior edge -- a missing stud rim, a lost ledge -- is
invisible to every automated check. This scores the inside. It reports
**missing edges only**: occt legitimately draws junctions between exact
surfaces that many parts never declare, so "stroke with no declared edge" is
not a defect signal.

## Truth

- Load the part with `hlr.flatten` and no `"analytic"` key, so primitives
  tessellate (as `truth_mask` does), under `cli.part_pose`.
- Camera from the drawing's own `.fit.json` (`right`, `up`, `fwd`, `k`, `kx`,
  `ky`), so the oracle and the drawing share one pose.
- Declared edges: every type-2 line, plus each type-5 line whose control
  points project to the same side of it (`hlr.same_side`).
- Visibility: a z-buffer of the triangles at canvas x zoom; type-2 edges
  depth-tested against the dilated buffer with `EDGE_BIAS`, type-5 against the
  plain buffer with `SIL_BIAS`, via `hlr.rasterize_zbuffer`, `dilate_zbuffer`
  and `clip_visible`. These are the naive engine's occlusion constants; the
  oracle shares them and nothing downstream of them (no snapping, culls or
  arc fitting).

## Scoring

- Rasterize the SVG with resvg at the same zoom. Ink is dark pixels only
  (luminance < 128, alpha > 128): white fills and white seal strokes are not
  drawing.
- Sample each visible edge every 0.5 canvas px. A sample is covered if ink
  lies within tolerance `T` = stroke half-width + 1.5 canvas px. **Measure `T`
  on the specimens before freezing it**: a tessellated curve sits a chord's
  sagitta from occt's exact arc.
- Paint uncovered samples into a mask, join neighbors, label. Record:
  - `declared_len` -- total visible declared length, canvas px
  - `missing_len` -- uncovered length, canvas px
  - `missing_comps` -- gaps at least 4 canvas px long
  - the largest gaps' bounding boxes, as JSON
- A part with no declared edges records `declared_len` 0: nothing to score,
  not clean.

## Storage

New table, keyed by the drawing rather than the run:

    edge_scores(part_id, source, sha256, build, declared_len, missing_len,
                missing_comps, gaps TEXT, error TEXT, detail TEXT, scored_at,
                PRIMARY KEY (part_id, source, sha256))

A census row cannot hold it: 8,060 of the 39,602 stored white drawings have
no matching `measurements` row. Keyed by `sha256`, a redrawn part gets a new
row and the wall reads the one matching the slot's current render.

## Runs

- **`brick_icons/edge_truth.py`** holds truth and scoring; everything below
  calls it.
- **`scripts/score-declared-edges.py`** scores stored drawings from the
  `renders` table (`--source`, `--list`). Resumable JSONL through `Runner`,
  one progress line per part, launched on the fleet with `onto` -- 39,602
  drawings is not a local job.
- **Census:** `compare-silhouette-truth.py` adds the edge fields when
  `--line-width` or `--silhouette-width` is above 0, hashing the SVG before it
  is deleted; the census ingest writes them to `edge_scores`.

## Lab

`cells.py` joins `edge_scores` on the slot's render sha and sends that row's
`missing_comps` as `missing_edges`, null where the drawing has no score; the
wall sorts on it, the part card shows it, and the detail panel shows all three
numbers.

## Errors

- No `.fit.json` beside the drawing: an `error` row, not a skip.
- A render that raises: `Runner` records it, as for the census.

## Testing

- Synthetic `.dat` box with type-2 edges: a complete drawing scores 0; one
  stroke erased gives one gap; a back edge is not declared-visible; a type-5
  line counts only at a pose where its condition holds.
- Specimens `3001`, `3941`, `4151a` under `white-occt`: an overlay on the
  wall -- visible declared edges in red over the drawing, gaps marked -- before
  any number is trusted, and before `T` is frozen.
