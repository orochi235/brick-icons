import { describe, expect, it, vi } from 'vitest';
import { runSheet } from '@lab/instruments/sheetJob';
import type { LabClient, RenderResult } from '@lab/api/client';

const result = (over: Partial<RenderResult> = {}): RenderResult => ({
  ok: true, cached: false, argv: ['3005'], command: '', key: 'k1',
  artifacts: [{ name: '3005.svg', bytes: 1 }], seconds: 1, error: null, ...over,
});

function fakeClient(results: RenderResult[], state = 'done') {
  return {
    startBatch: vi.fn(async () => ({ job: 'j1', count: results.length })),
    job: vi.fn(async () => ({
      id: 'j1', kind: 'batch', state, total: results.length,
      done: results.length, failed: 0, events: [], results,
    })),
  } as unknown as LabClient;
}

async function collect<T>(iter: AsyncIterable<T>): Promise<T[]> {
  const out: T[] = [];
  for await (const v of iter) out.push(v);
  return out;
}

describe('runSheet', () => {
  it('a cell out of order still lands on its own part', async () => {
    // The parts are asked for in one order and finish in another, which is
    // what running several renders at once produces.
    const client = fakeClient([result({ argv: ['3024'], key: 'k2' }),
                               result({ argv: ['3005'] })]);
    const events = await collect(runSheet({
      client, parts: ['3005', '3024'], config: {},
      signal: new AbortController().signal, pollMs: 0,
    }));
    const cells = events.filter((e) => e.kind === 'item');
    expect(cells.map((e) => (e as { item: { part: string; key: string } }).item))
      .toEqual([expect.objectContaining({ part: '3024', key: 'k2' }),
                expect.objectContaining({ part: '3005', key: 'k1' })]);
  });

  it('reports the total before any cell', async () => {
    const events = await collect(runSheet({
      client: fakeClient([result()]), parts: ['3005'], config: {},
      signal: new AbortController().signal, pollMs: 0,
    }));
    expect(events[0]).toEqual({ kind: 'total', total: 1 });
  });

  it('names each cell from the render that produced it', async () => {
    const client = fakeClient([result({ argv: ['3005'] }),
                               result({ argv: ['3024'], key: 'k2' })]);
    const events = await collect(runSheet({
      client, parts: ['3005', '3024'], config: {},
      signal: new AbortController().signal, pollMs: 0,
    }));
    const cells = events.filter((e) => e.kind === 'item');
    expect(cells.map((e) => (e as { item: { part: string } }).item.part))
      .toEqual(['3005', '3024']);
  });

  it('renders nothing for an empty list', async () => {
    const client = fakeClient([]);
    const events = await collect(runSheet({
      client, parts: [], config: {}, signal: new AbortController().signal, pollMs: 0,
    }));
    expect(client.startBatch).not.toHaveBeenCalled();
    expect(events).toEqual([{ kind: 'total', total: 0 }]);
  });

  it('carries a failed part through as a cell with its error', async () => {
    const client = fakeClient([result({ ok: false, error: 'boom' })]);
    const events = await collect(runSheet({
      client, parts: ['3005'], config: {},
      signal: new AbortController().signal, pollMs: 0,
    }));
    const cell = events.find((e) => e.kind === 'item') as
      { item: { error: string | null } };
    expect(cell.item.error).toBe('boom');
  });

  it('stops when the signal aborts', async () => {
    const controller = new AbortController();
    const client = {
      startBatch: vi.fn(async () => ({ job: 'j1', count: 1 })),
      job: vi.fn(async () => {
        controller.abort();
        return { id: 'j1', kind: 'batch', state: 'running', total: 1, done: 0,
                 failed: 0, events: [], results: [] };
      }),
    } as unknown as LabClient;
    const events = await collect(runSheet({
      client, parts: ['3005'], config: {}, signal: controller.signal, pollMs: 0,
    }));
    expect(events.filter((e) => e.kind === 'item')).toEqual([]);
  });
});
