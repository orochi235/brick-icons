import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchRender, rasterize } from '@lab/corpus/svgRaster';
import { VECTOR_LEVEL } from '@lab/corpus/levels';
import type { Cell } from '@lab/corpus/types';

export { VECTOR_LEVEL };

/** How much rasterized area stays resident, in device pixels -- ~190MB of
 *  RGBA. A count cap cannot express this: the same 96 cells cost 25MB at the
 *  bottom of the rung and 400MB at the top, so the budget buys many small
 *  cells or a few big ones as the zoom decides. */
export const PIXEL_BUDGET = 48e6;

/** Past this a cell is drawn from a raster smaller than its box. The eye
 *  cannot read the difference on a line drawing, and the alternative is a
 *  16MB bitmap for one cell. */
export const MAX_TARGET_PX = 1024;

/** How far the drawn size can drift from a cell's cached raster before it is
 *  rerastered -- 25% either way, so a continuous zoom rerasters a handful of
 *  times rather than once per frame. */
export const RERASTER_THRESHOLD = 0.25;

/** How long the camera has to hold still before a merely-wrong-sized raster
 *  is redone. A cell with no raster at all never waits for this. */
export const SETTLE_MS = 120;

/** Rasters decoded at once. Each is a blob URL, an `<img>` decode and a
 *  canvas draw; running the whole screen at once starves the frame that
 *  would show the ones already finished. */
export const CONCURRENCY = 8;

export function vectorUrl(cell: Cell, source: string): string {
  const v = cell.sha ? cell.sha.slice(0, 8) : '';
  return `/api/corpus/render/${source}/${cell.id}.svg?v=${v}`;
}

/** The device-pixel size a cell drawn at `cellPx` wants its raster at. */
export function targetPxFor(cellPx: number, dpr: number): number {
  return Math.max(1, Math.min(MAX_TARGET_PX, Math.round(cellPx * dpr)));
}

/** How many rasters of `targetPx` square the budget holds. */
export function residentCap(targetPx: number): number {
  return Math.max(1, Math.floor(PIXEL_BUDGET / Math.max(1, targetPx * targetPx)));
}

/** Visible cells worth rasterizing: only at the vector rung, only cells with
 *  a render, and only as many as the pixel budget holds. */
export function wantedVector(cells: Cell[], visible: number[], level: number,
                             targetPx = VECTOR_LEVEL): Cell[] {
  if (level < VECTOR_LEVEL) return [];
  const cap = residentCap(targetPx);
  const out: Cell[] = [];
  for (const i of visible) {
    const cell = cells[i];
    if (!cell || !cell.sha) continue;
    out.push(cell);
    if (out.length >= cap) break;
  }
  return out;
}

/** Whether a raster cached at `cachedPx` is stale enough at `targetPx` to
 *  redo -- `cachedPx == null` covers "never rasterized" the same as "too far
 *  off". */
export function needsRerender(cachedPx: number | null, targetPx: number,
                              threshold = RERASTER_THRESHOLD): boolean {
  return cachedPx == null || Math.abs(targetPx - cachedPx) > cachedPx * threshold;
}

/** What to rasterize now, and what can wait for the camera to stop.
 *
 *  A cell with nothing rasterized is showing the blurry 128px PNG, so it is
 *  drawn at whatever size the camera is passing through. A cell that already
 *  has a raster is only the wrong sharpness, and redoing those mid-gesture
 *  spends the whole budget on sizes the camera has already left.
 */
export function splitWork(want: Cell[], have: Map<string, { px: number }>,
                          targetPx: number): { now: Cell[]; onSettle: Cell[] } {
  const now: Cell[] = [];
  const onSettle: Cell[] = [];
  for (const cell of want) {
    const cached = have.get(cell.id);
    if (!cached) now.push(cell);
    else if (needsRerender(cached.px, targetPx)) onSettle.push(cell);
  }
  return { now, onSettle };
}

interface RasterEntry { image: CanvasImageSource; px: number }

/** The vector rung's rasterized cells, keyed by part id.
 *
 *  Square, device-pixel-sized bitmaps, one per visible cell -- kept only
 *  while a cell is both wanted and sized closely enough to the last raster,
 *  so a wall panned or zoomed away from never grows this without bound.
 *
 *  Work outlives the camera move that asked for it. Canceling on every
 *  dependency change -- and `visible` is a new array each frame a wheel
 *  turns -- meant a gesture threw away every raster in flight and started
 *  over, so cells only sharpened once the wall had been still for a full
 *  fetch and decode.
 */
export function useVectorThumbs(cells: Cell[], visible: number[], level: number,
                                source: string, cellPx: number):
    Map<string, CanvasImageSource> {
  const [raster, setRaster] = useState<Map<string, RasterEntry>>(new Map());
  const rasterRef = useRef(raster);
  rasterRef.current = raster;

  const mounted = useRef(true);
  const inFlight = useRef<Set<string>>(new Set());
  const queue = useRef<{ cell: Cell; px: number }[]>([]);
  const running = useRef(0);
  const wantedIds = useRef<Set<string>>(new Set());
  // Fetched render bytes, so rerastering a cell the zoom drifted past costs a
  // decode rather than another few hundred KB over the wire.
  const bytes = useRef<Map<string, Blob>>(new Map());
  // Arrivals are merged once a frame: one state update for a screenful,
  // rather than one repaint of the whole wall per cell.
  const arrived = useRef<Map<string, RasterEntry>>(new Map());
  const flush = useRef<number | null>(null);

  useEffect(() => () => { mounted.current = false; }, []);

  useEffect(() => {
    inFlight.current = new Set();
    queue.current = [];
    bytes.current = new Map();
    arrived.current = new Map();
    // The ref lags the state by a commit, and the effect below reads the ref.
    // Clearing only the state leaves that effect holding the previous slot's
    // rasters, which a parked camera makes look exactly the right size to
    // keep -- so the new slot is never drawn until the camera moves.
    rasterRef.current = new Map();
    setRaster(new Map());
  }, [source]);

  useEffect(() => {
    const dpr = window.devicePixelRatio || 1;
    const targetPx = targetPxFor(cellPx, dpr);
    const want = wantedVector(cells, visible, level, targetPx);
    wantedIds.current = new Set(want.map((c) => c.id));

    // Residency, not a draw-call concern, so this runs even when nothing new
    // needs fetching -- and the byte cache follows the rasters out.
    setRaster((prev) => {
      let changed = false;
      const next = new Map(prev);
      for (const id of next.keys()) {
        if (!wantedIds.current.has(id)) { next.delete(id); changed = true; }
      }
      return changed ? next : prev;
    });
    for (const id of bytes.current.keys()) {
      if (!wantedIds.current.has(id)) bytes.current.delete(id);
    }

    const scheduleFlush = () => {
      if (flush.current !== null) return;
      flush.current = requestAnimationFrame(() => {
        flush.current = null;
        if (!mounted.current || arrived.current.size === 0) return;
        const batch = arrived.current;
        arrived.current = new Map();
        setRaster((prev) => {
          const next = new Map(prev);
          for (const [id, entry] of batch) {
            if (wantedIds.current.has(id)) next.set(id, entry);
          }
          return next;
        });
      });
    };

    const drain = () => {
      while (running.current < CONCURRENCY && queue.current.length > 0) {
        const job = queue.current.shift()!;
        if (!wantedIds.current.has(job.cell.id)) {
          inFlight.current.delete(job.cell.id);
          continue;
        }
        running.current += 1;
        void rasterOne(job.cell, job.px)
          .finally(() => {
            running.current -= 1;
            inFlight.current.delete(job.cell.id);
            drain();
          });
      }
    };

    const rasterOne = async (cell: Cell, px: number) => {
      try {
        const url = vectorUrl(cell, source);
        let render = bytes.current.get(cell.id);
        if (render === undefined) {
          render = await fetchRender(url);
          if (!mounted.current) return;
          bytes.current.set(cell.id, render);
        }
        const image = await rasterize(render, px, px);
        if (!mounted.current || !wantedIds.current.has(cell.id)) return;
        arrived.current.set(cell.id, { image, px });
        scheduleFlush();
      } catch {
        /* the 128px loose thumb stays the fallback */
      }
    };

    const enqueue = (batch: Cell[]) => {
      for (const cell of batch) {
        if (inFlight.current.has(cell.id)) continue;
        inFlight.current.add(cell.id);
        queue.current.push({ cell, px: targetPx });
      }
      drain();
    };

    const { now, onSettle } = splitWork(want, rasterRef.current, targetPx);
    enqueue(now);
    if (onSettle.length === 0) return;
    const settle = setTimeout(() => enqueue(onSettle), SETTLE_MS);
    return () => clearTimeout(settle);
  }, [cells, visible, level, source, cellPx]);

  return useMemo(
    () => new Map([...raster].map(([id, entry]) => [id, entry.image])),
    [raster]);
}
