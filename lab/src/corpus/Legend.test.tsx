import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { Legend } from '@lab/corpus/Legend';
import { LEGEND_STATES, STATE_LABEL } from '@lab/corpus/palette';
import { conditionKeys } from '@lab/corpus/states';
import type { Cell } from '@lab/corpus/types';

const cell = (id: string, overrides: Partial<Cell> = {}): Cell => ({
  id, index: 0, title: id, category: null, family: null, printed: false, obsolete: false, base: true, out_of_scope: false, moved: false, year_from: null, year_to: null, sets: null, colors: null, tags: [],
  status: 'unreviewed', sha: null, made_at: null, extra_d99: null, secs: null,
  error: null, open_defects: 0, review_defects: 0, accepted_defects: 0,
  elsewhere: [], ...overrides,
});

const cells: Cell[] = [
  cell('a'),
  cell('b'),
  cell('c', { error: 'TimeoutError' }),
  cell('d', { error: 'TimeoutError' }),
  cell('e', { open_defects: 1 }),
];

it('renders a row per state with its own count', () => {
  render(<Legend cells={cells} highlight={null} onHighlight={() => {}} badges={[]} onBadges={vi.fn()}
                 highlightTag={null} onHighlightTag={vi.fn()} onClose={vi.fn()} />);
  expect(screen.getByLabelText('unknown, 2 parts')).toBeTruthy();
  expect(screen.getByLabelText('timed out, 2 parts')).toBeTruthy();
  expect(screen.getByLabelText('open defect, 1 parts')).toBeTruthy();
  expect(screen.getByLabelText('render error, 0 parts')).toBeTruthy();
  expect(screen.getByLabelText('fix to check, 0 parts')).toBeTruthy();
  expect(screen.queryByLabelText(/elsewhere/)).toBeNull();
});

it('counts a fault seen in another slot under the row for that fault', () => {
  render(<Legend cells={[...cells, cell('f', { elsewhere: ['timeout'] })]}
                 highlight={null} onHighlight={() => {}} badges={[]} onBadges={vi.fn()}
                 highlightTag={null} onHighlightTag={vi.fn()} onClose={vi.fn()} />);
  expect(screen.getByLabelText('timed out, 3 parts')).toBeTruthy();
});

it('renders one row per state, in the table\'s own legend order', () => {
  const { container } = render(<Legend cells={cells} highlight={null} onHighlight={() => {}}
                 badges={[]} onBadges={vi.fn()}
                 highlightTag={null} onHighlightTag={vi.fn()} onClose={vi.fn()} />);
  // The state rows are the `[data-state]` divs. A role query would answer with
  // the close button and the badge rows, which are the only buttons here.
  const rows = [...container.querySelectorAll('[data-state]')];
  expect(rows.map((row) => row.getAttribute('data-state'))).toEqual(conditionKeys());
  expect(rows.map((row) => row.querySelector('.corpus-legend-name')?.textContent))
    .toEqual(conditionKeys().map((state) => STATE_LABEL[state]));
});

it('reports the hovered state, and null once the pointer leaves', () => {
  const onHighlight = vi.fn();
  render(<Legend cells={cells} highlight={null} onHighlight={onHighlight} badges={[]} onBadges={vi.fn()}
                 highlightTag={null} onHighlightTag={vi.fn()} onClose={vi.fn()} />);
  const row = screen.getByLabelText('timed out, 2 parts');
  fireEvent.mouseEnter(row);
  expect(onHighlight).toHaveBeenCalledWith('timeout');
  fireEvent.mouseLeave(row);
  expect(onHighlight).toHaveBeenCalledWith(null);
});

it('treats keyboard focus the same as hover, and blur the same as leaving', () => {
  const onHighlight = vi.fn();
  render(<Legend cells={cells} highlight={null} onHighlight={onHighlight} badges={[]} onBadges={vi.fn()}
                 highlightTag={null} onHighlightTag={vi.fn()} onClose={vi.fn()} />);
  const row = screen.getByLabelText('open defect, 1 parts');
  fireEvent.focus(row);
  expect(onHighlight).toHaveBeenCalledWith('defect');
  fireEvent.blur(row);
  expect(onHighlight).toHaveBeenCalledWith(null);
});

it('is reachable by keyboard -- every row is focusable', () => {
  const { container } = render(<Legend cells={cells} highlight={null} onHighlight={() => {}} badges={[]} onBadges={vi.fn()}
                 highlightTag={null} onHighlightTag={vi.fn()} onClose={vi.fn()} />);
  const rows = container.querySelectorAll('[data-state]');
  expect(rows.length).toBe(LEGEND_STATES.length);
  for (const row of rows) {
    expect(row.getAttribute('tabindex')).toBe('0');
  }
});

it('asks its owner to close rather than hiding itself', () => {
  const onClose = vi.fn();
  const { container } = render(<Legend cells={cells} highlight={null} onHighlight={() => {}} badges={[]} onBadges={vi.fn()}
                 highlightTag={null} onHighlightTag={vi.fn()} onClose={onClose} />);
  fireEvent.click(screen.getByRole('button', { name: /close legend/i }));
  expect(onClose).toHaveBeenCalled();
  // Still on screen: whoever owns the toggle decides, so there is a way back.
  expect(container.querySelector('.corpus-legend')).toBeTruthy();
});

it('filters the wall by a badge, and stacks two picks', () => {
  const onBadges = vi.fn();
  render(<Legend cells={[cell('a', { tags: ['technic'] }), cell('b', { tags: ['technic', 'printed'] })]}
                 highlight={null} onHighlight={vi.fn()}
                 badges={[]} onBadges={onBadges}
                 highlightTag={null} onHighlightTag={vi.fn()} onClose={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: /^technic/ }));
  expect(onBadges).toHaveBeenCalled();
  // An updater, not an array: two rows clicked in one render both read the
  // same `badges` prop, and the second would drop the first's pick.
  const update = onBadges.mock.calls[0]![0] as (prev: string[]) => string[];
  expect(update(['printed'])).toEqual(['printed', 'technic']);
  expect(update(['technic'])).toEqual([]);
});

it('counts every badge over `tagCells`, falling back to the wall itself', () => {
  render(<Legend cells={[cell('a', { tags: ['technic'] }), cell('b', { tags: ['technic', 'printed'] })]}
                 highlight={null} onHighlight={vi.fn()}
                 badges={[]} onBadges={vi.fn()}
                 highlightTag={null} onHighlightTag={vi.fn()} onClose={vi.fn()} />);
  expect(screen.getByRole('button', { name: 'technic, 2 parts' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'printed, 1 parts' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'magnet, 0 parts' })).toBeTruthy();
});

it('counts states over the wall and tags over `tagCells`', () => {
  // The two lists answer different questions: the states describe what is on
  // the wall, the tags stay a menu of where you could go next.
  render(<Legend cells={[cell('a', { tags: ['technic'] })]}
                 tagCells={[cell('a', { tags: ['technic'] }),
                            cell('b', { tags: ['printed'] }),
                            cell('c', { tags: ['printed'] })]}
                 highlight={null} onHighlight={vi.fn()}
                 badges={['technic']} onBadges={vi.fn()}
                 highlightTag={null} onHighlightTag={vi.fn()} onClose={vi.fn()} />);
  expect(screen.getByLabelText('unknown, 1 parts')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'technic, 1 parts' })).toBeTruthy();
  // The point of the whole change: `printed` does not read 0 just because
  // `technic` is the pick currently narrowing the wall.
  expect(screen.getByRole('button', { name: 'printed, 2 parts' })).toBeTruthy();
});

it('reports the hovered tag, and null once the pointer leaves', () => {
  const onHighlightTag = vi.fn();
  render(<Legend cells={cells} highlight={null} onHighlight={vi.fn()}
                 badges={[]} onBadges={vi.fn()}
                 highlightTag={null} onHighlightTag={onHighlightTag}
                 onClose={vi.fn()} />);
  const row = screen.getByRole('button', { name: /^technic/ });
  fireEvent.mouseEnter(row);
  expect(onHighlightTag).toHaveBeenCalledWith('technic');
  fireEvent.mouseLeave(row);
  expect(onHighlightTag).toHaveBeenCalledWith(null);
});

it('treats focus on a tag row the same as hover, and blur the same as leaving', () => {
  const onHighlightTag = vi.fn();
  render(<Legend cells={cells} highlight={null} onHighlight={vi.fn()}
                 badges={[]} onBadges={vi.fn()}
                 highlightTag={null} onHighlightTag={onHighlightTag}
                 onClose={vi.fn()} />);
  const row = screen.getByRole('button', { name: /^printed/ });
  fireEvent.focus(row);
  expect(onHighlightTag).toHaveBeenCalledWith('printed');
  fireEvent.blur(row);
  expect(onHighlightTag).toHaveBeenCalledWith(null);
});

it('marks the hovered tag row the way a hovered state row is marked', () => {
  render(<Legend cells={cells} highlight={null} onHighlight={vi.fn()}
                 badges={[]} onBadges={vi.fn()}
                 highlightTag={'technic'} onHighlightTag={vi.fn()}
                 onClose={vi.fn()} />);
  const row = screen.getByRole('button', { name: /^technic/ });
  expect(row.getAttribute('data-highlighted')).toBe('true');
});

it('gives every state a swatch, however the table grows', () => {
  // The CSS enumerated a rule per state and fell four behind the table:
  // `review`, `accepted`, `reviewElsewhere` and `timeoutElsewhere` drew no
  // swatch at all, the last of them over 1,930 parts. Colors come off the
  // table now, so a condition added there needs no CSS.
  const { container } = render(
    <Legend cells={cells} highlight={null} onHighlight={() => {}} badges={[]} onBadges={vi.fn()}
            highlightTag={null} onHighlightTag={vi.fn()} onClose={vi.fn()} />);
  const rows = container.querySelectorAll<HTMLElement>('.corpus-legend-row[data-state]');
  expect(rows.length).toBe(LEGEND_STATES.length);
  for (const row of rows) {
    const state = row.dataset.state!;
    expect(row.style.getPropertyValue('--swatch-fill'),
           `${state} has no fill`).toMatch(/^var\(--corpus-cell-/);
    const line = row.style.getPropertyValue('--swatch-line');
    expect(line, `${state} has no line color`).not.toBe('');
    // A state the wall strikes must say so, or the swatch is a plain square
    // where the cell is struck corner to corner.
    const struck = row.dataset.struck === 'true';
    expect(struck, `${state} strike disagrees with its border`)
      .toBe(line !== 'transparent');
  }
});

it('gives a state the shape the wall draws it in, not a square for every row', () => {
  const { container } = render(<Legend cells={cells} highlight={null} onHighlight={() => {}}
                 badges={[]} onBadges={vi.fn()}
                 highlightTag={null} onHighlightTag={vi.fn()} onClose={vi.fn()} />);
  const shapeOf = (state: string) =>
    container.querySelector(`[data-state="${state}"]`)?.getAttribute('data-shape');
  expect(shapeOf('outOfScope')).toBe('circle');
  expect(shapeOf('timeout')).toBe('square');
});
