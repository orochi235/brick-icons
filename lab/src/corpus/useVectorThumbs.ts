import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchAndRasterize } from '@lab/corpus/svgRaster';
import { VECTOR_LEVEL } from '@lab/corpus/levels';
import type { Cell } from '@lab/corpus/types';

export { VECTOR_LEVEL };

/** At the vector rung, only this many cells stay rasterized at once -- a
 *  residency cap, not a request cap: `wanted` already only asks for what a
 *  full screen at this zoom can hold. */
export const MAX_RESIDENT = 96;

/** How far the drawn size can drift from a cell's cached raster before it is
 *  rerastered -- 25% either way, so a continuous zoom rerasters a handful of
 *  times rather than once per frame. */
export const RERASTER_THRESHOLD = 0.25;

export function vectorUrl(cell: Cell, source: string): string {
  const v = cell.sha ? cell.sha.slice(0, 8) : '';
  return `/api/corpus/render/${source}/${cell.id}.svg?v=${v}`;
}

/** Visible cells worth rasterizing: only at the vector rung, only cells with
 *  a render, and capped the same way the loose rung is. */
export function wantedVector(cells: Cell[], visible: number[], level: number): Cell[] {
  if (level < VECTOR_LEVEL) return [];
  const out: Cell[] = [];
  for (const i of visible) {
    const cell = cells[i];
    if (!cell || !cell.sha) continue;
    out.push(cell);
    if (out.length >= MAX_RESIDENT) break;
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

interface RasterEntry { image: CanvasImageSource; px: number }

/** The vector rung's rasterized cells, keyed by part id.
 *
 *  Square, device-pixel-sized bitmaps, one per visible cell -- kept only
 *  while a cell is both wanted and sized closely enough to the last raster,
 *  so a wall panned or zoomed away from never grows this without bound. */
export function useVectorThumbs(cells: Cell[], visible: number[], level: number,
                                source: string, cellPx: number):
    Map<string, CanvasImageSource> {
  const [raster, setRaster] = useState<Map<string, RasterEntry>>(new Map());
  const rasterRef = useRef(raster);
  rasterRef.current = raster;
  const inFlight = useRef<Set<string>>(new Set());

  useEffect(() => {
    inFlight.current = new Set();
    setRaster(new Map());
  }, [source]);

  useEffect(() => {
    const want = wantedVector(cells, visible, level);
    const wantedIds = new Set(want.map((c) => c.id));

    // Evicts cells that scrolled out of the wanted set -- residency, not a
    // draw-call concern, so this runs even when nothing new needs fetching.
    setRaster((prev) => {
      let changed = false;
      const next = new Map(prev);
      for (const id of next.keys()) {
        if (!wantedIds.has(id)) { next.delete(id); changed = true; }
      }
      return changed ? next : prev;
    });

    if (want.length === 0) return;
    const dpr = window.devicePixelRatio || 1;
    const targetPx = Math.max(1, Math.round(cellPx * dpr));
    let live = true;
    for (const cell of want) {
      if (inFlight.current.has(cell.id)) continue;
      const cached = rasterRef.current.get(cell.id);
      if (cached && !needsRerender(cached.px, targetPx)) continue;
      inFlight.current.add(cell.id);
      void fetchAndRasterize(vectorUrl(cell, source), targetPx, targetPx)
        .then((image) => {
          if (!live) return;
          setRaster((prev) => new Map(prev).set(cell.id, { image, px: targetPx }));
        })
        .catch(() => { /* the 128px loose thumb stays the fallback */ })
        .finally(() => { inFlight.current.delete(cell.id); });
    }
    return () => { live = false; };
  }, [cells, visible, level, source, cellPx]);

  return useMemo(
    () => new Map([...raster].map(([id, entry]) => [id, entry.image])),
    [raster]);
}
