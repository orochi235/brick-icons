import { expect, it } from 'vitest';
import { injectSize } from '@lab/corpus/svgRaster';

const RENDER = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170" '
  + 'preserveAspectRatio="xMidYMid meet">\n<g></g>\n</svg>';

it('sets an explicit width and height a render never declares', () => {
  const sized = injectSize(RENDER, 800, 800);
  expect(sized).toContain('width="800"');
  expect(sized).toContain('height="800"');
});

it('leaves the viewBox and preserveAspectRatio alone -- that is what letterboxes', () => {
  const sized = injectSize(RENDER, 800, 800);
  expect(sized).toContain('viewBox="0 0 256 170"');
  expect(sized).toContain('preserveAspectRatio="xMidYMid meet"');
});

it('replaces a width/height already present rather than duplicating it', () => {
  const already = injectSize(RENDER, 200, 200);
  const resized = injectSize(already, 800, 800);
  expect(resized).toContain('width="800"');
  expect(resized).not.toContain('width="200"');
  expect((resized.match(/width="/g) ?? []).length).toBe(1);
});
