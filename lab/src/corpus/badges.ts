/** Badges, as the wall's canvas draws them.
 *
 *  The artwork itself is `markShapes`, which the DOM renders from the same
 *  path data; this module is the canvas half and nothing more. A mark draws
 *  in a unit box centered on the origin -- `drawBadge` translates to the
 *  disc's center and scales -- so it is centered against its field by
 *  construction rather than by hand-tuned offsets.
 */
import { MARK_SHAPES, punches, type MarkShape,
  type Paint } from '@lab/corpus/markShapes';
import type { CellBadge } from '@lab/corpus/paint';

// Lighter than the caption it sits beside would suggest: a badge letter is
// reversed out of a solid field, and reversed type gains weight optically --
// at 600 the Greek psi filled its disc.
/** The face for everything set on a thumbnail -- badge letters, the part
 *  number, the year range, the placeholder glyph. Condensed, so a part number
 *  fits a small cell without dropping to a size nobody can read. */
export const THUMB_FACE = "'Oswald', ui-sans-serif, system-ui, sans-serif";

/** Two weights, and they mean different things: an identifier is something
 *  you pick out of a grid, the rest is something you read once you have. */
export const WEIGHT_ID = 500;
export const WEIGHT_TEXT = 300;

/** Resolve once the thumbnail face is actually usable.
 *
 *  Canvas does not wait: `ctx.font` with a webfont that has not arrived
 *  silently falls back and paints, and the wall paints once -- so without
 *  this the whole grid renders in the fallback face and stays there until
 *  something else forces a repaint. Resolves either way; a missing font is a
 *  worse-looking wall, not a broken one. */
export function thumbFontReady(): Promise<void> {
  const fonts = (globalThis as { document?: Document }).document?.fonts;
  if (!fonts) return Promise.resolve();
  return Promise.all([
    fonts.load(`${WEIGHT_ID} 16px Oswald`),
    fonts.load(`${WEIGHT_TEXT} 16px Oswald`),
  ]).then(() => undefined, () => undefined);
}

export const BADGE_WEIGHT = WEIGHT_TEXT;
export const BADGE_FACE = THUMB_FACE;

/** Which color a piece of a mark takes. `none` is a piece that is only
 *  stroked; anything else is one of the badge's own inks, or a literal for
 *  the one material that is not the badge's. */
export function markInk(badge: CellBadge, paint: Paint | 'none'): string | null {
  if (paint === 'none') return null;
  if (paint === 'ink') return badge.ink;
  if (paint === 'field') return badge.field;
  if (paint === 'accent') return badge.accent ?? badge.field;
  return paint;
}

/** One `Path2D` per path string, kept. A wall paint draws thousands of badges
 *  off a fixed set of about thirty paths, and re-parsing each of them every
 *  time is work the frame does not have. */
const parsed = new Map<string, Path2D>();

function pathOf(d: string): Path2D {
  let path = parsed.get(d);
  if (!path) { path = new Path2D(d); parsed.set(d, path); }
  return path;
}

/** The ring a badge wears, in the same units as `radius`. Drawn inside the
 *  radius, so `strokeScale` changes the line and never the footprint. Shared
 *  with `BadgeSwatch`, which paints the same ring in CSS -- the two computed
 *  it separately, and the swatch kept the old width when the canvas thinned.
 */
export function ringWidth(radius: number, badge: CellBadge): number {
  return Math.max(1, radius * 0.16 * (badge.strokeScale ?? 1));
}

/** Fill and stroke one mark's pieces into a canvas.
 *
 *  The geometry is `markShapes`, shared with the DOM renderer, so nothing
 *  here decides what a mark looks like -- only how a canvas says it. */
function drawMark(ctx: CanvasRenderingContext2D, shapes: readonly MarkShape[],
                  badge: CellBadge) {
  for (const shape of shapes) {
    const path = pathOf(shape.d);
    ctx.save();
    if (shape.transform) ctx.transform(...shape.transform);
    if (shape.alpha != null) ctx.globalAlpha = shape.alpha;
    if (shape.punch) {
      ctx.globalCompositeOperation = 'destination-out';
      ctx.fillStyle = '#000000';
      ctx.fill(path);
    } else {
      const fill = markInk(badge, shape.fill ?? 'ink');
      if (fill) {
        ctx.fillStyle = fill;
        ctx.fill(path, shape.rule ?? 'nonzero');
      }
      const stroke = shape.stroke ? markInk(badge, shape.stroke) : null;
      if (stroke) {
        ctx.strokeStyle = stroke;
        ctx.lineWidth = shape.width ?? 0.1;
        ctx.lineJoin = shape.join ?? 'miter';
        ctx.lineCap = shape.cap ?? 'butt';
        ctx.stroke(path);
      }
    }
    ctx.restore();
  }
}

/** One scratch canvas, reused. A wall paint draws thousands of badges and a
 *  fresh canvas each time is the kind of allocation that shows up in a frame. */
let scratch: HTMLCanvasElement | null = null;

/** `size` is CSS pixels and `dpr` is the scale of the context the result gets
 *  stamped into. Allocating the scratch at CSS size and stamping it into a
 *  dpr-scaled context upsamples it, which is why the sticker badge -- the
 *  only one routed through here -- was the one that rendered soft. */
function scratchOf(size: number, dpr: number): CanvasRenderingContext2D | null {
  if (typeof document === 'undefined') return null;
  scratch ??= document.createElement('canvas');
  const need = Math.ceil(size * dpr);
  if (scratch.width < need || scratch.height < need) {
    scratch.width = scratch.height = need;
  }
  const sctx = scratch.getContext('2d');
  if (!sctx) return null;
  sctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  sctx.clearRect(0, 0, scratch.width / dpr, scratch.height / dpr);
  return sctx;
}

/** The scale the destination context is already carrying. Read off the
 *  context rather than off `window`, so a canvas scaled for something other
 *  than the display still stamps at its own resolution. */
function scaleOf(ctx: CanvasRenderingContext2D): number {
  const m = ctx.getTransform?.();
  return m && Number.isFinite(m.a) && m.a > 0 ? m.a : 1;
}

export interface BadgeAt {
  cx: number; cy: number; size: number; radius: number; baseline?: number;
  /** A word set beside the mark on the badge's OWN field, which stretches to
   *  a stadium to hold it. The wall never passes one -- a cell has no room
   *  for words -- but a detail view has, and reading the tag off the same
   *  badge the thumbnail wears beats printing it in a pill of its own. */
  label?: string;
}

/** How wide `drawBadge` will draw `badge` with `at.label` set. The text has
 *  to be measured before a canvas can be sized to hold it, so the caller
 *  measures with the same ctx it will draw on. */
export function badgeWidth(ctx: CanvasRenderingContext2D, badge: CellBadge,
                           at: BadgeAt): number {
  if (!at.label) return at.radius * 2;
  ctx.save();
  ctx.font = labelFont(badge, at.size);
  const w = ctx.measureText(at.label).width;
  ctx.restore();
  return at.radius + labelX(badge, at) - at.cx + w + LABEL_PAD * at.size;
}

const LABEL_GAP = 0.32;     // multiples of the type size, mark to word
const LABEL_PAD = 0.55;     // and word to the end of the field

/** Where the word starts. A badge with nothing in its disc -- a status like
 *  `open` carries neither a mark nor a letter -- gets the field's own padding
 *  instead of a mark's width of empty room before its first glyph. */
function labelX(badge: CellBadge, at: BadgeAt): number {
  const filled = badge.mark != null || badge.text != null;
  return filled ? at.cx + at.radius + LABEL_GAP * at.size
                : at.cx - at.radius + LABEL_PAD * at.size;
}

function labelFont(badge: CellBadge, size: number) {
  return `${badge.weight ?? BADGE_WEIGHT} ${size * 0.92}px ${BADGE_FACE}`;
}

export function drawBadge(ctx: CanvasRenderingContext2D, badge: CellBadge,
                          at: BadgeAt) {
  // A punching mark is composited off to the side and stamped back, so its
  // hole ends at the edge of its own field and shows what is behind the
  // badge rather than the field's own color.
  if (punches(badge.mark)) {
    const w = Math.ceil(badgeWidth(ctx, badge, at)) + 2;
    const h = Math.ceil(at.radius * 2) + 2;
    const dpr = scaleOf(ctx);
    const sctx = scratchOf(Math.max(w, h), dpr);
    if (sctx) {
      drawBadgeDirect(sctx, badge, { ...at, cx: at.radius + 1, cy: h / 2,
                                     baseline: undefined });
      ctx.drawImage(scratch!, 0, 0, w * dpr, h * dpr,
                    at.cx - at.radius - 1, at.cy - h / 2, w, h);
      return;
    }
  }
  drawBadgeDirect(ctx, badge, at);
}

function drawBadgeDirect(ctx: CanvasRenderingContext2D, badge: CellBadge,
                         at: BadgeAt) {
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
    // Before measuring, not after: `actualBoundingBoxAscent` is measured FROM
    // the current baseline, so a measurement taken under one baseline and
    // painted under another is off by the distance between them.
    ctx.textBaseline = 'alphabetic';
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
  const line = ringWidth(radius, badge);
  const r = radius - line / 2;
  ctx.beginPath();
  if (at.label) {
    // The same disc, stretched right to carry the word: one field, so the
    // mark and its name read as one badge rather than a badge and a caption.
    const end = cx + badgeWidth(ctx, badge, at) - radius * 2 + line / 2;
    ctx.arc(cx, cy, r, Math.PI / 2, -Math.PI / 2);
    ctx.arc(end, cy, r, -Math.PI / 2, Math.PI / 2);
    ctx.closePath();
  } else {
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
  }
  const labelled = at.label != null;
  const field = labelled ? badge.labelField ?? badge.field : badge.field;
  ctx.fillStyle = field;
  ctx.fill();
  ctx.lineWidth = line;
  ctx.strokeStyle = badge.stroke ?? badge.field;
  // The ring either edges the artwork or frames the whole field. On the disc
  // it is stroked after the disc's own fill, below.
  if (!badge.ringOnDisc) ctx.stroke();
  if (labelled && field !== badge.field) {
    // The disc keeps its own field under the artwork while the stadium
    // carries the name on another.
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fillStyle = badge.field;
    ctx.fill();
  }
  if (badge.ringOnDisc) {
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.fillStyle = badge.ink;
  const mark = badge.mark ? MARK_SHAPES[badge.mark] : undefined;
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
    drawMark(ctx, mark, badge);
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
  if (at.label) {
    ctx.font = labelFont(badge, size);
    ctx.fillStyle = badge.labelInk ?? badge.ink;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    // Off the ink box, not the em box: the field is a stadium and the word
    // has to sit on its axis whatever the label's own ascenders and
    // descenders come to. Measured under the baseline it is painted on --
    // `measureText` reports the ascent FROM the current baseline, and
    // measuring under `middle` set every label 0.2 of a badge too high.
    const m = ctx.measureText(at.label);
    const asc = m.actualBoundingBoxAscent;
    const desc = m.actualBoundingBoxDescent;
    const y = Number.isFinite(asc) && Number.isFinite(desc)
      ? cy + (asc - desc) / 2 : cy;
    ctx.fillText(at.label, labelX(badge, at), y);
  }
  ctx.restore();
}

