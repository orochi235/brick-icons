import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Footprint } from '@lab/stats/Footprint';
import type { LabClient } from '@lab/api/client';
import type { Footprint as FootprintData } from '@lab/stats/types';

const DATA: FootprintData = {
  tiles: {
    out: 3_126_000_000, renders: 1_724_000_000, bakes: 612_000_000,
    lab_cache: 538_000_000, library: 641_000_000, corpus_db: 21_000_000,
    git: 15_000_000,
  },
  slots: [
    { source: 'silhouette-occt', renders: 398_000_000, bakes: 155_000_000,
      total: 553_000_000 },
    { source: 'ldview', renders: 285_000_000, bakes: 135_000_000,
      total: 420_000_000 },
  ],
  as_of: '2026-09-07T05:00:00+00:00',
};

const clientWith = (sizes: () => Promise<FootprintData>) =>
  ({ corpusSizes: vi.fn(sizes) } as unknown as LabClient);

it('names every tile and what it costs', async () => {
  render(<Footprint client={clientWith(async () => DATA)} />);
  await screen.findByText('2.9 GB');
  expect(screen.getByText('out/')).toBeTruthy();
  expect(screen.getByText('1.6 GB')).toBeTruthy();       // renders
  expect(screen.getByText('thumbnail bakes')).toBeTruthy();
});

it('says what a tile is as a share of out/, and never says it of out/ itself', async () => {
  render(<Footprint client={clientWith(async () => DATA)} />);
  await screen.findByText('2.9 GB');
  // renders is 1.724 of 3.126 GB
  expect(screen.getByText('55% of out/')).toBeTruthy();
  expect(screen.queryByText('100% of out/')).toBeNull();
});

it('breaks each slot into renders and bakes, and totals them', async () => {
  render(<Footprint client={clientWith(async () => DATA)} />);
  await screen.findByText('silhouette-occt');
  const foot = document.querySelector('.stats-slot-sizes tfoot')!;
  expect(foot.textContent).toContain('every slot');
  expect(foot.textContent).toContain('928 MB');          // 553 + 420
});

it('re-measures past the server memo when asked', async () => {
  const sizes = vi.fn(async () => DATA);
  render(<Footprint client={clientWith(sizes)} />);
  await screen.findByText('2.9 GB');
  expect(sizes).toHaveBeenLastCalledWith(false);

  fireEvent.click(screen.getByRole('button', { name: 'Re-measure' }));
  await waitFor(() => expect(sizes).toHaveBeenLastCalledWith(true));
});

it('says a measurement failed rather than showing nothing', async () => {
  render(<Footprint client={clientWith(async () => {
    throw new Error('no corpus database');
  })} />);
  expect((await screen.findByRole('alert')).textContent)
    .toContain('no corpus database');
});

it('draws no slot table when nothing has been rendered yet', async () => {
  render(<Footprint client={clientWith(async () => ({ ...DATA, slots: [] }))} />);
  await screen.findByText('2.9 GB');
  expect(document.querySelector('.stats-slot-sizes')).toBeNull();
});
