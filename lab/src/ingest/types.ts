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
  /** Attempts by state, everything that failed under `error`. Empty for a
   *  run that writes measurements rather than attempts. */
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
}

export interface IngestAttempts {
  rows: IngestAttempt[];
  errors: { error: string; n: number }[];
  /** What `rows` was sampled from -- larger than `rows.length` on a big run. */
  total: number;
}
