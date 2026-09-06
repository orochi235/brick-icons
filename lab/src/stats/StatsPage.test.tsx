import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StatsPage } from '@lab/stats/StatsPage';
import type { Stats } from '@lab/stats/types';

const body = (over: Partial<Stats> = {}): Stats => ({
  set: { size: 20, total: 24, kind: 'all', moved: false, out_of_scope: true,
         excluded: [], badges: [] },
  coverage: [{ source: 'census-naive', engine: 'naive', size: 20,
               counts: { defect: 1, failed: 2, timeout: 3, drawn: 8, untried: 6 } }],
  speed: [{ engine: 'naive', n: 14, total: 100, median: 2, p95: 30, max: 90,
            bins: [{ from: 0, to: 1, n: 4 }, { from: 1, to: null, n: 10 }] }],
  error: [{ engine: 'naive',
            d99: { n: 14, total: 0, median: 1.25, p95: 4, max: 9 },
            missing_px: { n: 14, total: 0, median: 3, p95: 8, max: 20 } }],
  runs: [{ id: 1, kind: 'census', started: '2026-09-06T09:00:00+00:00',
           finished: '2026-09-06T10:00:00+00:00', open: false,
           commit_sha: 'abc1234def', args: '{}', note: null, parts: 14 }],
  shape: { categories: [['Brick', 900], ['Minifig', 300], ['Rare', 4]],
           kinds: { printed: 2, obsolete: 1, base: 17, out_of_scope: 0, moved: 0 },
           dated: 11 },
  as_of: '2026-09-06T18:42:00+00:00',
  ...over,
});

const clientWith = (corpusStats: (q: URLSearchParams) => Promise<Stats>) =>
  ({ corpusStats } as unknown as Parameters<typeof StatsPage>[0]['client']);

describe('StatsPage', () => {
  it('says how big the working set is and when it was read', async () => {
    render(<StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => screen.getByText(/20 of 24 parts/));
    expect(screen.getByText(/as of 18:42/)).toBeTruthy();
  });

  it('draws a segment per coverage label, none of them zero-width', async () => {
    const { container } = render(<StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => expect(container.querySelectorAll('.stats-seg').length).toBe(5));
    const labels = [...container.querySelectorAll('.stats-seg')]
      .map((el) => el.getAttribute('data-label'));
    expect(labels).toEqual(['defect', 'failed', 'timeout', 'drawn', 'untried']);
  });

  it('leaves out a label no part is in', async () => {
    const none = body();
    none.coverage[0]!.counts.defect = 0;
    const { container } = render(<StatsPage client={clientWith(async () => none)} />);
    await waitFor(() => expect(container.querySelectorAll('.stats-seg').length).toBe(4));
  });

  it('sends a bar into the wall showing the same slot', async () => {
    const { container } = render(<StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => container.querySelector('a.stats-seg'));
    const href = container.querySelector('a.stats-seg')?.getAttribute('href') ?? '';
    expect(href.startsWith('/corpus.html?')).toBe(true);
    expect(new URLSearchParams(href.slice(href.indexOf('?'))).get('source'))
      .toBe('census-naive');
  });

  it('re-reads with the working set when a category is unticked', async () => {
    const corpusStats = vi.fn(async (_q: URLSearchParams) => body());
    render(<StatsPage client={clientWith(corpusStats)} />);
    await waitFor(() => screen.getByLabelText(/Brick/));
    fireEvent.click(screen.getByLabelText(/Brick/));
    await waitFor(() => expect(corpusStats.mock.calls.length).toBe(2));
    expect(corpusStats.mock.calls[1]![0].getAll('excluded')).toEqual(['Brick']);
  });

  it('offers a checkbox only for a category big enough to matter', async () => {
    render(<StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => screen.getByLabelText(/Brick/));
    expect(screen.queryByLabelText(/Rare/)).toBeNull();
  });

  it('says a run is still going, and only while it is', async () => {
    const open = body();
    open.runs[0]!.open = true;
    open.runs[0]!.finished = null;
    render(<StatsPage client={clientWith(async () => open)} />);
    await waitFor(() => screen.getByText('still running'));
    expect(screen.getByText(/a run is open, re-reading/)).toBeTruthy();
  });

  it('shows what a failed read said without dropping the numbers', async () => {
    let fail = false;
    render(<StatsPage client={clientWith(async () => {
      if (fail) throw new Error('database is locked');
      return body();
    })} />);
    await waitFor(() => screen.getByText(/20 of 24 parts/));
    fail = true;
    fireEvent.click(screen.getByText('Reload'));
    await waitFor(() => screen.getByRole('alert'));
    expect(screen.getByRole('alert').textContent).toBe('database is locked');
    expect(screen.getByText(/20 of 24 parts/)).toBeTruthy();
  });
});
