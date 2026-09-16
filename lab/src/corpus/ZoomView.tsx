import {
  useEffect, useRef, useState,
  type PointerEvent as ReactPointerEvent, type WheelEvent as ReactWheelEvent,
} from 'react';
import { createPortal } from 'react-dom';
import '@lab/corpus/ZoomView.css';

const MIN_ZOOM = 1;
// Vector renders cost nothing in fidelity, but a render's ink runs out well
// before 8x -- past that you are panning around empty magnification, not
// seeing more of the drawing.
const MAX_ZOOM = 8;

function clamp(value: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, value));
}

/** Keeps the image covering the frame once zoomed in, and centered until it
 *  is: pan can only reach as far as the image's own edge, so a drag can
 *  never carry the drawing fully off-screen. */
function clampPan(pan: { x: number; y: number }, zoom: number,
                   frame: HTMLElement | null, img: HTMLElement | null) {
  if (!frame || !img) return pan;
  const frameRect = frame.getBoundingClientRect();
  const imgRect = img.getBoundingClientRect();
  // imgRect already carries the current zoom's scale transform; dividing it
  // back out recovers the unscaled "as large as fits" size to scale from.
  const baseW = imgRect.width / zoom;
  const baseH = imgRect.height / zoom;
  const maxX = Math.max(0, (baseW * zoom - frameRect.width) / 2);
  const maxY = Math.max(0, (baseH * zoom - frameRect.height) / 2);
  return { x: clamp(pan.x, -maxX, maxX), y: clamp(pan.y, -maxY, maxY) };
}

type Drag = { id: number; startX: number; startY: number; startPan: { x: number; y: number } };

export function ZoomView({ partId, source, src, onClose }: {
  partId: string;
  source: string;
  src: string;
  onClose: () => void;
}) {
  const [{ zoom, pan }, setView] = useState({ zoom: MIN_ZOOM, pan: { x: 0, y: 0 } });
  const [dragging, setDragging] = useState(false);
  const frameRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const dragRef = useRef<Drag | null>(null);

  useEffect(() => { closeRef.current?.focus(); }, []);

  const onWheel = (e: ReactWheelEvent<HTMLDivElement>) => {
    e.preventDefault();
    const frame = frameRef.current;
    if (!frame) return;
    const rect = frame.getBoundingClientRect();
    const mx = e.clientX - rect.left - rect.width / 2;
    const my = e.clientY - rect.top - rect.height / 2;
    const factor = Math.exp(-e.deltaY * 0.0015);
    setView((prev) => {
      const nextZoom = clamp(prev.zoom * factor, MIN_ZOOM, MAX_ZOOM);
      // Hold the point under the cursor fixed as the scale changes.
      const nextPan = {
        x: mx - ((mx - prev.pan.x) / prev.zoom) * nextZoom,
        y: my - ((my - prev.pan.y) / prev.zoom) * nextZoom,
      };
      return { zoom: nextZoom, pan: clampPan(nextPan, nextZoom, frameRef.current, imgRef.current) };
    });
  };

  const onPointerDown = (e: ReactPointerEvent<HTMLImageElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { id: e.pointerId, startX: e.clientX, startY: e.clientY, startPan: pan };
    setDragging(true);
  };
  const onPointerMove = (e: ReactPointerEvent<HTMLImageElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.id !== e.pointerId) return;
    const nextPan = { x: drag.startPan.x + (e.clientX - drag.startX),
                       y: drag.startPan.y + (e.clientY - drag.startY) };
    setView((prev) => ({ ...prev, pan: clampPan(nextPan, prev.zoom, frameRef.current, imgRef.current) }));
  };
  const endDrag = () => { dragRef.current = null; setDragging(false); };

  const host = typeof document === 'undefined'
    ? null : document.querySelector('.lk-root') ?? document.body;

  const view = (
    <div className="zoomview-scrim" role="presentation" onClick={onClose}>
      <div className="zoomview-panel" role="dialog" aria-modal="true"
           aria-label={`Zoomed ${source} render of ${partId}`}
           onClick={(e) => e.stopPropagation()}>
        <button type="button" className="zoomview-close" aria-label="Close zoomed view"
                ref={closeRef} onClick={onClose}>x</button>
        <div className="zoomview-frame" ref={frameRef} onWheel={onWheel}>
          <img ref={imgRef} src={src}
               alt={`${partId} drawn by ${source}, zoomed`}
               className={dragging ? 'zoomview-img zoomview-img-dragging' : 'zoomview-img'}
               onPointerDown={onPointerDown} onPointerMove={onPointerMove}
               onPointerUp={endDrag} onPointerCancel={endDrag}
               // A per-frame pan/zoom transform has no class to live in.
               style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }} />
        </div>
      </div>
    </div>
  );

  return host ? createPortal(view, host) : view;
}
