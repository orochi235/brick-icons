import { useEffect, useRef, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import { DEFAULT_PARAMS } from '@lab/corpus/params';
import type { Cell, CellsBody } from '@lab/corpus/types';

export const POLL_MS = DEFAULT_PARAMS.pollMs;

/** Fold a delta into the wall's cells.
 *
 *  Identity of untouched cells is preserved so React and the paint loop can
 *  tell what actually changed when the render job lands a batch. */
export function mergeCells(current: Cell[], delta: Cell[]): Cell[] {
  if (delta.length === 0) return current;
  const byId = new Map(delta.map((c) => [c.id, c]));
  return current.map((c) => byId.get(c.id) ?? c);
}

/** The wall's cells, and the slot they are for.
 *
 *  The pair travels together because a slot change is a different set of
 *  drawings for the same parts: this slot's `source` beside the old slot's
 *  cells is what fires loose-thumb 404s. Keeping both until the new ones
 *  arrive is also what stops the wall blanking for a second on every switch.
 */
export interface CellsState { cells: Cell[] | null; source: string }

export function useCells(client: LabClient, source: string,
                         pollMs = POLL_MS): CellsState {
  const [state, setState] = useState<CellsState>({ cells: null, source });
  const version = useRef('');

  useEffect(() => {
    let live = true;
    version.current = '';
    void client.cells(source).then((body: CellsBody) => {
      if (!live) return;
      version.current = body.version;
      setState({ cells: body.cells, source });
    });
    const timer = setInterval(() => {
      void client.cells(source, version.current).then((body: CellsBody) => {
        if (!live || body.cells.length === 0) return;
        version.current = body.version;
        setState((prev) => (prev.source === source && prev.cells
          ? { source, cells: mergeCells(prev.cells, body.cells) }
          : prev));
      });
    }, pollMs);
    return () => { live = false; clearInterval(timer); };
  }, [client, source, pollMs]);

  return state;
}
