import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { Legend } from '@lab/corpus/Legend';
import { CELL_STATES } from '@lab/corpus/palette';
import type { Cell } from '@lab/corpus/types';

const cell = (id: string, overrides: Partial<Cell> = {}): Cell => ({
  id, index: 0, title: id, category: null, printed: false, obsolete: false, base: true, out_of_scope: false, year_from: null, year_to: null, sets: null, tags: [],
  status: 'unreviewed', sha: null, made_at: null, extra_d99: null, secs: null,
  error: null, open_defects: 0, open_defects_elsewhere: 0,
  error_elsewhere: false, ...overrides,
});

const cells: Cell[] = [
  cell('a'),
  cell('b'),
  cell('c', { error: 'TimeoutError' }),
  cell('d', { error: 'TimeoutError' }),
  cell('e', { open_defects: 1 }),
];

it('renders a row per state with its own count', () => {
  render(<Legend cells={cells} highlight={null} onHighlight={() => {}} />);
  expect(screen.getByLabelText('unknown, 2 parts')).toBeTruthy();
  expect(screen.getByLabelText('timed out here, 2 parts')).toBeTruthy();
  expect(screen.getByLabelText('open defect here, 1 parts')).toBeTruthy();
  expect(screen.getByLabelText('cannot be drawn here, 0 parts')).toBeTruthy();
  expect(screen.getByLabelText('problem in another slot, 0 parts')).toBeTruthy();
  expect(screen.getByLabelText('defect in another slot, 0 parts')).toBeTruthy();
});

it('reports the hovered state, and null once the pointer leaves', () => {
  const onHighlight = vi.fn();
  render(<Legend cells={cells} highlight={null} onHighlight={onHighlight} />);
  const row = screen.getByLabelText(/timed out here/);
  fireEvent.mouseEnter(row);
  expect(onHighlight).toHaveBeenCalledWith('timeout');
  fireEvent.mouseLeave(row);
  expect(onHighlight).toHaveBeenCalledWith(null);
});

it('treats keyboard focus the same as hover, and blur the same as leaving', () => {
  const onHighlight = vi.fn();
  render(<Legend cells={cells} highlight={null} onHighlight={onHighlight} />);
  const row = screen.getByLabelText(/open defect here/);
  fireEvent.focus(row);
  expect(onHighlight).toHaveBeenCalledWith('defect');
  fireEvent.blur(row);
  expect(onHighlight).toHaveBeenCalledWith(null);
});

it('is reachable by keyboard -- every row is focusable', () => {
  const { container } = render(<Legend cells={cells} highlight={null} onHighlight={() => {}} />);
  const rows = container.querySelectorAll('[data-state]');
  expect(rows.length).toBe(CELL_STATES.length);
  for (const row of rows) {
    expect(row.getAttribute('tabindex')).toBe('0');
  }
});

it('closes on its own dismissal', () => {
  const { container } = render(<Legend cells={cells} highlight={null} onHighlight={() => {}} />);
  fireEvent.click(screen.getByRole('button', { name: /close legend/i }));
  expect(container.querySelector('.corpus-legend')).toBeNull();
});
