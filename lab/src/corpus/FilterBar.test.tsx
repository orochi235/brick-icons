import { expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { FilterBar } from '@lab/corpus/FilterBar';

const SLOTS = [{ source: 'silhouette-naive', n: 200 }, { source: 'naive', n: 49 },
               { source: 'silhouette-occt', n: 180 }, { source: 'occt', n: 40 },
               { source: 'decal', n: 90 }];
const bar = (props: Record<string, unknown> = {}) => (
  <FilterBar sources={SLOTS} source="silhouette-naive" onSource={() => {}} {...props} />
);
const open = () => act(() => {
  fireEvent.click(screen.getByRole('button', { name: /Slot/ }));
});

// The picker is weasel-ui's Select, which builds its list in a popover -- so
// the options exist only once the trigger has been opened.
it('lists the facets its engine has drawn, with their counts', () => {
  render(bar());
  open();
  expect(screen.getByRole('option', { name: 'silhouette (200)' })).toBeTruthy();
  expect(screen.getByRole('option', { name: 'flat3 (49)' })).toBeTruthy();
  expect(screen.queryByRole('option', { name: /occt/ })).toBeNull();
});

it('reports a slot change', () => {
  const onSource = vi.fn();
  render(bar({ onSource }));
  open();
  fireEvent.click(screen.getByRole('option', { name: 'flat3 (49)' }));
  expect(onSource).toHaveBeenCalledWith('naive');
});

// Single-mode ToggleBar is a radiogroup, so the segments are radios.
it('offers a segment per family something has been drawn in', () => {
  render(bar());
  expect(screen.getAllByRole('radio').map((b) => b.textContent))
    .toEqual(['Engine', 'Legacy', 'Decal']);
  expect(screen.getByRole('radio', { name: 'Legacy' }).getAttribute('aria-checked'))
    .toBe('true');
});

it('keeps the facet when the engine changes', () => {
  const onSource = vi.fn();
  render(bar({ onSource }));
  fireEvent.click(screen.getByRole('radio', { name: 'Engine' }));
  expect(onSource).toHaveBeenCalledWith('silhouette-occt');
});

// Decal is the whole family -- there is no facet to pick within it.
it('drops the slot dropdown for a family holding one slot', () => {
  render(bar({ source: 'decal' }));
  expect(screen.queryByRole('button', { name: /Slot/ })).toBeNull();
  expect(screen.getByRole('radio', { name: 'Decal' }).getAttribute('aria-checked'))
    .toBe('true');
});
