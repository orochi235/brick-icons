import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CorpusWall } from '@lab/corpus/CorpusWall';
import type { Cell } from '@lab/corpus/types';

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
