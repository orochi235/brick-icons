import { expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { RenderHistory } from '@lab/corpus/RenderHistory';

const point = (at: string, secs: number, over = {}) => ({
  at, secs, bytes: 20480, objects: 58, build: '1494.3c9e936', error: null,
  run_id: 1, dated_by: 'drawn' as const, ...over,
});

const client = {
  corpusPartHistory: () => Promise.resolve({ series: [
    { source: 'occt', points: [point('2026-09-10T11:00:00+00:00', 6.2),
                               point('2026-09-26T07:00:00+00:00', 7.5, { dated_by: 'build' }),
                               point('2026-09-27T07:00:00+00:00', 150, { error: 'TimeoutError' })] },
    { source: 'naive', points: [point('2026-09-11T21:00:00+00:00', 3.8)] },
  ] }),
} as any;

it('charts time, size and objects for the slot shown, leaving out failed runs', async () => {
  const { container } = render(<RenderHistory partId="3001" source="occt" client={client} />);
  await waitFor(() => screen.getByRole('img', { name: 'render time (s)' }));
  for (const name of ['render time (s)', 'file size (KB)', 'visible objects']) {
    expect(screen.getByRole('img', { name })).toBeTruthy();
  }
  const dots = container.querySelectorAll('[aria-label="render time (s)"] .corpus-history-dot');
  expect(dots).toHaveLength(2);
  // Dated by its drawing: filled. Dated by its build: hollow.
  expect([...dots].map((d) => d.getAttribute('fill') === 'none')).toEqual([false, true]);
});

it('says so when the slot has no measurements of the part', async () => {
  render(<RenderHistory partId="3001" source="decal" client={client} />);
  await waitFor(() => screen.getByText(/no measurements of decal/));
});
