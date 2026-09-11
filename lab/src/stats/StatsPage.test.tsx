import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StatsPage } from '@lab/stats/StatsPage';
import type { Stats } from '@lab/stats/types';

const body = (over: Partial<Stats> = {}): Stats => ({
  set: { size: 20, total: 24, kind: 'all', moved: false, out_of_scope: true,
         excluded: [], badges: [] },
  failures: {
    totals: { size: 24,
              occt: { bad: 5, failed: 3, timeout: 2, facets: ['occt'] },
              decal: { bad: 7, failed: 7, timeout: 0 } },
    series: [
      { at: '2026-09-09T00:00:00+00:00', source: 'occt', build: '1.aaa',
        size: 24, failed: 4, timeout: 2, bad: 6 },
      { at: '2026-09-10T00:00:00+00:00', source: 'occt', build: '2.bbb',
        size: 24, failed: 3, timeout: 2, bad: 5 },
      { at: '2026-09-10T00:00:00+00:00', source: 'decal', build: null,
        size: 24, failed: 7, timeout: 0, bad: 7 },
    ],
    by_build: [
      { at: '2026-09-09T00:00:00+00:00', source: 'occt', build: '1.aaa',
        size: 10, failed: 2, timeout: 0, bad: 2 },
    ],
  },
  coverage: [{ source: 'silhouette-naive', engine: 'naive', size: 20,
               counts: { defect: 1, failed: 2, timeout: 3, drawn: 8, untried: 6,
                          notApplicable: 0 } }],
  speed: [{ engine: 'naive', n: 14, total: 100, median: 2, p95: 30, max: 90,
            bins: [{ from: 0, to: 1, n: 4 }, { from: 1, to: null, n: 10 }] }],
  error: [{ engine: 'naive',
            d99: { n: 14, total: 0, median: 1.25, p95: 4, max: 9 },
            missing_px: { n: 14, total: 0, median: 3, p95: 8, max: 20 } }],
  phases: [{ engine: 'naive', n: 14, total: 100,
             totals: { render: 70, rasterize: 10, truth_mask: 15, compare: 5 },
             split: { n: 3, total: 40, nodes: [
               { name: 'render', path: 'render', secs: 40, n: 3, children: [
                 { name: 'geometry', path: 'render/geometry', secs: 24, n: 3,
                   children: [
                     { name: 'engine', path: 'render/geometry/engine', secs: 20,
                       n: 3, children: [] },
                     { name: 'rest', path: 'render/geometry/rest', secs: 4,
                       children: [] }] },
                 { name: 'fill', path: 'render/fill', secs: 14, n: 2,
                   children: [] },
                 { name: 'rest', path: 'render/rest', secs: 2, children: [] }] }] },
             slowest: [
               { part_id: '3001', total: 30,
                 secs: { render: 20, rasterize: 4, truth_mask: 5, compare: 1 },
                 split: [{ name: 'render', path: 'render', secs: 20,
                           children: [] }] },
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

// The footprint reads its own route. Without a stub it fails and raises a
// second alert, which is indistinguishable from the one a stats error raises.
const EMPTY_FOOTPRINT = {
  tiles: { out: 0, renders: 0, bakes: 0, lab_cache: 0, library: 0,
           corpus_db: 0, git: 0 },
  slots: [],
  as_of: '2026-09-06T18:42:00+00:00',
};

type Client = Parameters<typeof StatsPage>[0]['client'];

const clientWith = (corpusStats: (q: URLSearchParams) => Promise<Stats>) =>
  ({ corpusStats, corpusSizes: async () => EMPTY_FOOTPRINT } as unknown as Client);

describe('StatsPage', () => {
  // -- the failure strip and chart ----------------------------------------

  it('puts the tiles above the coverage bars', async () => {
    const { container } = render(
      <StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => container.querySelector('.stats-tiles'));
    const headings = [...container.querySelectorAll('h2')].map((h) => h.textContent);
    const tiles = container.querySelector('.stats-tiles')!;
    const coverage = [...container.querySelectorAll('h2')]
      .find((h) => h.textContent === 'Coverage')!;
    expect(headings).toContain('Coverage');
    expect(tiles.compareDocumentPosition(coverage)
           & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('leads the strip with what occt and decal cannot draw, corpus-wide', async () => {
    const { container } = render(
      <StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => container.querySelector('.stats-tile-wide'));
    const wide = [...container.querySelectorAll('.stats-tile-wide')];
    expect(wide.length).toBe(2);
    expect(wide[0]!.textContent).toContain('5');
    expect(wide[0]!.textContent).toContain('parts occt cannot draw, corpus-wide');
    expect(wide[1]!.textContent).toContain('7');
    expect(wide[1]!.textContent).toContain('parts decal cannot draw, corpus-wide');
    // First two in the strip, so the number a reader came for is not third.
    const all = [...container.querySelectorAll('.stats-tile')];
    expect(all.slice(0, 2)).toEqual(wide);
  });

  it('draws one failure line per slot, each keeping its own hue', async () => {
    const { container } = render(
      <StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => container.querySelector('.stats-failure-line'));
    const slots = [...container.querySelectorAll('.stats-failures')][0]!
      .querySelectorAll('.stats-failure-line');
    expect([...slots].map((el) => el.getAttribute('data-slot')))
      .toEqual(['occt', 'decal']);
  });

  it('says a tally is owed rather than drawing an empty chart', async () => {
    const none = body();
    none.failures.series = [];
    render(<StatsPage client={clientWith(async () => none)} />);
    await waitFor(() => screen.getByText(/no tally has been taken yet/));
  });

  it('keeps the build prefix on its own axis, as a rate', async () => {
    const { container } = render(
      <StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => container.querySelector('.stats-failures'));
    const figures = container.querySelectorAll('.stats-failures');
    expect(figures.length).toBe(2);
    // 2 of 10 drawn, so the rate axis tops out in percent, not in parts.
    expect(figures[1]!.textContent).toContain('%');
  });

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
    expect(labels).toEqual(['drawn', 'defect', 'failed', 'timeout', 'untried']);
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

  it('breaks the render down at every depth the engine named', async () => {
    const { container } = render(<StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => container.querySelector('.stats-phase-tree'));
    const names = [...container.querySelectorAll('.stats-phase-row')]
      .map((el) => el.querySelector('.stats-phase-name')!.textContent!.trim());
    expect(names).toEqual(['▾ render', '▾ geometry', 'engine', 'rest',
                           'fill', 'rest']);
  });

  it('says how few of the set carry a breakdown at all', async () => {
    render(<StatsPage client={clientWith(async () => body())} />);
    expect(await screen.findByText(/3 of 14 parts whose render named its stages/))
      .toBeTruthy();
  });

  it('says so rather than drawing a tree when no row carries one', async () => {
    const none = body();
    none.phases[0]!.split = null;
    const { container } = render(<StatsPage client={clientWith(async () => none)} />);
    await waitFor(() => container.querySelector('.stats-phases'));
    expect(container.querySelector('.stats-phase-tree')).toBe(null);
    expect(screen.getByText(/nothing in this set was measured with the render/))
      .toBeTruthy();
  });

  it('draws the slowest parts shortest first, scaled to the tallest', async () => {
    const { container } = render(<StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => container.querySelector('.stats-column-plot'));
    const cols = [...container.querySelectorAll('.stats-col-series')];
    expect(cols.map((el) => el.getAttribute('title')))
      .toEqual(['naive #1: 3002 — 10.0s', 'naive #2: 3001 — 30.0s']);
    // The tallest part fills the plot; a third of its cost is a third as tall.
    expect((cols[1] as HTMLElement).style.height).toBe('100%');
    expect((cols[0] as HTMLElement).style.height).toBe('33.33333333333333%');
  });

  it('puts every engine\'s slowest parts on one seconds scale', async () => {
    const two = body();
    two.phases = [
      { ...two.phases[0]!, engine: 'naive',
        slowest: [{ part_id: 'a', total: 10, split: null,
                    secs: { render: 10, rasterize: 0,
                            truth_mask: 0, compare: 0 } }] },
      { ...two.phases[0]!, engine: 'occt',
        slowest: [{ part_id: 'b', total: 40, split: null,
                    secs: { render: 40, rasterize: 0,
                            truth_mask: 0, compare: 0 } }] },
    ];
    const { container } = render(<StatsPage client={clientWith(async () => two)} />);
    await waitFor(() => container.querySelector('.stats-col-series'));
    // One rank slot holding both engines, the shorter drawn in front, and the
    // heights are a quarter and full against the taller of the two.
    const cols = [...container.querySelectorAll('.stats-col-series')] as HTMLElement[];
    expect(cols.map((el) => el.style.height)).toEqual(['25%', '100%']);
    expect(cols[0]!.getAttribute('data-front')).toBe('true');
    expect(cols[1]!.getAttribute('data-front')).toBe(null);
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
    // Scoped to the histogram: the slowest-parts plot is an overlay too, and
    // carries a key per engine of its own.
    expect([...container.querySelectorAll(
      '.stats-histogram .stats-overlay-key strong')]
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
    expect(href.startsWith('/corpus?')).toBe(true);
    expect(new URLSearchParams(href.slice(href.indexOf('?'))).get('source'))
      .toBe('silhouette-naive');
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
