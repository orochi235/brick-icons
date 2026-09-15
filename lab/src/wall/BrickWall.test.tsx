import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { BrickWall } from '@lab/wall/BrickWall';

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
              { source: 'naive', n: 0 }],
  }),
  cells: () => Promise.resolve({ cells: [], count: 0, version: 'v1', source: 'occt' }),
  corpusPart: () => new Promise(() => {}),
  searchParts: () => Promise.resolve([]),
} as any;

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('{}', { status: 404 }))));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

it('puts the engine toggle where pezlie drew its slot select', async () => {
  render(<BrickWall client={client} />);
  expect(await screen.findByRole('radio', { name: 'Engine' })).toBeTruthy();
  expect(document.querySelector('.wall-slot')).toBeNull();
});

it('says when a searched part is not in the slot', async () => {
  render(<BrickWall client={client} />);
  fireEvent.click(await screen.findByRole('button', { name: 'search' }));
  expect(await screen.findByText('nope is not drawn in this slot')).toBeTruthy();
});
