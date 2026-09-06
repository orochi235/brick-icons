export interface Cell {
  id: string;
  index: number;
  title: string;
  category: string | null;
  printed: boolean;
  obsolete: boolean;
  status: string;
  sha: string | null;
  made_at: string | null;
  extra_d99: number | null;
  secs: number | null;
  error: string | null;
  open_defects: number;
  open_defects_elsewhere: number;
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
          status: string; status_note: string | null };
  findings: { part_id: string; engine: string; extra_d99: number | null;
              missing_px: number | null; secs: number | null;
              error: string | null }[];
  runs: { id: number; kind: string; started: string; commit_sha: string;
          engine: string; extra_d99: number | null; missing_px: number | null;
          secs: number | null; error: string | null }[];
  defects: { id: string; part: string; title: string; status: string }[];
}
