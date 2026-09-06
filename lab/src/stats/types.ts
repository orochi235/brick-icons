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
  runs: RunRow[];
  shape: Shape;
  as_of: string;
}
