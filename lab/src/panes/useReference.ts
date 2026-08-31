import { useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { PaneState } from '@lab/panes/SourcePane';

export interface ReferenceStatus {
  part: string;
  url: string | null;
  error: string | null;
  loading: boolean;
}

export function referenceState(status: ReferenceStatus): PaneState {
  if (!status.part.trim()) return { kind: 'idle' };
  if (status.error) return { kind: 'error', message: status.error };
  if (status.loading) return { kind: 'running' };
  if (status.url) return { kind: 'image', src: status.url };
  return { kind: 'idle' };
}

/** One LDView frame for the current part and angle.
 *
 * Keyed on the settled angle rather than on the live orbit: LDView is a
 * subprocess per frame, so asking on every pointer move would queue hundreds.
 */
export function useReference(client: LabClient, part: string, angle: string,
                             partColor?: string): PaneState {
  const [status, setStatus] = useState<ReferenceStatus>({
    part, url: null, error: null, loading: false,
  });

  useEffect(() => {
    if (!part.trim() || !angle.trim()) {
      setStatus({ part, url: null, error: null, loading: false });
      return;
    }
    let live = true;
    setStatus((prev) => ({ ...prev, part, loading: true, error: null }));
    client.reference(part, angle, partColor)
      .then((got) => {
        if (live) setStatus({ part, url: got.url, error: null, loading: false });
      })
      .catch((e: Error) => {
        if (live) setStatus({ part, url: null, error: e.message, loading: false });
      });
    return () => { live = false; };
  }, [client, part, angle, partColor]);

  return referenceState(status);
}
