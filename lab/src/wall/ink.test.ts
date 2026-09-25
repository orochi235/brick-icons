import { describe, expect, it } from 'vitest';
import { shadeFilter } from '@lab/wall/ink';

/** One row of RGBA pixels through the filter, on a context that only holds
 *  the pixel data. */
function shade(hex: string, pixels: number[][], maskPixels?: number[][]): number[][] {
  const data = new Uint8ClampedArray(pixels.flat());
  const mask = maskPixels && new Uint8ClampedArray(maskPixels.flat());
  const MASK = {} as CanvasImageSource;
  let drawn: unknown = null;
  const ctx = {
    drawImage: (img: unknown) => { drawn = img; },
    getImageData: () => ({ data: drawn === MASK ? mask : data }),
    putImageData: () => {},
    clearRect: () => {},
  } as unknown as CanvasRenderingContext2D;
  shadeFilter(hex).apply(ctx, {} as CanvasImageSource, pixels.length, 1, mask ? MASK : null);
  return pixels.map((_, i) => [...data.slice(i * 4, i * 4 + 4)]);
}

describe('shadeFilter', () => {
  it('draws the base gray as the color, and the top face 1.3 times it', () => {
    const [base, top] = shade('#b40000', [[157, 157, 157, 255], [204, 204, 204, 255]]);
    expect(base).toEqual([180, 0, 0, 255]);
    expect(top).toEqual([234, 0, 0, 255]);
  });

  it('keeps black outlines black and alpha untouched', () => {
    expect(shade('#b40000', [[0, 0, 0, 255], [157, 157, 157, 90]]))
      .toEqual([[0, 0, 0, 255], [180, 0, 0, 90]]);
  });

  it('leaves printing alone', () => {
    const yellow = [242, 205, 55, 255];
    expect(shade('#b40000', [yellow])).toEqual([yellow]);
  });

  it('blends the edge where a print meets a face', () => {
    const [edge] = shade('#b40000', [[170, 150, 145, 255]]);
    expect(edge![0]).toBeGreaterThan(170);
    expect(edge![1]).toBeLessThan(150);
    expect(edge![1]).toBeGreaterThan(0);
  });
});

describe('shadeFilter with a mask', () => {
  it('keeps gray printing the mask marks, which color alone cannot tell from a face', () => {
    const gray = [150, 150, 150, 255];
    expect(shade('#b40000', [gray], [[255, 255, 255, 255]])).toEqual([gray]);
  });

  it('shades what the mask says is the part, even where it has color', () => {
    const [px] = shade('#b40000', [[170, 150, 145, 255]], [[0, 0, 0, 255]]);
    expect(px![1]).toBe(0);
  });

  it('falls back to color where the mask has nothing', () => {
    const yellow = [242, 205, 55, 255];
    expect(shade('#b40000', [yellow, [157, 157, 157, 255]], [[0, 0, 0, 0], [0, 0, 0, 0]]))
      .toEqual([yellow, [180, 0, 0, 255]]);
  });
});
