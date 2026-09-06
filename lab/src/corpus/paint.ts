import { worldToScreen, viewToTransform, type View } from '@weasel-js/core';
import type { Rect } from '@lab/corpus/layout';
import { CELL_STATES, type CellState, type CellStyle, type Palette } from '@lab/corpus/palette';
import { DEFAULT_PARAMS } from '@lab/corpus/params';
import { isStale, sourceBox } from '@lab/corpus/sheet';
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

/** Below this drawn size a cell has no room for a badge without covering the
 *  drawing it is about; the year needs more room still, being words. */
export const BADGE_MIN_PX = 56;
export const LABEL_MIN_PX = 110;

export interface CellBadge {
  text: string;
  corner: 'tl' | 'br';
  field: string;
  ink: string;
}

/** The tags that earn a corner disc on the wall itself. The detail views
 *  show every tag in words; the wall has room for the two that change how a
 *  drawing should be read, one corner each so they never collide. */
export const BADGES: Record<string, CellBadge> = {
  retired: { text: 'R', corner: 'br', field: '#6b6b72', ink: '#ffffff' },
  popular: { text: 'P', corner: 'tl', field: '#7c5cff', ink: '#ffffff' },
};

export function isRetired(cell: Cell): boolean {
  return cell.tags?.includes('retired') ?? false;
}

/** The discs a drawn cell wears, if it is drawn big enough to hold them. */
export function badgesFor(cell: Cell, cellPx: number,
                          minPx = BADGE_MIN_PX): CellBadge[] {
  if (cellPx < minPx) return [];
  return (cell.tags ?? []).map((tag) => BADGES[tag]).filter((b): b is CellBadge => !!b);
}

/** The years written across the top of a cell, once it is big enough that
 *  they are readable rather than a smudge. */
export function labelFor(cell: Cell, cellPx: number,
                         minPx = LABEL_MIN_PX): string | null {
  if (cellPx < minPx) return null;
  return yearRange(cell.year_from, cell.year_to, isRetired(cell));
}

export type PaintCommand =
  | { kind: 'sprite'; dx: number; dy: number; dw: number; dh: number;
      sx: number; sy: number; sw: number; sh: number;
      border: string | null; borderWidth: number; alpha?: number;
      caret?: boolean; badges?: CellBadge[]; label?: string; wash?: number }
  | { kind: 'fill'; dx: number; dy: number; dw: number; dh: number;
      fill: string; border: string | null; borderWidth: number;
      /** Out-of-scope cells are drawn round, so a part the project is not
       *  trying to draw does not read as one it has failed to. */
      shape: 'square' | 'circle';
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
      caret?: boolean; badges?: CellBadge[]; label?: string };

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
}

/** What to draw this frame, as data.
 *
 *  Kept separate from the canvas so the decisions -- which cells, from where,
 *  in what color -- are testable without a rendering context, and so the
 *  drawing itself is the only thing weasel's mega view has to replace. */
export function paintCommands({ cells, rects, visible, cam, manifest, palette, loose, vector,
                                highlight = null, caret = null,
                                appearance = DEFAULT_APPEARANCE }: PaintInput): PaintCommand[] {
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
    const style = dimmed ? palette.unknown : palette[state];
    const border = style.border;
    const borderWidth = borderWidthFor(style.weight, dw, appearance);
    const badges = badgesFor(cell, dw);
    const label = labelFor(cell, dw) ?? undefined;
    const wash = isRetired(cell) ? appearance.retiredWash : undefined;
    const vectored = vector?.get(cell.id);
    const image = vectored ?? loose?.get(cell.id);
    if (image) {
      out.push({ kind: 'image', dx, dy, dw, dh, image, ground: THUMB_GROUND,
                 translucent: vectored !== undefined,
                 border, borderWidth, alpha, caret: isCaret, badges, label, wash });
      continue;
    }
    const box = manifest && cell.sha && !isStale(manifest, cell)
      ? sourceBox(manifest, cell.index)
      : null;
    if (box) {
      out.push({ kind: 'sprite', dx, dy, dw, dh, ...box, border, borderWidth, alpha,
                 caret: isCaret, badges, label, wash });
      continue;
    }
    out.push({ kind: 'fill', dx, dy, dw, dh, fill: style.fill, border, borderWidth,
               shape: state === 'outOfScope' ? 'circle' : 'square',
               slash: border !== null, caret: isCaret });
  }
  return out;
}
