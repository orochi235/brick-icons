import type { SheetManifest } from '@lab/corpus/types';

export interface SourceBox { sx: number; sy: number; sw: number; sh: number }

export function sourceBox(m: SheetManifest, index: number): SourceBox | null {
  if (index < 0 || index >= m.cols * m.rows) return null;
  return {
    sx: (index % m.cols) * m.pitch + m.gutter,
    sy: Math.floor(index / m.cols) * m.pitch + m.gutter,
    sw: m.level,
    sh: m.level,
  };
}

/** Whether the sheet holds a tile for this cell at all.
 *
 *  This, and not `isStale`, is what decides whether a sprite is drawn: a
 *  stale picture is worth drawing and an empty box never is. Gating the draw
 *  on freshness let one re-encode of a slot turn the whole wall into blank
 *  squares, silently, because every tile was "stale" and nothing said so. */
export function hasTile(m: SheetManifest,
                        cell: { id: string }): boolean {
  return m.baked[cell.id] !== undefined;
}

/** Whether the sheet's picture of this cell is behind the store's.
 *
 *  A cell with no render is not stale -- it is a placeholder, which is the
 *  common case on a wall the render job is still filling.
 *
 *  Use this to decide whether to FETCH a fresher tile, never whether to draw
 *  one. */
export function isStale(m: SheetManifest,
                        cell: { id: string; sha: string | null }): boolean {
  if (cell.sha === null) return false;
  return m.baked[cell.id] !== cell.sha;
}

/** How many of `cells` the sheet's picture is behind on.
 *
 *  A whole slot going stale at once is a bake that did not finish or a
 *  re-encode that changed every sha. It is worth saying out loud: the wall
 *  itself cannot tell the difference between that and a slot with no renders,
 *  and before this it reported neither. */
export function staleCount(m: SheetManifest,
                           cells: readonly { id: string; sha: string | null }[]):
                           { stale: number; missing: number; total: number } {
  let stale = 0;
  let missing = 0;
  for (const cell of cells) {
    if (!hasTile(m, cell)) missing++;
    else if (isStale(m, cell)) stale++;
  }
  return { stale, missing, total: cells.length };
}
