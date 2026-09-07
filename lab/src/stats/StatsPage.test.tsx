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
  phases: [{ engine: 'naive', n: 14, total: 100,
             totals: { render: 70, rasterize: 10, truth_mask: 15, compare: 5 },
             split: { n: 3, total: 40,
                      totals: { geometry: 20, decoration: 4, fill: 14, rest: 2 } },
             slowest: [
               { part_id: '3001', total: 30,
                 secs: { render: 20, rasterize: 4, truth_mask: 5, compare: 1 },
                 split: { geometry: 12, decoration: 0, fill: 7, rest: 1 } },
               { part_id: '3002', total: 10,
                 secs: { render: 7, rasterize: 1, truth_mask: 1, compare: 1 },
                 split: null }] }],
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
    await waitFor(() =>
      expect(container.querySelectorAll('.stats-bars .stats-seg').length).toBe(5));
    const labels = [...container.querySelectorAll('.stats-bars .stats-seg')]
      .map((el) => el.getAttribute('data-label'));
    expect(labels).toEqual(['defect', 'failed', 'timeout', 'drawn', 'untried']);
  });

  it('leaves out a label no part is in', async () => {
    const none = body();
    none.coverage[0]!.counts.defect = 0;
    const { container } = render(<StatsPage client={clientWith(async () => none)} />);
    await waitFor(() =>
      expect(container.querySelectorAll('.stats-bars .stats-seg').length).toBe(4));
  });


  it('stacks the four phases per engine, longest first in the data order', async () => {
    const { container } = render(<StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => container.querySelector('.stats-phases'));
    const phases = [...container.querySelectorAll('.stats-phases .stats-bar')[0]!
      .querySelectorAll('.stats-seg')].map((el) => el.getAttribute('data-phase'));
    expect(phases).toEqual(['render', 'rasterize', 'truth_mask', 'compare']);
  });

  it('gives the render split its own bar and says how few rows it covers', async () => {
    const { container } = render(<StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => container.querySelector('.stats-phase-split'));
    const split = [...container.querySelectorAll('.stats-seg[data-split]')]
      .map((el) => el.getAttribute('data-split'));
    expect(split).toEqual(['geometry', 'decoration', 'fill', 'rest']);
    expect(screen.getByText(/3 of 14 parts measured since the split existed/))
      .toBeTruthy();
  });

  it('leaves the split bar out when no row in the set carries one', async () => {
    const none = body();
    none.phases[0]!.split = null;
    const { container } = render(<StatsPage client={clientWith(async () => none)} />);
    await waitFor(() => container.querySelector('.stats-phases'));
    expect(container.querySelector('.stats-phase-split')).toBe(null);
  });

  it('draws the slowest parts shortest first, scaled to the tallest', async () => {
    const { container } = render(<StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => container.querySelector('.stats-column-plot'));
    const columns = [...container.querySelectorAll('.stats-column')];
    expect(columns.map((el) => el.getAttribute('title')))
      .toEqual(['3002 — 10.0s', '3001 — 30.0s']);
    // The tallest part fills the plot; a third of its cost is a third as tall.
    expect((columns[1] as HTMLElement).style.height).toBe('100%');
    expect((columns[0] as HTMLElement).style.height).toBe('33.33333333333333%');
  });

  it('scales both engines to one count, so their bars are comparable', async () => {
    const two = body();
    two.speed = [
      { engine: 'naive', n: 14, total: 100, median: 2, p95: 30, max: 90,
        bins: [{ from: 0, to: 1, n: 4 }, { from: 1, to: null, n: 10 }] },
      { engine: 'occt', n: 25, total: 60, median: 1, p95: 9, max: 20,
        bins: [{ from: 0, to: 1, n: 20 }, { from: 1, to: null, n: 5 }] },
    ];
    const { container } = render(<StatsPage client={clientWith(async () => two)} />);
    await waitFor(() => container.querySelector('.stats-bin-fill'));
    const heights = [...container.querySelectorAll('.stats-bin-fill')]
      .map((el) => [(el as HTMLElement).dataset.engine, (el as HTMLElement).style.height]);
    // 20 is the tallest bar anywhere, so it is the 100% both engines divide by.
    // Per-panel scaling drew naive's 10 and occt's 20 at the same height.
    expect(heights).toEqual([
      ['naive', '20%'], ['occt', '100%'],
      ['naive', '50%'], ['occt', '25%'],
    ]);
  });

  it('names both engines rather than leaving the fills to say which is which',
     async () => {
    const two = body();
    two.speed = [
      { engine: 'naive', n: 14, total: 100, median: 2, p95: 30, max: 90,
        bins: [{ from: 0, to: 1, n: 4 }, { from: 1, to: null, n: 10 }] },
      { engine: 'occt', n: 25, total: 60, median: 1, p95: 9, max: 20,
        bins: [{ from: 0, to: 1, n: 20 }, { from: 1, to: null, n: 5 }] },
    ];
    const { container } = render(<StatsPage client={clientWith(async () => two)} />);
    await waitFor(() => container.querySelector('.stats-overlay-key'));
    expect([...container.querySelectorAll('.stats-overlay-key strong')]
      .map((el) => el.textContent)).toEqual(['naive', 'occt']);
  });

  it('says so rather than drawing an empty chart when nothing is timed', async () => {
    const none = body();
    none.phases = [];
    render(<StatsPage client={clientWith(async () => none)} />);
    await waitFor(() =>
      screen.getByText('nothing in this set carries phase timings'));
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
