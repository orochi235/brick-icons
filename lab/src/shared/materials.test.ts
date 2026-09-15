import { expect, it } from 'vitest';
import { CHART_ORDER, chartRank, familyInk, materialOf, shade } from '@lab/shared/materials';

it('gives every family member its family color', () => {
  expect(materialOf('silhouette-occt').color).toBe(materialOf('occt').color);
  expect(materialOf('silhouette-naive').color).toBe(materialOf('naive').color);
  expect(materialOf('white-occt').stroke).toBe(materialOf('occt').color);
});

it('draws a slot it does not know as gray plastic', () => {
  expect(materialOf('ldview')).toEqual(
    { color: '#8A8C85', finish: 'solid', opacity: 1, stroke: '#000000' });
});

it('inks white with its stroke and everything else with its color', () => {
  expect(familyInk(materialOf('white-naive'))).toBe('#FE8A18');
  expect(familyInk(materialOf('silhouette-occt'))).toBe('#0055BF');
});

it('orders occt, naive, reference, the rest, then decal', () => {
  const shuffled = ['decal', 'white-naive', 'occt', 'mystery', 'reference',
                    'naive', 'translucent-occt'];
  expect([...shuffled].sort((a, b) => chartRank(a) - chartRank(b))).toEqual(
    ['occt', 'naive', 'reference', 'translucent-occt', 'white-naive', 'mystery', 'decal']);
  expect(CHART_ORDER.at(-1)).toBe('decal');
});

it('ranks an unlisted slot just before the last entry', () => {
  expect(chartRank('mystery')).toBe(CHART_ORDER.length - 1.5);
});

it('returns the same fallback object for two different unknown slots', () => {
  expect(materialOf('ldview')).toBe(materialOf('pov-ray'));
  expect(materialOf('occt')).toBe(materialOf('occt'));
});

it('shifts HLS lightness and clamps it', () => {
  expect(shade('#0055BF', 0)).toBe('#0055bf');
  expect(shade('#808080', 1)).toBe('#ffffff');
  expect(shade('#808080', 2)).toBe('#ffffff');
  expect(shade('#808080', -1)).toBe('#000000');
  // Same answer as Python's colorsys, which the mockups were drawn with.
  expect(shade('#0055BF', 0.34)).toBe('#6daeff');
});

it('throws on a hex string it cannot parse', () => {
  expect(() => shade('#fff', 0)).toThrow();
  expect(() => shade('0055BF', 0)).toThrow();
});
