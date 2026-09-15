import { expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { MaterialBar } from '@lab/shared/MaterialBar';

const bar = (source: string, extra: Record<string, unknown> = {}) =>
  render(<MaterialBar source={source} width={120} height={18} {...extra} />).container;

/** No attribute anywhere in the tree fell out of the geometry math as
 *  NaN or Infinity. */
const assertFinite = (container: HTMLElement) =>
  expect(container.innerHTML).not.toMatch(/NaN|Infinity/);

it('draws a top face and a front face, outlined where the material has a stroke', () => {
  const svg = bar('occt');
  expect(svg.querySelectorAll('polygon')).toHaveLength(1);
  const front = svg.querySelector('rect')!;
  expect(front.getAttribute('stroke')).toBe('#000000');
  expect(front.getAttribute('fill')).toMatch(/^url\(#/);
});

it('leaves a silhouette unoutlined', () => {
  expect(bar('silhouette-occt').querySelector('rect')!.hasAttribute('stroke')).toBe(false);
});

it('gives translucent plastic a blurred highlight clipped to the front', () => {
  const svg = bar('translucent-naive');
  expect(svg.querySelector('filter feGaussianBlur')).not.toBeNull();
  expect(svg.querySelector('g[clip-path] g[filter]')?.querySelectorAll('rect')).toHaveLength(2);
});

it('hatches a print on both faces', () => {
  const groups = bar('decal').querySelectorAll('g[clip-path]');
  expect(groups).toHaveLength(2);
  groups.forEach((g) => expect(g.querySelectorAll('polygon').length).toBeGreaterThan(3));
});

it('draws a timed-out bar as a dashed outline with no fill', () => {
  const svg = bar('silhouette-naive', { timedOut: true });
  const dashed = svg.querySelector('g[stroke-dasharray]')!;
  expect(dashed.getAttribute('fill')).toBe('none');
  expect(dashed.getAttribute('stroke')).toBe('#FE8A18');
  expect(svg.querySelector('linearGradient')).toBeNull();
});

it('degrades to a zero-size chip for a zero width', () => {
  const svg = bar('occt', { width: 0 });
  expect(svg.querySelector('svg')).not.toBeNull();
  assertFinite(svg);
});

it('degrades cleanly when the height is too small for the top face', () => {
  const svg = bar('translucent-naive', { height: 3 });
  assertFinite(svg);
});

it('degrades cleanly for a fractional width', () => {
  const svg = bar('occt', { width: 3.7 });
  assertFinite(svg);
});

it('bounds the print-stripe loop against a runaway computed width', () => {
  const svg = bar('decal', { width: Infinity });
  assertFinite(svg);
  expect(svg.querySelectorAll('polygon').length).toBeLessThan(500);
});

it('never lets two bars share a gradient, clip or filter id', () => {
  const { container } = render(
    <>
      <MaterialBar source="translucent-occt" width={80} height={18} />
      <MaterialBar source="translucent-occt" width={40} height={18} />
      <MaterialBar source="decal" width={80} height={18} />
      <MaterialBar source="decal" width={40} height={18} />
    </>);
  const ids = [...container.querySelectorAll('[id]')].map((el) => el.id);
  expect(new Set(ids).size).toBe(ids.length);
});
