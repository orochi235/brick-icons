import { useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { SheetManifest } from '@lab/corpus/types';

export const SHEET_LEVELS = [8, 32] as const;
export const LOOSE_LEVEL = 128;

export interface Sheet {
  image: HTMLImageElement;
  manifest: SheetManifest;
}

/** Both sprite-sheet levels for a slot, keyed by level.
 *
 *  Each is one small texture that never changes during a session, so nothing
 *  here evicts -- only a slot change clears and reloads. */
export function useSheets(client: LabClient, source: string):
    Record<number, Sheet> {
  const [sheets, setSheets] = useState<Record<number, Sheet>>({});

  useEffect(() => {
    let live = true;
    setSheets({});
    for (const level of SHEET_LEVELS) {
      void client.sheetManifest(source, level).then((manifest) => {
        if (!live) return;
        const img = new Image();
        img.onload = () => {
          if (!live) return;
          setSheets((prev) => ({ ...prev, [level]: { image: img, manifest } }));
        };
        img.src = `/api/thumbs/${source}/sheet-${level}.png`;
      }).catch(() => {});
    }
    return () => { live = false; };
  }, [client, source]);

  return sheets;
}
