import { useEffect, useState } from 'react';
import type { Artifact, LabClient, RenderResult } from '@lab/api/client';
import { SOURCE_ORDER, type SourceId } from '@lab/panes/sources';
import { isRenderFit, type RenderFit } from '@lab/panes/viewport';

export function fitArtifactName(artifacts: Artifact[]): string | null {
  const hit = artifacts.find((a) => a.name.endsWith('.fit.json'));
  return hit ? hit.name : null;
}

/** Which render the 3D pane registers against: the first engine pane showing,
 *  in the order the panes are laid out. Registering against whichever finished
 *  last would move the framing about as renders land. */
export function registrationSource(renders: Partial<Record<SourceId, RenderResult>>):
    SourceId | null {
  const hit = SOURCE_ORDER.find((source) => source.kind === 'engine'
    && renders[source.id]?.ok);
  return hit ? hit.id : null;
}

export async function fetchFit(url: string,
                               fetchImpl: typeof fetch = fetch): Promise<RenderFit | null> {
  const response = await fetchImpl(url);
  if (!response.ok) return null;
  const parsed: unknown = await response.json().catch(() => null);
  return isRenderFit(parsed) ? parsed : null;
}

/** The world -> viewBox map of the render the 3D pane frames itself by, or
 *  null while no render has produced one. */
export function useRenderFit(client: LabClient,
                             renders: Partial<Record<SourceId, RenderResult>>) {
  const [fit, setFit] = useState<RenderFit | null>(null);
  const source = registrationSource(renders);
  const key = source ? renders[source]?.key ?? '' : '';

  useEffect(() => {
    if (!source) {
      setFit(null);
      return;
    }
    const result = renders[source];
    const name = result ? fitArtifactName(result.artifacts) : null;
    if (!result || !name) {
      setFit(null);
      return;
    }
    let live = true;
    fetchFit(client.artifactUrl(result.key, name))
      .then((next) => { if (live) setFit(next); })
      .catch(() => { if (live) setFit(null); });
    return () => { live = false; };
    // The render's key is the whole dependency: a new key is a new fit.
  }, [source, key]);

  return fit;
}
