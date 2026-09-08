import { StrictMode, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { drawBadge } from '@lab/corpus/badges';
import { PROPERTY_FIELD } from '@lab/corpus/paint';

/** The two faces the sticker badge can wear, at the sizes the wall draws.
 *  `POLICE` is the one wired up; `flames` is kept as the alternative and this
 *  page is how you compare them -- swapping `mark` on the sticker badge in
 *  `paint.ts` is the whole change. */
const CANDIDATES: [string, string][] = [
  ['POLICE outlines', 'stickerPolice'], ['flames', 'stickerFlames'],
];
const SIZES = [10, 14, 18, 44];
const COL = 150, ROW = 120, GUTTER = 56;

function draw(canvas: HTMLCanvasElement) {
  const dpr = window.devicePixelRatio || 1;
  const w = COL * CANDIDATES.length + GUTTER * 2, h = ROW * SIZES.length + 50;
  canvas.width = w * dpr; canvas.height = h * dpr;
  canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
  const ctx = canvas.getContext('2d'); if (!ctx) return;
  ctx.scale(dpr, dpr);
  ctx.fillStyle = '#faf7f2'; ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = '#333'; ctx.font = '13px ui-monospace, monospace';
  ctx.textAlign = 'center';
  CANDIDATES.forEach(([name], i) => ctx.fillText(name, GUTTER + i * COL + COL / 2, 24));
  SIZES.forEach((size, r) => {
    const mid = 46 + r * ROW + ROW / 2;
    ctx.textAlign = 'right';
    ctx.fillStyle = '#333';
    ctx.fillText(`${size}px`, GUTTER - 12, mid);
    ctx.textAlign = 'center';
    CANDIDATES.forEach(([name, mark], i) => {
      const cx = GUTTER + i * COL + COL / 2;
      drawBadge(ctx, { tag: name, mark: mark as never, field: PROPERTY_FIELD,
                       ink: '#ffffff', accent: '#c9c9d0' },
                { cx, cy: mid, size, radius: size * 0.72 });
    });
  });
}

function Sheet() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current; if (!canvas) return;
    draw(canvas);
  });
  return <canvas ref={ref} />;
}
createRoot(document.getElementById('root')!).render(<StrictMode><Sheet /></StrictMode>);
