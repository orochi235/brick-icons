/** The pictures a cell badge can wear.
 *
 *  Every mark draws in a unit box centered on the origin -- `drawBadge`
 *  translates to the disc's center and scales -- so a mark is centered
 *  against its field by construction rather than by hand-tuned offsets.
 *  Their own module because nothing but a canvas can check them: keeping
 *  them out of `Wall.tsx` is what lets a page draw the set and look at it.
 */
import { BRUSH, BRUSH_CUT, MAGNET, MAGNET_CUT, MINIFIG,
  REDO } from '@lab/corpus/markPaths';
import type { CellBadge } from '@lab/corpus/paint';

// Lighter than the caption it sits beside would suggest: a badge letter is
// reversed out of a solid field, and reversed type gains weight optically --
// at 600 the Greek psi filled its disc.
export const BADGE_WEIGHT = 400;
export const BADGE_FACE = 'ui-monospace, monospace';

export type Mark = (ctx: CanvasRenderingContext2D, field: string) => void;

/** Fill each of a generated set of outlines in the field color -- the
 *  silhouette contracted and clipped, so a marking follows the form it sits
 *  on instead of reading as a rectangle chopped out of it. */
function cutPaths(ctx: CanvasRenderingContext2D, groups: number[][], field: string) {
  ctx.save();
  ctx.fillStyle = field;
  for (const pts of groups) fillPath(ctx, pts);
  ctx.restore();
}

/** Fill a generated outline: flat x,y pairs, closed. */
function fillPath(ctx: CanvasRenderingContext2D, pts: number[]) {
  ctx.beginPath();
  ctx.moveTo(pts[0]!, pts[1]!);
  for (let i = 2; i < pts.length; i += 2) ctx.lineTo(pts[i]!, pts[i + 1]!);
  ctx.closePath();
  ctx.fill();
}

// A five-pointed star, point up.
export const drawStar: Mark = (ctx) => {
  const inner = 0.42;
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const reach = i % 2 === 0 ? 1 : inner;
    const angle = -Math.PI / 2 + (i * Math.PI) / 5;
    const x = Math.cos(angle) * reach;
    const y = Math.sin(angle) * reach;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.fill();
};

// An archive box: a body under its lid band. Retired now means put away
// rather than replaced -- `updated` took the parts that had a successor.
// Kept well inside the unit box: a full-extent rectangle puts its corners at
// 1.41, which is almost the field's edge.
export const drawArchive: Mark = (ctx) => {
  ctx.fillRect(-0.82, -0.78, 1.64, 0.46);
  ctx.fillRect(-0.66, -0.2, 1.32, 1);
};

// Redo: the subset sign with a head, as one filled band so the head cannot
// come adrift of the stroke it finishes. Clockwise, or it reads as undo.
export const drawRedo: Mark = (ctx) => fillPath(ctx, REDO);

// A lightning bolt. A zigzag silhouette is the shape that survives the mark
// budget best -- a little over 4px at the badge floor -- and it wants some
// mass to survive it, so the strokes are wide.
export const drawBolt: Mark = (ctx) => {
  ctx.beginPath();
  ctx.moveTo(0.52, -1);
  ctx.lineTo(-0.72, 0.14);
  ctx.lineTo(-0.06, 0.14);
  ctx.lineTo(-0.42, 1);
  ctx.lineTo(0.74, -0.16);
  ctx.lineTo(0.06, -0.16);
  ctx.closePath();
  ctx.fill();
};

// A horseshoe magnet: a U with its poles marked by the silhouette contracted
// and clipped to the tips, so the marking follows the limb rather than
// cutting across it.
export const drawMagnet: Mark = (ctx, field) => {
  fillPath(ctx, MAGNET);
  cutPaths(ctx, MAGNET_CUT, field);
};

// A brush: bristles whose width goes to nothing at the tip, a ferrule under
// them broken off by a band of the field, and paint cut out of the tip so
// the field shows through. Printed parts are pad prints, so if this does not
// hold at the strip's floor the fallback is a halftone dot cluster.
export const drawBrush: Mark = (ctx, field) => {
  fillPath(ctx, BRUSH);
  ctx.beginPath();
  ctx.moveTo(-0.3, 0.42);
  ctx.lineTo(0.3, 0.42);
  ctx.lineTo(0.25, 1);
  ctx.lineTo(-0.25, 1);
  ctx.closePath();
  ctx.fill();
  ctx.save();
  ctx.fillStyle = field;
  ctx.fillRect(-0.34, 0.4, 0.68, 0.1);
  ctx.restore();
  cutPaths(ctx, BRUSH_CUT, field);
};

// A minifig head in silhouette -- stud, body and neck. Not drawn by eye: it
// is `3626b`'s own geometry seen face on, resampled at a fine step so the
// dome stays a curve. No face, because most minifig parts are printed and a
// face would read as the printed badge twice over.
export const drawMinifig: Mark = (ctx) => {
  ctx.save();
  ctx.scale(0.84, 0.84);
  fillPath(ctx, MINIFIG);
  ctx.restore();
};

// Composite: three stacked bars. Several things in one place, in the shape
// everyone already reads as a stack.
export const drawComposite: Mark = (ctx) => {
  for (const y of [-0.74, -0.18, 0.38]) ctx.fillRect(-0.7, y, 1.4, 0.36);
};

// Technic's T, drawn rather than set: a font's italic T carries a short
// crossbar and its slant walks the glyph off the disc's center. The shear is
// about the vertical middle, so the letter stays centered as it leans.
export const drawTechnic: Mark = (ctx) => {
  ctx.save();
  ctx.transform(1, 0, -0.15, 1, 0.07, 0);
  ctx.strokeStyle = ctx.fillStyle;
  ctx.lineWidth = 0.29;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(-0.82, -0.6);
  ctx.lineTo(0.58, -0.6);
  ctx.moveTo(-0.1, -0.6);
  ctx.lineTo(-0.1, 0.7);
  ctx.stroke();
  ctx.restore();
};

export const MARKS: Record<string, Mark> = {
  star: drawStar, archive: drawArchive, redo: drawRedo, bolt: drawBolt,
  magnet: drawMagnet, brush: drawBrush, minifig: drawMinifig,
  technic: drawTechnic, composite: drawComposite,
};

export function drawBadge(ctx: CanvasRenderingContext2D, badge: CellBadge,
                   at: { cx: number; cy: number; size: number; radius: number;
                         baseline?: number }) {
  const { cx, size, radius } = at;
  const font = `${badge.style ?? 'normal'} ${badge.weight ?? BADGE_WEIGHT} `
    + `${size * (badge.scale ?? 1)}px ${badge.font ?? BADGE_FACE}`;
  // Discs share one center, and each glyph is centered in its own disc: a
  // lowercase `d` climbs to its ascender and a capital does not, so setting
  // both on one text baseline puts their discs at different heights, which
  // is what a reader sees on the strip.
  const cy = at.cy;
  let textY = at.baseline ?? cy;
  if (badge.text) {
    ctx.save();
    ctx.font = font;
    const m = ctx.measureText(badge.text);
    const asc = m.actualBoundingBoxAscent;
    const desc = m.actualBoundingBoxDescent;
    ctx.restore();
    if (Number.isFinite(asc) && Number.isFinite(desc)) textY = cy + (asc - desc) / 2;
    textY += size * (badge.dy ?? 0);
  }
  ctx.save();
  // Every badge is stroked, most of them in their own field: duplo needs a
  // ring because red on white would vanish into the cell, and a ring only it
  // carries would make its disc the largest on the strip.
  const line = Math.max(1, radius * 0.16);
  ctx.beginPath();
  ctx.arc(cx, cy, radius - line / 2, 0, Math.PI * 2);
  ctx.fillStyle = badge.field;
  ctx.fill();
  ctx.lineWidth = line;
  ctx.strokeStyle = badge.stroke ?? badge.field;
  ctx.stroke();
  ctx.fillStyle = badge.ink;
  const mark = badge.mark ? MARKS[badge.mark] : undefined;
  if (mark) {
    ctx.save();
    ctx.translate(cx, cy);
    const m = radius * 0.66 * (badge.scale ?? 1);
    ctx.scale(m, m);
    mark(ctx, badge.field);
    ctx.restore();
  } else if (badge.text) {
    ctx.font = font;
    ctx.textAlign = 'center';
    if (at.baseline != null) {
      // On the part number's own baseline, so `4761 T d` reads as one line
      // rather than as a caption with ornaments floating beside it.
      ctx.textBaseline = 'alphabetic';
      ctx.fillText(badge.text, cx + size * (badge.dx ?? 0), textY);
    } else {
      ctx.textBaseline = 'alphabetic';
      ctx.fillText(badge.text, cx + size * (badge.dx ?? 0), textY);
    }
  }
  ctx.restore();
}

