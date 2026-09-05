import { useEffect, useRef, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { Cell, CellsBody } from '@lab/corpus/types';

export const POLL_MS = 10_000;

/** Fold a delta into the wall's cells.
 *
 *  Identity of untouched cells is preserved so React and the paint loop can
 *  tell what actually changed when the render job lands a batch. */
export function mergeCells(current: Cell[], delta: Cell[]): Cell[] {
  if (delta.length === 0) return current;
  const byId = new Map(delta.map((c) => [c.id, c]));
  return current.map((c) => byId.get(c.id) ?? c);
}

export function useCells(client: LabClient, source: string): Cell[] | null {
  const [cells, setCells] = useState<Cell[] | null>(null);
  const [fetchedFor, setFetchedFor] = useState(source);
  const version = useRef('');

  // Cleared during render, not in an effect: a slot change is a different
  // set of drawings for the same parts, and clearing a render later would
  // let a child see this slot's `source` paired with the old slot's `cells`
  // for one commit -- exactly the mismatch that fires loose-thumb 404s.
  if (fetchedFor !== source) {
    setFetchedFor(source);
    setCells(null);
    version.current = '';
  }

  useEffect(() => {
    let live = true;
    void client.cells(source).then((body: CellsBody) => {
      if (!live) return;
      version.current = body.version;
      setCells(body.cells);
    });
    const timer = setInterval(() => {
      void client.cells(source, version.current).then((body: CellsBody) => {
        if (!live || body.cells.length === 0) return;
        version.current = body.version;
        setCells((prev) => (prev ? mergeCells(prev, body.cells) : prev));
      });
    }, POLL_MS);
    return () => { live = false; clearInterval(timer); };
  }, [client, source]);

  return cells;
}
