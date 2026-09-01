import { useEffect, useState } from 'react';
import type { Artifact, LabClient, RenderResult } from '@lab/api/client';
import type { SourceId } from '@lab/panes/sources';

/** The render's own SVG. `.unwrap.svg` and `.decal.svg` are debug output from
 *  other stages and are not what the pane shows. */
export function svgArtifactName(artifacts: Artifact[]): string | null {
  const hit = artifacts.find((a) => a.name.endsWith('.svg')
    && !a.name.includes('.unwrap.') && !a.name.includes('.decal.'));
  return hit ? hit.name : null;
}

export async function fetchSvgMarkup(url: string,
                                     fetchImpl: typeof fetch = fetch): Promise<string | null> {
  const response = await fetchImpl(url);
  if (!response.ok) return null;
  return response.text();
}

/** SVG markup for each finished render, keyed by source. */
export function useArtifactSvg(client: LabClient,
                               renders: Partial<Record<SourceId, RenderResult>>) {
  const [markup, setMarkup] = useState<Partial<Record<SourceId, string>>>({});

  const signature = Object.entries(renders)
    .map(([id, r]) => `${id}:${r?.key ?? ''}`).sort().join('|');

  useEffect(() => {
    let live = true;
    (async () => {
      const next: Partial<Record<SourceId, string>> = {};
      for (const [id, result] of Object.entries(renders)) {
        if (!result) continue;
        const name = svgArtifactName(result.artifacts);
        if (!name) continue;
        const text = await fetchSvgMarkup(client.artifactUrl(result.key, name));
        if (text) next[id as SourceId] = text;
      }
      if (live) setMarkup(next);
    })();
    return () => { live = false; };
    // `signature` is the whole dependency: the render keys are what change.
  }, [signature]);

  return markup;
}
