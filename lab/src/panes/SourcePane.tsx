import { type ReactNode, useEffect, useRef, useState } from 'react';
import { type Camera, panBy, zoomAt } from '@lab/panes/camera';
import { PaneStage, type PaneState } from '@lab/panes/PaneStage';
import { bubbleDiameter, loupeCamera, stageOffset, type Point }
  from '@lab/panes/loupe';
import type { Source } from '@lab/panes/sources';
import '@lab/panes/SourcePane.css';

export type { PaneState };

export interface LoupeView {
  /** Where the cursor is, in body pixels. */
  at: Point;
  factor: number;
  /** A pane whose drawing is not DOM supplies it as an image instead. The 3D
   *  pane's snapshot is the only one. */
  image?: string | null;
}

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
  /** The magnifier over this pane, or null when it is elsewhere. */
  loupe?: LoupeView | null;
  /** Where the pointer is in this pane's body, and null when it leaves.
   *  Passed only while the loupe is live -- it fires on every move. */
  onHover?: (at: Point | null) => void;
  /** One notch of the wheel while Alt is down: +1 in, -1 out. */
  onFactor?: (steps: number) => void;
}

/** A press inside an overlay child that wants the pointer for itself -- a
 *  mark to click, a drag that draws one -- must not also pan the pane.
 *  `data-no-drag` is the attribute labkit's own panels honour, so an overlay
 *  says it once instead of stopping the event on every child. */
function startsPan(target: EventTarget | null): boolean {
  return !(target instanceof Element) || !target.closest('[data-no-drag]');
}

export function SourcePane({ source, state, camera, onCamera, note, busy,
                             overlay, onBox, loupe, onHover, onFactor }: SourcePaneProps) {
  const dragging = useRef(false);
  const body = useRef<HTMLDivElement | null>(null);
  // The callback goes through a ref so the effect does not re-subscribe when
  // the caller passes a fresh arrow each render -- which it will, because it
  // is written inline inside a map over the sources.
  const report = useRef(onBox);
  report.current = onBox;

  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = body.current;
    if (!el) return;
    const emit = () => {
      const box = { width: el.clientWidth, height: el.clientHeight };
      setSize(box);
      report.current?.(box);
    };
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
          if (onHover) {
            const box = e.currentTarget.getBoundingClientRect();
            onHover({ x: e.clientX - box.left, y: e.clientY - box.top });
          }
        }}
        onPointerLeave={() => onHover?.(null)}
        onWheel={(e) => {
          if (e.altKey && onFactor) {
            onFactor(e.deltaY < 0 ? 1 : -1);
            return;
          }
          const box = e.currentTarget.getBoundingClientRect();
          const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
          onCamera(zoomAt(camera, factor, e.clientX - box.left, e.clientY - box.top));
        }}
      >
        <PaneStage state={state} camera={camera} label={source.label} busy={busy} />
        {overlay}
        {loupe && size.width >= 1 ? (
          <div className="pane-loupe"
            style={{ left: `${loupe.at.x}px`, top: `${loupe.at.y}px`,
                     width: `${bubbleDiameter(size)}px`,
                     height: `${bubbleDiameter(size)}px` }}>
            <div className="pane-loupe-inner"
              style={{
                left: `${stageOffset(loupe.at, bubbleDiameter(size)).x}px`,
                top: `${stageOffset(loupe.at, bubbleDiameter(size)).y}px`,
                width: `${size.width}px`, height: `${size.height}px`,
              }}>
              <PaneStage
                state={loupe.image ? { kind: 'image', src: loupe.image } : state}
                camera={loupeCamera(camera, loupe.factor, loupe.at)}
                label={source.label} />
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
