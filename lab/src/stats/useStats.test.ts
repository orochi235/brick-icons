import { describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useStats } from '@lab/stats/useStats';
import { DEFAULT_SET } from '@lab/stats/workingSet';
import type { Stats } from '@lab/stats/types';

const body = (open: boolean): Stats => ({
  set: { size: 2, total: 3, kind: 'all', moved: false, out_of_scope: true,
         excluded: [], badges: [] },
  coverage: [], speed: [], error: [],
  runs: [{ id: 1, kind: 'census', started: 's', finished: open ? null : 'f',
           open, commit_sha: 'abc1234', args: '{}', note: null, parts: 2 }],
  shape: { categories: [], kinds: { printed: 0, obsolete: 0, base: 0,
                                    out_of_scope: 0, moved: 0 }, dated: 0 },
  as_of: '2026-09-06T18:00:00+00:00',
});

const clientFor = (corpusStats: unknown) =>
  ({ corpusStats } as unknown as Parameters<typeof useStats>[0]);

describe('useStats', () => {
  it('reads the tallies once for a settled database', async () => {
    const corpusStats = vi.fn(async () => body(false));
    const { result } = renderHook(() => useStats(clientFor(corpusStats), DEFAULT_SET, 10));
    await waitFor(() => expect(result.current.stats).not.toBeNull());
    expect(result.current.polling).toBe(false);
    await new Promise((r) => setTimeout(r, 60));
    expect(corpusStats).toHaveBeenCalledTimes(1);
  });

  it('keeps re-reading while a run is open', async () => {
    const corpusStats = vi.fn(async () => body(true));
    const { result, unmount } = renderHook(
      () => useStats(clientFor(corpusStats), DEFAULT_SET, 10));
    await waitFor(() => expect(result.current.polling).toBe(true));
    await waitFor(() => expect(corpusStats.mock.calls.length).toBeGreaterThan(2));
    unmount();
    const settled = corpusStats.mock.calls.length;
    await new Promise((r) => setTimeout(r, 60));
    // The timer does not outlive the page that armed it.
    expect(corpusStats.mock.calls.length).toBe(settled);
  });

  it('sends the working set as the query', async () => {
    const corpusStats = vi.fn(async (_q: URLSearchParams) => body(false));
    renderHook(() => useStats(clientFor(corpusStats),
                              { ...DEFAULT_SET, kind: 'base', excluded: ['Sticker'] }, 10));
    await waitFor(() => expect(corpusStats).toHaveBeenCalled());
    const q = corpusStats.mock.calls[0]![0];
    expect(q.get('kind')).toBe('base');
    expect(q.getAll('excluded')).toEqual(['Sticker']);
  });

  it('keeps the numbers it has when a read fails', async () => {
    let fail = false;
    const corpusStats = vi.fn(async () => {
      if (fail) throw new Error('database is locked');
      return body(false);
    });
    const { result } = renderHook(() => useStats(clientFor(corpusStats), DEFAULT_SET, 10));
    await waitFor(() => expect(result.current.stats).not.toBeNull());
    fail = true;
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.error).toBe('database is locked'));
    expect(result.current.stats).not.toBeNull();
  });
});
