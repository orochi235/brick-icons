import { expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { FilterBar } from '@lab/corpus/FilterBar';

const SLOTS = [{ source: 'silhouette-naive', n: 200 }, { source: 'naive', n: 49 }];
const bar = (props: Record<string, unknown> = {}) => (
  <FilterBar sources={SLOTS} source="silhouette-naive" onSource={() => {}} {...props} />
);

// The picker is weasel-ui's Select, which builds its list in a popover -- so
// the options exist only once the trigger has been opened.
it('lists the slots that have renders, with their counts', () => {
  render(bar());
  act(() => { fireEvent.click(screen.getByRole('button', { name: /Slot/ })); });
  expect(screen.getByRole('option', { name: 'silhouette-naive (200)' })).toBeTruthy();
  expect(screen.getByRole('option', { name: 'naive (49)' })).toBeTruthy();
});

it('reports a slot change', () => {
  const onSource = vi.fn();
  render(bar({ onSource }));
  act(() => { fireEvent.click(screen.getByRole('button', { name: /Slot/ })); });
  fireEvent.click(screen.getByRole('option', { name: 'naive (49)' }));
  expect(onSource).toHaveBeenCalledWith('naive');
});
