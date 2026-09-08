/** Every badge mark as path data, in the unit box a mark draws in.
 *
 *  One definition, two renderers: `badges.ts` fills these into a canvas for
 *  the wall, `BadgeMark.tsx` emits them as `<path>` for the DOM. A mark
 *  described as canvas calls could only ever be drawn by a canvas, which is
 *  what put a rasterizer behind the legend and the tag pills.
 *
 *  The box is centered on the origin and the field's edge sits at 1.515, so
 *  a mark may run past 1 and be clipped by its own disc.
 */
import { BRUSH, BRUSH_CUT, MAGNET, MAGNET_CUT, REDO,
  REDO_SPARK } from '@lab/corpus/markPaths';

/** Which of the badge's inks a piece takes. A literal color is for the one
 *  material that is not the badge's -- the brush's ferrule. */
export type Paint = 'ink' | 'field' | 'accent' | (string & {});

export interface MarkShape {
  /** SVG path data. Both renderers take it verbatim. */
  d: string;
  /** Omitted means `ink`; `none` is for a piece that is only stroked. */
  fill?: Paint | 'none';
  rule?: 'evenodd';
  stroke?: Paint;
  /** In mark units, the same as the path's own coordinates. */
  width?: number;
  join?: 'round' | 'miter';
  cap?: 'round' | 'butt';
  alpha?: number;
  /** Applied to this piece alone. Only where a stroke has to be transformed
   *  with its path -- a shear thickens the pen, and baking the shear into the
   *  endpoints would not. Everything else is baked. */
  transform?: readonly [number, number, number, number, number, number];
  /** Erases rather than paints: a hole through the badge to whatever is
   *  behind it. `destination-out` on a canvas, a mask in SVG. */
  punch?: true;
}

/** The radius of the badge's own field in mark units. A mark is scaled so
 *  that 1 unit is 0.66 of the disc's radius, which puts the edge here. */
export const FIELD_R = 1.515;

// ---------------------------------------------------------------- path text

const round = (n: number) => {
  const s = n.toFixed(4);
  return s.replace(/\.?0+$/, '') || '0';
};

const pt = (x: number, y: number) => `${round(x)} ${round(y)}`;

/** A closed polygon from flat x,y pairs. */
function poly(pts: readonly number[]): string {
  if (pts.length < 6) return '';
  let d = `M${pt(pts[0]!, pts[1]!)}`;
  for (let i = 2; i < pts.length; i += 2) d += `L${pt(pts[i]!, pts[i + 1]!)}`;
  return `${d}Z`;
}

/** Several closed polygons as one path. */
function polys(groups: readonly (readonly number[])[]): string {
  return groups.map(poly).join('');
}

/** An open polyline -- a path to stroke, not to fill. */
function line(pts: readonly number[]): string {
  if (pts.length < 4) return '';
  let d = `M${pt(pts[0]!, pts[1]!)}`;
  for (let i = 2; i < pts.length; i += 2) d += `L${pt(pts[i]!, pts[i + 1]!)}`;
  return d;
}

/** A full circle. Two half-arcs, because one `A` command whose ends coincide
 *  draws nothing. */
function circle(cx: number, cy: number, r: number): string {
  return `M${pt(cx - r, cy)}A${round(r)} ${round(r)} 0 1 1 ${pt(cx + r, cy)}`
       + `A${round(r)} ${round(r)} 0 1 1 ${pt(cx - r, cy)}Z`;
}

/** An open arc, angles as canvas takes them: y-down, increasing clockwise. */
function arc(cx: number, cy: number, r: number, a0: number, a1: number): string {
  const p = (a: number) => pt(cx + r * Math.cos(a), cy + r * Math.sin(a));
  const large = Math.abs(a1 - a0) > Math.PI ? 1 : 0;
  const sweep = a1 > a0 ? 1 : 0;
  return `M${p(a0)}A${round(r)} ${round(r)} 0 ${large} ${sweep} ${p(a1)}`;
}

/** An axis-aligned rectangle, given as corner and extent the way
 *  `ctx.fillRect` takes it. */
function rect(x: number, y: number, w: number, h: number): string {
  return poly([x, y, x + w, y, x + w, y + h, x, y + h]);
}

// ------------------------------------------------------------- baked frames

type Matrix = readonly [number, number, number, number, number, number];

/** Move a polygon's points through an affine, so the shape carries its own
 *  placement and neither renderer has to hold a transform stack. Rigid and
 *  uniform frames only -- a shear or a squash would have to stay a transform,
 *  because it changes what a stroke's pen draws. */
function through(m: Matrix, pts: readonly number[]): number[] {
  const [a, b, c, d, e, f] = m;
  const out: number[] = [];
  for (let i = 0; i < pts.length; i += 2) {
    const x = pts[i]!, y = pts[i + 1]!;
    out.push(a * x + c * y + e, b * x + d * y + f);
  }
  return out;
}

function rotation(theta: number, tx = 0, ty = 0): Matrix {
  const cos = Math.cos(theta), sin = Math.sin(theta);
  return [cos, sin, -sin, cos, tx, ty];
}

/** Clip a convex-or-not polygon to a half-plane, keeping the side the test
 *  accepts. Sutherland-Hodgman, one edge at a time: exact for polygons, which
 *  is what every clipped mark is. */
function clipHalf(pts: readonly number[], keep: (x: number, y: number) => number)
    : number[] {
  const n = pts.length / 2;
  if (n === 0) return [];
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const xi = pts[i * 2]!, yi = pts[i * 2 + 1]!;
    const xj = pts[j * 2]!, yj = pts[j * 2 + 1]!;
    const di = keep(xi, yi), dj = keep(xj, yj);
    if (di >= 0) out.push(xi, yi);
    if ((di >= 0) !== (dj >= 0)) {
      const t = di / (di - dj);
      out.push(xi + (xj - xi) * t, yi + (yj - yi) * t);
    }
  }
  return out;
}

/** Clip to a rectangle given as `ctx.rect` takes it. */
function clipRect(pts: readonly number[],
                  x: number, y: number, w: number, h: number): number[] {
  let p = clipHalf(pts, (px) => px - x);
  p = clipHalf(p, (px) => x + w - px);
  p = clipHalf(p, (_px, py) => py - y);
  p = clipHalf(p, (_px, py) => y + h - py);
  return p;
}

// ------------------------------------------------------------------- shapes

// A five-pointed star, point up, with its points and valleys rounded: the
// path is built small and then stroked back out to size with round joins,
// which is what takes the needle off each point.
function starPoints(): number[] {
  const outer = 0.78, inner = 0.34;
  const pts: number[] = [];
  for (let i = 0; i < 10; i++) {
    const reach = i % 2 === 0 ? outer : inner;
    const angle = -Math.PI / 2 + (i * Math.PI) / 5;
    pts.push(Math.cos(angle) * reach, Math.sin(angle) * reach);
  }
  return pts;
}

const star: MarkShape[] = [
  { d: poly(starPoints()), fill: 'ink', stroke: 'ink', width: 0.2,
    join: 'round', cap: 'round' },
];

// An archive box: a body under its lid band, with the handle slot punched out
// of its front. Retired now means put away rather than replaced -- `replaced`
// took the parts that had a successor. Kept well inside the unit box: a
// full-extent rectangle puts its corners at 1.41, almost the field's edge.
const archive: MarkShape[] = [
  { d: rect(-0.74, -0.67, 1.48, 0.32) + rect(-0.66, -0.21, 1.32, 0.88) },
  { d: line([-0.16, 0.04, 0.16, 0.04]), fill: 'none', stroke: 'field',
    width: 0.26, cap: 'round' },
];

// Redo: the arrow and the sparkle beside its tail, both from
// `scripts/redo.svg`. Computed instead it was an arc with a triangle glued
// on, and the head's aim never quite belonged to the curve.
const redo: MarkShape[] = [
  { d: poly(REDO) },
  { d: polys(REDO_SPARK), fill: 'accent' },
];

// A lightning bolt. A zigzag silhouette is the shape that survives the mark
// budget best -- a little over 4px at the badge floor -- and it wants some
// mass to survive it, so the strokes are wide.
const bolt: MarkShape[] = [
  { d: poly([0.52, -1, -0.72, 0.14, -0.06, 0.14, -0.42, 1, 0.74, -0.16,
             0.06, -0.16]),
    stroke: 'ink', width: 0.17, join: 'round' },
];

// A horseshoe magnet: a U with its poles in their own color, the silhouette
// clipped to the tips so they sit flush with the limbs' edges. Contracted
// inside them instead, they read as damage to the shape.
const magnet: MarkShape[] = [
  { d: poly(MAGNET) },
  { d: polys(MAGNET_CUT), fill: 'accent' },
];

// A brush: bristles whose width goes to nothing at the tip, a crimped ferrule
// under them broken off by a band of the field, and paint cut out of the tip
// so the field shows through. Printed parts are pad prints, so if this does
// not hold at the strip's floor the fallback is a halftone dot cluster.
//
// Cut flat along a horizontal line in the badge's frame rather than the
// brush's: the tip is pressed against the ground of a stroke, and the ground
// does not tilt with the brush.
const BRUSH_FRAME = rotation(-Math.PI * 2 / 3, 0, 0.18);
const brushed = (pts: readonly number[]) =>
  poly(clipRect(through(BRUSH_FRAME, pts), -1.8, -1.8, 3.6, 2.42));

// Kept, though nothing points at it: `printed` was drawn as a brush until the
// halftone took the badge, and a mark is cheap to hold and slow to redraw.
// The handle runs off the edge of the field rather than stopping inside it: a
// ferrule drawn whole is a stack of bands at the strip's floor, and the mark
// is clipped to the disc, so this reads as a brush held into frame. Narrow
// where it meets the head and widening as it runs out, the way a ferrule
// crimps onto a handle.
const brush: MarkShape[] = [
  { d: brushed([-0.15, 0.55, 0.15, 0.55, 0.34, 2.15, -0.34, 2.15]),
    fill: '#c9c9d0' },
  { d: brushed(BRUSH) },
  { d: BRUSH_CUT.map(brushed).join(''), fill: 'accent' },
];

// A minifig face: the disc is the head, so all the mark has to carry is the
// 1978 smiley. Measured off a face-on photograph of `3626` and expressed
// against the head's width -- the proportions are the recognizable part, and
// the disc is 3.03 mark units across. Drawing the head's own silhouette
// instead gave a shape that stopped reading below about 20px.
const EYE_DROP = 0.185;   // the face group, centered in a disc that has no stud
const minifig: MarkShape[] = [
  { d: circle(-0.433, -0.064 - EYE_DROP, 0.215)
     + circle(0.433, -0.064 - EYE_DROP, 0.215) },
  // The ends land about mid-pupil, which is where the print puts them.
  { d: arc(0, 0.15 - EYE_DROP, 0.626, Math.PI * 0.245, Math.PI * 0.755),
    fill: 'none', stroke: 'ink', width: 0.175, cap: 'round' },
];

// Technic's T, drawn rather than set: a font's italic T carries a short
// crossbar and its slant walks the glyph off the disc's center. The shear is
// about the vertical middle, so the letter stays centered as it leans.
const technic: MarkShape[] = [
  { d: line([-0.82, -0.6, 0.58, -0.6]) + line([-0.1, -0.6, -0.1, 0.7]),
    fill: 'none', stroke: 'ink', width: 0.29, cap: 'round',
    transform: [1, 0, -0.15, 1, 0.07, 0] },
];

// ------------------------------------------------------------- the printing

/** A halftone screen filling the whole field: dots on a square lattice turned
 *  to the 45 degrees a single-color screen is always shot at, clipped by the
 *  badge's own disc. The field IS the printing, rather than carrying a picture
 *  of a tool that does it.
 *
 *  `radiusAt` is given the dot's center, so a caller can ramp the dot across
 *  the field the way a real screen renders a tone. Dots that fall entirely
 *  outside the disc are dropped rather than drawn and clipped -- at the wall's
 *  floor the whole mark is about seven dots across, and every one that is
 *  really there costs a fill.
 */
function halftone(pitch: number,
                  radiusAt: (x: number, y: number) => number): string {
  const c = Math.SQRT1_2 * pitch;        // the 45-degree lattice's two vectors
  const reach = FIELD_R + pitch;
  const n = Math.ceil(reach / c) + 1;
  let d = '';
  for (let i = -n; i <= n; i++) {
    for (let j = -n; j <= n; j++) {
      const x = (i - j) * c, y = (i + j) * c;
      const r = radiusAt(x, y);
      if (r <= 0 || Math.hypot(x, y) - r > FIELD_R) continue;
      d += circle(x, y, r);
    }
  }
  return d;
}

/** Dots the same size everywhere. A decorated part is a flat tint -- printing
 *  over the whole face -- so the screen renders no tone and needs no ramp.
 *
 *  Coarse on purpose: the wall draws this from 9px up, and at a finer pitch
 *  the dots stop resolving and the badge is a gray disc a reader has to tell
 *  apart from `retired` by its color alone. These hold as dots to about 14.
 */
const printed: MarkShape[] = [{ d: halftone(0.86, () => 0.30) }];

// Composite: two L-trominoes interlocked into a 2x3 block -- the smallest
// rectangle two identical pieces can tile, and it says assembled-from-parts
// rather than merely stacked. Drawn at the size that overruns the field on
// both axes, so the disc is a hole cut through the join rather than a frame
// around a picture of one: the same move the minifig badge makes, where the
// disc is the head. What survives the clip is the step where the two pieces
// take hold of each other, which is the part that carries the meaning -- an
// L drawn whole is a diagram, and at the strip's floor it is a smudge.
// The seam is cut in the field so neither piece needs an outline.
const COMPOSITE_FILL = 2.6;   // the short axis (1.2) has to clear 2*FIELD_R
const COMPOSITE_FRAME: Matrix = [0, -COMPOSITE_FILL, COMPOSITE_FILL, 0, 0, 0];
const composite: MarkShape[] = [
  { d: poly(through(COMPOSITE_FRAME,
      [-0.6, -0.9, 0.6, -0.9, 0.6, -0.3, 0, -0.3, 0, 0.3, -0.6, 0.3])) },
  { d: poly(through(COMPOSITE_FRAME,
      [0, -0.3, 0.6, -0.3, 0.6, 0.9, -0.6, 0.9, -0.6, 0.3, 0, 0.3])),
    fill: 'accent' },
  { d: line(through(COMPOSITE_FRAME, [0.6, -0.3, 0, -0.3, 0, 0.3, -0.6, 0.3])),
    fill: 'none', stroke: 'field', width: 0.30, join: 'miter' },
];

// Duplo's d, in the weight its logotype uses: a heavy rounded geometric with a
// counter small against the stroke. The bowl is cut thicker than the stem -- a
// curved stroke of the same width reads lighter than a straight one -- and the
// stem's right edge sits on the bowl's, or the two pile up into a lump heavier
// than the side opposite it. The stem stops at the bowl's widest point rather
// than running to its foot: past that the bowl curves away from it, and the
// stem's corner hangs outside the letter as a serif the logotype does not have.
const DX = 0.22, DY = -0.02;
const duplo: MarkShape[] = [
  { d: circle(-0.3 + DX, 0.28 + DY, 0.7) },
  { d: line([0.18 + DX, -0.72 + DY, 0.18 + DX, 0.28 + DY]), fill: 'none',
    stroke: 'ink', width: 0.44, cap: 'round' },
  { d: circle(-0.3 + DX, 0.28 + DY, 0.22), fill: 'field' },
];

// ------------------------------------------------------------- the stickers

// The field is the sticker, and its lower right is peeling off -- the same
// move the minifig badge makes, where the disc is the head rather than a
// picture of one. A mark is clipped to its own disc and the field's edge sits
// at FIELD_R, so the peel is built against that radius: the sticker is only
// the part of the disc the flap has not lifted, and behind it there is a hole
// rather than any ink.

// The tab: how much of the edge lifts, and how far the flap stands off the
// fold. `lift` 1 lays it flat back down on the sticker.
const PEEL_FROM = Math.PI * 0.02;
const PEEL_ARC = Math.PI * 0.62;
const PEEL_LIFT = 0.72;

/** One peel, at `arc` radians of the field's edge, folding `lift` of the way
 *  back toward it. Larger reads at small sizes; smaller keeps more sticker. */
function peel(from: number, span: number, lift: number): MarkShape[] {
  const to = from + span;
  const p = (a: number): [number, number] =>
    [Math.cos(a) * FIELD_R, Math.sin(a) * FIELD_R];
  const [x0, y0] = p(from);
  const [x1, y1] = p(to);

  // The flap is the lifted cap folded over the chord, so it is that cap
  // reflected in the chord line -- not a curve drawn to look like one. `lift`
  // foreshortens it toward the fold, which is what a corner standing up off
  // the page does; at 1 it lies flat back on the sticker.
  const dx = x1 - x0, dy = y1 - y0;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len, uy = dy / len;
  const STEPS = 24;
  const flap: number[] = [x0, y0];
  for (let i = 0; i <= STEPS; i++) {
    const [qx, qy] = p(from + (span * i) / STEPS);
    const vx = qx - x0, vy = qy - y0;
    const t = vx * ux + vy * uy;
    const rx = x0 + 2 * t * ux - vx, ry = y0 + 2 * t * uy - vy;
    // toward the chord by (1 - lift): the fold stays put, the free edge comes in
    const s = (rx - x0) * ux + (ry - y0) * uy;
    const mx = x0 + s * ux, my = y0 + s * uy;
    flap.push(mx + (rx - mx) * lift, my + (ry - my) * lift);
  }

  return [
    // What the sticker lifted off: nothing at all. The cap is erased rather
    // than inked, so the hole shows the cell instead of a white patch that
    // reads as another piece of sticker.
    { d: `M${pt(x0, y0)}A${round(FIELD_R)} ${round(FIELD_R)} 0 `
       + `${span > Math.PI ? 1 : 0} 1 ${pt(x1, y1)}Z`, punch: true },
    { d: poly(flap), fill: 'accent' },
    // The fold, kept faint: it is a crease, not an outline.
    { d: line([x0, y0, x1, y1]), fill: 'none', stroke: 'field', width: 0.05,
      cap: 'round' },
  ];
}

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

/** Where each face's own drawn box sits against the disc's center, measured
 *  at 250px per unit and subtracted.
 *
 *  The box, not the area centroid, and never the ink left showing after the
 *  fold: a mark reads centered when its extent is centered, so compensating
 *  for what the flap covers shoves it visibly off -- POLICE ended up a fifth
 *  of a unit right of where it belonged. A traced face is already centered by
 *  the trace, which is why most of these are zero; what needs correcting is
 *  type, where the baseline is not the cap-height center. */
const shifted = (groups: number[][], dx: number, dy: number) =>
  groups.map((g) => through([1, 0, 0, 1, -dx, -dy], g));

/** The print on the sticker's face. Centered on the disc, not on the flat
 *  part the fold leaves showing: the print was applied while the sticker was
 *  flat, so the fold covers whatever it covers -- which is what makes the
 *  corner read as lifted off the print rather than as a shape drawn beside
 *  it. The face is laid down before the peel, so the peel occludes it. */
const FACES: Record<string, MarkShape[]> = {
  police: [{ d: polys(POLICE_OUTLINES), rule: 'evenodd' }],
  flames: shifted(FLAMES, -0.004, -0.002).map((ring, n) => ({
    d: poly(ring), alpha: FLAME_ALPHA[n] ?? 1,
  })),
};

const sticker = (face: string): MarkShape[] =>
  [...FACES[face]!, ...peel(PEEL_FROM, PEEL_ARC, PEEL_LIFT)];

// ------------------------------------------------------------------ the set

export const MARK_SHAPES: Record<string, MarkShape[]> = {
  star, archive, redo, bolt, magnet, minifig, technic, composite, duplo,
  printed, brush,
  stickerPolice: sticker('police'), stickerFlames: sticker('flames'),
};

/** Marks that erase part of their own badge. They need a layer of their own:
 *  badges are painted straight onto the cell, over the render, so a
 *  `destination-out` on that context would cut through the drawing too. */
export function punches(mark: string | undefined): boolean {
  return !!mark && (MARK_SHAPES[mark]?.some((s) => s.punch) ?? false);
}
