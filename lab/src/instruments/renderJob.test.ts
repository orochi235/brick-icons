import { describe, expect, it, vi } from 'vitest';
import { runRenders } from '@lab/instruments/renderJob';
import type { LabClient, RenderResult } from '@lab/api/client';

function result(over: Partial<RenderResult> = {}): RenderResult {
  return {
    ok: true, cached: false, argv: ['3941'], command: 'brick-icons 3941',
    key: 'k1', artifacts: [{ name: '3941.svg', bytes: 10 }], seconds: 1,
    error: null, ...over,
  };
}

function fakeClient(over: Partial<LabClient> = {}): LabClient {
  return {
    startRender: vi.fn(async () => ({ job: 'j1', argv: [], command: '' })),
    job: vi.fn(async () => ({
      id: 'j1', kind: 'render', state: 'done' as const, total: 1, done: 1,
      failed: 0, events: [], results: [result()],
    })),
    cancelJob: vi.fn(async () => {}),
    ...over,
  } as unknown as LabClient;
}

async function collect<T>(iter: AsyncIterable<T>): Promise<T[]> {
  const out: T[] = [];
  for await (const value of iter) out.push(value);
  return out;
}

describe('runRenders', () => {
  it('yields a total before any item', async () => {
    const events = await collect(runRenders({
      client: fakeClient(), part: '3941', config: {},
      sources: ['naive', 'occt'], signal: new AbortController().signal, pollMs: 0,
    }));
    expect(events[0]).toEqual({ kind: 'total', total: 2 });
  });

  it('yields one item per engine source, tagged with its source', async () => {
    const events = await collect(runRenders({
      client: fakeClient(), part: '3941', config: {},
      sources: ['naive', 'occt'], signal: new AbortController().signal, pollMs: 0,
    }));
    const items = events.filter((e) => e.kind === 'item');
    expect(items.map((e) => (e as { item: { source: string } }).item.source))
      .toEqual(['naive', 'occt']);
  });

  it('pins each render to its own engine', async () => {
    const startRender = vi.fn(async () => ({ job: 'j1', argv: [], command: '' }));
    await collect(runRenders({
      client: fakeClient({ startRender }), part: '3941',
      config: { shading: 'outline' }, sources: ['naive', 'occt'],
      signal: new AbortController().signal, pollMs: 0,
    }));
    expect(startRender.mock.calls.map((c) => (c[1] as { engine: string }).engine))
      .toEqual(['naive', 'occt']);
  });

  it('renders nothing when the part is empty', async () => {
    const startRender = vi.fn();
    const events = await collect(runRenders({
      client: fakeClient({ startRender }), part: '', config: {},
      sources: ['naive'], signal: new AbortController().signal, pollMs: 0,
    }));
    expect(startRender).not.toHaveBeenCalled();
    expect(events).toEqual([{ kind: 'total', total: 0 }]);
  });

  it('reports a failed render as a failed event AND an item the pane can show', async () => {
    const client = fakeClient({
      job: vi.fn(async () => ({
        id: 'j1', kind: 'render', state: 'done' as const, total: 1, done: 0,
        failed: 1, events: [], results: [result({ ok: false, error: 'boom' })],
      })),
    } as never);
    const events = await collect(runRenders({
      client, part: '3941', config: {}, sources: ['naive'],
      signal: new AbortController().signal, pollMs: 0,
    }));
    expect(events.some((e) => e.kind === 'failed')).toBe(true);
    const item = events.find((e) => e.kind === 'item') as
      { item: { result: { ok: boolean; error: string | null } } } | undefined;
    expect(item?.item.result.ok).toBe(false);
    expect(item?.item.result.error).toBe('boom');
  });

  it('stops when the signal aborts', async () => {
    const controller = new AbortController();
    const client = fakeClient({
      job: vi.fn(async () => {
        controller.abort();
        return { id: 'j1', kind: 'render', state: 'running' as const, total: 1,
                 done: 0, failed: 0, events: [], results: [] };
      }),
    } as never);
    const events = await collect(runRenders({
      client, part: '3941', config: {}, sources: ['naive'],
      signal: controller.signal, pollMs: 0,
    }));
    expect(events.filter((e) => e.kind === 'item')).toEqual([]);
  });

  it('skips a non-engine source, which does not render through the CLI', async () => {
    const startRender = vi.fn(async () => ({ job: 'j1', argv: [], command: '' }));
    await collect(runRenders({
      client: fakeClient({ startRender }), part: '3941', config: {},
      sources: ['naive', '3d'], signal: new AbortController().signal, pollMs: 0,
    }));
    expect(startRender).toHaveBeenCalledTimes(1);
  });
});
