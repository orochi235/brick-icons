/** One flag of the CLI, as the server derived it from argparse. */
export interface SchemaField {
  key: string;
  flag: string;
  type: 'int' | 'float' | 'str' | 'bool';
  choices: string[] | null;
  help: string;
  nargs: number | null;
  default: unknown;
  /** What `load_config` resolves this flag to — the value the CLI actually
   *  uses. Null for a flag with no Config field (--out, --debug-dir). */
  effective: unknown;
}

export interface PartHit {
  id: string;
  description: string;
  printed: boolean;
}

/** One LDraw palette entry, as `/api/colors` sends it. `hex` is `#rrggbb`;
 *  `alpha` is 255 for everything but the transparent colors, and `category` is
 *  the LDConfig heading it was listed under. */
export interface LdrawColor {
  code: number;
  name: string;
  hex: string;
  alpha: number;
  category: string;
  /** LEGO's own number for the color, where LDConfig declares one. Null for
   *  the LDraw-only entries — derived materials, Modulex, the retired list. */
  legoId: number | null;
}

export interface Artifact {
  name: string;
  bytes: number;
}

/** What `runner.render` returned for one argv. */
export interface RenderResult {
  ok: boolean;
  cached: boolean;
  argv: string[];
  command: string;
  key: string;
  artifacts: Artifact[];
  seconds: number;
  error: string | null;
  /** The process that ran it, so a render that died names its own corpse.
   *  Absent on a cached hit and on a render that never started. */
  pid?: number | null;
  cancelled?: boolean;
}

export interface JobState {
  id: string;
  kind: string;
  state: 'running' | 'done' | 'failed' | 'cancelled';
  total: number;
  done: number;
  failed: number;
  events: { index: number; total: number; message: string; ok: boolean }[];
  results: RenderResult[];
}

export type LabConfig = Record<string, unknown>;
