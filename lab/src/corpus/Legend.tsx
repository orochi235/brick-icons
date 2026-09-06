import { useMemo, useState } from 'react';
import { FloatingPanel } from '@weasel-js/labkit';
import { tally } from '@lab/corpus/paint';
import { CELL_STATES, STATE_LABEL, type CellState } from '@lab/corpus/palette';
import type { Cell } from '@lab/corpus/types';
import '@lab/corpus/Legend.css';

export interface LegendProps {
  cells: Cell[];
  highlight: CellState | null;
  onHighlight: (state: CellState | null) => void;
}

/** The wall's six states, with a swatch, a name and a corpus-wide count.
 *  Hovering or focusing a row raises `highlight`; `Wall` dims every cell
 *  that isn't in that state rather than brightening the ones that are. */
export function Legend({ cells, highlight, onHighlight }: LegendProps) {
  const counts = useMemo(() => tally(cells), [cells]);
  const [open, setOpen] = useState(true);

  if (!open) return null;

  return (
    <FloatingPanel anchor="top-right" storageKey="brick-icons-lab.corpus-legend"
      className="corpus-legend">
      <div className="corpus-legend-head">
        <strong>Legend</strong>
        <button type="button" aria-label="Close legend" onClick={() => setOpen(false)}>
          x
        </button>
      </div>
      <ul className="corpus-legend-list">
        {CELL_STATES.map((state) => (
          <li key={state} className="corpus-legend-item">
            <div className="corpus-legend-row" data-state={state}
                 data-highlighted={highlight === state} tabIndex={0}
                 aria-label={`${STATE_LABEL[state]}, ${counts[state].toLocaleString()} parts`}
                 onMouseEnter={() => onHighlight(state)}
                 onMouseLeave={() => onHighlight(null)}
                 onFocus={() => onHighlight(state)}
                 onBlur={() => onHighlight(null)}>
              <span className="corpus-legend-swatch" aria-hidden="true" />
              <span className="corpus-legend-name">{STATE_LABEL[state]}</span>
              <span className="corpus-legend-count">{counts[state].toLocaleString()}</span>
            </div>
          </li>
        ))}
      </ul>
    </FloatingPanel>
  );
}
