import { useCallback, useState } from 'react';
import type { ImageFilter } from '@pezlie/wall/src/filter';

const STORAGE_KEY = 'brick-icons.wall.ink';

function stored(): string {
  try { return localStorage.getItem(STORAGE_KEY) ?? ''; } catch { return ''; }
}

function store(value: string) {
  try {
    if (value) localStorage.setItem(STORAGE_KEY, value);
    else localStorage.removeItem(STORAGE_KEY);
  } catch { /* a remembered color is a convenience */ }
}

/** What the wall's color field holds -- a name, a code or hex, as typed. */
export function useInk(): [string, (value: string | null) => void] {
  const [value, setValue] = useState(stored);
  const set = useCallback((next: string | null) => { store(next ?? ''); setValue(next ?? ''); }, []);
  return [value, set];
}

/** `Flat3Style`'s default part color: every face tone is this gray times a
 *  fixed factor (1.30 top, 0.85 and 0.60 sides, 0.55-1.40 on a curve). */
const BASE_GRAY = 157;
/** Chroma, in 0-255 steps, where a pixel stops reading as a gray face and
 *  starts reading as printing. Between the two it is blended, for the
 *  antialiased edge where a print meets a face. */
const CHROMA_FACE = 10;
const CHROMA_PRINT = 40;

function rgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [n >> 16, (n >> 8) & 255, n & 255];
}

/** The drawing as if rendered with `--part-color hex`: each gray becomes
 *  `hex * gray / BASE_GRAY`, and black outlines stay black.
 *
 *  What counts as decoration comes from the render's own mask where it has
 *  one -- white where the render marked `class="deco"` -- so gray and white
 *  printing is kept too. With no mask, a pixel with color in it is taken for
 *  printing, which gray printing defeats. */
export function shadeFilter(hex: string): ImageFilter {
  const [ir, ig, ib] = rgb(hex);
  return {
    key: `shade:${hex}`,
    apply(ctx, src, w, h, mask) {
      let m: Uint8ClampedArray | null = null;
      if (mask) {
        ctx.drawImage(mask, 0, 0);
        m = ctx.getImageData(0, 0, w, h).data;
        ctx.clearRect(0, 0, w, h);
      }
      ctx.drawImage(src, 0, 0);
      const image = ctx.getImageData(0, 0, w, h);
      const d = image.data;
      for (let i = 0; i < d.length; i += 4) {
        if (d[i + 3] === 0) continue;
        const r = d[i]!, g = d[i + 1]!, b = d[i + 2]!;
        let t: number;
        if (m && m[i + 3]! > 0) {
          t = 1 - m[i]! / 255;
        } else {
          const chroma = Math.max(r, g, b) - Math.min(r, g, b);
          t = chroma <= CHROMA_FACE ? 1 : chroma >= CHROMA_PRINT ? 0
            : (CHROMA_PRINT - chroma) / (CHROMA_PRINT - CHROMA_FACE);
        }
        if (t === 0) continue;
        const k = (r + g + b) / (3 * BASE_GRAY);
        d[i] = r + (Math.min(255, ir * k) - r) * t;
        d[i + 1] = g + (Math.min(255, ig * k) - g) * t;
        d[i + 2] = b + (Math.min(255, ib * k) - b) * t;
      }
      ctx.putImageData(image, 0, 0);
    },
  };
}
