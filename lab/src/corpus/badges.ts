/** The pictures a cell badge can wear.
 *
 *  Every mark draws in a unit box centered on the origin -- `drawBadge`
 *  translates to the disc's center and scales -- so a mark is centered
 *  against its field by construction rather than by hand-tuned offsets.
 *  Their own module because nothing but a canvas can check them: keeping
 *  them out of `Wall.tsx` is what lets a page draw the set and look at it.
 */
import { BRUSH, BRUSH_CUT, MAGNET, MAGNET_CUT, REDO,
  REDO_SPARK } from '@lab/corpus/markPaths';
import type { CellBadge } from '@lab/corpus/paint';

// Lighter than the caption it sits beside would suggest: a badge letter is
// reversed out of a solid field, and reversed type gains weight optically --
// at 600 the Greek psi filled its disc.
export const BADGE_WEIGHT = 400;
export const BADGE_FACE = 'ui-monospace, monospace';

export type Mark = (ctx: CanvasRenderingContext2D, field: string,
                    accent: string) => void;

/** Fill each of a generated set of outlines in the field color -- the
 *  silhouette contracted and clipped, so a marking follows the form it sits
 *  on instead of reading as a rectangle chopped out of it. */
function cutPaths(ctx: CanvasRenderingContext2D, groups: number[][], color: string) {
  ctx.save();
  ctx.fillStyle = color;
  for (const pts of groups) fillPath(ctx, pts);
  ctx.restore();
}

/** Build a generated outline as the current path: flat x,y pairs, closed. */
function tracePath(ctx: CanvasRenderingContext2D, pts: number[]) {
  ctx.beginPath();
  ctx.moveTo(pts[0]!, pts[1]!);
  for (let i = 2; i < pts.length; i += 2) ctx.lineTo(pts[i]!, pts[i + 1]!);
  ctx.closePath();
}

function fillPath(ctx: CanvasRenderingContext2D, pts: number[]) {
  tracePath(ctx, pts);
  ctx.fill();
}

// A five-pointed star, point up, with its points and valleys rounded: the
// path is built small and then stroked back out to size with round joins,
// which is what takes the needle off each point.
export const drawStar: Mark = (ctx) => {
  const outer = 0.78;
  const inner = 0.34;
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const reach = i % 2 === 0 ? outer : inner;
    const angle = -Math.PI / 2 + (i * Math.PI) / 5;
    const x = Math.cos(angle) * reach;
    const y = Math.sin(angle) * reach;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.save();
  ctx.strokeStyle = ctx.fillStyle;
  ctx.lineWidth = 0.2;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.stroke();
  ctx.restore();
  ctx.fill();
};

// An archive box: a body under its lid band, with the handle slot punched
// out of its front. Retired now means put away
// rather than replaced -- `updated` took the parts that had a successor.
// Kept well inside the unit box: a full-extent rectangle puts its corners at
// 1.41, which is almost the field's edge.
export const drawArchive: Mark = (ctx, field) => {
  ctx.fillRect(-0.74, -0.67, 1.48, 0.32);
  ctx.fillRect(-0.66, -0.21, 1.32, 0.88);
  ctx.save();
  ctx.strokeStyle = field;
  ctx.lineWidth = 0.26;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(-0.16, 0.04);
  ctx.lineTo(0.16, 0.04);
  ctx.stroke();
  ctx.restore();
};

// Redo: the arrow and the sparkle beside its tail, both from
// `scripts/redo.svg`. Computed instead it was an arc with a triangle glued
// on, and the head's aim never quite belonged to the curve.
export const drawRedo: Mark = (ctx, _field, accent) => {
  fillPath(ctx, REDO);
  cutPaths(ctx, REDO_SPARK, accent);
};

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
  // Stroked as well as filled: the zigzag's arms are the thinnest thing on
  // the strip, and at the badge floor they close up before anything else.
  ctx.save();
  ctx.strokeStyle = ctx.fillStyle;
  ctx.lineWidth = 0.17;
  ctx.lineJoin = 'round';
  ctx.stroke();
  ctx.restore();
  ctx.fill();
};

// A horseshoe magnet: a U with its poles in their own color, the silhouette
// clipped to the tips so they sit flush with the limbs' edges. Contracted
// inside them instead, they read as damage to the shape.
export const drawMagnet: Mark = (ctx, _field, accent) => {
  fillPath(ctx, MAGNET);
  cutPaths(ctx, MAGNET_CUT, accent);
};

// A brush: bristles whose width goes to nothing at the tip, a crimped
// ferrule under them broken off by a band of the field, and paint cut out of
// the tip so the field shows through. Printed parts are pad prints, so if this does not
// hold at the strip's floor the fallback is a halftone dot cluster.
export const drawBrush: Mark = (ctx, _field, accent) => {
  ctx.save();
  // Cut flat along a horizontal line, in the badge's frame rather than the
  // brush's: the tip is pressed against the ground of a stroke, and the
  // ground does not tilt with the brush.
  ctx.beginPath();
  ctx.rect(-1.8, -1.8, 3.6, 2.42);
  ctx.clip();
  ctx.translate(0, 0.18);
  ctx.rotate(-Math.PI * 2 / 3);
  // The handle runs off the edge of the field rather than stopping inside
  // it: a ferrule drawn whole is a stack of bands at the strip's floor, and
  // `drawBadge` clips the mark to the disc, so this reads as a brush held
  // into frame.
  ctx.save();
  ctx.fillStyle = '#c9c9d0';
  // Narrow where it meets the head and widening as it runs out, the way a
  // ferrule crimps onto a handle.
  ctx.beginPath();
  ctx.moveTo(-0.15, 0.55);
  ctx.lineTo(0.15, 0.55);
  ctx.lineTo(0.34, 2.15);
  ctx.lineTo(-0.34, 2.15);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
  fillPath(ctx, BRUSH);
  cutPaths(ctx, BRUSH_CUT, accent);
  ctx.restore();
};

// A minifig face: the disc is the head, so all the mark has to carry is the
// 1978 smiley. Measured off a face-on photograph of `3626` and expressed
// against the head's width -- the proportions are the recognizable part, and
// the disc is 3.03 mark units across. Drawing the head's own silhouette
// instead gave a shape that stopped reading below about 20px.
export const drawMinifig: Mark = (ctx) => {
  const drop = 0.185;   // the face group, centered in a disc that has no stud
  ctx.beginPath();
  ctx.arc(-0.433, -0.064 - drop, 0.215, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(0.433, -0.064 - drop, 0.215, 0, Math.PI * 2);
  ctx.fill();
  ctx.save();
  ctx.strokeStyle = ctx.fillStyle;
  ctx.lineWidth = 0.175;
  ctx.lineCap = 'round';
  ctx.beginPath();
  // The ends land about mid-pupil, which is where the print puts them.
  ctx.arc(0, 0.15 - drop, 0.626, Math.PI * 0.245, Math.PI * 0.755, false);
  ctx.stroke();
  ctx.restore();
};

// Composite: two L-trominoes interlocked into a 2x3 block -- the smallest
// rectangle two identical pieces can tile, and it says assembled-from-parts
// rather than merely stacked. Each piece takes its own color and the seam
// between them is cut in the field, so neither needs an outline.
export const drawComposite: Mark = (ctx, field, accent) => {
  ctx.save();
  ctx.rotate(-Math.PI / 2);
  ctx.beginPath();
  ctx.moveTo(-0.6, -0.9);
  ctx.lineTo(0.6, -0.9);
  ctx.lineTo(0.6, -0.3);
  ctx.lineTo(0, -0.3);
  ctx.lineTo(0, 0.3);
  ctx.lineTo(-0.6, 0.3);
  ctx.closePath();
  ctx.fill();
  ctx.save();
  ctx.fillStyle = accent;
  ctx.beginPath();
  ctx.moveTo(0, -0.3);
  ctx.lineTo(0.6, -0.3);
  ctx.lineTo(0.6, 0.9);
  ctx.lineTo(-0.6, 0.9);
  ctx.lineTo(-0.6, 0.3);
  ctx.lineTo(0, 0.3);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = field;
  ctx.lineWidth = 0.12;
  ctx.lineJoin = 'miter';
  ctx.beginPath();
  ctx.moveTo(0.6, -0.3);
  ctx.lineTo(0, -0.3);
  ctx.lineTo(0, 0.3);
  ctx.lineTo(-0.6, 0.3);
  ctx.stroke();
  ctx.restore();
  ctx.restore();
};

// Duplo's d, in the weight its logotype uses: a heavy rounded geometric with
// a counter small against the stroke. The bowl is cut thicker than the stem
// -- a curved stroke of the same width reads lighter than a straight one --
// and the stem's right edge sits on the bowl's, or the two pile up into a
// lump heavier than the side opposite it. The stem stops at the bowl's
// widest point rather than running to its foot: past that the bowl curves
// away from it, and the stem's corner hangs outside the letter as a serif
// the logotype does not have.
export const drawDuplo: Mark = (ctx, field) => {
  ctx.save();
  ctx.translate(0.22, -0.02);
  ctx.beginPath();
  ctx.arc(-0.3, 0.28, 0.7, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = ctx.fillStyle;
  ctx.lineWidth = 0.44;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(0.18, -0.72);
  ctx.lineTo(0.18, 0.28);
  ctx.stroke();
  ctx.fillStyle = field;
  ctx.beginPath();
  ctx.arc(-0.3, 0.28, 0.22, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
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
  technic: drawTechnic, composite: drawComposite, duplo: drawDuplo,
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
    // Clipped to its own disc, so a mark may run off the edge of the field
    // without spilling onto the cell behind it.
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.clip();
    ctx.translate(cx, cy);
    const m = radius * 0.66 * (badge.scale ?? 1);
    ctx.scale(m, m);
    mark(ctx, badge.field, badge.accent ?? badge.field);
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

