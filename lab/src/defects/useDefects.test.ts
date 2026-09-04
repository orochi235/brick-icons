import { describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { buildDefect, useDefects } from '@lab/defects/useDefects';
import type { LabClient } from '@lab/api/client';

describe('buildDefect', () => {
  const args = {
    part: '3941',
    engines: ['occt'],
    title: 'borehole rim not drawn',
    notes: '',
    mark: { x: 0.42, y: 0.55, w: 0.11, h: 0.09 },
    config: { angle: '30,25', shading: 'outline', shade_style: 'flat3' },
    existing: [] as string[],
    today: '2026-08-31',
  };

  it('builds a record the server will accept', () => {
    const got = buildDefect(args);
    expect(got.id).toBe('3941-occt-borehole-rim-not-drawn');
    expect(got.part).toBe('3941');
    expect(got.engines).toEqual(['occt']);
    expect(got.status).toBe('open');
    expect(got.mark).toEqual(args.mark);
    expect(got.filed).toBe('2026-08-31');
  });

  it('avoids an id already in use', () => {
    expect(buildDefect({ ...args, existing: ['3941-occt-borehole-rim-not-drawn'] }).id)
      .toBe('3941-occt-borehole-rim-not-drawn-2');
  });

  it('keeps notes when given', () => {
    expect(buildDefect({ ...args, notes: 'only at 30,25' }).notes).toBe('only at 30,25');
  });

  it('refuses an untitled defect, which nothing could later find', () => {
    expect(() => buildDefect({ ...args, title: '   ' })).toThrow(/title/i);
  });

  it('carries a mark kind and its points', () => {
    const d = buildDefect({
      part: '3001', engines: ['naive'], title: 'missing edge', notes: '',
      mark: { x: 0.1, y: 0.1, w: 0.3, h: 0.2 },
      kind: 'line',
      points: [{ x: 0.1, y: 0.1 }, { x: 0.4, y: 0.3 }],
      config: {}, existing: [], today: '2026-09-03',
    });
    expect(d.kind).toBe('line');
    expect(d.points).toHaveLength(2);
  });

  it('leaves kind and points off a plain rectangle', () => {
    const d = buildDefect({
      part: '3001', engines: ['naive'], title: 'blob', notes: '',
      mark: { x: 0, y: 0, w: 0.2, h: 0.2 },
      config: {}, existing: [], today: '2026-09-03',
    });
    expect(d.kind).toBeUndefined();
    expect(d.points).toBeUndefined();
  });
});

const record = buildDefect({
  part: '3941', engines: ['occt'], title: 'a', notes: '',
  mark: { x: 0, y: 0, w: 1, h: 1 }, config: {}, existing: [], today: '2026-08-31',
});

function fakeClient() {
  const rows: unknown[] = [];
  return {
    rows,
    client: {
      defects: vi.fn(async () => [...rows]),
      addDefect: vi.fn(async (r: unknown) => { rows.push(r); return r; }),
      patchDefect: vi.fn(async () => ({})),
    } as unknown as LabClient,
  };
}

describe('useDefects', () => {
  it('loads the part it was given', async () => {
    const { client } = fakeClient();
    const { result } = renderHook(() => useDefects(client, '3941'));
    await waitFor(() => expect(client.defects).toHaveBeenCalledWith('3941'));
    expect(result.current.defects).toEqual([]);
  });

  it('asks for nothing when no part is chosen', async () => {
    const { client } = fakeClient();
    renderHook(() => useDefects(client, '   '));
    await waitFor(() => expect(client.defects).not.toHaveBeenCalled());
  });

  // The status bar and the panes each hold their own hook. A file in one that
  // the other never sees is a count that reads `no defects` beside a drawn mark.
  it('refreshes every hook on the same part when one files', async () => {
    const { client } = fakeClient();
    const a = renderHook(() => useDefects(client, '3941'));
    const b = renderHook(() => useDefects(client, '3941'));
    await waitFor(() => expect(a.result.current.defects).toEqual([]));

    await act(async () => { await a.result.current.file(record); });

    await waitFor(() => expect(b.result.current.defects).toHaveLength(1));
  });

  it('leaves a hook on another part alone', async () => {
    const { client } = fakeClient();
    const a = renderHook(() => useDefects(client, '3941'));
    const other = renderHook(() => useDefects(client, '4070'));
    await waitFor(() => expect(a.result.current.defects).toEqual([]));
    const before = (client.defects as ReturnType<typeof vi.fn>).mock.calls.length;

    await act(async () => { await a.result.current.file(record); });

    // one reload for the filer itself, none for the other part
    await waitFor(() => expect(a.result.current.defects).toHaveLength(1));
    expect((client.defects as ReturnType<typeof vi.fn>).mock.calls
      .slice(before).filter(([p]) => p === '4070')).toEqual([]);
    expect(other.result.current.defects).toEqual([]);
  });
});
