import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { FilterBar } from '@lab/corpus/FilterBar';
import { DEFAULT_SHOWN } from '@lab/corpus/select';

const SLOTS = [{ source: 'census-naive', n: 200 }, { source: 'naive', n: 49 }];
const bar = (props: Record<string, unknown> = {}) => (
  <FilterBar selection={{ sort: 'id', filter: 'all', shown: DEFAULT_SHOWN }} onChange={() => {}}
             shown={10} total={100} sources={SLOTS} source="census-naive"
             onSource={() => {}} {...props} />
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

it('reports a sort change', () => {
  const onChange = vi.fn();
  render(bar({ onChange }));
  fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'secs' } });
  expect(onChange).toHaveBeenCalledWith(
    { sort: 'secs', filter: 'all', shown: DEFAULT_SHOWN });
});

it('reports a filter change', () => {
  const onChange = vi.fn();
  render(bar({ onChange }));
  fireEvent.change(screen.getByLabelText('Show'),
                   { target: { value: 'unrendered' } });
  expect(onChange).toHaveBeenCalledWith(
    { sort: 'id', filter: 'unrendered', shown: DEFAULT_SHOWN });
});

it('says how much of the corpus is on the wall', () => {
  render(bar());
  expect(screen.getByText('10 of 100')).toBeTruthy();
});

it('turns the moved redirects back on from a checkbox', () => {
  const onChange = vi.fn();
  render(<FilterBar selection={{ sort: 'id', filter: 'all', shown: DEFAULT_SHOWN }}
                    onChange={onChange} shown={2} total={3}
                    sources={[]} source="naive" onSource={() => {}} />);
  fireEvent.click(screen.getByLabelText('moved'));
  expect(onChange).toHaveBeenCalledWith(
    { sort: 'id', filter: 'all', shown: { ...DEFAULT_SHOWN, moved: true } });
});
