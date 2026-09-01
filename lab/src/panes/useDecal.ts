import { useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { PaneState } from '@lab/panes/SourcePane';

export interface DecalStatus {
  part: string;
  urls: string[];
  error: string | null;
  loading: boolean;
}

export function decalState(status: DecalStatus): PaneState {
  if (!status.part.trim()) return { kind: 'idle' };
  if (status.error) return { kind: 'error', message: status.error };
  if (status.loading) return { kind: 'running' };
  // Running the extractor is what settles whether a part is printed, so an
  // empty result is the answer and not a failure. `part_index`'s `printed`
  // flag is a guess from the id; this is not.
  if (status.urls.length === 0) return { kind: 'error', message: 'no decal on this part' };
  return { kind: 'image', src: status.urls[0]! };
}

/** What the pane shows beside its label when a part decorates several faces. */
export function decalCaption(urls: string[]): string {
  return urls.length > 1 ? `+${urls.length - 1} more surfaces` : '';
}

/** The decoration of a printed part, unwrapped flat onto the face it came from.
 *
 * The first URL is the largest print: `decal_one` sorts by print area, so `.0`
 * is the real decoration and the rest are usually offcuts of it. Gated on the
 * pane being shown: extraction re-parses and tessellates the whole part.
 */
export function useDecal(client: LabClient, part: string, enabled = true): {
  pane: PaneState; urls: string[];
} {
  const [status, setStatus] = useState<DecalStatus>({
    part, urls: [], error: null, loading: false,
  });

  useEffect(() => {
    if (!enabled || !part.trim()) {
      setStatus({ part, urls: [], error: null, loading: false });
      return;
    }
    let live = true;
    setStatus({ part, urls: [], error: null, loading: true });
    client.decal(part)
      .then((got) => {
        if (live) setStatus({ part, urls: got.urls, error: null, loading: false });
      })
      .catch((e: Error) => {
        if (live) setStatus({ part, urls: [], error: e.message, loading: false });
      });
    return () => { live = false; };
  }, [client, part, enabled]);

  return { pane: decalState(status), urls: status.urls };
}
