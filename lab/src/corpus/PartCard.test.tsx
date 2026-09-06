import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { PartCard } from '@lab/corpus/PartCard';
import type { Cell } from '@lab/corpus/types';

const cell: Cell = {
  id: '3001', index: 0, title: 'Brick 2 x 4', category: 'Brick',
  printed: false, obsolete: false, status: 'good', sha: 'deadbeefcafe',
  made_at: '2026-09-05T10:00:00+00:00', extra_d99: 4.5, secs: 12, error: null,
  open_defects: 0, open_defects_elsewhere: 0, error_elsewhere: false,
};

const card = (props: Record<string, unknown> = {}) => (
  <PartCard cell={cell} source="naive" at={{ x: 100, y: 100 }}
            viewport={{ width: 1000, height: 800 }}
            onOpen={() => {}} onClose={() => {}} {...props} />
);

it('shows what the wall already knows, without fetching', () => {
  render(card());
  expect(screen.getByText('Brick 2 x 4')).toBeTruthy();
  expect(screen.getByText(/3001/)).toBeTruthy();
  expect(screen.getByText(/good/)).toBeTruthy();
});

it('shows the thumbnail for the slot being viewed', () => {
  render(card());
  expect(screen.getByRole('img', { name: /3001/ })
    .getAttribute('src')).toContain('/api/thumbs/naive/128/3001.png');
});

it('says so when a part has no render rather than showing a broken image', () => {
  render(card({ cell: { ...cell, sha: null } }));
  expect(screen.queryByRole('img')).toBeNull();
  expect(screen.getByText(/not rendered/i)).toBeTruthy();
});

it('opens the lightbox from its button', () => {
  const onOpen = vi.fn();
  render(card({ onOpen }));
  fireEvent.click(screen.getByRole('button', { name: /open/i }));
  expect(onOpen).toHaveBeenCalledWith('3001');
});

it('closes on Escape', () => {
  const onClose = vi.fn();
  render(card({ onClose }));
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(onClose).toHaveBeenCalled();
});

it('stays inside the viewport when clicked near the right edge', () => {
  const { container } = render(card({ at: { x: 990, y: 790 } }));
  const el = container.querySelector('.corpus-card') as HTMLElement;
  expect(parseInt(el.style.getPropertyValue('--card-x'), 10)).toBeLessThan(990);
});

it('names a timeout separately from a real failure', () => {
  render(card({ cell: { ...cell, error: 'TimeoutError' } }));
  expect(screen.getByText(/render timed out/i)).toBeTruthy();
});

it('names the real error when the part cannot be drawn', () => {
  render(card({ cell: { ...cell, error: 'GEOSException' } }));
  expect(screen.getByText(/cannot be drawn: GEOSException/)).toBeTruthy();
});

it('counts open defects filed against this slot', () => {
  render(card({ cell: { ...cell, open_defects: 2 } }));
  expect(screen.getByText(/2 open defects/)).toBeTruthy();
});

it('names a defect filed against another slot as belonging elsewhere', () => {
  render(card({ cell: { ...cell, open_defects_elsewhere: 1 } }));
  expect(screen.getByText(/1 open defect in another slot/)).toBeTruthy();
});
