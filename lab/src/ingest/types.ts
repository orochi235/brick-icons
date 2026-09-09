/** One ingest, as `/api/ingest/runs` reports it. */
export interface IngestRun {
  id: number;
  kind: string;
  started: string;
  finished: string | null;
  /** Wall-clock, or null while the run is still open. */
  secs: number | null;
  commit_sha: string;
  note: string | null;
  args: Record<string, unknown>;
  /** What the run took in. Attempts by state, everything that failed under
   *  `error`; `drawn` and `scored` for the tables that carry no state. */
  counts: Record<string, number>;
  total: number;
}

export interface IngestAttempt {
  part_id: string;
  source: string;
  state: string | null;
  secs: number | null;
  error: string | null;
  detail: string | null;
  /** What the part was in this slot before this run, or null for one the run
   *  met first. The reason to read a row: `drawn` -> `TimeoutError` is a
   *  regression, `TimeoutError` -> `drawn` is the fix landing. */
  prior: string | null;
}

export interface IngestAttempts {
  rows: IngestAttempt[];
  errors: { error: string; n: number }[];
  /** What `rows` was sampled from -- larger than `rows.length` on a big run. */
  total: number;
  /** Which table the rows came out of: a store run files attempts, a census
   *  or a watcher measurements. */
  kind: 'attempts' | 'measurements';
}
