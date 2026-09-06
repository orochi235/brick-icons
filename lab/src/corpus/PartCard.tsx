import { useEffect, useRef } from 'react';
import type { Cell } from '@lab/corpus/types';
import '@lab/corpus/PartCard.css';

const WIDTH = 320;
const HEIGHT = 190;
const MARGIN = 8;
// Offset the card past the clicked cell, so it never lands directly on top
// of what was clicked.
const OFFSET = 16;

/** Names what the wall's colour and ring are saying about this cell. */
function cellState(cell: Cell): string | null {
  if (cell.open_defects > 0)
    return `${cell.open_defects} open defect${cell.open_defects === 1 ? '' : 's'}`;
  if (cell.error === 'TimeoutError') return 'render timed out';
  if (cell.error) return `cannot be drawn: ${cell.error}`;
  if (cell.open_defects_elsewhere > 0)
    return `${cell.open_defects_elsewhere} open defect${cell.open_defects_elsewhere === 1 ? '' : 's'} in another slot`;
  if (cell.error_elsewhere) return 'fails in another slot';
  return null;
}

export function PartCard({ cell, source, at, viewport, onOpen, onClose }: {
  cell: Cell;
  source: string;
  at: { x: number; y: number };
  viewport: { width: number; height: number };
  onOpen: (id: string) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const x = Math.max(MARGIN,
      Math.min(at.x + OFFSET, viewport.width - WIDTH - MARGIN));
    const y = Math.max(MARGIN,
      Math.min(at.y + OFFSET, viewport.height - HEIGHT - MARGIN));
    el.style.setProperty('--card-x', `${x}px`);
    el.style.setProperty('--card-y', `${y}px`);
  }, [at, viewport]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="corpus-card" ref={ref} role="dialog"
         aria-label={`${cell.title} card`}>
      <h3 className="corpus-card-title">{cell.title}</h3>
      <p className="corpus-card-sub">
        {cell.id} · {cell.category ?? 'uncategorised'} · {cell.status}
      </p>
      {cellState(cell) && <p className="corpus-card-state">{cellState(cell)}</p>}
      <div className="corpus-card-body">
        {cell.sha ? (
          <img className="corpus-card-thumb" alt={`${cell.id} render`}
               src={`/api/thumbs/${source}/128/${cell.id}.png`} />
        ) : (
          <p className="corpus-card-none">not rendered</p>
        )}
        <dl className="corpus-card-stats">
          {cell.extra_d99 !== null && (
            <>
              <dt>extra d99</dt><dd>{cell.extra_d99}</dd>
            </>
          )}
          {cell.secs !== null && (
            <>
              <dt>secs</dt><dd>{cell.secs}</dd>
            </>
          )}
        </dl>
      </div>
      <button type="button" className="corpus-card-open"
              onClick={() => onOpen(cell.id)}>
        Open
      </button>
    </div>
  );
}
