import { useEffect, useRef } from 'react';
import type { ChangedEvent } from '@lab/api/types';

/** How long the first event of a burst waits for the rest. pezlie's wall
 *  copies every sheet level on each poll that moves a sha, so ten redraws
 *  landing together must be one poll, not ten. */
export const CHANGED_BATCH_MS = 250;

interface Listens {
  onChanged?: (listener: (event: ChangedEvent) => void) => () => void;
}

/** `onBatch` with every redraw stored in each window of `CHANGED_BATCH_MS`,
 *  starting at the first. A client that cannot listen -- a test stub -- is
 *  simply quiet. */
export function useChanged(client: Listens, onBatch: (events: ChangedEvent[]) => void,
                           windowMs = CHANGED_BATCH_MS): void {
  const latest = useRef(onBatch);
  latest.current = onBatch;
  useEffect(() => {
    let held: ChangedEvent[] = [];
    let timer: ReturnType<typeof setTimeout> | null = null;
    const stop = client.onChanged?.((event) => {
      held.push(event);
      if (timer !== null) return;
      timer = setTimeout(() => {
        const batch = held;
        held = [];
        timer = null;
        latest.current(batch);
      }, windowMs);
    });
    return () => {
      if (timer !== null) clearTimeout(timer);
      stop?.();
    };
  }, [client, windowMs]);
}
