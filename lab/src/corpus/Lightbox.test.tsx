import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Lightbox } from '@lab/corpus/Lightbox';

const detail = {
  part: { id: '3001', title: 'Brick 2 x 4', category: 'Brick',
          status: 'good', status_note: null },
  findings: [{ part_id: '3001', engine: 'naive', extra_d99: 1.5,
               missing_px: 3, secs: 12.0, error: null }],
  runs: [{ id: 7, kind: 'census', started: '2026-09-05T10:00:00+00:00',
           commit_sha: 'abc1234', engine: 'naive', extra_d99: 1.5,
           missing_px: 3, secs: 12.0, error: null }],
  defects: [{ id: 'd1', part: '3001', title: 'rim nubs', status: 'open' }],
  slots: [
    { source: 'census-occt', sha256: 'cafebabe0000', made_at: '2026-09-05T10:00:00+00:00' },
    { source: 'naive', sha256: 'deadbeef0000', made_at: '2026-09-05T11:00:00+00:00' },
  ],
};

const client = { corpusPart: () => Promise.resolve(detail) } as any;
const box = (props: Record<string, unknown> = {}) => (
  <Lightbox partId="3001" source="naive" client={client} onClose={() => {}}
            {...props} />
);

it('shows the part title and the part as every slot drew it', async () => {
  render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  const srcs = screen.getAllByRole('img', { name: /3001/ })
    .map((img) => img.getAttribute('src'));
  expect(srcs).toEqual([
    '/api/corpus/render/census-occt/3001.svg?v=cafebabe',
    '/api/corpus/render/naive/3001.svg?v=deadbeef',
  ]);
});

it('marks which of the slots the wall is showing', async () => {
  const { container } = render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  const current = container.querySelectorAll('[data-current="true"] .corpus-slot-name');
  expect([...current].map((el) => el.textContent)).toEqual(['naive']);
});

it('lists each engine measurement', async () => {
  render(box());
  await waitFor(() => screen.getByText('1.5'));
});

it('lists open defects', async () => {
  render(box());
  await waitFor(() => screen.getByText('rim nubs'));
});

it('closes on the button', async () => {
  const onClose = vi.fn();
  render(box({ onClose }));
  await waitFor(() => screen.getByLabelText('Close'));
  fireEvent.click(screen.getByLabelText('Close'));
  expect(onClose).toHaveBeenCalled();
});

it('closes on Escape', async () => {
  const onClose = vi.fn();
  render(box({ onClose }));
  await waitFor(() => screen.getByLabelText('Close'));
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(onClose).toHaveBeenCalled();
});

it('focuses the Close button on mount', async () => {
  render(box());
  await waitFor(() => screen.getByLabelText('Close'));
  expect(document.activeElement).toBe(screen.getByLabelText('Close'));
});

it('links the part out to the public catalogs, each in a new window', async () => {
  render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  const rebrickable = screen.getByRole('link', { name: 'Rebrickable' });
  expect(rebrickable.getAttribute('href')).toBe('https://rebrickable.com/parts/3001/');
  expect(rebrickable.getAttribute('target')).toBe('_blank');
  expect(rebrickable.getAttribute('rel')).toContain('noopener');
  expect(screen.getByRole('link', { name: 'BrickLink' }).getAttribute('href'))
    .toBe('https://www.bricklink.com/v2/catalog/catalogitem.page?P=3001');
});
