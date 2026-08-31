import type { LabClient, RenderResult } from '@lab/api/client';
import type { SourceId } from '@lab/config/nodes';
import { SOURCES, sourceConfig } from '@lab/panes/sources';

/** One finished render, tagged with the pane it belongs to. */
export interface SourceRender {
  source: SourceId;
  result: RenderResult;
}

export type RenderEvent =
  | { kind: 'total'; total: number }
  | { kind: 'item'; item: SourceRender }
  | { kind: 'failed'; index: number; error: string };

export interface RunRendersArgs {
  client: LabClient;
  part: string;
  config: Record<string, unknown>;
  sources: readonly SourceId[];
  signal: AbortSignal;
  /** Poll interval. Zero in tests; the app leaves it at the default. */
  pollMs?: number;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function* runRenders(
  { client, part, config, sources, signal, pollMs = 250 }: RunRendersArgs,
): AsyncIterable<RenderEvent> {
  const engines = sources.filter((id) => SOURCES[id]?.kind === 'engine');
  const wanted = part.trim() ? engines : [];
  yield { kind: 'total', total: wanted.length };

  for (const [index, id] of wanted.entries()) {
    if (signal.aborted) return;
    const started = await client.startRender(part, sourceConfig(SOURCES[id]!, config));

    let state = await client.job(started.job);
    while (state.state === 'running') {
      if (signal.aborted) return;
      await sleep(pollMs);
      if (signal.aborted) return;
      state = await client.job(started.job);
    }
    if (signal.aborted) return;

    const result = state.results[0] ?? {
      ok: false, cached: false, argv: [], command: '', key: '', artifacts: [],
      seconds: 0, error: 'the job finished without a result',
    };
    if (!result.ok) {
      // Both: `failed` so the trial chrome counts it, and `item` so the pane
      // can show the message. A failure the runtime counts but nothing
      // displays is the silent-`[]` failure in another costume.
      yield { kind: 'failed', index, error: result.error ?? 'render failed' };
    }
    yield { kind: 'item', item: { source: id, result } };
  }
}
