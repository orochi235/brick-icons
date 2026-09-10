/** The wall's Canvas2D executor: a `PaintCommand` list drawn into a context.
 *
 *  Split from `Wall.tsx` so a second executor can be measured against it over
 *  the identical command list. `paint.ts` decides what to draw; this decides
 *  nothing, and the pair of them is the whole seam.
 */
import { BADGE_FACE, BADGE_WEIGHT, THUMB_FACE, WEIGHT_ID, WEIGHT_TEXT,
         drawBadge } from '@lab/corpus/badges';
import { badgeGeometry, CAPTION_INK_RISE, captionSize, cornerPad, LINKED_BADGE,
  RETIRED_WASH, stripGeometry, type CellBadge, type CellCaption,
  type PaintCommand } from '@lab/corpus/paint';
import type { Palette } from '@lab/corpus/palette';

// An undrawn cell only: a drawn one carries its state in the ground instead,
// where a ring reads as nothing at the zooms most cells are seen at. A stroke
// straddles its path, so inset by half the width -- otherwise it overshoots
// the cell and eats into its neighbors.
export function strokeBorder(ctx: CanvasRenderingContext2D,
                      cmd: { dx: number; dy: number; dw: number; dh: number;
                             border: string | null; borderWidth: number;
                             slash?: boolean }) {
  if (!cmd.border || cmd.borderWidth <= 0) return;
  const inset = cmd.borderWidth / 2;
  ctx.save();
  ctx.strokeStyle = cmd.border;
  ctx.lineWidth = cmd.borderWidth;
  ctx.strokeRect(cmd.dx + inset, cmd.dy + inset,
                 cmd.dw - cmd.borderWidth, cmd.dh - cmd.borderWidth);
  ctx.restore();
  if (cmd.slash) strokeSlash(ctx, cmd);
}

// Split from the border so the hybrid renderer can draw it alone: weasel maps
// the border rect and has no diagonal, and re-stroking the rect over the one
// it already drew hardens that edge.
export function strokeSlash(ctx: CanvasRenderingContext2D,
                            cmd: { dx: number; dy: number; dw: number; dh: number;
                                   border: string | null; borderWidth: number }) {
  if (!cmd.border || cmd.borderWidth <= 0) return;
  const inset = cmd.borderWidth / 2;
  ctx.save();
  ctx.strokeStyle = cmd.border;
  ctx.lineWidth = cmd.borderWidth;
  ctx.beginPath();
  ctx.moveTo(cmd.dx + inset, cmd.dy + inset);
  ctx.lineTo(cmd.dx + cmd.dw - inset, cmd.dy + cmd.dh - inset);
  ctx.stroke();
  ctx.restore();
}

// Dashed and drawn outside the cell, so it never collides with the inset
// defect ring when a cell carries both.
export function strokeCaret(ctx: CanvasRenderingContext2D,
                     cmd: { dx: number; dy: number; dw: number; dh: number },
                     palette: Palette) {
  ctx.save();
  ctx.strokeStyle = palette.caret;
  ctx.lineWidth = 2;
  ctx.setLineDash([4, 2]);
  ctx.strokeRect(cmd.dx - 1, cmd.dy - 1, cmd.dw + 2, cmd.dh + 2);
  ctx.restore();
}

// A sheet with its corner turned up: the sticker every catalog draws. Stroked
// rather than filled, so it reads as a mark on the field instead of a blob.
export function drawSticker(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  const fold = r * 0.62;
  const x0 = cx - r, y0 = cy - r, x1 = cx + r, y1 = cy + r;
  ctx.save();
  ctx.lineWidth = Math.max(1, r * 0.16);
  ctx.lineJoin = 'round';
  ctx.strokeStyle = ctx.fillStyle;
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y0);
  ctx.lineTo(x1, y1 - fold);
  ctx.lineTo(x1 - fold, y1);
  ctx.lineTo(x0, y1);
  ctx.closePath();
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x1, y1 - fold);
  ctx.lineTo(x1 - fold, y1 - fold);
  ctx.lineTo(x1 - fold, y1);
  ctx.stroke();
  ctx.restore();
}

// A filled disc in one corner, on the letterbox margin rather than the
// drawing, which is centered. Reversed out so it reads over ink and over the
// white ground alike.
/** Where a corner badge's disc sits. Shared with the hit test, so a click
 *  cannot land somewhere the disc is not drawn. */
export function cornerBadgeAt(badge: CellBadge,
                              cmd: { dx: number; dy: number; dw: number; dh: number }) {
  const { size, radius, inset, rise, fall } = badgeGeometry(cmd.dw);
  const right = badge.corner === 'br' || badge.corner === 'tr';
  const bottom = badge.corner === 'br';
  return {
    cx: right ? cmd.dx + cmd.dw - inset : cmd.dx + inset,
    cy: bottom ? cmd.dy + cmd.dh - fall : cmd.dy + rise,
    size, radius,
  };
}

/** The kind badges, running right along the bottom edge from wherever the
 *  part number ended. Stops short of the bottom-right corner rather than
 *  drawing under the badge that lives there. */
/** Half a capital's height in the current font, measured rather than
 *  assumed: it is what turns the caption's `middle` position into the
 *  baseline the badges have to sit on. */
function capHalf(ctx: CanvasRenderingContext2D, size: number): number {
  const ascent = ctx.measureText('H').actualBoundingBoxAscent;
  return Number.isFinite(ascent) && ascent > 0 ? ascent / 2 : size * 0.35;
}

function drawStrip(ctx: CanvasRenderingContext2D, strip: CellBadge[],
                   cmd: { dx: number; dy: number; dw: number; dh: number },
                   startX: number) {
  if (strip.length === 0) return;
  const { size, radius } = stripGeometry(cmd.dw);
  const gap = radius * 0.5;
  // Stop at the corner badge's left edge, not a badge-width short of it:
  // `inset` is already that badge's center, so subtracting a strip diameter
  // on top of it cost the strip about two badges' room.
  const corner = badgeGeometry(cmd.dw);
  const limit = cmd.dx + cmd.dw - corner.inset - corner.radius - gap;
  ctx.save();
  ctx.font = `${BADGE_WEIGHT} ${size}px ${BADGE_FACE}`;
  const half = capHalf(ctx, size);
  ctx.restore();
  // The part number's baseline, derived from where drawCaption centers it.
  const baseline = cmd.dy + cmd.dh - cornerPad(cmd.dw, size) - size * 0.5 + half;
  const cy = baseline - half - size * CAPTION_INK_RISE;
  let cx = startX + radius;
  for (const badge of strip) {
    if (cx + radius > limit) return;
    drawBadge(ctx, badge, { cx, cy, size, radius, baseline });
    cx += radius * 2 + gap;
  }
}

// A caption in one of the corners the badges leave free, set straight onto
// the cell: the drawing is centered and letterboxed, so its corners are empty.
function drawCaption(ctx: CanvasRenderingContext2D, caption: CellCaption,
                     cmd: { dx: number; dy: number; dw: number; dh: number },
                     rightPad = 0): number {
  const size = captionSize(cmd.dw);
  const right = caption.corner === 'tr';
  const top = caption.corner[0] === 't';
  ctx.save();
  ctx.font = `${caption.weight ?? WEIGHT_TEXT} ${size}px ${THUMB_FACE}`;
  ctx.textAlign = right ? 'right' : 'left';
  ctx.textBaseline = 'middle';
  const pad = cornerPad(cmd.dw, size);
  ctx.fillStyle = caption.ink;
  const x = right ? cmd.dx + cmd.dw - pad - rightPad : cmd.dx + pad;
  ctx.fillText(caption.text, x,
               top ? cmd.dy + pad + size * 0.5 : cmd.dy + cmd.dh - pad - size * 0.5);
  const width = ctx.measureText(caption.text).width;
  ctx.restore();
  return right ? x - width : x + width;
}

/** How much of its cell a round cell fills across, and how tall its letter
 *  stands when there is room for one. */
export const CIRCLE_SCALE = 0.6;
export const GLYPH_SCALE = 0.62;

// Flattens a retired cell toward the wash color: white goes gray, ink goes
// gray, and the whole thumbnail drops in contrast without a second bake.
function washCell(ctx: CanvasRenderingContext2D, wash: number,
                  cmd: { dx: number; dy: number; dw: number; dh: number }) {
  ctx.save();
  ctx.globalAlpha = (ctx.globalAlpha || 1) * wash;
  ctx.fillStyle = RETIRED_WASH;
  ctx.fillRect(cmd.dx, cmd.dy, cmd.dw, cmd.dh);
  ctx.restore();
}

/** The captions, corner discs and kind strip a cell wears, drawn or not. The
 *  strip starts where the part number ended, so it runs after the captions. */
export function drawOverlays(ctx: CanvasRenderingContext2D,
                      cmd: { captions?: CellCaption[]; badges?: CellBadge[];
                             strip?: CellBadge[] },
                      box: { dx: number; dy: number; dw: number; dh: number }) {
  const { size, radius } = stripGeometry(box.dw);
  let stripX = box.dx + cornerPad(box.dw, size);
  // The top-right discs are drawn at the corner, so the year has to set to
  // their left or the two overlap. Measured off the same geometry the discs
  // are placed with, never a guess at how many there are.
  const topRight = (cmd.badges ?? []).filter((b) => b.corner === 'tr').length;
  const trPad = topRight === 0 ? 0
    : topRight * badgeGeometry(box.dw).radius * 2 + radius * 0.6;
  for (const caption of cmd.captions ?? []) {
    const end = drawCaption(ctx, caption, box, caption.corner === 'tr' ? trPad : 0);
    if (caption.corner === 'bl') stripX = end + radius * 0.6;
  }
  for (const badge of cmd.badges ?? []) drawBadge(ctx, badge, cornerBadgeAt(badge, box));
  drawStrip(ctx, cmd.strip ?? [], box, stripX);
}

/** One paint command, drawn into `ctx` and shifted by `offset` -- the loupe
 *  reuses this to redraw the same commands into its own small canvas,
 *  recentred on the aimed point rather than at their outer screen position. */
export function drawPaintCommand(ctx: CanvasRenderingContext2D, cmd: PaintCommand,
                          sheet: HTMLImageElement | null, palette: Palette,
                          offset: { x: number; y: number } = { x: 0, y: 0 }) {
  const dx = cmd.dx + offset.x;
  const dy = cmd.dy + offset.y;
  if (cmd.kind === 'sprite' && sheet) {
    ctx.save();
    ctx.globalAlpha = cmd.alpha ?? 1;
    ctx.fillStyle = cmd.ground;
    ctx.fillRect(dx, dy, cmd.dw, cmd.dh);
    ctx.drawImage(sheet, cmd.sx, cmd.sy, cmd.sw, cmd.sh, dx, dy, cmd.dw, cmd.dh);
    if (cmd.wash) washCell(ctx, cmd.wash, { ...cmd, dx, dy });
    // After the border, not before: the badge sits in the corner the frame
    // runs through, and it is the badge that has to stay readable.
    drawOverlays(ctx, cmd, { ...cmd, dx, dy });
    ctx.restore();
    if (cmd.caret) strokeCaret(ctx, { ...cmd, dx, dy }, palette);
  } else if (cmd.kind === 'image') {
    ctx.save();
    ctx.globalAlpha = cmd.alpha ?? 1;
    // Under the same alpha as the image, so a dimmed cell fades whole. Every
    // rung is ink on transparency, so this is what a cell's state colors.
    ctx.fillStyle = cmd.ground;
    ctx.fillRect(dx, dy, cmd.dw, cmd.dh);
    ctx.drawImage(cmd.image, dx, dy, cmd.dw, cmd.dh);
    if (cmd.wash) washCell(ctx, cmd.wash, { ...cmd, dx, dy });
    // After the border, not before: the badge sits in the corner the frame
    // runs through, and it is the badge that has to stay readable.
    drawOverlays(ctx, cmd, { ...cmd, dx, dy });
    ctx.restore();
    if (cmd.caret) strokeCaret(ctx, { ...cmd, dx, dy }, palette);
  } else if (cmd.kind === 'fill') {
    ctx.fillStyle = cmd.fill;
    if (cmd.mark === 'sticker') {
      drawSticker(ctx, dx + cmd.dw / 2, dy + cmd.dh / 2, cmd.dw * CIRCLE_SCALE / 2);
    } else if (cmd.glyph) {
      // The category's initial, sized to the cell: a block of S says sticker
      // at a glance, and no filled square competes with the drawings around it.
      ctx.save();
      ctx.font = `${WEIGHT_ID} ${cmd.dh * GLYPH_SCALE}px ${THUMB_FACE}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(cmd.glyph, dx + cmd.dw / 2, dy + cmd.dh / 2 + cmd.dh * 0.03);
      ctx.restore();
    } else if (cmd.shape === 'circle') {
      // Well inside the cell: an out-of-scope part is not competing for
      // attention with the ones the project is actually drawing.
      ctx.beginPath();
      ctx.ellipse(dx + cmd.dw / 2, dy + cmd.dh / 2,
                  cmd.dw * CIRCLE_SCALE / 2, cmd.dh * CIRCLE_SCALE / 2, 0, 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.fillRect(dx, dy, cmd.dw, cmd.dh);
    }
    strokeBorder(ctx, { ...cmd, dx, dy });
    // Over the fill and under the overlays, the way a drawn cell takes it: an
    // undrawn cell is just as much the slot the wall has moved off.
    if (cmd.wash) washCell(ctx, cmd.wash, { ...cmd, dx, dy });
    drawOverlays(ctx, cmd, { ...cmd, dx, dy });
    if (cmd.caret) strokeCaret(ctx, { ...cmd, dx, dy }, palette);
  } else if (cmd.kind === 'label') {
    ctx.save();
    ctx.fillStyle = cmd.depth === 0 ? palette.label.fill : palette.sublabel.fill;
    ctx.font = `${cmd.depth === 0 ? 700 : 600} ${cmd.size}px ui-sans-serif, system-ui, sans-serif`;
    ctx.textBaseline = 'alphabetic';
    ctx.fillText(cmd.depth === 0 ? `${cmd.text}  ${cmd.count.toLocaleString()}`
                                 : cmd.text, dx, dy);
    ctx.restore();
  }
}
