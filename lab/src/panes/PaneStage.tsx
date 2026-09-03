import { type Camera, cssTransform } from '@lab/panes/camera';

export type PaneState =
  | { kind: 'idle' }
  | { kind: 'running' }
  | { kind: 'svg'; markup: string }
  | { kind: 'image'; src: string }
  | { kind: 'error'; message: string };

export interface PaneStageProps {
  state: PaneState;
  camera: Camera;
  label: string;
  busy?: boolean;
}

/** The drawing's own aspect, read off the SVG's viewBox. Null when nothing is
 *  drawn yet, or when what is drawn does not declare one. */
export function stageAspect(state: PaneState): number | null {
  if (state.kind !== 'svg') return null;
  const found = /viewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)/
    .exec(state.markup);
  if (!found) return null;
  const width = Number(found[1]);
  const height = Number(found[2]);
  return width > 0 && height > 0 ? width / height : null;
}

/** The drawing itself, at a camera. Its own component because the loupe draws
 *  a second one at the magnified camera. */
export function PaneStage({ state, camera, label, busy }: PaneStageProps) {
  return (
    <div className={`pane-stage${busy ? ' pane-waiting' : ''}`}
      style={{ transform: cssTransform(camera) }}>
      {state.kind === 'svg' ? (
        // The SVG is the artifact under test; a raster of it would be a proxy.
        <div dangerouslySetInnerHTML={{ __html: state.markup }} />
      ) : null}
      {state.kind === 'image' ? <img src={state.src} alt={label} /> : null}
      {state.kind === 'running' ? <p>rendering…</p> : null}
    </div>
  );
}
