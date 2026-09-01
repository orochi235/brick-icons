import { type ReactNode, useEffect, useRef } from 'react';
import { type Camera, cssTransform, panBy, zoomAt } from '@lab/panes/camera';
import type { Source } from '@lab/panes/sources';
import '@lab/panes/SourcePane.css';

export type PaneState =
  | { kind: 'idle' }
  | { kind: 'running' }
  | { kind: 'svg'; markup: string }
  | { kind: 'image'; src: string }
  | { kind: 'error'; message: string };

export interface SourcePaneProps {
  source: Source;
  state: PaneState;
  camera: Camera;
  onCamera: (next: Camera) => void;
  /** A measurement this pane reports, shown beside its label. Not a caption
   *  about the source: only a pane with something to say passes one. */
  note?: string;
  /** A newer render is in flight; what is drawn is the previous one. */
  busy?: boolean;
  /** Drawn above the stage, in body coordinates. */
  overlay?: ReactNode;
  /** The body's pixel size, reported when it is measured or changes. */
  onBox?: (box: { width: number; height: number }) => void;
}

export function SourcePane({ source, state, camera, onCamera, note, busy,
                             overlay, onBox }: SourcePaneProps) {
  const dragging = useRef(false);
  const body = useRef<HTMLDivElement | null>(null);
  // The callback goes through a ref so the effect does not re-subscribe when
  // the caller passes a fresh arrow each render -- which it will, because it
  // is written inline inside a map over the sources.
  const report = useRef(onBox);
  report.current = onBox;

  useEffect(() => {
    const el = body.current;
    if (!el) return;
    const emit = () => report.current?.({ width: el.clientWidth, height: el.clientHeight });
    emit();
    const observer = new ResizeObserver(emit);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <section className="pane">
      <header className="pane-head">
        <strong>{source.label}</strong>
        {note ? <span className="pane-note">{note}</span> : null}
        {busy ? <span className="pane-busy">rendering…</span> : null}
      </header>
      {state.kind === 'error' ? <p className="pane-error">{state.message}</p> : null}
      <div
        className="pane-body"
        ref={body}
        onPointerDown={(e) => {
          dragging.current = true;
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerUp={() => { dragging.current = false; }}
        onPointerMove={(e) => {
          if (dragging.current) onCamera(panBy(camera, e.movementX, e.movementY));
        }}
        onWheel={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
          onCamera(zoomAt(camera, factor, e.clientX - box.left, e.clientY - box.top));
        }}
      >
        <div className={`pane-stage${busy ? ' pane-waiting' : ''}`}
          style={{ transform: cssTransform(camera) }}>
          {state.kind === 'svg' ? (
            // The SVG is the artifact under test; a raster of it would be a proxy.
            <div dangerouslySetInnerHTML={{ __html: state.markup }} />
          ) : null}
          {state.kind === 'image' ? <img src={state.src} alt={source.label} /> : null}
          {state.kind === 'running' ? <p>rendering…</p> : null}
        </div>
        {overlay}
      </div>
    </section>
  );
}
