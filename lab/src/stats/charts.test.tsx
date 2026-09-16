// Focused on the slot-materials wiring in charts.tsx: a chip beside a slot
// name, a material fill in the cost bars, and the two line charts staying
// untouched. StatsPage.test.tsx exercises these charts through the whole
// page and its client plumbing; testing them directly here needs neither.
import { describe, expect, it } from 'vitest';
import { act, render } from '@testing-library/react';
import { CostBars, CoverageBars, SecsOverlay, SlotLines } from '@lab/stats/charts';
import type { Cost, CoverageRow, SpeedRow } from '@lab/stats/types';

const COVERAGE_ROWS: CoverageRow[] = [
  { source: 'occt', engine: 'occt', size: 10,
    counts: { defect: 0, failed: 0, timeout: 0, drawn: 8, untried: 2, notApplicable: 0 } },
  { source: 'naive', engine: 'naive', size: 10,
    counts: { defect: 1, failed: 0, timeout: 0, drawn: 7, untried: 2, notApplicable: 0 } },
];

const COST: Cost = {
  build: '1.aaa', base: 'occt', n: 100, total: 60,
  slots: [
    { source: 'occt', build: '1.aaa', revisions: 1, n: 100, total: 40,
      share: 0.4, ratio: 1, median: 6.2, p90: 58 },
    { source: 'naive', build: '1.aaa', revisions: 1, n: 100, total: 20,
      share: 0.2, ratio: 0.5, median: 3.1, p90: 20 },
  ],
};

const SPEED_ROWS: SpeedRow[] = [
  { engine: 'occt', n: 10, total: 40, median: 4, p95: 8, max: 9,
    bins: [{ from: 0, to: 1, n: 4 }, { from: 1, to: null, n: 6 }] },
  { engine: 'naive', n: 8, total: 30, median: 3, p95: 7, max: 8,
    bins: [{ from: 0, to: 1, n: 3 }, { from: 1, to: null, n: 5 }] },
];

/** Stands in for the browser's real one: `test-setup.ts`'s stub never calls
 *  back, so a test that needs a measurement supplies its own and fires it
 *  by hand, the way `CorpusWall.test.tsx` does. */
class CapturingResizeObserver {
  static instances: CapturingResizeObserver[] = [];
  cb: ResizeObserverCallback;
  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
    CapturingResizeObserver.instances.push(this);
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}

function installCapturingResizeObserver() {
  CapturingResizeObserver.instances = [];
  const original = globalThis.ResizeObserver;
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = CapturingResizeObserver;
  return () => { (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = original; };
}

function fireTrackWidth(width: number) {
  const observer = CapturingResizeObserver.instances[0]!;
  act(() => {
    observer.cb([{ contentRect: { width } } as ResizeObserverEntry],
                observer as unknown as ResizeObserver);
  });
}

describe('CostBars', () => {
  it('renders nothing in the fill track before the track is measured', () => {
    const restore = installCapturingResizeObserver();
    try {
      const { container } = render(<CostBars cost={COST} />);
      const fills = container.querySelectorAll('.stats-cost-row .stats-bar .material-bar');
      expect(fills.length).toBe(0);
    } finally {
      restore();
    }
  });

  it("a row's material fill width tracks its share of the widest", () => {
    const restore = installCapturingResizeObserver();
    try {
      const { container } = render(<CostBars cost={COST} />);
      fireTrackWidth(200);
      const rows = [...container.querySelectorAll('.stats-cost-row:not(.stats-cost-head)')];
      const width = (row: Element) =>
        Number(row.querySelector('.stats-bar .material-bar')!.getAttribute('width'));
      // occt's share (0.4) is the widest, so it fills the whole track; naive
      // (0.2) is exactly half that.
      expect(width(rows[0]!)).toBe(200);
      expect(width(rows[1]!)).toBe(100);
    } finally {
      restore();
    }
  });
});

describe('slot-name chips', () => {
  it('CoverageBars puts a chip before the name, leaving its text unchanged', () => {
    const { container } = render(<CoverageBars rows={COVERAGE_ROWS} />);
    const names = [...container.querySelectorAll('.stats-bar-name')];
    expect(names).toHaveLength(2);
    for (const [i, name] of names.entries()) {
      expect(name.querySelector('.material-bar')).toBeTruthy();
      expect(name.textContent).toBe(COVERAGE_ROWS[i]!.source);
      // The chip precedes the name in the DOM, so it draws first visually.
      expect(name.firstElementChild?.classList.contains('material-bar')).toBe(true);
    }
  });

  it('CostBars puts a chip before the name, leaving its text unchanged', () => {
    const { container } = render(<CostBars cost={COST} />);
    const names = [...container.querySelectorAll('.stats-cost-row:not(.stats-cost-head) .stats-bar-name')];
    expect(names).toHaveLength(2);
    for (const [i, name] of names.entries()) {
      expect(name.querySelector('.material-bar')).toBeTruthy();
      // Both COST rows share cost.build at one revision and are not thin, so
      // no dagger follows the name -- textContent is the bare source.
      expect(name.textContent).toBe(COST.slots[i]!.source);
    }
  });
});

describe('SecsOverlay', () => {
  it('shows a chip per engine in the legend', () => {
    const { container } = render(<SecsOverlay rows={SPEED_ROWS} />);
    const keys = [...container.querySelectorAll('.stats-overlay-key')];
    expect(keys).toHaveLength(2);
    for (const key of keys) {
      expect(key.querySelector('.material-bar')).toBeTruthy();
    }
  });

  it('draws the bins by color, not by material bar', () => {
    const { container } = render(<SecsOverlay rows={SPEED_ROWS} />);
    expect(container.querySelectorAll('.stats-bins .material-bar').length).toBe(0);
  });
});

describe('SlotLines', () => {
  it('never draws a material bar', () => {
    const rows = [
      { at: '2026-09-09T00:00:00+00:00', source: 'occt', bad: 2, size: 10, build: '1.aaa' },
      { at: '2026-09-10T00:00:00+00:00', source: 'occt', bad: 1, size: 10, build: '1.aaa' },
    ];
    const { container } = render(
      <SlotLines rows={rows} unit="count" caption="what will not draw" />);
    expect(container.querySelectorAll('.material-bar').length).toBe(0);
  });
});
