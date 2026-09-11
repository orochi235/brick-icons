import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import * as core from '@weasel-js/core';
import * as levels from '@lab/corpus/levels';
import { CorpusWall } from '@lab/corpus/CorpusWall';
import type { Cell } from '@lab/corpus/types';

vi.mock('@weasel-js/core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@weasel-js/core')>();
  return { ...actual, fitViewToBounds: vi.fn(actual.fitViewToBounds) };
});

vi.mock('@lab/corpus/levels', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@lab/corpus/levels')>();
  return { ...actual, pickLevel: vi.fn(actual.pickLevel) };
});

const cell = (id: string, index: number, sha: string | null = null): Cell => ({
  id, index, title: `Part ${id}`, category: 'Brick', family: null, printed: false,
  obsolete: false, base: true, out_of_scope: false, moved: false, year_from: null, year_to: null, sets: null, colors: null, tags: [], status: 'unreviewed', sha, made_at: null,
  extra_d99: null, secs: null, error: null, open_defects: 0,
  review_defects: 0, accepted_defects: 0, elsewhere: [],
});

const client = {
  corpusSources: () => Promise.resolve({
    sources: [{ source: 'silhouette-naive', n: 2 }],
  }),
  cells: () => Promise.resolve({
    cells: [cell('a', 0, 'sha-a'), cell('b', 1)], count: 2,
    version: '2026-09-05T10:00:00+00:00', source: 'silhouette-naive',
  }),
  sheetManifest: () => Promise.resolve({
    level: 32, gutter: 2, pitch: 36, cols: 2, rows: 1, count: 2, size: 72,
    baked: { a: 'sha-a' },
  }),
  corpusPart: () => new Promise(() => {}),
  searchParts: () => Promise.resolve([]),
} as any;

// The wall's own canvas, by class: the legend's badge swatches and the
// loupe are canvases too, and the first one in the document is not the wall.
const findCanvas = (container: HTMLElement) => waitFor(() => {
  const el = container.querySelector('canvas.corpus-canvas');
  expect(el).toBeTruthy();
  return el as HTMLCanvasElement;
});

// jsdom does no layout, and `useCanvasSize` measures the stage via
// `getBoundingClientRect` rather than a ResizeObserver entry -- this stands
// in for both, at the same 800x600 the wall's own state used to default to.
const rect = (width: number, height: number): DOMRect => ({
  width, height, top: 0, left: 0, right: width, bottom: height, x: 0, y: 0,
  toJSON() { return this; },
});

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect')
    .mockReturnValue(rect(800, 600));
  // The wall keeps the open part and the drawn slot in the hash, and one
  // jsdom location outlives every case in this file -- so without this a test
  // that opens a lightbox reopens it in the next one.
  window.history.replaceState(null, '', window.location.pathname);
});

// Every `FloatingPanel` (the legend, the params panel) observes its own size
// with a second, real `ResizeObserver`, and since its offsetParent falls back
// to `.corpus-stage` in jsdom, that instance watches the stage too -- but
// alongside its own panel div, so it always has two targets. `useCanvasSize`'s
// own observer watches only the stage, which is what distinguishes it from
// however many floating panels the wall grows.
class CapturingResizeObserver {
  static instances: CapturingResizeObserver[] = [];
  targets: Element[] = [];
  constructor(public cb: ResizeObserverCallback) { CapturingResizeObserver.instances.push(this); }
  observe(el: Element) { this.targets.push(el); }
  unobserve() {}
  disconnect() {}
}

function installCapturingResizeObserver() {
  CapturingResizeObserver.instances = [];
  const original = globalThis.ResizeObserver;
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = CapturingResizeObserver;
  return () => { (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = original; };
}

function stageResizeCallback(container: HTMLElement): ResizeObserverCallback {
  const stage = container.querySelector('.corpus-stage')!;
  const observer = CapturingResizeObserver.instances.find(
    (i) => i.targets.length === 1 && i.targets[0] === stage);
  if (!observer) throw new Error('no ResizeObserver is watching only .corpus-stage');
  return observer.cb;
}

// jsdom loads nothing, so a sheet's `<img>` never fires and `useSheets` never
// settles -- which is the one thing a slot change waits on. Firing `load` on
// assignment lets the wall actually reach the new slot, and the srcs it
// collects say which slot's drawings were asked for.
function installLoadingImages() {
  const srcs: string[] = [];
  const desc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src')!;
  Object.defineProperty(HTMLImageElement.prototype, 'src', {
    configurable: true,
    get(this: HTMLImageElement) { return desc.get!.call(this); },
    set(this: HTMLImageElement, value: string) {
      srcs.push(value);
      desc.set!.call(this, value);
      queueMicrotask(() => { this.dispatchEvent(new Event('load')); });
    },
  });
  return { srcs, restore: () => Object.defineProperty(HTMLImageElement.prototype, 'src', desc) };
}

afterEach(() => { vi.restoreAllMocks(); });

const pending = () => ({ cells: () => new Promise(() => {}),
                         corpusSources: () => new Promise(() => {}),
                         sheetManifest: () => new Promise(() => {}) } as any);

it('says it is loading before the cells arrive', () => {
  render(<CorpusWall client={pending()} />);
  expect(screen.getByText(/loading the corpus/i)).toBeTruthy();
});

it('lays out the wall it is about to draw rather than a blank page', () => {
  // A cell's size is a parameter, so the grid can be drawn while the fetch is
  // still out. 24,591 rows is a long time to look at nothing.
  const { container } = render(<CorpusWall client={pending()} />);
  expect(container.querySelectorAll('.corpus-skeleton__cell').length)
    .toBeGreaterThan(0);
});

it('keeps the chrome usable while the cells are out', () => {
  // None of it needs cells: the slot picker has its own poll, search goes
  // straight to the API, and the sidebar's counts start empty either way.
  render(<CorpusWall client={pending()} />);
  expect(screen.getByRole('button', { name: /legend/i })).toBeTruthy();
  expect(document.querySelector('.corpus-side')).toBeTruthy();
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

it('drops the card once a drag starts moving the wall under it', async () => {
  const { container } = render(<CorpusWall client={client} />);
  const canvas = await findCanvas(container);
  fireEvent.click(canvas, { clientX: 10, clientY: 10 });
  expect(await screen.findByRole('dialog', { name: /Part a/ })).toBeTruthy();
  fireEvent.pointerDown(canvas, { button: 0, clientX: 10, clientY: 10, pointerId: 1 });
  fireEvent.pointerMove(canvas, { clientX: 60, clientY: 40, pointerId: 1 });
  await waitFor(() => expect(container.querySelector('.corpus-card')).toBeNull());
});

it('drops the card when two fingers start a pinch over it', async () => {
  const { container } = render(<CorpusWall client={client} />);
  const canvas = await findCanvas(container);
  fireEvent.click(canvas, { clientX: 10, clientY: 10 });
  expect(await screen.findByRole('dialog', { name: /Part a/ })).toBeTruthy();
  fireEvent.pointerDown(canvas, { button: 0, clientX: 40, clientY: 40, pointerId: 1 });
  fireEvent.pointerDown(canvas, { button: 0, clientX: 60, clientY: 40, pointerId: 2 });
  fireEvent.pointerMove(canvas, { clientX: 80, clientY: 40, pointerId: 2 });
  await waitFor(() => expect(container.querySelector('.corpus-card')).toBeNull());
});

it('does not raise a card from the click that ends a pinch', async () => {
  const { container } = render(<CorpusWall client={client} />);
  const canvas = await findCanvas(container);
  fireEvent.pointerDown(canvas, { button: 0, clientX: 10, clientY: 10, pointerId: 1 });
  fireEvent.pointerDown(canvas, { button: 0, clientX: 30, clientY: 10, pointerId: 2 });
  fireEvent.pointerMove(canvas, { clientX: 50, clientY: 10, pointerId: 2 });
  fireEvent.pointerUp(canvas, { clientX: 50, clientY: 10, pointerId: 2 });
  fireEvent.pointerUp(canvas, { clientX: 10, clientY: 10, pointerId: 1 });
  fireEvent.click(canvas, { clientX: 10, clientY: 10 });
  expect(container.querySelector('.corpus-card')).toBeNull();
});

// Both cells land fully on screen at the initial fit, but 'b' sits nearer
// the viewport's center -- so it, not the leftmost 'a', is the implied
// caret these tests start from.
it('is keyboard-focusable and raises a card for the caret on Enter', async () => {
  const { container } = render(<CorpusWall client={client} />);
  const canvas = await findCanvas(container);
  expect(canvas.tabIndex).toBe(0);
  fireEvent.keyDown(canvas, { key: 'Enter' });
  expect(await screen.findByRole('dialog', { name: /Part b/ })).toBeTruthy();
});

it('moves the caret with arrow keys before Enter opens it', async () => {
  const { container } = render(<CorpusWall client={client} />);
  const canvas = await findCanvas(container);
  fireEvent.keyDown(canvas, { key: 'ArrowLeft' });
  fireEvent.keyDown(canvas, { key: 'Enter' });
  expect(await screen.findByRole('dialog', { name: /Part a/ })).toBeTruthy();
});

it('drops the explicit caret back to the implied one on Escape', async () => {
  const { container } = render(<CorpusWall client={client} />);
  const canvas = await findCanvas(container);
  fireEvent.keyDown(canvas, { key: 'ArrowLeft' });
  fireEvent.keyDown(canvas, { key: 'Escape' });
  fireEvent.keyDown(canvas, { key: 'Enter' });
  expect(await screen.findByRole('dialog', { name: /Part b/ })).toBeTruthy();
});

it("announces the caret's part through a live region", async () => {
  const { container } = render(<CorpusWall client={client} />);
  await findCanvas(container);
  const live = container.querySelector('[aria-live="polite"]');
  expect(live).toBeTruthy();
  await waitFor(() => expect(live!.textContent).toBe('Part b'));
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

it('flies a search hit to the caret and raises its card', async () => {
  const { container } = render(<CorpusWall client={client} />);
  await findCanvas(container);
  const input = screen.getByPlaceholderText(/part/i);
  fireEvent.change(input, { target: { value: 'a' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(await screen.findByRole('dialog', { name: /Part a/ })).toBeTruthy();
  const live = container.querySelector('[aria-live="polite"]');
  await waitFor(() => expect(live!.textContent).toBe('Part a'));
});

it('says a searched part is hidden by the current filter, rather than doing nothing', async () => {
  const { container } = render(<CorpusWall client={client} />);
  await findCanvas(container);
  fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'unrendered' } });
  await waitFor(() => screen.getByText('1 of 2'));
  const input = screen.getByPlaceholderText(/part/i);
  fireEvent.change(input, { target: { value: 'a' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(await screen.findByText('a is hidden by the current filter')).toBeTruthy();
  expect(screen.queryByRole('dialog')).toBeNull();
});

it("says a searched part isn't drawn in this slot at all", async () => {
  const { container } = render(<CorpusWall client={client} />);
  await findCanvas(container);
  const input = screen.getByPlaceholderText(/part/i);
  fireEvent.change(input, { target: { value: 'zzz' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(await screen.findByText('zzz is not drawn in this slot')).toBeTruthy();
});

it('opens on the level the initial fit asks for, and holds it through a jiggle', async () => {
  const restore = installCapturingResizeObserver();

  const fit = vi.mocked(core.fitViewToBounds);
  const pick = vi.mocked(levels.pickLevel);
  fit.mockClear();
  pick.mockClear();
  // CELL(32) * 11/32 = 11px -- inside the 8/32 dead zone (10.7-24px) and
  // below the 16px boundary, so a fresh pick wants level 8. A fixed level
  // (32) held by pickLevel across this zone is exactly the pre-fix bug.
  fit.mockImplementation(() => ({ x: 0, y: 0, scale: { x: 11 / 32, y: 11 / 32 } }));

  try {
    const { container } = render(<CorpusWall client={client} />);
    await waitFor(() => expect(container.querySelector('canvas')).toBeTruthy());

    // The very first pick bypasses pickLevel entirely -- there is nothing
    // yet to be hysteretic about.
    expect(pick).not.toHaveBeenCalled();

    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue(rect(801, 601));
    const onResize = stageResizeCallback(container);
    act(() => { onResize([] as unknown as ResizeObserverEntry[], {} as any); });
    await waitFor(() => expect(pick).toHaveBeenCalled());

    // The jiggle re-fits at the same scale; pickLevel should see the level
    // already sitting at 8 (not the old hardcoded 32) and hold it there.
    expect(pick.mock.calls[0]![0]).toBe(8);
    expect(pick.mock.results[0]!.value).toBe(8);
  } finally {
    restore();
  }
});

it('holds its level through a slot change, so a zoomed-in wall stays zoomed in', async () => {
  const restore = installCapturingResizeObserver();
  const images = installLoadingImages();

  const twoSlots = { ...client, corpusSources: () => Promise.resolve({
    sources: [{ source: 'silhouette-naive', n: 2 }, { source: 'silhouette-occt', n: 2 }],
  }) } as any;

  const fit = vi.mocked(core.fitViewToBounds);
  const pick = vi.mocked(levels.pickLevel);
  fit.mockClear();
  pick.mockClear();
  // CELL(32) * 3 = 96px on screen -- the 128px loose rung, well past the
  // 32px sheet the wall opens on.
  fit.mockImplementation(() => ({ x: 0, y: 0, scale: { x: 3, y: 3 } }));

  try {
    const { container } = render(<CorpusWall client={twoSlots} />);
    await waitFor(() => expect(container.querySelector('canvas')).toBeTruthy());

    // The two slots differ by engine, which the toolbar asks with its
    // segmented Engine control rather than the facet dropdown.
    fireEvent.click(screen.getByRole('radio', { name: 'Engine' }));
    // A loose thumb for the new slot means the wall has actually swapped to
    // it -- those are keyed on the drawn slot, not the selected one.
    await waitFor(() => expect(images.srcs.some(
      (s) => s.includes('/api/thumbs/silhouette-occt/128/'))).toBe(true));

    // Nothing but a camera change re-picks the level, so a slot change that
    // drops it lands the wall on the 32px sheet until the next zoom.
    pick.mockClear();
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue(rect(801, 601));
    const onResize = stageResizeCallback(container);
    act(() => { onResize([] as unknown as ResizeObserverEntry[], {} as any); });
    await waitFor(() => expect(pick).toHaveBeenCalled());

    expect(pick.mock.calls[0]![0]).toBe(128);
  } finally {
    images.restore();
    restore();
  }
});

it('re-fits the camera when the observed size changes, but not after a wheel', async () => {
  const restore = installCapturingResizeObserver();
  const fit = vi.mocked(core.fitViewToBounds);
  fit.mockClear();

  try {
    const { container } = render(<CorpusWall client={client} />);
    await waitFor(() => expect(container.querySelector('canvas')).toBeTruthy());
    const initial = fit.mock.calls.length;
    expect(initial).toBeGreaterThan(0);

    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue(rect(1000, 700));
    const onResize = stageResizeCallback(container);
    act(() => { onResize([] as unknown as ResizeObserverEntry[], {} as any); });
    await waitFor(() => expect(fit.mock.calls.length).toBeGreaterThan(initial));

    const stage = container.querySelector('.corpus-stage')!;
    fireEvent.wheel(stage, { deltaY: -1, clientX: 10, clientY: 10 });
    const afterWheel = fit.mock.calls.length;

    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue(rect(1200, 900));
    act(() => { onResize([] as unknown as ResizeObserverEntry[], {} as any); });
    await new Promise((r) => setTimeout(r, 0));
    expect(fit.mock.calls.length).toBe(afterWheel);
  } finally {
    restore();
  }
});

it('regroups the wall without going back to the server', async () => {
  const cells = vi.fn(client.cells);
  const { container } = render(<CorpusWall client={{ ...client, cells } as any} />);
  await findCanvas(container);
  const fetches = cells.mock.calls.length;
  fireEvent.change(screen.getByLabelText('Group'), { target: { value: 'category' } });
  await new Promise((r) => setTimeout(r, 0));
  expect(cells.mock.calls.length).toBe(fetches);
});

it('excludes a category without going back to the server', async () => {
  const cells = vi.fn(client.cells);
  const { container } = render(<CorpusWall client={{ ...client, cells } as any} />);
  await findCanvas(container);
  const fetches = cells.mock.calls.length;
  fireEvent.click(screen.getByRole('checkbox', { name: /Brick/ }));
  await waitFor(() => screen.getByText('0 of 2'));
  expect(cells.mock.calls.length).toBe(fetches);
});

it('offers the direction toggle only once the wall is grouped by release', async () => {
  const { container } = render(<CorpusWall client={client} />);
  await findCanvas(container);
  expect(screen.queryByLabelText('Newest first')).toBeNull();
  fireEvent.change(screen.getByLabelText('Group'), { target: { value: 'release' } });
  expect(screen.getByLabelText('Newest first')).toBeTruthy();
});

it('closes the legend and gets it back from the topbar', async () => {
  const { container } = render(<CorpusWall client={client} />);
  await waitFor(() => expect(container.querySelector('.corpus-legend')).toBeTruthy());
  fireEvent.click(screen.getByRole('button', { name: /close legend/i }));
  expect(container.querySelector('.corpus-legend')).toBeNull();
  // The whole point: a dismissed legend used to need a reload to come back.
  fireEvent.click(screen.getByRole('button', { name: 'Legend' }));
  expect(container.querySelector('.corpus-legend')).toBeTruthy();
});

it('counts states over the wall, and keeps the tag rows a menu', async () => {
  const tagged = {
    ...client,
    cells: () => Promise.resolve({
      cells: [{ ...cell('a', 0, 'sha-a'), tags: ['technic'] },
              { ...cell('b', 1), tags: ['printed'] },
              { ...cell('c', 2), tags: ['printed'] }],
      count: 3, version: '2026-09-05T10:00:00+00:00', source: 'silhouette-naive',
    }),
  } as any;
  const { container } = render(<CorpusWall client={tagged} />);
  await waitFor(() => expect(container.querySelector('.corpus-legend')).toBeTruthy());
  expect(screen.getByRole('button', { name: 'printed, 2 parts' })).toBeTruthy();
  expect(screen.getByLabelText('unknown, 3 parts')).toBeTruthy();

  fireEvent.click(screen.getByRole('button', { name: /^technic/ }));
  // The state rows describe what is left on the wall...
  await waitFor(() => expect(screen.getByLabelText('unknown, 1 parts')).toBeTruthy());
  // ...while `printed` still says where the other two went, instead of 0.
  expect(screen.getByRole('button', { name: 'printed, 2 parts' })).toBeTruthy();
});

it('refits the wall on cmd-0, even after the camera was touched', async () => {
  const fit = vi.mocked(core.fitViewToBounds);
  const { container } = render(<CorpusWall client={client} />);
  await waitFor(() => expect(container.querySelector('canvas')).toBeTruthy());

  const stage = container.querySelector('.corpus-stage')!;
  fireEvent.wheel(stage, { deltaY: -1, clientX: 10, clientY: 10 });
  fit.mockClear();

  fireEvent.keyDown(window, { key: '0', metaKey: true });
  await waitFor(() => expect(fit.mock.calls.length).toBeGreaterThan(0));
});

it('leaves a bare 0 alone -- only the modified one resets', async () => {
  const fit = vi.mocked(core.fitViewToBounds);
  const { container } = render(<CorpusWall client={client} />);
  await waitFor(() => expect(container.querySelector('canvas')).toBeTruthy());
  fireEvent.wheel(container.querySelector('.corpus-stage')!,
                  { deltaY: -1, clientX: 10, clientY: 10 });
  fit.mockClear();
  fireEvent.keyDown(window, { key: '0' });
  await new Promise((r) => setTimeout(r, 0));
  expect(fit.mock.calls.length).toBe(0);
});

it('drops the card on a zoom, but keeps the one the pointer is over', async () => {
  const { container } = render(<CorpusWall client={client} />);
  const canvas = await findCanvas(container);
  const stage = container.querySelector('.corpus-stage')!;

  fireEvent.click(canvas, { clientX: 10, clientY: 10 });
  expect(await screen.findByRole('dialog', { name: /Part a/ })).toBeTruthy();
  fireEvent.wheel(stage, { deltaY: -1, clientX: 10, clientY: 10 });
  expect(container.querySelector('.corpus-card')).toBeNull();

  fireEvent.click(canvas, { clientX: 10, clientY: 10 });
  const card = await screen.findByRole('dialog', { name: /Part a/ });
  fireEvent.pointerEnter(card);
  fireEvent.wheel(stage, { deltaY: -1, clientX: 10, clientY: 10 });
  expect(container.querySelector('.corpus-card')).toBeTruthy();

  // Once the pointer leaves it, the card is ordinary again.
  fireEvent.pointerLeave(card);
  fireEvent.wheel(stage, { deltaY: -1, clientX: 10, clientY: 10 });
  expect(container.querySelector('.corpus-card')).toBeNull();
});

it('picks up a slot that appears after the page is open, without moving off yours', async () => {
  // The slot list used to be fetched at mount alone, so a page open across an
  // ingest showed a menu that no longer matched the store -- reference was
  // indexed and stayed invisible until someone reloaded.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  let slots = [{ source: 'silhouette-naive', n: 2 }];
  const growing = { ...client, corpusSources: () => Promise.resolve({ sources: slots }) };
  const { container } = render(<CorpusWall client={growing} />);
  await findCanvas(container);
  await waitFor(() => expect(screen.getByRole('radio', { name: 'Legacy' })).toBeTruthy());

  // A slot in a family nobody had drawn in arrives as a new Engine segment.
  slots = [{ source: 'reference', n: 9 }, { source: 'silhouette-naive', n: 2 }];
  await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
  await waitFor(() => expect(screen.getAllByRole('radio').map((r) => r.textContent))
    .toEqual(['Legacy', 'Reference']));

  // reference now sorts first, but the wall stays on what was already open.
  expect(screen.getByRole('radio', { name: 'Legacy' }).getAttribute('aria-checked'))
    .toBe('true');

  // One in a family is no choice, so the facet dropdown appears only once
  // Legacy has a second slot to offer.
  expect(screen.queryByRole('button', { name: /Slot/ })).toBeNull();
  slots = [...slots, { source: 'white-naive', n: 1 }];
  await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
  const trigger = () => screen.getByRole('button', { name: /Slot/ });
  await waitFor(() => expect(trigger()).toBeTruthy());

  // The Select builds its rows in a popover, so the menu is read by opening
  // it -- and an open one hides the rest of the page from the a11y tree, so
  // the trigger is read before this and not after.
  expect(trigger().textContent).toContain('silhouette');
  act(() => { fireEvent.click(trigger()); });
  // The rows join facet and count with a non-breaking space.
  await waitFor(() => expect(screen.getAllByRole('option')
    .map((o) => o.textContent?.replace(/\u00a0/g, ' ')))
    .toEqual(['silhouette (2)', 'white (1)']));
  vi.useRealTimers();
});

it('opens on the engine slot with nothing in the hash, not on the biggest one', async () => {
  // `reference` is every part in the library, so it heads the route's
  // population order forever -- opening on it showed LDView's renders to
  // anyone who followed a bare /corpus link.
  const cells = vi.fn((source: string) => Promise.resolve({
    cells: [cell('a', 0, 'sha-a'), cell('b', 1)], count: 2,
    version: '2026-09-05T10:00:00+00:00', source,
  }));
  const wide = { ...client, cells, corpusSources: () => Promise.resolve({
    sources: [{ source: 'reference', n: 9 }, { source: 'occt', n: 2 }],
  }) } as any;

  const { container } = render(<CorpusWall client={wide} />);
  await findCanvas(container);
  await waitFor(() => expect(screen.getByRole('radio', { name: 'Engine' })
    .getAttribute('aria-checked')).toBe('true'));
  expect(cells.mock.calls.map((c) => c[0])).not.toContain('reference');
  expect(cells.mock.calls[0]?.[0]).toBe('occt');
});

it('falls back to the most-populated slot when the engine has drawn nothing', async () => {
  const cells = vi.fn((source: string) => Promise.resolve({
    cells: [cell('a', 0, 'sha-a'), cell('b', 1)], count: 2,
    version: '2026-09-05T10:00:00+00:00', source,
  }));
  const noOcct = { ...client, cells, corpusSources: () => Promise.resolve({
    sources: [{ source: 'reference', n: 9 }, { source: 'silhouette-naive', n: 2 }],
  }) } as any;

  const { container } = render(<CorpusWall client={noOcct} />);
  await findCanvas(container);
  await waitFor(() => expect(screen.getByRole('radio', { name: 'Reference' })
    .getAttribute('aria-checked')).toBe('true'));
  await waitFor(() => expect(cells.mock.calls.map((c) => c[0])).toContain('reference'));
});

it('says the pictures belong to the old slot while the new one loads', async () => {
  // The wall keeps drawing what it has rather than blanking, which without a
  // word of warning reads as "the slot you just picked looks identical".
  const body = (source: string) => ({
    cells: [cell('a', 0, 'sha-a'), cell('b', 1)], count: 2,
    version: '2026-09-05T10:00:00+00:00', source,
  });
  // Only the slot switched TO stays out, so the wall has something drawn and
  // nothing to replace it with.
  const cells = vi.fn((source: string) =>
    (source === 'silhouette-naive'
      ? new Promise(() => {})
      : Promise.resolve(body(source))));
  const two = { ...client, cells, corpusSources: () => Promise.resolve({
    sources: [{ source: 'occt', n: 2 }, { source: 'silhouette-naive', n: 2 }],
  }) } as any;

  const { container } = render(<CorpusWall client={two} />);
  await findCanvas(container);
  expect(document.querySelector('.corpus-stale')).toBeNull();

  fireEvent.click(screen.getByRole('radio', { name: 'Legacy' }));
  const said = await screen.findByText(/still showing/);
  expect(said.textContent).toContain('occt');
  expect(said.textContent).toContain('silhouette-naive');
});
