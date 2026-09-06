import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { FilterBar } from '@lab/corpus/FilterBar';

const SLOTS = [{ source: 'census-naive', n: 200 }, { source: 'naive', n: 49 }];
const bar = (props: Record<string, unknown> = {}) => (
  <FilterBar sources={SLOTS} source="census-naive" onSource={() => {}} {...props} />
);

it('lists the slots that have renders, with their counts', () => {
  render(bar());
  expect(screen.getByRole('option', { name: 'census-naive (200)' })).toBeTruthy();
  expect(screen.getByRole('option', { name: 'naive (49)' })).toBeTruthy();
});

it('reports a slot change', () => {
  const onSource = vi.fn();
  render(bar({ onSource }));
  fireEvent.change(screen.getByLabelText('Slot'), { target: { value: 'naive' } });
  expect(onSource).toHaveBeenCalledWith('naive');
});
