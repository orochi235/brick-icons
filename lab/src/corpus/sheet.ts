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

/** Whether the sheet's picture of this cell is behind the store's.
 *
 *  A cell with no render is not stale -- it is a placeholder, which is the
 *  common case on a wall the render job is still filling. */
export function isStale(m: SheetManifest,
                        cell: { id: string; sha: string | null }): boolean {
  if (cell.sha === null) return false;
  return m.baked[cell.id] !== cell.sha;
}
