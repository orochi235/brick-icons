import { worldToScreen, viewToTransform, type View } from '@weasel-js/core';
import type { Band, Rect } from '@lab/corpus/layout';
import { CELL_STATES, type CellState, type CellStyle, type Palette } from '@lab/corpus/palette';
import { DEFAULT_PARAMS } from '@lab/corpus/params';
import { isStale, sourceBox } from '@lab/corpus/sheet';
import { tintFor, type TintMode } from '@lab/corpus/tint';
import type { Cell, SheetManifest } from '@lab/corpus/types';
import { yearRange } from '@lab/corpus/years';

export type { CellStyle } from '@lab/corpus/palette';

/** What a cell's color says about it: out of scope first, then
 *  worst-here-first and worst-elsewhere.
 *  The single precedence table -- `fillFor`, the legend and `PartCard` all
 *  read a cell's state through this, so they cannot drift apart. */
export function cellState(cell: Cell): CellState {
  // Ahead of every problem state: a part the project is not drawing yet has
  // not failed at anything, and a wall of red stickers would say it had.
  if (cell.out_of_scope) return 'outOfScope';
  if (cell.open_defects > 0) return 'defect';
  if (cell.error === 'TimeoutError') return 'timeout';
  if (cell.error) return 'failed';
  // Below every live fault and above anything happening in another slot: it
  // is this slot's problem, and it is settled.
  if (cell.accepted_defects > 0) return 'accepted';
  if (cell.open_defects_elsewhere > 0) return 'defectElsewhere';
  if (cell.error_elsewhere) return 'problemElsewhere';
  return 'unknown';
}

export function fillFor(cell: Cell, palette: Palette): CellStyle {
  return palette[cellState(cell)];
}

/** How many cells are in each state -- a pure count over cells already in
 *  hand, so the legend can show a summary of the corpus without a request. */
export function tally(cells: Cell[]): Record<CellState, number> {
  const out = Object.fromEntries(CELL_STATES.map((s) => [s, 0])) as Record<CellState, number>;
  for (const cell of cells) out[cellState(cell)] += 1;
  return out;
}

// A fixed pixel width vanishes when the wall is zoomed out, which is the case
// that matters most -- so the border scales with the drawn cell, capped
// before it turns a large cell into a picture frame. Defaults come from the
// params panel's schema; `Appearance` below is how a live tuning session
// overrides them without every other caller having to know the knob exists.
export interface Appearance {
  thickBorderFactor: number;
  thinBorderFactor: number;
  maxBorderPx: number;
  dimAlpha: number;
  retiredWash: number;
}

// A label narrower than its own text is ink, not a word.
const MIN_LABEL_PX = 40;
const OUTER_LABEL_PX = 18;
const INNER_LABEL_PX = 11;

const DEFAULT_APPEARANCE: Appearance = {
  thickBorderFactor: DEFAULT_PARAMS.thickBorderFactor,
  thinBorderFactor: DEFAULT_PARAMS.thinBorderFactor,
  maxBorderPx: DEFAULT_PARAMS.maxBorderPx,
  dimAlpha: DEFAULT_PARAMS.dimAlpha,
  retiredWash: DEFAULT_PARAMS.retiredWash,
};

function borderWidthFor(weight: CellStyle['weight'], cellPx: number,
                        appearance: Appearance): number {
  if (!weight) return 0;
  const factor = weight === 'thick' ? appearance.thickBorderFactor : appearance.thinBorderFactor;
  return Math.min(appearance.maxBorderPx, Math.max(1, cellPx * factor));
}

/** The ground every baked thumbnail sits on -- `thumbs._square` in
 *  `brick_icons/thumbs.py` fills the whole cell with it, because a render is
 *  ink on transparency. A cell drawn from the vector rung has to be given the
 *  same ground, or zooming past the loose PNG swaps the surround to the
 *  wall's dark canvas. */
export const THUMB_GROUND = '#ffffff';

/** What a retired cell is washed with, over the drawing rather than under it:
 *  every rung draws the same white bake, and the viewer decides how faded a
 *  retired part looks. Baking a second ground meant a full rebake to change
 *  the shade, and a part retiring later kept the wrong one until someone
 *  noticed. */
export const RETIRED_WASH = '#d8d8d8';

/** Below this a cell's category initial is a smudge, and the mark falls back
 *  to a plain dot. */
export const GLYPH_MIN_PX = 22;

/** Categories drawn as a picture rather than a letter, where there is an
 *  obvious one. */
export const CATEGORY_MARKS: Record<string, 'sticker'> = { sticker: 'sticker' };

/** A category without its LDraw sigil, lowercased -- mirrors
 *  `tags.normalize_category`. */
export function plainCategory(cell: Cell): string {
  return (cell.category ?? '').replace(/^[~=_|]+/, '').trim().toLowerCase();
}

/** What an out-of-scope cell wears: a picture where its category has one, its
 *  initial otherwise, so a block of them says which category it is. */
export function glyphFor(cell: Cell, cellPx: number,
                         minPx = GLYPH_MIN_PX): string | undefined {
  if (cellPx < minPx || CATEGORY_MARKS[plainCategory(cell)]) return undefined;
  const plain = (cell.category ?? '').replace(/^[~=_|]+/, '').trim();
  return plain ? plain[0]!.toUpperCase() : undefined;
}

/** No size gate, unlike a letter: three strokes still read as a sticker at
 *  the width where an S is a smudge, and a recognizable shape beats the dot
 *  at every zoom. */
export function markFor(cell: Cell): 'sticker' | undefined {
  return CATEGORY_MARKS[plainCategory(cell)];
}

/** Below this drawn size a cell has no room for a badge without covering the
 *  drawing it is about; the year needs more room still, being words. */
export const BADGE_MIN_PX = 56;
export const LABEL_MIN_PX = 110;

/** A picture rather than a letter, where a letter would need explaining. */
export type BadgeMark = 'star' | 'archive' | 'redo' | 'bolt' | 'magnet'
                      | 'brush' | 'minifig' | 'technic' | 'composite' | 'duplo';

export interface CellBadge {
  /** The tag that drew it. The strip is hit-tested by tag, so a click knows
   *  which badge it landed on without matching on appearance. */
  tag: string;
  /** A letter, or a shape where a letter would need explaining. */
  text?: string;
  mark?: BadgeMark;
  corner?: 'tl' | 'br';
  field: string;
  ink: string;
  /** Only where the field would vanish: duplo is red on white and
   *  `THUMB_GROUND` is white. */
  stroke?: string;
  /** A second ink, for the one part of a mark that is not the mark's own
   *  material -- the paint on the brush. */
  accent?: string;
  /** A face other than the badge default, for a glyph the default sets
   *  badly. */
  font?: string;
  weight?: number;
  /** Slanted, where the system's own lettering is. */
  style?: string;
  /** A multiple of the mark or type size, for a shape that sets large or
   *  small against the rest of the set. */
  scale?: number;
  /** Optical centering, in multiples of the type size: a glyph's measured
   *  ink box is not always where it looks centered. */
  dx?: number;
  dy?: number;
}

/** The two discs that keep a corner of their own. `retired` and `updated`
 *  share the bottom-right slot and never both apply -- a part that stopped
 *  and a part that was replaced are different things wearing one badge
 *  today. */
export const CORNER_BADGES: Record<string, CellBadge> = {
  popular: { tag: 'popular', mark: 'star', corner: 'tl', field: '#daa520', ink: '#ffffff' },
  retired: { tag: 'retired', mark: 'archive', corner: 'br', field: '#6b6b72', ink: '#ffffff' },
  updated: { tag: 'updated', mark: 'redo', corner: 'br', field: '#2f7d4f', ink: '#ffffff' },
};

/** The system letters are set in a wide rounded sans rather than the wall's
 *  monospace, which is too condensed for a single letter standing alone on a
 *  disc, and reads nothing like the systems' own lettering. */
/** The psi is a physics symbol, so it is set the way a textbook sets one --
 *  a plain text serif, not a display face. */
export const WEIRD_FACE = '"STIX Two Text", "Times New Roman", Times, serif';

export const SYSTEM_FACE =
  '"SF Pro Rounded", "Avenir Next", Futura, "Trebuchet MS", sans-serif';

/** One field for the whole property family, so a run of them reads as a
 *  group against the system badges' own liveries. */
export const PROPERTY_FIELD = '#4a4a4f';

/** The strip that runs right from the part number. System badges first --
 *  a part has one category, so at most one of those shows -- then the
 *  properties, which stack. Tag order, which `tags.TAGS` already sets. */
export const STRIP_BADGES: Record<string, CellBadge> = {
  // The bright yellow a bare minifig head is moulded in, not LDraw's own
  // Yellow (#f2cd37), which reads golden against the rest of the strip.
  minifig: { tag: 'minifig', mark: 'minifig', field: '#ffd500', ink: '#1a1a1a' },
  technic: { tag: 'technic', mark: 'technic', field: '#1b2a5e', ink: '#ffffff' },
  duplo: { tag: 'duplo', mark: 'duplo', field: '#ffffff', ink: '#c8102e',
           stroke: '#c8102e' },
  weird: { tag: 'weird', text: '\u03a8', field: '#5b3a86', ink: '#ffffff',
           font: WEIRD_FACE, dy: 0.035 },
  // The one property badge off the shared field: a gold bolt on black is
  // what a live circuit looks like everywhere else, and it earns the break.
  electric: { tag: 'electric', mark: 'bolt', field: '#101014', ink: '#ffd60a',
              scale: 0.86 },
  magnet: { tag: 'magnet', mark: 'magnet', field: PROPERTY_FIELD, ink: '#ffffff',
            scale: 0.86 },
  printed: { tag: 'printed', mark: 'brush', field: PROPERTY_FIELD, ink: '#ffffff',
             accent: '#00ff00' },
  composite: { tag: 'composite', mark: 'composite', field: PROPERTY_FIELD,
               ink: '#ffffff', scale: 0.86 },
};

/** The badge that links somewhere when clicked. Only one does. */
export const LINKED_BADGE = 'updated';

export function isRetired(cell: Cell): boolean {
  return (cell.tags?.includes('retired') ?? false)
      || (cell.tags?.includes('updated') ?? false);
}

/** How big a badge is drawn on a cell of this width, and how far its center
 *  sits off the edge. One derivation: the wall draws badges from this and
 *  hit-tests them against it, so a click cannot land somewhere the disc
 *  isn't. */
export function badgeGeometry(cellPx: number) {
  const size = Math.max(9, Math.min(20, cellPx * 0.14));
  const radius = size * 0.72;
  return { size, radius, inset: radius + cornerPad(cellPx, size) };
}

/** The type size a caption is set at. */
export function captionSize(cellPx: number): number {
  return Math.max(10, Math.min(18, cellPx * 0.1));
}

/** The strip sits on the part number's line and is set to match it: a `T`
 *  reads as part of `4761 T`, not as a separate ornament beside it. Its
 *  inset stays the corner badges', so the row lines up with them. */
export function stripGeometry(cellPx: number) {
  const size = captionSize(cellPx);
  return { size, radius: size * 0.72, inset: badgeGeometry(cellPx).inset };
}

/** How far a corner mark sits off the cell's edge. A fraction of the cell
 *  rather than of the mark: both the badge and the caption stop scaling at
 *  their floor sizes, so at the small end of the zoom a margin measured off
 *  them crowds the corner. */
export function cornerPad(cellPx: number, size: number): number {
  return Math.max(size * 0.35, cellPx * 0.06);
}

/** The corner discs a drawn cell wears, if it is drawn big enough to hold
 *  them. */
export function badgesFor(cell: Cell, cellPx: number,
                          minPx = BADGE_MIN_PX): CellBadge[] {
  if (cellPx < minPx) return [];
  return (cell.tags ?? []).map((tag) => CORNER_BADGES[tag])
    .filter((b): b is CellBadge => !!b);
}

/** The strip of kind badges, in tag order. */
export function stripFor(cell: Cell, cellPx: number,
                         minPx = BADGE_MIN_PX): CellBadge[] {
  if (cellPx < minPx) return [];
  return (cell.tags ?? []).map((tag) => STRIP_BADGES[tag])
    .filter((b): b is CellBadge => !!b);
}

export interface CellCaption {
  text: string;
  /** The two corners the badges leave free. */
  corner: 'tr' | 'bl';
  ink: string;
}

/** Dark on a thumbnail's white ground, white on a state fill -- the same two
 *  captions have to read on both. */
export const CAPTION_ON_THUMB = '#4a4a4f';
export const CAPTION_ON_FILL = '#ffffff';

/** What a cell says about itself once it is drawn big enough to read: its
 *  years on the top edge, its part number on the bottom. */
export function captionsFor(cell: Cell, cellPx: number, ink: string,
                            minPx = LABEL_MIN_PX): CellCaption[] {
  if (cellPx < minPx) return [];
  const out: CellCaption[] = [];
  const years = yearRange(cell.year_from, cell.year_to, isRetired(cell));
  if (years) out.push({ text: years, corner: 'tr', ink });
  out.push({ text: cell.id, corner: 'bl', ink });
  return out;
}

export type PaintCommand =
  | { kind: 'sprite'; dx: number; dy: number; dw: number; dh: number;
      sx: number; sy: number; sw: number; sh: number;
      border: string | null; borderWidth: number; alpha?: number;
      caret?: boolean; badges?: CellBadge[]; strip?: CellBadge[];
      captions?: CellCaption[]; wash?: number }
  | { kind: 'fill'; dx: number; dy: number; dw: number; dh: number;
      fill: string; border: string | null; borderWidth: number;
      /** Out-of-scope cells are drawn as a mark rather than a filled square,
       *  so a part the project is not trying to draw does not read as one it
       *  has failed to: its category's initial where there is room for a
       *  letter, a dot where there is not. */
      shape: 'square' | 'circle';
      glyph?: string;
      mark?: 'sticker';
      captions?: CellCaption[];
      /** Struck corner to corner in the border's own color and width. Every
       *  bordered state earns it when there is nothing drawn in the cell: the
       *  border alone reads as a tint at the zooms where most cells are small,
       *  and an empty cell is the one that has something to say. */
      slash: boolean; caret?: boolean }
  | { kind: 'image'; dx: number; dy: number; dw: number; dh: number;
      image: CanvasImageSource; ground: string; wash?: number;
      /** The vector rung's rasters are ink on transparency, so the ground and
       *  the state's frame both show through them. A baked PNG carries its
       *  own opaque ground and hides anything drawn under it. */
      translucent: boolean;
      border: string | null; borderWidth: number; alpha?: number;
      caret?: boolean; badges?: CellBadge[]; strip?: CellBadge[];
      captions?: CellCaption[] }
  | { kind: 'label'; text: string; count: number; dx: number; dy: number;
      size: number; depth: 0 | 1 };

export interface PaintInput {
  cells: Cell[];
  rects: Rect[];
  visible: number[];
  cam: View;
  manifest: SheetManifest | null;
  palette: Palette;
  loose?: Map<string, HTMLImageElement>;
  /** The vector rung's rasterized cells -- checked before `loose`, since a
   *  cell only lands here once it is past the 128px loose PNG's own rung. */
  vector?: Map<string, CanvasImageSource>;
  /** The legend's hovered or focused row, if any -- cells outside this state
   *  are painted dimmed rather than the matching cells being brightened. */
  highlight?: CellState | null;
  /** Index of the caret cell, if any -- explicit or implied, resolved by the
   *  caller (`caret.ts`). */
  caret?: number | null;
  /** Border and dim tuning, live from the params panel. Defaults to the same
   *  values `DEFAULT_PARAMS` gives that panel. */
  appearance?: Appearance;
  /** Group headers the layout asked for. Absent for a dense grid. */
  bands?: Band[];
  /** What a cell's color says. Outside `status` the thumbnail gives way to
   *  the ramp -- an opaque drawing and a ramp cannot both be read. */
  tint?: TintMode;
}

/** What to draw this frame, as data.
 *
 *  Kept separate from the canvas so the decisions -- which cells, from where,
 *  in what color -- are testable without a rendering context, and so the
 *  drawing itself is the only thing weasel's mega view has to replace. */
export function paintCommands({ cells, rects, visible, cam, manifest, palette, loose, vector,
                                highlight = null, bands, caret = null,
                                appearance = DEFAULT_APPEARANCE,
                                tint = 'status' }: PaintInput): PaintCommand[] {
  const out: PaintCommand[] = [];
  const transform = viewToTransform(cam);
  for (const i of visible) {
    const cell = cells[i];
    const rect = rects[i];
    if (!cell || !rect) continue;
    const [dx, dy] = worldToScreen(rect.x, rect.y, transform);
    const dw = rect.w * cam.scale.x;
    const dh = rect.h * cam.scale.y;
    const isCaret = caret != null && i === caret ? true : undefined;
    const state = cellState(cell);
    const dimmed = highlight !== null && highlight !== state;
    const alpha = dimmed ? appearance.dimAlpha : undefined;
    // A drawn cell wears its state's border too: a part that fails in another
    // slot looks perfectly fine in this one, and the frame is the only thing
    // saying otherwise.
    const style = dimmed ? palette.unknown : tintFor(cell, tint, palette);
    const border = style.border;
    const borderWidth = borderWidthFor(style.weight, dw, appearance);
    const badges = badgesFor(cell, dw);
    const strip = stripFor(cell, dw);
    const captions = captionsFor(cell, dw, CAPTION_ON_THUMB);
    const wash = isRetired(cell) ? appearance.retiredWash : undefined;
    const vectored = tint === 'status' ? vector?.get(cell.id) : undefined;
    const image = tint === 'status' ? (vectored ?? loose?.get(cell.id)) : undefined;
    if (image) {
      out.push({ kind: 'image', dx, dy, dw, dh, image, ground: THUMB_GROUND,
                 translucent: vectored !== undefined,
                 border, borderWidth, alpha, caret: isCaret, badges, strip, captions, wash });
      continue;
    }
    const box = tint === 'status' && manifest && cell.sha && !isStale(manifest, cell)
      ? sourceBox(manifest, cell.index)
      : null;
    if (box) {
      out.push({ kind: 'sprite', dx, dy, dw, dh, ...box, border, borderWidth, alpha,
                 caret: isCaret, badges, strip, captions, wash });
      continue;
    }
    out.push({ kind: 'fill', dx, dy, dw, dh, fill: style.fill, border, borderWidth,
               shape: state === 'outOfScope' ? 'circle' : 'square',
               glyph: state === 'outOfScope' ? glyphFor(cell, dw) : undefined,
               mark: state === 'outOfScope' ? markFor(cell) : undefined,
               // Not on an out-of-scope cell: it is deliberately the quietest
               // thing on the wall, and captions would undo that.
               captions: state === 'outOfScope'
                 ? undefined : captionsFor(cell, dw, CAPTION_ON_FILL),
               slash: border !== null, caret: isCaret });
  }
  for (const b of bands ?? []) {
    const w = b.rect.w * cam.scale.x;
    if (w < MIN_LABEL_PX) continue;
    const [dx, dy] = worldToScreen(b.rect.x, b.rect.y, transform);
    const size = b.depth === 0 ? OUTER_LABEL_PX : INNER_LABEL_PX;
    out.push({ kind: 'label', text: b.label, count: b.count,
               dx, dy: dy + size, size, depth: b.depth });
  }
  return out;
}
