import type { Coverage } from '@lab/corpus/facts';

export interface Spread {
  n: number;
  total: number;
  median: number | null;
  p95: number | null;
  max: number | null;
}

export interface SecsBin {
  from: number;
  /** Open-ended on the last bin. */
  to: number | null;
  n: number;
}

export interface CoverageRow {
  source: string;
  engine: string;
  counts: Record<Coverage, number>;
  /** The working set's size, so a bar knows its own whole. */
  size: number;
  /** The set less the parts this slot was never going to draw -- what it is
   *  actually short of, which is the figure the row reads out. The bar still
   *  spans `size`, so the rows stay comparable by one edge. Absent from an
   *  API older than the field. */
  owed?: number;
}

export interface SpeedRow extends Spread {
  engine: string;
  bins: SecsBin[];
}

export interface ErrorRow {
  engine: string;
  d99: Spread;
  missing_px: Spread;
}

/** The four exclusive phases every timed row carries. */
export type Phase = 'render' | 'rasterize' | 'truth_mask' | 'compare';

/** One stage of a render, and whatever the engine names inside it.
 *
 *  `secs` is INCLUSIVE of every descendant, so a seam added below a node
 *  narrows what that node leaves unnamed rather than shrinking the node. The
 *  leftover arrives as a synthetic `rest` child; a leaf never has one. */
export interface PhaseNode {
  name: string;
  /** Slash-separated, e.g. `render/geometry/engine/hlr`. Unique in a tree,
   *  which is what lets a row be expanded and collapsed by identity. */
  path: string;
  secs: number;
  /** How many parts reached this stage. Present only on a summed tree, and
   *  the only honest way to read a node's share: a seam added halfway
   *  through a census is measured over fewer parts than its parent. */
  n?: number;
  children: PhaseNode[];
}

export interface PhaseRow {
  engine: string;
  /** Rows carrying phases at all -- fewer than the engine's timed parts. */
  n: number;
  total: number;
  totals: Record<Phase, number>;
  /** Null until some row in the set named anything below the top four bands.
   *  Its own `n` is smaller again, so it is never mixed into `totals`. */
  split: { n: number; total: number; nodes: PhaseNode[] } | null;
}

export interface Shape {
  categories: [string, number][];
  kinds: Record<'printed' | 'obsolete' | 'base' | 'out_of_scope' | 'moved', number>;
  dated: number;
}

/** One slot at one moment: how many parts it could not draw, out of how many
 *  it was counted over. `size` is the corpus for a tally and the parts that
 *  build drew for a build point, which is why the two never share a y-axis. */
export interface FailurePoint {
  at: string;
  source: string;
  build: string | null;
  size: number;
  failed: number;
  timeout: number;
  bad: number;
}

/** One slot's failing count over the whole corpus after one ingest. Carries
 *  the run rather than a date: a run is an ingest, not a revision, and the
 *  order this corpus learned things is the only clock it has -- see
 *  `tally.history`. */
export interface HistoryPoint {
  run: number;
  source: string;
  /** Parts this slot renders without failing. Not what is on disk for it:
   *  two thirds of the corpus's drawings carry no run, and the row that
   *  survives a re-bake names the re-bake. */
  clean: number;
  /** The newest revision among that ingest's rows, or the run's own commit
   *  where none of them names one. */
  build: string | null;
  size: number;
  failed: number;
  timeout: number;
  bad: number;
}

export interface FailureTotal {
  bad: number;
  failed: number;
  timeout: number;
}

export interface Failures {
  totals: {
    /** In-scope parts the tiles are counted over. */
    size: number;
    occt: FailureTotal & { facets: string[] };
    decal: FailureTotal;
  };
  /** Corpus-wide counts, one step per slot per change. */
  series: FailurePoint[];
  /** The same counts replayed over every ingest that came before the first
   *  tally. Optional: a lab API older than the field sends none. */
  history?: HistoryPoint[];
  /** The sparse prefix off `measurements.build`, dated from git. */
  by_build: FailurePoint[];
}

/** One slot's share of running every slot over the same parts, at one engine
 *  revision. `ratio` is against `Cost.base`, so the number reads as "a
 *  translucent pass costs 0.35 of an occt one". */
export interface CostSlot {
  source: string;
  /** The revision this slot's seconds were taken at. `Cost.build` for every
   *  slot that ran there; its own when the slot has nothing at that one. */
  build: string;
  /** Parts this slot and the base both drew at their revisions. */
  n: number;
  /** Seconds this slot spent on those parts. */
  total: number;
  /** Of a pass of every slot, off the ratios rather than the seconds: the
   *  rows are measured over different parts and do not share a denominator.
   *  The slots sum to 1. */
  share: number;
  ratio: number | null;
  median: number | null;
  p90: number | null;
}

/** Null until two slots have drawn the same parts at one recorded revision.
 *  The revision is not decoration: a slot's stored seconds span every engine
 *  that ever drew it, and mixing them reverses which slot reads as the
 *  expensive one. */
export interface Cost {
  build: string;
  /** The slot every `ratio` is measured against. */
  base: string;
  /** Parts drawn by every slot shown, at this build. */
  n: number;
  total: number;
  slots: CostSlot[];
}

export interface Stats {
  set: {
    size: number;
    total: number;
    kind: string;
    moved: boolean;
    out_of_scope: boolean;
    excluded: string[];
    badges: string[];
  };
  coverage: CoverageRow[];
  speed: SpeedRow[];
  error: ErrorRow[];
  phases: PhaseRow[];
  /** Whether any run is unfinished, which is what sets the poll interval. */
  running: boolean;
  shape: Shape;
  /** Optional because the lab API is a separate process: a dev server started
   *  before this field existed serves a payload without it, and the page must
   *  render the rest rather than white-screen on a stale backend. */
  failures?: Failures;
  /** Optional for the same reason as `failures`: a lab API older than this
   *  bundle sends no `cost`, and the page's other sections must still draw. */
  cost?: Cost | null;
  as_of: string;
}

/** What each footprint tile counts. Size on disk everywhere, never apparent
 *  size -- a 32px thumbnail is mostly block overhead, and two cells measured
 *  differently cannot be compared. */
export interface FootprintTiles {
  out: number;
  renders: number;
  bakes: number;
  lab_cache: number;
  library: number;
  corpus_db: number;
  git: number;
}

export interface SlotSize {
  source: string;
  renders: number;
  bakes: number;
  total: number;
}

export interface Footprint {
  tiles: FootprintTiles;
  slots: SlotSize[];
  as_of: string;
}
