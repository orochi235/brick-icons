/** The pictures a cell badge can wear.
 *
 *  Every mark draws in a unit box centered on the origin -- `drawBadge`
 *  translates to the disc's center and scales -- so a mark is centered
 *  against its field by construction rather than by hand-tuned offsets.
 *  Their own module because nothing but a canvas can check them: keeping
 *  them out of `Wall.tsx` is what lets a page draw the set and look at it.
 */
export type Mark = (ctx: CanvasRenderingContext2D) => void;

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

// A clockwise curved arrow -- redo, not undo -- turned a quarter left so the
// head leads forward. Drawn rather than typed: the arrow glyphs are
// unreliable in a monospace face.
export const drawRedo: Mark = (ctx) => {
  ctx.save();
  ctx.rotate(-Math.PI / 2);
  ctx.strokeStyle = ctx.fillStyle;
  ctx.lineWidth = 0.34;
  ctx.beginPath();
  ctx.arc(0, 0, 0.66, Math.PI * 0.9, Math.PI * 0.2, false);
  ctx.stroke();
  const a = Math.PI * 0.2;
  const hx = Math.cos(a) * 0.66;
  const hy = Math.sin(a) * 0.66;
  ctx.translate(hx, hy);
  ctx.rotate(a + Math.PI / 2);
  ctx.beginPath();
  ctx.moveTo(0, 0.46);
  ctx.lineTo(-0.42, -0.3);
  ctx.lineTo(0.42, -0.3);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
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
  ctx.fill();
};

// A horseshoe magnet as mass rather than line: a thick arc with two square
// poles, opening upward the way one is drawn everywhere else. A real
// horseshoe reads by its two-tone poles, which a single-ink badge cannot
// draw, so the closed bend and the gap carry it instead.
export const drawMagnet: Mark = (ctx) => {
  ctx.save();
  ctx.rotate(Math.PI);
  ctx.strokeStyle = ctx.fillStyle;
  ctx.lineWidth = 0.44;
  ctx.beginPath();
  ctx.arc(0, -0.16, 0.6, Math.PI, 0, false);
  ctx.stroke();
  ctx.fillRect(-0.82, -0.16, 0.44, 1.16);
  ctx.fillRect(0.38, -0.16, 0.44, 1.16);
  ctx.restore();
};

// A brush: a narrow ferrule at the base, a head with a rounded belly
// tapering to a tip that curls off to one side, and a dab of paint coming
// off it. Printed parts are pad prints, so if this does not hold at the
// strip's floor the fallback is a halftone dot cluster.
export const drawBrush: Mark = (ctx) => {
  ctx.beginPath();
  ctx.moveTo(-0.18, 0.66);
  ctx.bezierCurveTo(-0.5, 0.5, -0.5, 0.05, -0.32, -0.34);
  ctx.bezierCurveTo(-0.16, -0.68, 0.04, -0.78, 0.3, -0.98);
  ctx.bezierCurveTo(0.12, -0.58, 0.2, -0.24, 0.3, 0.06);
  ctx.bezierCurveTo(0.42, 0.38, 0.36, 0.56, 0.18, 0.66);
  ctx.closePath();
  ctx.fill();
  ctx.fillRect(-0.2, 0.6, 0.4, 0.4);
  ctx.beginPath();
  ctx.arc(0.66, -0.6, 0.19, 0, Math.PI * 2);
  ctx.fill();
};

// A minifig head in silhouette: a cylinder with a flat open bottom, straight
// sides, a domed top, and its stud. No face -- most minifig parts are
// printed, so a face would read as the printed badge twice over.
export const drawMinifig: Mark = (ctx) => {
  ctx.beginPath();
  ctx.moveTo(-0.7, 1);
  ctx.lineTo(-0.7, -0.28);
  ctx.quadraticCurveTo(-0.7, -0.66, -0.34, -0.66);
  ctx.lineTo(0.34, -0.66);
  ctx.quadraticCurveTo(0.7, -0.66, 0.7, -0.28);
  ctx.lineTo(0.7, 1);
  ctx.closePath();
  ctx.fill();
  ctx.fillRect(-0.25, -1, 0.5, 0.42);
};

export const MARKS: Record<string, Mark> = {
  star: drawStar, archive: drawArchive, redo: drawRedo, bolt: drawBolt,
  magnet: drawMagnet, brush: drawBrush, minifig: drawMinifig,
};

