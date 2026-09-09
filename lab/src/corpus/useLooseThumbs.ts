import { useEffect, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import type { Cell } from '@lab/corpus/types';

/** Read-and-reset for this rung, for the topbar's cache report.
 *
 *  A handle rather than a second return value: every failure here is silent
 *  by design -- an image that errors leaves the sheet tile on screen and
 *  tells nobody -- so something has to be able to ask how many were asked
 *  for against how many arrived. `reset` puts the rung back to a cold start,
 *  which is the fix when `requested` is holding ids whose loads all failed:
 *  the set only grows, so nothing would ever ask for them again. */
export interface LooseHandle {
  stats(): { loaded: number; requested: number };
  reset(): void;
}

export const LOOSE_LEVEL = 128;
export const MAX_IN_FLIGHT = 200;

export function thumbUrl(cell: Cell, source: string): string {
  const v = cell.sha ? cell.sha.slice(0, 8) : '';
  return `/api/thumbs/${source}/128/${cell.id}.webp?v=${v}`;
}

/** Visible cells worth a loose fetch: only once the wall is at the level
 *  where individual files replace the sheet, and only for cells that have
 *  something rendered to fetch. Capped so a big viewport at 128px never
 *  fires hundreds of requests in one frame.
 *
 *  `have` is what is already requested, and it is skipped BEFORE the cap.
 *  Counting it toward the cap is what made the wall stop loading after
 *  enough panning: the first 200 visible cells were all already in hand, the
 *  cap was reached on them, and every un-fetched cell behind them in the
 *  viewport was cut off -- permanently, since the set only grows. */
export function wanted(cells: Cell[], visible: number[], level: number,
                       have: ReadonlySet<string> = new Set()): Cell[] {
  if (level < LOOSE_LEVEL) return [];
  const out: Cell[] = [];
  for (const i of visible) {
    const cell = cells[i];
    if (!cell || !cell.sha || have.has(cell.id)) continue;
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
                               source: string,
                               handle?: MutableRefObject<LooseHandle | null>):
                               Map<string, HTMLImageElement> {
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
    if (!handle) return;
    handle.current = {
      stats: () => ({ loaded: loose.size, requested: requested.current.size }),
      reset: () => { requested.current = new Set(); setLoose(new Map()); },
    };
    return () => { handle.current = null; };
  }, [handle, loose]);

  useEffect(() => {
    for (const cell of wanted(cells, visible, level, requested.current)) {
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
