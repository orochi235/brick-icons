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
             }],
  running: false,
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

const COST = {
  build: '1099.d500ca9+', base: 'occt', n: 1587, total: 1000,
  slots: [
    { source: 'occt', total: 400, share: 0.4, ratio: 1, median: 6.2, p90: 58 },
    { source: 'white-occt', total: 400, share: 0.4, ratio: 1.0, median: 6.2,
      p90: 58.9 },
    { source: 'translucent-occt', total: 200, share: 0.2, ratio: 0.5,
      median: 3.7, p90: 17.5 },
  ],
};

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

  it('renders the rest of the page when the API is older than the bundle', async () => {
    // The lab API is a separate process. A dev server started before
    // `failures` existed sends a payload without it, and nine other sections
    // must not go dark over that.
    const old = body();
    delete (old as { failures?: unknown }).failures;
    const { container } = render(<StatsPage client={clientWith(async () => old)} />);
    await waitFor(() => screen.getByText('Coverage'));
    expect(container.querySelectorAll('[role=alert]').length).toBe(0);
    // A dash, not a zero: "nothing is broken" and "this server cannot say"
    // must not draw the same.
    expect(container.querySelector('.stats-tile-wide strong')!.textContent).toBe('—');
    expect(screen.getAllByText(/predates the failure tallies/).length).toBe(2);
  });

  it('says a tally is owed rather than drawing an empty chart', async () => {
    const none = body();
    none.failures!.series = [];
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


  it('stacks the phases per engine in the order a census row runs them',
     async () => {
    const { container } = render(<StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => container.querySelector('.stats-phases'));
    const phases = [...container.querySelectorAll('.stats-phases .stats-bar')[0]!
      .querySelectorAll('.stats-seg')].map((el) => el.getAttribute('data-phase'));
    expect(phases).toEqual(['render', 'rasterize', 'truth_mask', 'compare']);
  });

  /** The fixture's tree is tallied over 3 of its 14 parts, so its stages come
   *  to 40 seconds against a 70-second render band. */
  const addingUp = () => {
    const one = body();
    const row = one.phases[0]!;
    row.totals = { ...row.totals, render: 40 };
    row.total = 70;
    return one;
  };

  it('divides the render band into the stages the engine named', async () => {
    const { container } = render(
      <StatsPage client={clientWith(async () => addingUp())} />);
    await waitFor(() => container.querySelector('.stats-phases'));
    const segs = [...container.querySelectorAll('.stats-phases .stats-bar')[0]!
      .querySelectorAll('.stats-seg')] as HTMLElement[];
    expect(segs.map((el) => el.title.split(' —')[0]))
      .toEqual(['geometry', 'fill', 'render, unnamed',
                'rasterize', 'truth mask', 'compare']);
    // Against the whole bar, not against the render band: 24 of 70.
    expect(segs[0]!.style.width).toBe('34.285714285714285%');
  });

  it('names the render stages in the legend rather than a fixed four',
     async () => {
    const { container } = render(
      <StatsPage client={clientWith(async () => addingUp())} />);
    await waitFor(() => container.querySelector('.stats-phase-legend'));
    expect([...container.querySelectorAll('.stats-phase-legend li')]
      .map((el) => el.textContent))
      .toEqual(['geometry', 'fill', 'render, unnamed',
                'rasterize', 'truth mask', 'compare']);
  });

  it('leaves the render whole when its stages do not add up to it', async () => {
    // The fixture as it stands: a tree over 3 parts under a band over 14.
    // Drawing those stages as slices of this band would read as a whole they
    // are not.
    const { container } = render(<StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => container.querySelector('.stats-phases'));
    const segs = [...container.querySelectorAll('.stats-phases .stats-bar')[0]!
      .querySelectorAll('.stats-seg')] as HTMLElement[];
    expect(segs.map((el) => el.title.split(' —')[0])[0]).toBe('render');
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

  it('ticks the axis every ten seconds rather than labelling every bucket',
     async () => {
    const many = body();
    many.speed = [{ engine: 'occt', n: 30, total: 100, median: 5, p95: 40,
                    max: 90,
                    bins: [...Array.from({ length: 10 }, (_, i) => (
                      { from: i * 2, to: i * 2 + 2, n: 3 })),
                           { from: 20, to: null, n: 0 }] }];
    const { container } = render(<StatsPage client={clientWith(async () => many)} />);
    await waitFor(() => container.querySelector('.stats-bin-fill'));
    expect([...container.querySelectorAll('.stats-histogram .stats-bin-label')]
      .map((el) => el.textContent)).toEqual(['0s', '10s', '20s+']);
  });

  it('leaves an empty bucket empty instead of standing a stub on it',
     async () => {
    const gap = body();
    gap.speed = [{ engine: 'occt', n: 5, total: 10, median: 1, p95: 3, max: 4,
                   bins: [{ from: 0, to: 2, n: 5 }, { from: 2, to: 4, n: 0 },
                          { from: 4, to: null, n: 0 }] }];
    const { container } = render(<StatsPage client={clientWith(async () => gap)} />);
    await waitFor(() => container.querySelector('.stats-bin-fill'));
    // A bar carries `min-height: 1px`, so an empty bucket that still renders
    // one draws a tick mark the reader reads as a part that took that long.
    expect(container.querySelectorAll('.stats-histogram .stats-bin-fill').length)
      .toBe(1);
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
    open.running = true;
    render(<StatsPage client={clientWith(async () => open)} />);
    await waitFor(() => screen.getByText(/a run is open, re-reading/));
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

  // -- what a pass costs --------------------------------------------------

  it('draws one cost bar per slot, with its share and its ratio', async () => {
    const { container } = render(
      <StatsPage client={clientWith(async () => body({ cost: COST }))} />);
    await waitFor(() => container.querySelector('.stats-cost'));
    const rows = [...container.querySelectorAll('.stats-cost-row')]
      .filter((r) => !r.classList.contains('stats-cost-head'));
    expect(rows.map((r) => r.querySelector('.stats-bar-name')!.textContent))
      .toEqual(['occt', 'white-occt', 'translucent-occt']);
    expect(rows[2]!.textContent).toContain('20.0%');
    expect(rows[2]!.textContent).toContain('0.50');
    expect(rows[2]!.textContent).toContain('3.7');
  });

  it('names the revision the comparison was taken at', async () => {
    const { container } = render(
      <StatsPage client={clientWith(async () => body({ cost: COST }))} />);
    await waitFor(() => container.querySelector('.stats-cost'));
    const note = [...container.querySelectorAll('.stats-note')]
      .find((n) => n.textContent?.includes('1099.d500ca9+'))!;
    expect(note).toBeTruthy();
    expect(note.textContent).toContain('1,587');
  });

  it('says what running every slot costs against one base pass', async () => {
    const { container } = render(
      <StatsPage client={clientWith(async () => body({ cost: COST }))} />);
    await waitFor(() => container.querySelector('.stats-cost'));
    const note = [...container.querySelectorAll('.stats-note')]
      .find((n) => n.textContent?.includes('1099.d500ca9+'))!;
    // occt is 0.4 of the whole, so the three passes cost 2.5 of one.
    expect(note.textContent).toContain('2.5');
  });

  it('says so rather than drawing an empty panel when no two slots pair up',
     async () => {
    const { container } = render(
      <StatsPage client={clientWith(async () => body({ cost: null }))} />);
    await waitFor(() => container.querySelector('.stats-cost, .stats-empty'));
    expect(container.querySelector('.stats-cost')).toBeNull();
    expect(container.textContent)
      .toContain('no two slots have drawn the same parts');
  });

  it('draws the rest of the page when a stale API sends no cost', async () => {
    const { container } = render(
      <StatsPage client={clientWith(async () => body())} />);
    await waitFor(() => container.querySelector('.stats-tiles'));
    expect(container.querySelector('.stats-cost')).toBeNull();
    expect([...container.querySelectorAll('h2')].map((h) => h.textContent))
      .toContain('Coverage');
  });
});
