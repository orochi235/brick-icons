import { useEffect, useState } from 'react';
import type { LabClient, RenderResult } from '@lab/api/client';
import type { SourceId } from '@lab/panes/sources';
import type { PaneState } from '@lab/panes/SourcePane';
import { svgArtifactName } from '@lab/panes/useArtifactSvg';

export interface DiffResult {
  components: number;
  sizes: number[];
  pixels: number;
  url: string;
}

/** What the diff pane says under its picture.
 *
 * Leads with the component count, not the pixel total: antialias fringe
 * scatters into hundreds of tiny components and a real defect is a handful of
 * chunky ones, so a pixel count cannot tell the two apart.
 */
export function diffCaption(result: DiffResult | null): string {
  if (!result) return '';
  if (result.components === 0) return 'identical';
  const biggest = result.sizes[0] ?? 0;
  return `${result.components} component${result.components === 1 ? '' : 's'}`
    + ` · largest ${biggest}px · ${result.pixels}px total`;
}

/** The two engine renders a diff compares, in a fixed order so the answer does
 *  not depend on which finished first. */
export function diffPair(renders: Partial<Record<SourceId, RenderResult>>) {
  const a = renders.naive;
  const b = renders.occt;
  if (!a?.ok || !b?.ok) return null;
  const aName = svgArtifactName(a.artifacts);
  const bName = svgArtifactName(b.artifacts);
  if (!aName || !bName) return null;
  return { aKey: a.key, aName, bKey: b.key, bName };
}

export function useDiff(client: LabClient,
                        renders: Partial<Record<SourceId, RenderResult>>) {
  const [state, setState] = useState<{ result: DiffResult | null; error: string | null }>(
    { result: null, error: null });

  const pair = diffPair(renders);
  const signature = pair ? `${pair.aKey}:${pair.bKey}` : '';

  useEffect(() => {
    if (!pair) {
      setState({ result: null, error: null });
      return;
    }
    let live = true;
    client.diff(pair.aKey, pair.aName, pair.bKey, pair.bName)
      .then((result) => { if (live) setState({ result, error: null }); })
      .catch((e: Error) => { if (live) setState({ result: null, error: e.message }); });
    return () => { live = false; };
  }, [signature]);

  const pane: PaneState = state.error
    ? { kind: 'error', message: state.error }
    : state.result
      ? { kind: 'image', src: state.result.url }
      : pair
        ? { kind: 'running' }
        : { kind: 'idle' };

  return { pane, result: state.result };
}

/** Why a diff can be huge and still tell you nothing.
 *
 * `occt` returns no faces, so on a filled combo it draws strokes where `naive`
 * paints a body -- and the diff is then the whole silhouette. Comparing the
 * hidden-line work means putting both engines on strokes only, which is what
 * the `outline` golden combo does for the same reason.
 */
export function diffWarning(config: Record<string, unknown>): string | null {
  const filled = config.shade_style !== 'none' && config.shade_style !== undefined;
  if (!filled) return null;
  return 'comparing fills — occt draws none, so set fill: none to diff the strokes';
}
