export interface Cell {
  id: string;
  index: number;
  title: string;
  category: string | null;
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
  open_defects: number;
  open_defects_elsewhere: number;
  /** Filed against this slot's engine and accepted rather than fixed. */
  accepted_defects: number;
  error_elsewhere: boolean;
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
}

export interface PartDetail {
  part: { id: string; title: string; category: string | null;
          status: string; status_note: string | null;
          year_from: number | null; year_to: number | null;
          sets: number | null; tags: string[] };
  /** Every slot that has drawn this part, in slot order. */
  slots: { source: string; sha256: string; made_at: string }[];
  findings: { part_id: string; engine: string; extra_d99: number | null;
              missing_px: number | null; secs: number | null;
              error: string | null }[];
  runs: { id: number; kind: string; started: string; commit_sha: string;
          engine: string; extra_d99: number | null; missing_px: number | null;
          secs: number | null; error: string | null }[];
  defects: { id: string; part: string; title: string; status: string }[];
}
