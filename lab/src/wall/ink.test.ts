import { describe, expect, it } from 'vitest';
import { shadeFilter } from '@lab/wall/ink';

/** One row of RGBA pixels through the filter, on a context that only holds
 *  the pixel data. */
function shade(hex: string, pixels: number[][]): number[][] {
  const data = new Uint8ClampedArray(pixels.flat());
  const ctx = {
    drawImage: () => {},
    getImageData: () => ({ data }),
    putImageData: () => {},
  } as unknown as CanvasRenderingContext2D;
  shadeFilter(hex).apply(ctx, {} as CanvasImageSource, pixels.length, 1);
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
