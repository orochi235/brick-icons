import { useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { SheetManifest } from '@lab/corpus/types';

export const SHEET_LEVELS = [8, 32] as const;
export const LOOSE_LEVEL = 128;

export interface Sheet {
  image: HTMLImageElement;
  manifest: SheetManifest;
}

/** Both sprite-sheet levels for a slot, and the slot they are for.
 *
 *  Each is one small texture that never changes during a session, so nothing
 *  here evicts. A slot change keeps the old pair on screen and swaps the whole
 *  set in once the new one has settled -- a half-swapped wall reads every
 *  cell as stale and blanks it.
 */
export interface SheetsState { sheets: Record<number, Sheet>; source: string }

export function useSheets(client: LabClient, source: string): SheetsState {
  const [state, setState] = useState<SheetsState>({ sheets: {}, source });

  useEffect(() => {
    let live = true;
    const next: Record<number, Sheet> = {};
    let pending = SHEET_LEVELS.length;
    const settle = () => {
      if (--pending > 0 || !live) return;
      setState({ sheets: next, source });
    };
    for (const level of SHEET_LEVELS) {
      void client.sheetManifest(source, level).then((manifest) => {
        if (!live) return settle();
        const img = new Image();
        img.onload = () => { next[level] = { image: img, manifest }; settle(); };
        // A slot with no sheet baked yet settles too, or the wall would hold
        // the previous slot's drawings for the rest of the session.
        img.onerror = () => settle();
        img.src = `/api/thumbs/${source}/sheet-${level}.webp`;
      }).catch(settle);
    }
    return () => { live = false; };
  }, [client, source]);

  return state;
}
