import { expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import * as camera from '@lab/corpus/camera';
import { CorpusWall } from '@lab/corpus/CorpusWall';
import type { Cell } from '@lab/corpus/types';

vi.mock('@lab/corpus/camera', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@lab/corpus/camera')>();
  return { ...actual, fitBounds: vi.fn(actual.fitBounds),
           pickLevel: vi.fn(actual.pickLevel) };
});

const cell = (id: string, index: number, sha: string | null = null): Cell => ({
  id, index, title: `Part ${id}`, category: 'Brick', printed: false,
  obsolete: false, status: 'unreviewed', sha, made_at: null,
  extra_d99: null, secs: null, error: null,
});

const client = {
  corpusSources: () => Promise.resolve({
    sources: [{ source: 'census-naive', n: 2 }],
  }),
  cells: () => Promise.resolve({
    cells: [cell('a', 0, 'sha-a'), cell('b', 1)], count: 2,
    version: '2026-09-05T10:00:00+00:00', source: 'census-naive',
  }),
  sheetManifest: () => Promise.resolve({
    level: 32, gutter: 2, pitch: 36, cols: 2, rows: 1, count: 2, size: 72,
    baked: { a: 'sha-a' },
  }),
  corpusPart: () => new Promise(() => {}),
} as any;

const findCanvas = (container: HTMLElement) => waitFor(() => {
  const el = container.querySelector('canvas');
  expect(el).toBeTruthy();
  return el as HTMLCanvasElement;
});

it('says it is loading before the cells arrive', () => {
  render(<CorpusWall client={{ cells: () => new Promise(() => {}),
                               corpusSources: () => new Promise(() => {}),
                               sheetManifest: () => new Promise(() => {}) } as any} />);
  expect(screen.getByText(/loading the corpus/i)).toBeTruthy();
});

it('draws a canvas once the cells arrive', async () => {
  const { container } = render(<CorpusWall client={client} />);
  await waitFor(() => expect(container.querySelector('canvas')).toBeTruthy());
});

it('reports how much of the corpus the filter is showing', async () => {
  render(<CorpusWall client={client} />);
  await waitFor(() => screen.getByText('2 of 2'));
  fireEvent.change(screen.getByLabelText('Show'),
                   { target: { value: 'unrendered' } });
  await waitFor(() => screen.getByText('1 of 2'));
});

it('raises a card on a single click', async () => {
  const { container } = render(<CorpusWall client={client} />);
  const canvas = await findCanvas(container);
  fireEvent.click(canvas, { clientX: 10, clientY: 10 });
  expect(await screen.findByRole('dialog', { name: /Part a/ })).toBeTruthy();
  expect(container.querySelector('.corpus-lightbox')).toBeNull();
});

it("raises the lightbox from the card's Open button", async () => {
  const { container } = render(<CorpusWall client={client} />);
  const canvas = await findCanvas(container);
  fireEvent.click(canvas, { clientX: 10, clientY: 10 });
  await screen.findByRole('dialog', { name: /Part a/ });
  fireEvent.click(screen.getByRole('button', { name: /open/i }));
  expect(await waitFor(() => container.querySelector('.corpus-lightbox')))
    .toBeTruthy();
  expect(container.querySelector('.corpus-card')).toBeNull();
});

it('opens the lightbox on a double click with no card flash', async () => {
  const { container } = render(<CorpusWall client={client} />);
  const canvas = await findCanvas(container);
  fireEvent.doubleClick(canvas, { clientX: 10, clientY: 10 });
  expect(await waitFor(() => container.querySelector('.corpus-lightbox')))
    .toBeTruthy();
  expect(container.querySelector('.corpus-card')).toBeNull();
});

it('opens on the level the initial fit asks for, and holds it through a jiggle', async () => {
  let observed: ResizeObserverCallback | null = null;
  class CapturingResizeObserver {
    constructor(cb: ResizeObserverCallback) { observed = cb; }
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  const original = globalThis.ResizeObserver;
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver =
    CapturingResizeObserver;

  const fit = vi.mocked(camera.fitBounds);
  const pick = vi.mocked(camera.pickLevel);
  fit.mockClear();
  pick.mockClear();
  // CELL(32) * 11/32 = 11px -- inside the 8/32 dead zone (10.7-24px) and
  // below the 16px boundary, so a fresh pick wants level 8. A fixed level
  // (32) held by pickLevel across this zone is exactly the pre-fix bug.
  fit.mockImplementation(() => ({ x: 0, y: 0, scale: 11 / 32 }));

  try {
    const { container } = render(<CorpusWall client={client} />);
    await waitFor(() => expect(container.querySelector('canvas')).toBeTruthy());

    // The very first pick bypasses pickLevel entirely -- there is nothing
    // yet to be hysteretic about.
    expect(pick).not.toHaveBeenCalled();

    act(() => {
      observed!([{ contentRect: { width: 801, height: 601 } }] as any, {} as any);
    });
    await waitFor(() => expect(pick).toHaveBeenCalled());

    // The jiggle re-fits at the same scale; pickLevel should see the level
    // already sitting at 8 (not the old hardcoded 32) and hold it there.
    expect(pick.mock.calls[0]![0]).toBe(8);
    expect(pick.mock.results[0]!.value).toBe(8);
  } finally {
    (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = original;
  }
});

it('re-fits the camera when the observed size changes, but not after a wheel', async () => {
  let observed: ResizeObserverCallback | null = null;
  class CapturingResizeObserver {
    constructor(cb: ResizeObserverCallback) { observed = cb; }
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  const original = globalThis.ResizeObserver;
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver =
    CapturingResizeObserver;
  const fit = vi.mocked(camera.fitBounds);
  fit.mockClear();

  try {
    const { container } = render(<CorpusWall client={client} />);
    await waitFor(() => expect(container.querySelector('canvas')).toBeTruthy());
    const initial = fit.mock.calls.length;
    expect(initial).toBeGreaterThan(0);

    act(() => {
      observed!([{ contentRect: { width: 1000, height: 700 } }] as any, {} as any);
    });
    await waitFor(() => expect(fit.mock.calls.length).toBeGreaterThan(initial));

    const stage = container.querySelector('.corpus-stage')!;
    fireEvent.wheel(stage, { deltaY: -1, clientX: 10, clientY: 10 });
    const afterWheel = fit.mock.calls.length;

    act(() => {
      observed!([{ contentRect: { width: 1200, height: 900 } }] as any, {} as any);
    });
    await new Promise((r) => setTimeout(r, 0));
    expect(fit.mock.calls.length).toBe(afterWheel);
  } finally {
    (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = original;
  }
});
