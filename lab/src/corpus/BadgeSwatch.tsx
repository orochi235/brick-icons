import { useEffect, useRef } from 'react';
import { badgeWidth, drawBadge } from '@lab/corpus/badges';
import type { CellBadge } from '@lab/corpus/paint';

/** Sized so a badge comes out the same 14px across as the legend's state
 *  swatches -- the two halves of that panel are one list to read down. */
export const SWATCH_BOX = 14;

/** A badge drawn through the wall's own `drawBadge`, so a detail view and a
 *  cell cannot show different artwork for the same tag. `label` sets the
 *  word on the badge's own field; without one this is the bare disc.
 *
 *  Everything about the badge -- its field, its ink, its mark -- comes off
 *  the one record in `paint.ts`. A DOM re-drawing of the same mark would
 *  drift from the canvas one, which is how the corner and strip badges came
 *  apart before. */
export function BadgeSwatch({ badge, label, box = SWATCH_BOX, className }:
                            { badge: CellBadge; label?: string; box?: number;
                              className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const radius = box / 2;
    const at = { cx: radius, cy: radius, size: radius / 0.72, radius, label };
    const dpr = window.devicePixelRatio || 1;
    // jsdom throws out of getContext rather than returning null, and a
    // swatch that cannot draw must not take the view down with it.
    let ctx: CanvasRenderingContext2D | null = null;
    try {
      ctx = canvas.getContext('2d');
    } catch {
      return;
    }
    if (!ctx) return;
    // Measured before the canvas is sized: a stadium's width is its label's,
    // and only a live context can measure text.
    const w = Math.ceil(badgeWidth(ctx, badge, at));
    canvas.width = w * dpr;
    canvas.height = box * dpr;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${box}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, box);
    drawBadge(ctx, badge, at);
  }, [badge, label, box]);
  return <canvas ref={ref} aria-hidden="true"
                 className={className ?? 'corpus-badge-swatch'} />;
}
