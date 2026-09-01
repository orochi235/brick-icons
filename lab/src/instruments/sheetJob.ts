import type { LabClient, RenderResult } from '@lab/api/client';
import { jobStates } from '@lab/api/jobPoll';
import { svgArtifactName } from '@lab/panes/useArtifactSvg';

export interface SheetCell {
  part: string;
  key: string;
  svg: string | null;
  error: string | null;
  seconds: number;
}

export type SheetEvent =
  | { kind: 'total'; total: number }
  | { kind: 'item'; item: SheetCell };

export interface RunSheetArgs {
  client: LabClient;
  parts: string[];
  config: Record<string, unknown>;
  signal: AbortSignal;
  pollMs?: number;
}

function cellFrom(part: string, result: RenderResult): SheetCell {
  return {
    part,
    key: result.key,
    svg: svgArtifactName(result.artifacts),
    error: result.ok ? null : (result.error ?? 'render failed'),
    seconds: result.seconds,
  };
}

/** One batch job for the whole list. The server renders in order, so a result
 *  at index i belongs to `parts[i]`. */
export async function* runSheet(
  { client, parts, config, signal, pollMs = 400 }: RunSheetArgs,
): AsyncIterable<SheetEvent> {
  yield { kind: 'total', total: parts.length };
  if (parts.length === 0) return;

  const started = await client.startBatch(parts, config);
  let seen = 0;

  for await (const state of jobStates(client, started.job, { signal, pollMs })) {
    while (seen < state.results.length) {
      const part = parts[seen];
      const result = state.results[seen];
      if (part && result) yield { kind: 'item', item: cellFrom(part, result) };
      seen += 1;
    }
  }
}
