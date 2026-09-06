import { createElement } from 'react';
import { expect, it, vi } from 'vitest';
import { act, render, renderHook } from '@testing-library/react';
import { mergeCells, POLL_MS, useCells } from '@lab/corpus/useCells';
import type { Cell, CellsBody } from '@lab/corpus/types';
import type { LabClient } from '@lab/api/client';

const cell = (id: string, index: number, sha: string | null = null): Cell => ({
  id, index, title: id, category: null, printed: false, obsolete: false,
  status: 'unreviewed', sha, made_at: null, extra_d99: null, secs: null,
  error: null, open_defects: 0, open_defects_elsewhere: 0,
  error_elsewhere: false,
});

it('replaces a cell the delta names', () => {
  const merged = mergeCells([cell('a', 0), cell('b', 1)],
                            [cell('b', 1, 'sha-b')]);
  expect(merged[1]!.sha).toBe('sha-b');
});

it('leaves untouched cells alone, by identity', () => {
  const a = cell('a', 0);
  const merged = mergeCells([a, cell('b', 1)], [cell('b', 1, 'sha-b')]);
  expect(merged[0]).toBe(a);
});

it('keeps the array in index order', () => {
  const merged = mergeCells([cell('a', 0), cell('b', 1), cell('c', 2)],
                            [cell('c', 2, 'sha-c'), cell('a', 0, 'sha-a')]);
  expect(merged.map((c) => c.id)).toEqual(['a', 'b', 'c']);
});

it('ignores a delta cell that is not on the wall', () => {
  const merged = mergeCells([cell('a', 0)], [cell('zz', 99)]);
  expect(merged.map((c) => c.id)).toEqual(['a']);
});

it('returns the same array when the delta is empty', () => {
  const current = [cell('a', 0)];
  expect(mergeCells(current, [])).toBe(current);
});

/** A stub `cells()` keyed by call count, so a test can script what each poll
 *  returns without caring how the hook decides when to call it. */
function fakeClient(bodies: Record<string, CellsBody[]>) {
  const cursor: Record<string, number> = {};
  const calls: { source: string; since?: string }[] = [];
  const client = {
    cells: vi.fn(async (source: string, since?: string) => {
      calls.push({ source, since });
      const list = bodies[source] ?? [];
      const i = cursor[source] ?? 0;
      cursor[source] = Math.min(i + 1, list.length - 1);
      return list[i]!;
    }),
  } as unknown as LabClient;
  return { client, calls };
}

// Under fake timers, testing-library's `waitFor` polls with a real timer and
// never sees a resolution -- flush the microtask queue by hand instead.
async function flush() {
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
}

it('fetches the full list on mount, then polls the delta and merges it', async () => {
  vi.useFakeTimers();
  try {
    const full: CellsBody = {
      cells: [cell('a', 0), cell('b', 1)], count: 2, version: 'v1', source: 'naive',
    };
    const delta: CellsBody = {
      cells: [cell('b', 1, 'sha-b')], count: 2, version: 'v2', source: 'naive',
    };
    const { client, calls } = fakeClient({ naive: [full, delta] });

    const { result, unmount } = renderHook(() => useCells(client, 'naive'));

    await flush();
    expect(result.current!.map((c) => c.id)).toEqual(['a', 'b']);
    expect(calls[0]).toEqual({ source: 'naive', since: undefined });

    const untouched = result.current![0];

    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS); });

    expect(calls[1]).toEqual({ source: 'naive', since: 'v1' });
    expect(result.current!.find((c) => c.id === 'b')!.sha).toBe('sha-b');
    expect(result.current![0]).toBe(untouched);

    unmount();
    const callsBeforeUnmount = calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS * 3); });
    expect(calls.length).toBe(callsBeforeUnmount);
  } finally {
    vi.useRealTimers();
  }
});

it('refetches from scratch, with no since, when the source changes', async () => {
  vi.useFakeTimers();
  try {
    const naiveFull: CellsBody = {
      cells: [cell('a', 0)], count: 1, version: 'v1', source: 'naive',
    };
    const occtFull: CellsBody = {
      cells: [cell('a', 0, 'sha-occt')], count: 1, version: 'w1', source: 'occt',
    };
    const { client, calls } = fakeClient({ naive: [naiveFull], occt: [occtFull] });

    const { result, rerender } = renderHook(
      ({ source }) => useCells(client, source),
      { initialProps: { source: 'naive' } },
    );
    await flush();
    expect(calls[0]).toEqual({ source: 'naive', since: undefined });

    rerender({ source: 'occt' });
    await flush();

    const occtCall = calls.find((c) => c.source === 'occt');
    expect(occtCall).toEqual({ source: 'occt', since: undefined });
    expect(result.current!.find((c) => c.id === 'a')!.sha).toBe('sha-occt');
  } finally {
    vi.useRealTimers();
  }
});

it('clears cells during render on a source change, so no child ever sees the new source paired with the old slot\'s cells', async () => {
  const seen: { source: string; cells: Cell[] | null }[] = [];
  let resolveNaive!: (body: CellsBody) => void;
  const naive = new Promise<CellsBody>((res) => { resolveNaive = res; });
  const client = {
    cells: vi.fn((source: string) =>
      source === 'naive' ? naive : new Promise<CellsBody>(() => {})),
  } as unknown as LabClient;

  function Child({ source, cells }: { source: string; cells: Cell[] | null }) {
    seen.push({ source, cells });
    return null;
  }
  function Parent({ source }: { source: string }) {
    return createElement(Child, { source, cells: useCells(client, source) });
  }

  const { rerender } = render(createElement(Parent, { source: 'naive' }));
  await act(async () => {
    resolveNaive({ cells: [cell('a', 0, 'sha-a')], count: 1,
                    version: 'v1', source: 'naive' });
  });
  expect(seen.at(-1)!.cells).not.toBeNull();

  seen.length = 0;
  rerender(createElement(Parent, { source: 'occt' }));

  expect(seen.every((s) => !(s.source === 'occt' && s.cells !== null))).toBe(true);
  expect(seen[0]).toEqual({ source: 'occt', cells: null });
});
