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
  slowest: SlowestRow[];
}

export interface SlowestRow {
  part_id: string;
  total: number;
  secs: Record<Phase, number>;
  split: PhaseNode[] | null;
}

export interface RunRow {
  id: number;
  kind: string;
  started: string;
  finished: string | null;
  open: boolean;
  commit_sha: string;
  args: string;
  note: string | null;
  /** Parts of the working set this run measured. */
  parts: number;
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
  /** The sparse prefix off `measurements.build`, dated from git. */
  by_build: FailurePoint[];
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
  runs: RunRow[];
  shape: Shape;
  /** Optional because the lab API is a separate process: a dev server started
   *  before this field existed serves a payload without it, and the page must
   *  render the rest rather than white-screen on a stale backend. */
  failures?: Failures;
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
