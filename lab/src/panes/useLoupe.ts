import { useEffect, useState } from 'react';
import { DEFAULT_FACTOR, clampFactor, type Point } from '@lab/panes/loupe';
import type { SourceId } from '@lab/panes/sources';

export interface LoupeControl {
  live: boolean;
  factor: number;
  allPanes: boolean;
  /** The pane the pointer is in, and where in its body. Null unless live. */
  over: SourceId | null;
  at: Point | null;
  onHover: (id: SourceId, at: Point | null) => void;
  bumpFactor: (steps: number) => void;
}

/** Alt state and the loupe's settings, held once for every pane so they agree
 *  on whether the bubble is up and where. */
export function useLoupe(config: Record<string, unknown>,
                         setConfig: (key: string, value: unknown) => void): LoupeControl {
  const [alt, setAlt] = useState(false);
  const [hover, setHover] = useState<{ id: SourceId; at: Point } | null>(null);

  useEffect(() => {
    const down = (e: KeyboardEvent) => { if (e.key === 'Alt') setAlt(true); };
    const up = (e: KeyboardEvent) => { if (e.key === 'Alt') setAlt(false); };
    // A window that loses focus never sees the keyup, so the bubble would hang
    // there until Alt was pressed and released again.
    const blur = () => setAlt(false);
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    window.addEventListener('blur', blur);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
      window.removeEventListener('blur', blur);
    };
  }, []);

  const factor = clampFactor(Number(config.loupe_factor ?? DEFAULT_FACTOR));
  const live = alt || Boolean(config.loupe_sticky);

  return {
    live,
    factor,
    allPanes: Boolean(config.loupe_all_panes),
    over: live && hover ? hover.id : null,
    at: live && hover ? hover.at : null,
    onHover: (id, at) => setHover(at ? { id, at } : null),
    bumpFactor: (steps) => setConfig('loupe_factor', clampFactor(factor + steps)),
  };
}
