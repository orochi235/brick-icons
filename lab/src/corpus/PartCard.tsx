import { useEffect, useRef } from 'react';
import { cellState } from '@lab/corpus/paint';
import { Tags, yearRange } from '@lab/corpus/tags';
import { cellValue, formatScale, SCALE_LABEL, type TintMode }
  from '@lab/corpus/tint';
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
const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`;

function cellStateLabel(cell: Cell): string | null {
  switch (cellState(cell)) {
    case 'review':
      return `${plural(cell.review_defects, 'defect')} redrawn since last looked at`;
    case 'defect':
      return `${plural(cell.open_defects, 'open defect')}`;
    case 'timeout':
      return 'render timed out';
    case 'failed':
      return `render error: ${cell.error}`;
    case 'reviewElsewhere':
      return 'a defect was redrawn in another slot';
    case 'defectElsewhere':
      return 'open defect in another slot';
    case 'timeoutElsewhere':
      return 'times out in another slot';
    case 'failedElsewhere':
      return 'errors in another slot';
    case 'outOfScope':
      return 'currently out of scope';
    case 'accepted':
      return `${plural(cell.accepted_defects, 'known issue')}, not being fixed`;
    case 'notApplicable':
      return 'nothing for this slot to draw';
    case 'unknown':
      return null;
  }
}

export function PartCard({ cell, source, at, viewport, tint = 'status',
                          onOpen, onClose, onHoverChange }: {
  cell: Cell;
  source: string;
  /** What the wall is colored by. The card is how you find out why a cell is
   *  the shade it is, so the fact behind that shade leads its stats -- and
   *  says "not measured" rather than going missing, which is the difference
   *  between a part with no timing and a part this card forgot. */
  tint?: TintMode;
  at: { x: number; y: number };
  viewport: { width: number; height: number };
  onOpen: (id: string) => void;
  onClose: () => void;
  /** Whether the pointer is over the card. The wall drops the card on a zoom,
   *  and this is the exception: the one you are reading stays. */
  onHoverChange?: (over: boolean) => void;
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
         aria-label={`${cell.title} card`}
         onPointerEnter={() => onHoverChange?.(true)}
         onPointerLeave={() => onHoverChange?.(false)}>
      <div className="corpus-card-head">
        {cell.sha ? (
          <img className="corpus-card-thumb" alt={`${cell.id} render`}
               src={`/api/thumbs/${source}/128/${cell.id}.webp`} />
        ) : (
          <p className="corpus-card-none">not rendered</p>
        )}
        <div className="corpus-card-text">
          <h3 className="corpus-card-title">{cell.title}</h3>
          <p className="corpus-card-sub">
            {cell.id} · {cell.category ?? 'uncategorized'} · {cell.status}
            {years ? ` · ${years}` : ''}
          </p>
          <Tags tags={cell.tags} />
          {cellStateLabel(cell) && <p className="corpus-card-state">{cellStateLabel(cell)}</p>}
          <dl className="corpus-card-stats">
            {tint !== 'status' && (
              <>
                <dt className="corpus-card-tinted">{SCALE_LABEL[tint]}</dt>
                <dd className="corpus-card-tinted">
                  {cellValue(cell, tint) === null
                    ? 'not measured'
                    : formatScale(tint, cellValue(cell, tint)!)}
                </dd>
              </>
            )}
            {cell.extra_d99 !== null && (
              <>
                <dt>extra d99</dt><dd>{cell.extra_d99}</dd>
              </>
            )}
            {/* Not under a `secs` tint: the row above is already this
                number, said in the units the scale uses. */}
            {cell.secs !== null && tint !== 'secs' && (
              <>
                <dt>render time</dt><dd>{cell.secs}</dd>
              </>
            )}
          </dl>
        </div>
      </div>
      <button type="button" className="corpus-card-open"
              onClick={() => onOpen(cell.id)}>
        Open
      </button>
    </div>
  );
}
