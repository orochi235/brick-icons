import { StrictMode, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { drawBadge } from '@lab/corpus/badges';
import { PROPERTY_FIELD } from '@lab/corpus/paint';

/** Throwaway: candidate faces for the sticker badge, at the sizes the wall
 *  draws. Delete once one is picked. */
const CANDIDATES: [string, string][] = [
  ['M solid', 'stickerMtronSolid'], ['M outline', 'stickerMtronOutline'],
  ['POLICE', 'stickerPolice'], ['skull', 'stickerSkull'],
];
const SIZES = [10, 14, 18, 44];
const COL = 150, ROW = 120;

function draw(canvas: HTMLCanvasElement) {
  const dpr = window.devicePixelRatio || 1;
  const w = COL * CANDIDATES.length + 50, h = ROW * SIZES.length + 50;
  canvas.width = w * dpr; canvas.height = h * dpr;
  canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
  const ctx = canvas.getContext('2d'); if (!ctx) return;
  ctx.scale(dpr, dpr);
  ctx.fillStyle = '#faf7f2'; ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = '#333'; ctx.font = '13px ui-monospace, monospace';
  ctx.textAlign = 'center';
  CANDIDATES.forEach(([name], i) => ctx.fillText(name, 50 + i * COL + COL / 2, 24));
  SIZES.forEach((size, r) => {
    const mid = 46 + r * ROW + ROW / 2;
    ctx.textAlign = 'right';
    ctx.fillStyle = '#333';
    ctx.fillText(`${size}px`, 42, mid);
    ctx.textAlign = 'center';
    CANDIDATES.forEach(([name, mark], i) => {
      const cx = 50 + i * COL + COL / 2;
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
    // Oswald lands after the first paint; a sheet drawn before it measures
    // the fallback and shows the wrong face.
    void document.fonts.ready.then(() => draw(canvas));
  });
  return <canvas ref={ref} />;
}
createRoot(document.getElementById('root')!).render(<StrictMode><Sheet /></StrictMode>);
