import type { LabClient, RenderResult } from '@lab/api/client';
import { SOURCES, sourceConfig, type SourceId } from '@lab/panes/sources';

/** One finished render, tagged with the pane it belongs to and with the run
 *  that asked for it. The signature is what tells a pane whether the drawing
 *  it is holding belongs to the config on screen or to the one before it. */
export interface SourceRender {
  source: SourceId;
  result: RenderResult;
  signature: string;
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

/** What identifies a render to the pane showing it: the part and the flags,
 *  and nothing about which engine drew it. */
export function renderSignature(part: string,
                                config: Record<string, unknown>): string {
  return JSON.stringify([part.trim(), config]);
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function failedResult(error: string): RenderResult {
  return { ok: false, cached: false, argv: [], command: '', key: '',
           artifacts: [], seconds: 0, error };
}

interface OneArgs extends Required<Pick<RunRendersArgs, 'client' | 'part' | 'config'>> {
  source: SourceId;
  index: number;
  signature: string;
  signal: AbortSignal;
  pollMs: number;
}

/** Every event one pane's render produces. It never throws: a transport
 *  failure is that pane's failure, and the other panes still want their
 *  drawings. */
async function renderOne(
  { client, part, config, source, index, signature, signal, pollMs }: OneArgs,
): Promise<RenderEvent[]> {
  const fail = (error: string): RenderEvent[] => [
    // Both: `failed` so the trial chrome counts it, and `item` so the pane can
    // show the message. A failure the runtime counts but nothing displays is
    // the silent-`[]` failure in another costume.
    { kind: 'failed', index, error },
    { kind: 'item', item: { source, result: failedResult(error), signature } },
  ];
  try {
    if (signal.aborted) return [];
    const started = await client.startRender(part, sourceConfig(SOURCES[source]!, config));

    let state = await client.job(started.job);
    while (state.state === 'running') {
      if (signal.aborted) return [];
      await sleep(pollMs);
      if (signal.aborted) return [];
      state = await client.job(started.job);
    }
    if (signal.aborted) return [];

    const result = state.results[0]
      ?? failedResult('the job finished without a result');
    if (!result.ok) return fail(result.error ?? 'render failed');
    return [{ kind: 'item', item: { source, result, signature } }];
  } catch (error) {
    return fail(error instanceof Error ? error.message : String(error));
  }
}

/** Each task's value in the order the tasks settle, not the order they were
 *  started. Tasks must not reject; `renderOne` is written so they cannot. */
async function* asSettled<T>(tasks: Promise<T>[]): AsyncIterable<T> {
  const pending = new Map(
    tasks.map((task, i) => [i, task.then((value) => ({ i, value }))] as const));
  while (pending.size > 0) {
    const { i, value } = await Promise.race(pending.values());
    pending.delete(i);
    yield value;
  }
}

export async function* runRenders(
  { client, part, config, sources, signal, pollMs = 250 }: RunRendersArgs,
): AsyncIterable<RenderEvent> {
  const engines = sources.filter((id) => SOURCES[id]?.kind === 'engine');
  const wanted = part.trim() ? engines : [];
  yield { kind: 'total', total: wanted.length };

  const signature = renderSignature(part, config);
  // Started together, reported as they land: a pane waits for its own render
  // and for nobody else's.
  const tasks = wanted.map((source, index) => renderOne({
    client, part, config, source, index, signature, signal, pollMs,
  }));
  for await (const events of asSettled(tasks)) yield* events;
}
