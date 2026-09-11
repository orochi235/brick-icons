import { UNKNOWN } from '@lab/corpus/facts';
import type { Band, Layout, LayoutOptions, Rect } from '@lab/corpus/layout';
import type { Cell } from '@lab/corpus/types';

export interface Group { key: string; label?: string; items: number[] }
export interface Placed { index: number; rect: Rect }
export interface Flowed { placed: Placed[]; bands: Band[]; height: number }

// A block a little wider than tall reads as a block rather than a column, and
// packs more groups per row than a square would.
const BLOCK_ASPECT = 1.35;
// Blocks are separated by two pitches; less and two groups read as one.
const BLOCK_GAP_PITCHES = 2;

// Wide enough that an empty block is a named space rather than a gap: with
// one column its heading is narrower than its own word and `paint` drops it.
const EMPTY_BLOCK_COLS = 4;

export function blockCols(n: number, cols: number): number {
  if (n === 0) return Math.min(cols, EMPTY_BLOCK_COLS);
  return Math.min(cols, Math.max(1, Math.ceil(Math.sqrt(n * BLOCK_ASPECT))));
}

/** Pack `groups` as blocks flowed across `cols` cells, starting at `top`.
 *
 *  `headerRows` rows of pitch are reserved above every block for its label.
 *  The caller places cells by index, so this never sees a `Cell`.
 *
 *  `depth` is how the label is set, not how deep the call is: a grouping with
 *  one level has no outer band for its blocks to defer to, so they are the
 *  outer band and read like it. */
export function flowBlocks(groups: Group[], opts: LayoutOptions, top: number,
                           headerRows: number, depth: 0 | 1 = 1): Flowed {
  const pitch = opts.cell + opts.gap;
  const width = opts.cols * pitch;
  const gutter = BLOCK_GAP_PITCHES * pitch;
  const placed: Placed[] = [];
  const bands: Band[] = [];
  let x = 0;
  let y = top;
  let rowHeight = 0;

  for (const group of groups) {
    const n = group.items.length;
    const c = blockCols(n, opts.cols);
    const rows = Math.ceil(n / c);
    const w = c * pitch;
    if (x > 0 && x + w > width) {
      x = 0;
      y += rowHeight + gutter;
      rowHeight = 0;
    }
    const cellTop = y + headerRows * pitch;
    group.items.forEach((index, i) => {
      placed.push({
        index,
        rect: { x: x + (i % c) * pitch, y: cellTop + Math.floor(i / c) * pitch,
                w: opts.cell, h: opts.cell },
      });
    });
    const h = headerRows * pitch + rows * pitch - opts.gap;
    bands.push({ key: group.key, label: group.label ?? group.key, count: n,
                 rect: { x, y, w: w - opts.gap, h }, depth,
                 header: headerRows * pitch });
    rowHeight = Math.max(rowHeight, h);
    x += w + gutter;
  }

  return { placed, bands, height: groups.length ? y + rowHeight - top : 0 };
}

const OUTER_HEADER_ROWS = 2;
const INNER_HEADER_ROWS = 1;
// Between two outer bands. Wider than the gap between blocks inside one, or
// the levels stop reading as levels.
const BAND_GAP_PITCHES = 3;

function bucket(cells: Cell[], key: (c: Cell) => string): Map<string, number[]> {
  const out = new Map<string, number[]>();
  cells.forEach((cell, i) => {
    const k = key(cell);
    const held = out.get(k);
    if (held) held.push(i);
    else out.set(k, [i]);
  });
  return out;
}

function boundsOf(rects: Rect[], bands: Band[]): { w: number; h: number } {
  let w = 0;
  let h = 0;
  for (const r of [...rects, ...bands.map((b) => b.rect)]) {
    w = Math.max(w, r.x + r.w);
    h = Math.max(h, r.y + r.h);
  }
  return { w, h };
}

function rectsInOrder(cells: Cell[], placed: Placed[]): Rect[] {
  // `rects[i]` must address `cells[i]`: paint, hit-testing and the caret all
  // index the two together.
  const out = new Array<Rect>(cells.length);
  for (const p of placed) out[p.index] = p.rect;
  return out;
}

/** One level of grouping, blocks flowed and wrapped. `order` fixes which block
 *  comes first; a key it does not name sorts after the ones it does. */
export function blockLayout(key: (c: Cell) => string, order: string[]): Layout {
  return (cells, opts) => {
    const held = bucket(cells, key);
    // Every named class keeps its place whether or not this slot has any: the
    // wall is read by flipping slots, and a class that vanished when it hit
    // zero reflowed every block after it, so the same part moved across the
    // screen for a reason that had nothing to do with it.
    for (const k of order) if (!held.has(k)) held.set(k, []);
    const rank = new Map(order.map((k, i) => [k, i]));
    const groups: Group[] = [...held.entries()]
      .sort((a, b) => (rank.get(a[0]) ?? order.length)
                    - (rank.get(b[0]) ?? order.length)
                    || a[0].localeCompare(b[0]))
      .map(([k, items]) => ({ key: k, items }));
    const { placed, bands } = flowBlocks(groups, opts, 0, OUTER_HEADER_ROWS, 0);
    const rects = rectsInOrder(cells, placed);
    return { rects, bands, bounds: boundsOf(rects, bands) };
  };
}

// `UNKNOWN` is always last, in both directions: it is an absence, not an
// extreme, and sorting it to one end would read as a date.
function keyOrder(desc: boolean) {
  return (a: string, b: string) => {
    if ((a === UNKNOWN) !== (b === UNKNOWN)) return a === UNKNOWN ? 1 : -1;
    return a.localeCompare(b, undefined, { numeric: true }) * (desc ? -1 : 1);
  };
}

/** Two levels: outer groups stack as bands, inner groups flow inside one. */
export function bandedLayout(outer: (c: Cell) => string,
                             inner: (c: Cell) => string,
                             desc: boolean): Layout {
  return (cells, opts) => {
    const pitch = opts.cell + opts.gap;
    const cmp = keyOrder(desc);
    const outerGroups = [...bucket(cells, outer).entries()]
      .sort((a, b) => cmp(a[0], b[0]));
    const placed: Placed[] = [];
    const bands: Band[] = [];
    let y = 0;

    for (const [key, indices] of outerGroups) {
      const innerGroups: Group[] = [...bucket(
        indices.map((i) => cells[i]!), inner).entries()]
        .sort((a, b) => cmp(a[0], b[0]))
        .map(([k, local]) => ({ key: k, items: local.map((j) => indices[j]!) }));
      const top = y + OUTER_HEADER_ROWS * pitch;
      const flowed = flowBlocks(innerGroups, opts, top, INNER_HEADER_ROWS);
      placed.push(...flowed.placed);
      const h = OUTER_HEADER_ROWS * pitch + flowed.height;
      bands.push({ key, label: key, count: indices.length,
                   rect: { x: 0, y, w: opts.cols * pitch - opts.gap, h },
                   depth: 0, header: OUTER_HEADER_ROWS * pitch });
      bands.push(...flowed.bands);
      y += h + BAND_GAP_PITCHES * pitch;
    }

    const rects = rectsInOrder(cells, placed);
    return { rects, bands, bounds: boundsOf(rects, bands) };
  };
}
