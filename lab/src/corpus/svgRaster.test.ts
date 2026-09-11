import { expect, it, vi } from 'vitest';
import { contain, fetchRender, injectSize, sizedBlob } from '@lab/corpus/svgRaster';

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

// The decal slot writes its own width and height and no box at all. Sizing
// that without one is a crop: user units are CSS pixels, so the wall drew the
// top-left corner of a 405x900 decal at full size and called it a thumbnail.
const DECAL = '<svg xmlns="http://www.w3.org/2000/svg" width="405" height="900">'
  + '<path d="M 0 0"/></svg>';

it('gives a render that declares a size but no box one to be scaled by', () => {
  const sized = injectSize(DECAL, 128, 128);
  expect(sized).toContain('viewBox="0 0 405 900"');
  expect(sized).toContain('width="128"');
  expect((sized.match(/viewBox="/g) ?? []).length).toBe(1);
});

it('never invents a box over the one a render already declares', () => {
  const sized = injectSize(injectSize(RENDER, 200, 200), 800, 800);
  expect(sized).toContain('viewBox="0 0 256 170"');
  expect((sized.match(/viewBox="/g) ?? []).length).toBe(1);
});

it('sizes an SVG blob and leaves a raster blob alone', async () => {
  const svg = await sizedBlob(new Blob([RENDER], { type: 'image/svg+xml' }), 800, 800);
  expect(await svg.text()).toContain('width="800"');

  const webp = new Blob([new Uint8Array([0x52, 0x49, 0x46, 0x46])],
                        { type: 'image/webp' });
  expect(await sizedBlob(webp, 800, 800)).toBe(webp);
});

it('reads a render as bytes, so a raster slot survives the trip', async () => {
  const bytes = new Uint8Array([0x52, 0x49, 0x46, 0x46, 0x00, 0xff, 0xfe]);
  const fetched: string[] = [];
  vi.stubGlobal('fetch', async (url: string) => {
    fetched.push(url);
    return new Response(bytes, { headers: { 'content-type': 'image/webp' } });
  });
  const blob = await fetchRender('/api/corpus/render/reference/3001.svg');
  expect(fetched).toEqual(['/api/corpus/render/reference/3001.svg']);
  expect(blob.type).toBe('image/webp');
  expect(new Uint8Array(await blob.arrayBuffer())).toEqual(bytes);
  vi.unstubAllGlobals();
});

it('refuses a render the API could not find', async () => {
  vi.stubGlobal('fetch', async () => new Response('', { status: 404 }));
  await expect(fetchRender('/api/corpus/render/reference/9999.svg')).rejects.toThrow('404');
  vi.unstubAllGlobals();
});

it('fits a tall render inside a square without changing its shape', () => {
  // reference's narrowest: 936x2048 stretched 2.19x wide before this.
  const at = contain(936, 2048, 256, 256);
  expect(at.h).toBe(256);
  expect(Math.round(at.w)).toBe(117);
  expect(at.w / at.h).toBeCloseTo(936 / 2048, 5);
  expect(at.x).toBeCloseTo((256 - at.w) / 2, 5);
  expect(at.y).toBe(0);
});

it('fits a wide render the same way', () => {
  const at = contain(2048, 1629, 256, 256);
  expect(at.w).toBe(256);
  expect(at.w / at.h).toBeCloseTo(2048 / 1629, 5);
  expect(at.x).toBe(0);
});

it('fills the box for a source with no size to preserve', () => {
  expect(contain(0, 0, 256, 256)).toEqual({ x: 0, y: 0, w: 256, h: 256 });
});
