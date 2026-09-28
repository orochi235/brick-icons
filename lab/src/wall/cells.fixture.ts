import { ALL_BADGES } from '@lab/corpus/paint';
import type { SheetManifest } from '@lab/corpus/types';
import type { Cell } from '@lab/corpus/types';
import { naturalCompare } from '@pezlie/wall/src/natural';

/** mulberry32: small, seedable, and the same on every machine. */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const TAGS = [...Object.keys(ALL_BADGES), 'unclaimed'];
const CONDITIONS = ['review', 'defect', 'timeout', 'failed', 'accepted'];
const PREFIXES = ['3001', '3001a', 'u9012', '98138p07', 'x10', 'x9', '4761', '3626bp63', 'c01'];

/** A corpus exercising every state, variant, tag, category sigil, null field
 *  and optional field the brick-icons feed can send. */
export function generateCells(seed: number, n: number): Cell[] {
  const r = rng(seed);
  const pick = <V>(xs: readonly V[]): V => xs[Math.floor(r() * xs.length)]!;
  const maybe = (p: number) => r() < p;
  const cells = Array.from({ length: n }, (_, index) => {
    const from = maybe(0.2) ? null : 1954 + Math.floor(r() * 73);
    const to = from === null ? (maybe(0.5) ? null : 1990)
      : maybe(0.3) ? from : from + Math.floor(r() * 30);
    return {
      id: `${pick(PREFIXES)}-${index}`,
      index,
      title: `t${index}`,
      category: pick(['Brick', '_Sticker', '~Moved to 3002', 'Plate', null, '=Technic', 'Sticker', '']),
      family: pick([null, null, '', 'Fabuland']),
      printed: maybe(0.3),
      obsolete: maybe(0.2),
      ...(maybe(0.5) ? { posed: maybe(0.5) } : {}),
      base: maybe(0.5),
      out_of_scope: maybe(0.15),
      moved: maybe(0.1),
      year_from: from,
      year_to: to,
      sets: maybe(0.2) ? null : Math.floor(r() * 10000),
      colors: maybe(0.2) ? null : Math.floor(r() * 100),
      tags: TAGS.filter(() => maybe(0.12)),
      ...(maybe(0.3) ? { successor: pick([null, '3002']) } : {}),
      status: pick(['unreviewed', 'good', 'bad', 'Unreviewed']),
      sha: maybe(0.3) ? null : `sha-${index}`,
      made_at: maybe(0.3) ? null : `2025-0${1 + Math.floor(r() * 9)}-01T00:00:00Z`,
      extra_d99: maybe(0.4) ? null : Math.round(r() * 1000) / 10,
      secs: maybe(0.2) ? null : r() < 0.1 ? r() : r() * 800,
      error: pick([null, null, null, 'TimeoutError', 'RuntimeError']),
      ...(maybe(0.5) ? { error_at: pick([null, '2025-02-01T00:00:00Z', '2025-03-01T00:00:00Z']) } : {}),
      open_defects: maybe(0.2) ? 1 + Math.floor(r() * 3) : 0,
      review_defects: maybe(0.1) ? 1 : 0,
      accepted_defects: maybe(0.1) ? 1 : 0,
      elsewhere: CONDITIONS.filter(() => maybe(0.15)),
      ...(maybe(0.1) ? { not_applicable: maybe(0.5) } : {}),
    } as Cell;
  });
  // A feed numbers its items in id order, so a tie in a sort falls in id order.
  return cells.sort((a, b) => naturalCompare(a.id, b.id)).map((c, index) => ({ ...c, index }));
}

/** A sheet holding most drawn cells, some at an older sha, some missing, and a
 *  few undrawn cells that still have a tile. */
export function generateManifest(seed: number, cells: readonly Cell[]): SheetManifest {
  const r = rng(seed ^ 0x9e3779b9);
  const baked: Record<string, string> = {};
  for (const c of cells) {
    const roll = r();
    if (c.sha !== null) {
      if (roll < 0.7) baked[c.id] = c.sha;
      else if (roll < 0.85) baked[c.id] = `${c.sha}-older`;
    } else if (roll < 0.05) {
      baked[c.id] = 'orphan';
    }
  }
  const cols = Math.max(1, Math.ceil(Math.sqrt(cells.length)));
  return { level: 32, gutter: 2, pitch: 36, cols, rows: Math.ceil(cells.length / cols),
           count: cells.length, size: cols * 36, baked };
}
