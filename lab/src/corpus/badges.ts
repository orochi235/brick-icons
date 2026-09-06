/** The pictures a cell badge can wear.
 *
 *  Every mark draws in a unit box centered on the origin -- `drawBadge`
 *  translates to the disc's center and scales -- so a mark is centered
 *  against its field by construction rather than by hand-tuned offsets.
 *  Their own module because nothing but a canvas can check them: keeping
 *  them out of `Wall.tsx` is what lets a page draw the set and look at it.
 */
export type Mark = (ctx: CanvasRenderingContext2D, field: string) => void;

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

// Redo: the subset sign with an arrowhead on it -- an arc bulging left,
// running bottom-right around to top-right, and a head continuing along the
// tangent so its aim is the curve's own rather than eyeballed. Drawn rather
// than typed: the arrow glyphs are unreliable in a monospace face.
export const drawRedo: Mark = (ctx) => {
  const r = 0.62;
  const stop = Math.PI * 1.2;
  const tip = Math.PI * 1.56;
  ctx.save();
  ctx.strokeStyle = ctx.fillStyle;
  ctx.lineWidth = 0.28;
  ctx.lineCap = 'butt';
  ctx.beginPath();
  ctx.arc(0, 0, r, Math.PI / 3, stop, false);
  ctx.stroke();
  ctx.restore();
  ctx.save();
  ctx.translate(Math.cos(tip) * r, Math.sin(tip) * r);
  ctx.rotate(tip + Math.PI / 2);
  ctx.beginPath();
  ctx.moveTo(0.62, 0);
  ctx.lineTo(-0.34, -0.5);
  ctx.lineTo(-0.34, 0.5);
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

// A horseshoe magnet: a thick U with a square notched out of the outer
// corner of each tip. A band straight across a limb reads as a severed tip
// -- a letter U with an umlaut -- so the notch takes a corner instead and
// leaves the limbs whole.
// Both arcs sweep anticlockwise-relative-to-the-angle so the bend lands at
// the bottom: `false` runs the direction of increasing angle, which in a
// y-down space goes over the top and fills the U's mouth.
// Without the poles it is a letter U -- they are the whole cue, and single
// ink cannot color them, so it borrows the field to cut them.
export const drawMagnet: Mark = (ctx, field) => {
  ctx.beginPath();
  ctx.moveTo(-0.72, -0.94);
  ctx.lineTo(-0.72, 0.28);
  ctx.arc(0, 0.28, 0.72, Math.PI, 0, true);
  ctx.lineTo(0.72, -0.94);
  ctx.lineTo(0.3, -0.94);
  ctx.lineTo(0.3, 0.28);
  ctx.arc(0, 0.28, 0.3, 0, Math.PI, false);
  ctx.lineTo(-0.3, -0.94);
  ctx.closePath();
  ctx.fill();
  ctx.save();
  ctx.fillStyle = field;
  ctx.fillRect(-0.72, -0.94, 0.2, 0.22);
  ctx.fillRect(0.52, -0.94, 0.2, 0.22);
  ctx.restore();
};

// A brush: bristles tapering to a fine tip, a ferrule under them broken off
// by a band of the field, and paint cut out of the tip so the field shows
// through. Specified point by point rather than in a handful of beziers --
// four control points could not hold the taper and kept reading as a bottle.
// Printed parts are pad prints, so if this does not hold at the strip's
// floor the fallback is a halftone dot cluster.
export const drawBrush: Mark = (ctx, field) => {
  ctx.beginPath();
  ctx.moveTo(-0.3, 0.46);
  ctx.lineTo(-0.36, 0.32);
  ctx.lineTo(-0.41, 0.16);
  ctx.lineTo(-0.44, 0.0);
  ctx.lineTo(-0.45, -0.16);
  ctx.lineTo(-0.44, -0.3);
  ctx.lineTo(-0.41, -0.43);
  ctx.lineTo(-0.36, -0.55);
  ctx.lineTo(-0.3, -0.66);
  ctx.lineTo(-0.22, -0.76);
  ctx.lineTo(-0.13, -0.85);
  ctx.lineTo(-0.03, -0.93);
  ctx.lineTo(0.08, -0.99);
  ctx.lineTo(0.18, -1.02);
  ctx.lineTo(0.14, -0.9);
  ctx.lineTo(0.14, -0.78);
  ctx.lineTo(0.17, -0.64);
  ctx.lineTo(0.21, -0.5);
  ctx.lineTo(0.26, -0.34);
  ctx.lineTo(0.31, -0.18);
  ctx.lineTo(0.35, -0.02);
  ctx.lineTo(0.38, 0.14);
  ctx.lineTo(0.39, 0.3);
  ctx.lineTo(0.36, 0.42);
  ctx.lineTo(0.3, 0.46);
  ctx.closePath();
  ctx.fill();
  // The ferrule, tapering the way a real one crimps toward the handle.
  ctx.beginPath();
  ctx.moveTo(-0.32, 0.44);
  ctx.lineTo(0.32, 0.44);
  ctx.lineTo(0.27, 1);
  ctx.lineTo(-0.27, 1);
  ctx.closePath();
  ctx.fill();
  ctx.save();
  ctx.fillStyle = field;
  ctx.fillRect(-0.36, 0.4, 0.72, 0.11);
  // Paint on the tip.
  ctx.beginPath();
  ctx.moveTo(0.12, -0.9);
  ctx.lineTo(-0.16, -0.44);
  ctx.lineTo(0.2, -0.38);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
};

// A minifig head in silhouette -- stud, body and neck. Not drawn by eye: it
// is `3626b`'s own geometry seen face on, its triangles and its analytic
// cylinders unioned and simplified, then normalized into the unit box. No
// face, because most minifig parts are printed and a face would read as the
// printed badge twice over.
export const drawMinifig: Mark = (ctx) => {
  ctx.beginPath();
  ctx.moveTo(-0.888, -0.537);
  ctx.lineTo(-0.915, 0.501);
  ctx.lineTo(-0.81, 0.702);
  ctx.lineTo(-0.562, 0.792);
  ctx.lineTo(-0.558, 1.0);
  ctx.lineTo(0.585, 1.0);
  ctx.lineTo(0.59, 0.79);
  ctx.lineTo(0.837, 0.702);
  ctx.lineTo(0.915, 0.609);
  ctx.lineTo(0.915, -0.537);
  ctx.lineTo(0.721, -0.692);
  ctx.lineTo(0.448, -0.72);
  ctx.lineTo(0.442, -1.0);
  ctx.lineTo(-0.415, -1.0);
  ctx.lineTo(-0.421, -0.72);
  ctx.lineTo(-0.694, -0.692);
  ctx.closePath();
  ctx.fill();
};

// Technic's T, drawn rather than set: a font's italic T carries a short
// crossbar and its slant walks the glyph off the disc's center. The shear is
// about the vertical middle, so the letter stays centered as it leans.
export const drawTechnic: Mark = (ctx) => {
  ctx.save();
  ctx.transform(1, 0, -0.24, 1, 0, 0);
  ctx.strokeStyle = ctx.fillStyle;
  ctx.lineWidth = 0.29;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(-0.72, -0.6);
  ctx.lineTo(0.72, -0.6);
  ctx.moveTo(0, -0.6);
  ctx.lineTo(0, 0.7);
  ctx.stroke();
  ctx.restore();
};

export const MARKS: Record<string, Mark> = {
  star: drawStar, archive: drawArchive, redo: drawRedo, bolt: drawBolt,
  magnet: drawMagnet, brush: drawBrush, minifig: drawMinifig,
  technic: drawTechnic,
};
