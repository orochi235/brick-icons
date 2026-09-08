import { useEffect, useRef, useState } from 'react';
import type { Cell } from '@lab/corpus/types';

export const LOOSE_LEVEL = 128;
export const MAX_IN_FLIGHT = 200;

export function thumbUrl(cell: Cell, source: string): string {
  const v = cell.sha ? cell.sha.slice(0, 8) : '';
  return `/api/thumbs/${source}/128/${cell.id}.png?v=${v}`;
}

/** Visible cells worth a loose fetch: only once the wall is at the level
 *  where individual files replace the sheet, and only for cells that have
 *  something rendered to fetch. Capped so a big viewport at 128px never
 *  fires hundreds of requests in one frame. */
export function wanted(cells: Cell[], visible: number[], level: number): Cell[] {
  if (level < LOOSE_LEVEL) return [];
  const out: Cell[] = [];
  for (const i of visible) {
    const cell = cells[i];
    if (!cell || !cell.sha) continue;
    out.push(cell);
    if (out.length >= MAX_IN_FLIGHT) break;
  }
  return out;
}

/** The loose 128px images currently loaded, keyed by part id.
 *
 *  A cell already requested (loaded or in flight) is never requested again
 *  for the same slot -- `visible` is a new array most frames the camera
 *  moves, but the id-keyed guard means that churn recomputes `wanted`
 *  without re-issuing any fetch. */
export function useLooseThumbs(cells: Cell[], visible: number[], level: number,
                               source: string): Map<string, HTMLImageElement> {
  const [loose, setLoose] = useState<Map<string, HTMLImageElement>>(new Map());
  const requested = useRef<Set<string>>(new Set());
  // Only unmounting stops an image landing. Keying liveness to the effect
  // instead dropped every image that finished loading after the next camera
  // move -- and `requested` still held the id, so it was never asked for
  // again.
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);

  useEffect(() => {
    requested.current = new Set();
    setLoose(new Map());
  }, [source]);

  useEffect(() => {
    for (const cell of wanted(cells, visible, level)) {
      if (requested.current.has(cell.id)) continue;
      requested.current.add(cell.id);
      const img = new Image();
      img.onload = () => {
        if (!mounted.current) return;
        setLoose((prev) => new Map(prev).set(cell.id, img));
      };
      img.src = thumbUrl(cell, source);
    }
  }, [cells, visible, level, source]);

  return loose;
}
