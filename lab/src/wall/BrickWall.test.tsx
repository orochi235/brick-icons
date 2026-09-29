import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { BrickWall, linkTarget } from '@lab/wall/BrickWall';
import type { Cell } from '@lab/corpus/types';

// The real search is an async ComboBox; the wiring under test is what its
// commit does, so a button stands in for it.
vi.mock('@lab/shared/PartSearch', () => ({
  PartSearch: ({ onOpen }: { onOpen: (part: string) => void }) => (
    <button type="button" onClick={() => onOpen('nope')}>search</button>
  ),
}));

const client = {
  corpusSources: () => Promise.resolve({
    sources: [{ source: 'occt', n: 0 }, { source: 'silhouette-occt', n: 0 },
              { source: 'naive', n: 0 }, { source: 'reference', n: 0 }],
  }),
  cells: () => Promise.resolve({ cells: [], count: 0, version: 'v1', source: 'occt' }),
  corpusPart: () => new Promise(() => {}),
  searchParts: () => Promise.resolve([]),
  colors: () => Promise.resolve([]),
} as any;

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('{}', { status: 404 }))));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  // A slot change writes its hash (BrickWall's `onChange`), which otherwise
  // survives into the next test's `openingState` and picks its initial slot.
  window.history.replaceState(null, '', window.location.pathname);
});

const part = (over: Partial<Cell>) => ({ id: '3001', ...over }) as Cell;

it('follows a replacement badge in the direction it points', () => {
  expect(linkTarget(part({ successor: '3002' }), 'replaced')).toBe('3002');
  expect(linkTarget(part({ predecessors: ['3000'] }), 'replaces')).toBe('3000');
});

it('falls through to the card where a part replaced several', () => {
  // Null is a normal pick, which opens the card -- and the card is the only
  // thing that can name more than one of them.
  expect(linkTarget(part({ predecessors: ['3000', '3004'] }), 'replaces')).toBeNull();
  expect(linkTarget(part({ predecessors: [] }), 'replaces')).toBeNull();
  expect(linkTarget(part({ successor: null }), 'replaced')).toBeNull();
});

it('puts the engine toggle where pezlie drew its slot select', async () => {
  render(<BrickWall client={client} />);
  const group = await screen.findByRole('radiogroup', { name: 'Engine' });
  expect(within(group).getByRole('radio', { name: 'Engine' })).toBeTruthy();
  expect(within(group).getByRole('radio', { name: 'Reference' })).toBeTruthy();
  // naive's slots are for the lightbox only (9d789a2), so no Legacy segment.
  expect(within(group).queryByRole('radio', { name: 'Legacy' })).toBeNull();
  expect(document.querySelector('.wall-slot')).toBeNull();
});

it('says when a searched part is not in the slot', async () => {
  render(<BrickWall client={client} />);
  fireEvent.click(await screen.findByRole('button', { name: 'search' }));
  expect(await screen.findByText('nope is not drawn in this slot')).toBeTruthy();
});

it('clears a stale notice when the engine changes', async () => {
  const { container } = render(<BrickWall client={client} />);
  const notice = () => container.querySelector('.brick-wall-search [role=status]');
  fireEvent.click(await screen.findByRole('button', { name: 'search' }));
  await waitFor(() => expect(notice()?.textContent).toBe('nope is not drawn in this slot'));

  const group = await screen.findByRole('radiogroup', { name: 'Engine' });
  fireEvent.click(within(group).getByRole('radio', { name: 'Reference' }));
  await waitFor(() => expect(notice()?.textContent).toBe(''));
});

it('asks for the delta at once when a redraw lands in the slot on screen', async () => {
  let tell: (e: unknown) => void = () => {};
  const cells = vi.fn(() => Promise.resolve(
    { cells: [], count: 0, version: 'v1', source: 'occt' }));
  const listening = { ...client, cells,
                      onChanged: (f: (e: unknown) => void) => { tell = f; return () => {}; } };
  render(<BrickWall client={listening} />);
  await screen.findByRole('radiogroup', { name: 'Engine' });
  await waitFor(() => expect(cells).toHaveBeenCalled());
  // Let the opening fetches settle, so the count below is only the poll's.
  await new Promise((resolve) => setTimeout(resolve, 300));
  const asked = cells.mock.calls.length;
  tell({ part: '3001', source: 'reference', sha: 'x', build: '9.c' });
  await new Promise((resolve) => setTimeout(resolve, 300));
  expect(cells.mock.calls.length).toBe(asked);
  tell({ part: '3001', source: 'occt', sha: 'x', build: '9.c' });
  await waitFor(() => expect(cells.mock.calls.length).toBe(asked + 1));
});
