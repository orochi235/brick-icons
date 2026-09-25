/** What `/api/review` says about one side of a displacement. The
 *  measurement fields are absent when no run measured that side, which is
 *  every local redraw. */
export interface ReviewSide {
  path: string;
  sha256: string;
  made_at: string | null;
  run_id: number | null;
  kept?: string | null;
  build?: string | null;
  secs?: number | null;
  extra_d99?: number | null;
  missing_px?: number | null;
  error?: string | null;
  edge: { declared_len: number | null; missing_len: number | null;
          missing_comps: number | null } | null;
}

export type Verdict = 'fixed' | 'better' | 'neutral' | 'regression';

export interface ReviewDefect {
  id: string;
  title: string;
  status: string;
  /** The render sha this defect was last judged against in this slot. */
  checked: string | null;
}

export interface ReviewEntry {
  id: string;
  part: string;
  title: string | null;
  source: string;
  engine: string;
  at: string;
  run_id: number | null;
  by: string | null;
  before: ReviewSide;
  after: ReviewSide;
  diff: { components: number; pixels: number; width: number; at: string } | null;
  defects: ReviewDefect[];
  request: { part: string; source: string; at: string; by: string } | null;
  judged: { verdict: Verdict; note: string; at: string; by: string;
            defects: string[] } | null;
  superseded_by: string | null;
  urls: { before: string; after: string; diff: string;
          reference: string };
  /** Set by an undo: false when the verdict predates the restore record
   *  and the previous `checked` sha could not be given back. */
  restored?: boolean;
}

export type ReviewView = 'linked' | 'all';

export interface ReviewList {
  entries: ReviewEntry[];
  total: number;
  /** Entries this view is about that fell under the component bar: a redraw
   *  that displaced a render without changing what it draws. */
  hidden: number;
  /** Unjudged entries the slot has drawn past: the queue shows only the
   *  newest entry for a part, and these are its earlier hops. */
  superseded: number;
  view: ReviewView;
  verdicts: Verdict[];
}
