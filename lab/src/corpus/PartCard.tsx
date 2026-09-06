import { useEffect, useRef } from 'react';
import { cellState } from '@lab/corpus/paint';
import { Tags, yearRange } from '@lab/corpus/tags';
import type { Cell } from '@lab/corpus/types';
import '@lab/corpus/PartCard.css';

const WIDTH = 320;
const HEIGHT = 190;
const MARGIN = 8;
// Offset the card past the clicked cell, so it never lands directly on top
// of what was clicked.
const OFFSET = 16;

/** Names what the wall's color and ring are saying about this cell, from the
 *  same precedence `fillFor` and the legend read. */
function cellStateLabel(cell: Cell): string | null {
  switch (cellState(cell)) {
    case 'defect':
      return `${cell.open_defects} open defect${cell.open_defects === 1 ? '' : 's'}`;
    case 'timeout':
      return 'render timed out';
    case 'failed':
      return `render error: ${cell.error}`;
    case 'defectElsewhere':
      return `${cell.open_defects_elsewhere} open defect${cell.open_defects_elsewhere === 1 ? '' : 's'} in another slot`;
    case 'problemElsewhere':
      return 'fails in another slot';
    case 'outOfScope':
      return 'currently out of scope';
    case 'accepted':
      return `${cell.accepted_defects} known issue`
        + `${cell.accepted_defects === 1 ? '' : 's'}, not being fixed`;
    case 'unknown':
      return null;
  }
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

  const years = yearRange(cell.year_from, cell.year_to,
                          (cell.tags ?? []).includes('retired'));

  return (
    <div className="corpus-card" ref={ref} role="dialog"
         aria-label={`${cell.title} card`}>
      <h3 className="corpus-card-title">{cell.title}</h3>
      <p className="corpus-card-sub">
        {cell.id} · {cell.category ?? 'uncategorised'} · {cell.status}
        {years ? ` · ${years}` : ''}
      </p>
      <Tags tags={cell.tags} />
      {cellStateLabel(cell) && <p className="corpus-card-state">{cellStateLabel(cell)}</p>}
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
