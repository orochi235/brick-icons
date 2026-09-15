import { expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { Measurements, tier } from '@lab/corpus/Measurements';

const finding = (source: string, extra: Record<string, unknown> = {}) => ({
  part_id: '4449-f1', engine: source.endsWith('naive') ? 'naive' : 'occt', source,
  extra_d99: 1.01, missing_px: 0, missing_comps: 0, secs: 30, error: null, ...extra,
});

const rowsOf = (container: HTMLElement) =>
  [...container.querySelectorAll('tbody tr')].map((tr) => tr.getAttribute('data-slot'));

it('orders rows occt, naive, reference, the rest, then decal', () => {
  const { container } = render(<Measurements findings={[
    finding('decal'), finding('white-naive'), finding('occt'),
    finding('reference'), finding('naive')]} />);
  expect(rowsOf(container)).toEqual(['occt', 'naive', 'reference', 'white-naive', 'decal']);
});

it('names a row by engine when an older API sends no source', () => {
  const { container } = render(<Measurements findings={[
    { ...finding('naive'), source: undefined }]} />);
  expect(rowsOf(container)).toEqual(['naive']);
});

it('marks a value at the corpus p90 warm and at p99 hot', () => {
  expect(tier('extra_d99', 1.40)).toBeUndefined();
  expect(tier('extra_d99', 1.41)).toBe('warm');
  expect(tier('extra_d99', 7.44)).toBe('hot');
  expect(tier('missing_comps', 0)).toBeUndefined();
  expect(tier('missing_comps', 1)).toBe('warm');
  expect(tier('missing_px', 61026)).toBe('hot');
  expect(tier('missing_px', null)).toBeUndefined();
});

it('shades the cells that are remarkable, and only those', () => {
  const { container } = render(<Measurements findings={[
    finding('occt', { missing_px: 2927, missing_comps: 6 })]} />);
  const tiers = [...container.querySelectorAll('tbody td.corpus-measure-num')]
    .map((td) => td.getAttribute('data-tier'));
  expect(tiers).toEqual([null, 'warm', 'hot']);
  expect(container.textContent).toContain('2,927');
});

it('says what stopped a slot across the three number cells', () => {
  const { container } = render(<Measurements findings={[
    finding('occt', { extra_d99: null, missing_px: null, missing_comps: null,
                      error: 'OCCError' })]} />);
  const cell = container.querySelector('td.corpus-measure-error')!;
  expect(cell.getAttribute('colspan')).toBe('3');
  expect(cell.textContent).toBe('OCCError');
});

it('scales secs to the slowest slot and puts the value right after the bar', () => {
  const { container } = render(<Measurements findings={[
    finding('occt', { secs: 30 }), finding('naive', { secs: 120 })]} />);
  const widths = [...container.querySelectorAll('.corpus-measure-bar .material-bar')]
    .map((svg) => Number(svg.getAttribute('width')));
  expect(widths).toEqual([75, 300]);
  expect(container.querySelector('.corpus-measure-bar .material-bar + .corpus-measure-value')
    ?.textContent).toBe('30.0s');
});

it('draws a timeout as a dashed bar with its value dimmed', () => {
  const { container } = render(<Measurements findings={[
    finding('silhouette-occt', { secs: 120.1, error: 'TimeoutError' })]} />);
  expect(container.querySelector('.corpus-measure-bar g[stroke-dasharray]')).not.toBeNull();
  expect(container.querySelector('.corpus-measure-value')?.hasAttribute('data-timed-out'))
    .toBe(true);
});

it('puts a chip before each slot name', () => {
  const { container } = render(<Measurements findings={[finding('reference')]} />);
  const label = container.querySelector('tbody th .corpus-chip-label')!;
  expect(label.firstElementChild?.classList.contains('material-bar')).toBe(true);
  expect(label.textContent).toBe('reference');
});
