import { type ReactNode, useEffect, useRef } from 'react';
import { type Camera, panBy, zoomAt } from '@lab/panes/camera';
import { PaneStage, type PaneState } from '@lab/panes/PaneStage';
import type { Source } from '@lab/panes/sources';
import '@lab/panes/SourcePane.css';

export type { PaneState };

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

/** A press inside an overlay child that wants the pointer for itself -- a
 *  mark to click, a drag that draws one -- must not also pan the pane.
 *  `data-no-drag` is the attribute labkit's own panels honour, so an overlay
 *  says it once instead of stopping the event on every child. */
function startsPan(target: EventTarget | null): boolean {
  return !(target instanceof Element) || !target.closest('[data-no-drag]');
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
          // Secondary and middle drags belong to whatever the overlay does
          // with them -- on the 3D pane, orbiting.
          if (e.button !== 0 || !startsPan(e.target)) return;
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
        <PaneStage state={state} camera={camera} label={source.label} busy={busy} />
        {overlay}
      </div>
    </section>
  );
}
