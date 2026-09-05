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
  const version = useRef('');

  useEffect(() => {
    let live = true;
    // A slot change is a different set of drawings for the same parts, so the
    // version resets with it -- polling the old one would merge the wrong shas.
    version.current = '';
    setCells(null);
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
