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
