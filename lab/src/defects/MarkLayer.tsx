import { useRef, useState } from 'react';
import type { Camera } from '@lab/panes/camera';
import { type Box, type Mark, markFromDrag, markToScreen, normalizeMark }
  from '@lab/defects/geometry';
import { seenMatches } from '@lab/defects/identity';
import type { Defect } from '@lab/defects/useDefects';
import '@lab/defects/MarkLayer.css';

export interface MarkLayerProps {
  defects: Defect[];
  box: Box;
  camera: Camera;
  config: Record<string, unknown>;
  /** Whether a drag draws a mark. Off, the pane beneath keeps the drag to pan. */
  armed?: boolean;
  onDraw: (mark: Mark) => void;
  onSelect: (id: string) => void;
}

export function MarkLayer({ defects, box, camera, config, armed = false,
                            onDraw, onSelect }: MarkLayerProps) {
  const start = useRef<{ x: number; y: number } | null>(null);
  const [drawing, setDrawing] = useState<Mark | null>(null);

  const boxStyle = (mark: Mark) => {
    const r = markToScreen(mark, box, camera);
    return { left: `${r.left}px`, top: `${r.top}px`,
             width: `${r.width}px`, height: `${r.height}px` };
  };

  const local = (e: { clientX: number; clientY: number; currentTarget: Element }) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  return (
    <div
      className={armed ? 'mark-layer mark-layer-armed' : 'mark-layer'}
      // Armed, a drag draws instead of panning; unarmed, the layer is
      // transparent to the pane's own drag.
      data-no-drag={armed ? '' : undefined}
      onPointerDown={(e) => {
        // A draw starts on bare canvas. A press on a mark already drawn is a
        // press on that mark, armed or not.
        if (!armed || e.target !== e.currentTarget) return;
        start.current = local(e);
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (start.current) setDrawing(markFromDrag(start.current, local(e), box, camera));
      }}
      onPointerUp={(e) => {
        const from = start.current;
        start.current = null;
        setDrawing(null);
        if (!from) return;
        const mark = normalizeMark(markFromDrag(from, local(e), box, camera));
        if (mark) onDraw(mark);
      }}
    >
      {defects.map((d) => {
        const stale = !seenMatches(d.seen, config);
        const classes = ['mark', stale ? 'mark-stale' : '',
                         d.status === 'fixed' ? 'mark-fixed' : ''].filter(Boolean);
        return (
          <div
            key={d.id}
            className={classes.join(' ')}
            title={stale ? `${d.title} (seen at other settings)` : d.title}
            role="button"
            tabIndex={0}
            style={boxStyle(d.mark)}
            data-no-drag=""
            onClick={() => onSelect(d.id)}
            onKeyDown={(e) => { if (e.key === 'Enter') onSelect(d.id); }}
          />
        );
      })}
      {drawing ? <div className="mark-drawing" style={boxStyle(drawing)} /> : null}
    </div>
  );
}
