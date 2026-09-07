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
// rather than replaced -- `replaced` took the parts that had a successor.
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

// The field is the sticker, and its lower right is peeling off -- the same
// move the minifig badge makes, where the disc is the head rather than a
// picture of one. `drawBadge` clips a mark to its own disc and hands it a
// unit box where the field's edge sits at 1.515, so the peel is built against
// that radius: the sticker is only the part of the disc the flap has not
// lifted, and what shows behind it is the ink the rest of the set reverses to.
const FIELD_R = 1.515;

/** One peel, at `arc` radians of the field's edge, folding `back` of the way
 *  toward the center. Larger reads at small sizes; smaller keeps more sticker. */
function peel(ctx: CanvasRenderingContext2D, field: string, accent: string,
              from: number, arc: number, lift: number) {
  const to = from + arc;
  const p = (a: number): [number, number] =>
    [Math.cos(a) * FIELD_R, Math.sin(a) * FIELD_R];
  const [x0, y0] = p(from);
  const [x1, y1] = p(to);

  // What the sticker lifted off: the cap between the chord and the edge, in
  // the ink every other mark on this field is drawn in.
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.arc(0, 0, FIELD_R, from, to);
  ctx.closePath();
  ctx.fill();

  // The flap is that same cap folded over the chord, so it is the cap
  // reflected in the chord line -- not a curve drawn to look like one. `lift`
  // foreshortens it toward the fold, which is what a corner standing up off
  // the page does; at 1 it lies flat back on the sticker.
  const dx = x1 - x0, dy = y1 - y0;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len, uy = dy / len;
  const reflect = (qx: number, qy: number): [number, number] => {
    const vx = qx - x0, vy = qy - y0;
    const t = vx * ux + vy * uy;
    return [x0 + 2 * t * ux - vx, y0 + 2 * t * uy - vy];
  };
  const STEPS = 24;
  ctx.save();
  ctx.fillStyle = accent;
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  for (let i = 0; i <= STEPS; i++) {
    const a = from + (arc * i) / STEPS;
    const [qx, qy] = p(a);
    const [rx, ry] = reflect(qx, qy);
    // toward the chord by (1 - lift): the fold stays put, the free edge comes in
    const mx = x0 + ((rx - x0) * ux + (ry - y0) * uy) * ux;
    const my = y0 + ((rx - x0) * ux + (ry - y0) * uy) * uy;
    ctx.lineTo(mx + (rx - mx) * lift, my + (ry - my) * lift);
  }
  ctx.closePath();
  ctx.fill();

  // The fold, kept faint: it is a crease, not an outline.
  ctx.strokeStyle = field;
  ctx.lineWidth = 0.05;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.stroke();
  ctx.restore();
}

// The tab: how much of the edge lifts, and how far the flap stands off the
// fold. `lift` 1 lays it flat back down on the sticker.
const PEEL_FROM = Math.PI * 0.02;
const PEEL_ARC = Math.PI * 0.62;
const PEEL_LIFT = 0.72;

/** Print on the sticker's face. Centered on the disc, not on the flat part
 *  that is left: the print was applied while the sticker was flat, so the
 *  fold covers whatever it covers -- which is what makes the corner read as
 *  lifted off the print rather than as a shape drawn beside it. Marks are
 *  laid down before the peel, so it occludes them. */
type FaceMark = (ctx: CanvasRenderingContext2D) => void;

/** The fire emblem off sticker 004659a, in one ink. Its three flames are three
 *  colors in the artwork and only ~19px apart in a 900px field, so monochrome
 *  would weld them into a blob; each is pulled in 13px first, which opens the
 *  gaps to ~45px and keeps three flames readable. One ink cannot carry the
 *  yellow, orange and red, but it can carry their order. */
const FLAMES: number[][] = [
  [-0.566, 0.911, -0.442, 0.838, -0.369, 0.777, -0.268, 0.646, -0.259, 0.591, -0.291, 0.35, -0.333, 0.222, -0.376, 0.105, -0.54, -0.214, -0.552, -0.285, -0.552, -0.405, -0.672, -0.309, -0.765, -0.186, -0.795, -0.115, -0.826, 0.02, -0.816, 0.25, -0.785, 0.376, -0.687, 0.581, -0.654, 0.693, -0.631, 0.816, -0.629, 0.93],
  [-0.142, 0.534, -0.155, 0.617, -0.061, 0.567, 0.011, 0.505, 0.071, 0.434, 0.101, 0.366, 0.121, 0.251, 0.143, 0.017, 0.132, -0.088, 0.111, -0.204, 0.003, -0.53, -0.009, -0.614, -0.005, -0.733, -0.17, -0.562, -0.221, -0.48, -0.263, -0.376, -0.294, -0.199, -0.284, -0.022, -0.186, 0.291],
  [0.172, 0.481, 0.292, 0.444, 0.385, 0.392, 0.446, 0.342, 0.518, 0.258, 0.57, 0.176, 0.601, 0.104, 0.643, -0.064, 0.654, -0.355, 0.676, -0.578, 0.711, -0.703, 0.826, -0.93, 0.765, -0.93, 0.653, -0.899, 0.548, -0.847, 0.443, -0.784, 0.339, -0.69, 0.267, -0.597, 0.215, -0.484, 0.195, -0.403, 0.195, -0.346, 0.26, -0.129, 0.271, -0.038, 0.271, 0.15, 0.258, 0.265],
];
const FLAME_ALPHA = [1, 0.72, 0.48];

const faceFlames: FaceMark = (ctx) => {
  ctx.save();
  FLAMES.forEach((ring, n) => {
    ctx.globalAlpha = FLAME_ALPHA[n] ?? 1;
    ctx.beginPath();
    ctx.moveTo(ring[0]!, ring[1]!);
    for (let i = 2; i < ring.length; i += 2) ctx.lineTo(ring[i]!, ring[i + 1]!);
    ctx.closePath();
    ctx.fill();
  });
  ctx.restore();
};

/** The word every LEGO sticker says, as outlines rather than type: converted
 *  from Bebas Neue with fontTools, curves flattened, simplified to 131 points
 *  and normalized so its box is the origin. Baking it means no webfont to
 *  load, no race between the first paint and the font arriving, and no
 *  fallback face quietly setting it at another width.
 *
 *  Filled `evenodd`, so the counters in P and O punch through whichever way
 *  the contours happen to wind. */
const POLICE_OUTLINES: number[][] = [
  [-1.21, -0.422, -0.991, -0.422, -0.928, -0.409, -0.894, -0.393, -0.854, -0.355, -0.829, -0.304, -0.82, -0.262, -0.82, -0.082, -0.829, -0.04, -0.854, 0.011, -0.894, 0.049, -0.928, 0.065, -0.991, 0.078, -1.077, 0.079, -1.077, 0.422, -1.21, 0.422],
  [-1.014, -0.042, -0.975, -0.052, -0.953, -0.085, -0.949, -0.122, -0.953, -0.259, -0.966, -0.284, -0.986, -0.297, -1.077, -0.302, -1.077, -0.042],
  [-0.754, 0.222, -0.753, -0.247, -0.734, -0.331, -0.714, -0.364, -0.688, -0.392, -0.656, -0.413, -0.619, -0.427, -0.528, -0.434, -0.485, -0.427, -0.448, -0.413, -0.416, -0.392, -0.38, -0.348, -0.358, -0.292, -0.351, -0.247, -0.351, 0.247, -0.371, 0.331, -0.39, 0.364, -0.416, 0.392, -0.466, 0.421, -0.528, 0.434, -0.619, 0.427, -0.673, 0.403, -0.702, 0.379, -0.725, 0.348, -0.747, 0.292],
  [-0.483, 0.231, -0.484, -0.25, -0.493, -0.281, -0.51, -0.302, -0.536, -0.312, -0.568, -0.312, -0.604, -0.293, -0.62, -0.25, -0.621, 0.231, -0.617, 0.267, -0.594, 0.302, -0.568, 0.312, -0.536, 0.312, -0.501, 0.293, -0.488, 0.267],
  [-0.261, -0.422, -0.129, -0.422, -0.129, 0.302, 0.09, 0.302, 0.09, 0.422, -0.261, 0.422],
  [0.154, -0.422, 0.287, -0.422, 0.287, 0.422, 0.154, 0.422],
  [0.377, 0.227, 0.378, -0.251, 0.397, -0.333, 0.415, -0.366, 0.441, -0.393, 0.471, -0.413, 0.508, -0.427, 0.596, -0.434, 0.638, -0.427, 0.674, -0.413, 0.718, -0.38, 0.74, -0.35, 0.756, -0.315, 0.767, -0.251, 0.768, -0.138, 0.643, -0.138, 0.642, -0.254, 0.626, -0.294, 0.605, -0.309, 0.576, -0.314, 0.547, -0.309, 0.526, -0.294, 0.514, -0.27, 0.51, -0.235, 0.511, 0.255, 0.526, 0.294, 0.547, 0.309, 0.592, 0.313, 0.617, 0.303, 0.633, 0.284, 0.642, 0.255, 0.643, 0.107, 0.768, 0.107, 0.767, 0.251, 0.749, 0.333, 0.73, 0.366, 0.705, 0.393, 0.657, 0.421, 0.596, 0.434, 0.508, 0.427, 0.455, 0.404, 0.415, 0.366, 0.397, 0.333, 0.384, 0.295],
  [0.848, -0.422, 1.21, -0.422, 1.21, -0.302, 0.981, -0.302, 0.981, -0.079, 1.163, -0.079, 1.163, 0.042, 0.981, 0.042, 0.981, 0.302, 1.21, 0.302, 1.21, 0.422, 0.848, 0.422],
];

const facePolice: FaceMark = (ctx) => {
  ctx.beginPath();
  for (const c of POLICE_OUTLINES) {
    ctx.moveTo(c[0]!, c[1]!);
    for (let i = 2; i < c.length; i += 2) ctx.lineTo(c[i]!, c[i + 1]!);
    ctx.closePath();
  }
  ctx.fill('evenodd');
};

/** Every face, so a centering pass can weigh one on its own. */
export const FACE_MARKS: Record<string, FaceMark> = {
  police: facePolice, flames: faceFlames,
};

/** Where each face's own ink sits against the disc's center, measured off
 *  `FACE_MARKS` at 400px per unit. Subtracted so the print is centered on the
 *  sticker, not on the part of it the fold left showing. */
/** Where each face's own drawn box sits against the disc's center, measured
 *  at 250px per unit and subtracted.
 *
 *  The box, not the area centroid, and never the ink left showing after the
 *  fold: a mark reads centered when its extent is centered, so compensating
 *  for what the flap covers shoves it visibly off -- POLICE ended up a fifth
 *  of a unit right of where it belonged. A traced face is already centered by
 *  the trace, which is why most of these are zero; what needs correcting is
 *  type, where the baseline is not the cap-height center. */
const FACE_NUDGE: Record<string, [number, number]> = {
  police: [0, 0],
  flames: [-0.004, -0.002],
};

const sticker = (name?: string): Mark => (ctx, field, accent) => {
  const face = name ? FACE_MARKS[name] : undefined;
  if (face) {
    const [dx, dy] = FACE_NUDGE[name!] ?? [0, 0];
    ctx.save();
    ctx.translate(-dx, -dy);
    face(ctx);
    ctx.restore();
  }
  peel(ctx, field, accent, PEEL_FROM, PEEL_ARC, PEEL_LIFT);
};


export const drawStickerPolice: Mark = sticker('police');
export const drawStickerFlames: Mark = sticker('flames');

export const MARKS: Record<string, Mark> = {
  star: drawStar, archive: drawArchive, redo: drawRedo, bolt: drawBolt,
  magnet: drawMagnet, brush: drawBrush, minifig: drawMinifig,
  technic: drawTechnic, composite: drawComposite, duplo: drawDuplo,
  stickerPolice: drawStickerPolice, stickerFlames: drawStickerFlames,
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

