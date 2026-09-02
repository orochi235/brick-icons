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
