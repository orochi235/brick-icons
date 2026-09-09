export interface Cell {
  id: string;
  index: number;
  title: string;
  category: string | null;
  /** The sideline theme its description opens with -- Fabuland, Znap -- or
   *  null for a mainline part. */
  family: string | null;
  printed: boolean;
  obsolete: boolean;
  base: boolean;
  out_of_scope: boolean;
  moved: boolean;
  /** First and last year a set carried this part, and how many sets did --
   *  null for a part the catalogs do not list. */
  year_from: number | null;
  year_to: number | null;
  sets: number | null;
  /** How many distinct colors the part was made in. */
  colors: number | null;
  tags: string[];
  /** The part that replaced this one, where Rebrickable records one. The
   *  updated badge links to it. Optional for the same reason `tags` is: the
   *  lab's server is long-lived and can be older than the page in front of
   *  it, and a missing field must not break the view. */
  successor?: string | null;
  status: string;
  sha: string | null;
  made_at: string | null;
  extra_d99: number | null;
  secs: number | null;
  error: string | null;
  /** How far this slot got: see `coverage_of` in `brick_icons/lab/cells.py`.
   *  Absent from an API older than the field. */
  coverage?: 'defect' | 'failed' | 'timeout' | 'drawn' | 'untried';
  /** Open here, and not waiting on a fresh render -- the two are disjoint so
   *  a redrawn defect cannot hide behind the part's untouched ones. */
  open_defects: number;
  /** Open here, judged once, and the slot has drawn something else since. */
  review_defects: number;
  /** Filed against this slot's engine and accepted rather than fixed. */
  accepted_defects: number;
  /** Condition keys holding in a slot that is not this one, which the wall
   *  draws as each condition's `<key>Elsewhere` sibling. One field for every
   *  condition there will ever be. */
  elsewhere: string[];
}

export interface CellsBody {
  cells: Cell[];
  count: number;
  version: string;
  source: string;
}

export interface SheetManifest {
  level: number;
  gutter: number;
  pitch: number;
  cols: number;
  rows: number;
  count: number;
  size: number;
  baked: Record<string, string>;
  /** Stamped by the server from the atlas image's mtime, so a rewritten sheet
   *  is not served from cache against a fresh manifest. Absent on a manifest
   *  read straight off disk. */
  version?: string;
}

export interface PartDetail {
  part: { id: string; title: string; category: string | null;
          status: string; status_note: string | null;
          year_from: number | null; year_to: number | null;
          sets: number | null; tags: string[];
          /** LDraw's `!PREVIEW` line, verbatim, for the 394 parts that carry
           *  one. Absent from an API older than the field, like `slots`. */
          preview?: string | null;
          out_of_scope?: boolean };
  /** Every live slot, in slot order, each carrying what the wall would color
   *  its cell by. A slot with no `sha256` did not draw this part -- it timed
   *  out, it failed, or nothing has run it. The state fields are optional for
   *  the same reason `slots` itself is. */
  slots: {
    source: string; sha256: string | null; made_at: string | null;
    /** How long the last run of this slot took, from its attempt row. */
    secs?: number | null;
    error?: string | null;
    open_defects?: number;
    review_defects?: number;
    accepted_defects?: number;
    elsewhere?: string[];
    /** This slot has nothing to draw for this part -- a plain brick on the
     *  decal slot. `cells.not_applicable` is the server's rule. */
    not_applicable?: boolean;
  }[];
  findings: { part_id: string; engine: string; extra_d99: number | null;
              missing_px: number | null; secs: number | null;
              error: string | null }[];
  runs: { id: number; kind: string; started: string; commit_sha: string;
          engine: string; extra_d99: number | null; missing_px: number | null;
          secs: number | null; error: string | null }[];
  defects: { id: string; part: string; title: string; status: string;
             engines?: string[];
             /** Slot -> the render sha last judged. The lightbox re-stamps it
              *  on a verdict; absent means this defect never asks for one. */
             checked?: Record<string, string> }[];
  /** How the part is built, from `part_features`: a null value is a flag the
   *  part carries, a number is a measure every part has. Absent from an API
   *  older than the field. */
  features?: Record<string, number | null>;
}
