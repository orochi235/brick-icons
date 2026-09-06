import { useEffect, useMemo, useRef, useState } from 'react';
import { FloatingPanel } from '@weasel-js/labkit';
import { drawBadge } from '@lab/corpus/badges';
import { ALL_BADGES, tally, type CellBadge } from '@lab/corpus/paint';
import { CELL_STATES, STATE_LABEL, type CellState } from '@lab/corpus/palette';
import type { Cell } from '@lab/corpus/types';
import '@lab/corpus/Legend.css';

export interface LegendProps {
  cells: Cell[];
  highlight: CellState | null;
  onHighlight: (state: CellState | null) => void;
  /** Badge tags the wall is filtered to, and a way to change them. Takes an
   *  updater rather than the next array: two rows clicked in quick
   *  succession both read `badges` from the same render, and the second
   *  would drop the first's change. */
  badges: string[];
  onBadges: (update: (prev: string[]) => string[]) => void;
  /** The tag row under the pointer, and a way to report it. Hovering a tag
   *  dims every cell without it, exactly as hovering a state row does. */
  highlightTag: string | null;
  onHighlightTag: (tag: string | null) => void;
}

/** Sized so a badge comes out the same 14px across as the state swatches
 *  above it -- the two halves of the legend are one list to read down. */
const SWATCH_BOX = 14;

/** The badge itself, drawn through the wall's own `drawBadge`. A second
 *  rendering of the same mark would drift from the one on the cells, which
 *  is the only thing this row is here to explain. */
function BadgeSwatch({ badge }: { badge: CellBadge }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const radius = SWATCH_BOX / 2;
    const box = SWATCH_BOX;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = box * dpr;
    canvas.height = box * dpr;
    canvas.style.width = `${box}px`;
    canvas.style.height = `${box}px`;
    // jsdom throws out of getContext rather than returning null, and a
    // swatch that cannot draw must not take the wall down with it.
    let ctx: CanvasRenderingContext2D | null = null;
    try {
      ctx = canvas.getContext('2d');
    } catch {
      return;
    }
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, box, box);
    drawBadge(ctx, badge, { cx: box / 2, cy: box / 2, size: radius / 0.72, radius });
  }, [badge]);
  return <canvas ref={ref} className="corpus-legend-badge" aria-hidden="true" />;
}

/** The wall's cell states, with a swatch, a name and a corpus-wide count.
 *  Hovering or focusing a row raises `highlight`; `Wall` dims every cell
 *  that isn't in that state rather than brightening the ones that are. */
export function Legend({ cells, highlight, onHighlight,
                        badges, onBadges,
                        highlightTag, onHighlightTag }: LegendProps) {
  const counts = useMemo(() => tally(cells), [cells]);
  const badgeCounts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const tag of Object.keys(ALL_BADGES)) out[tag] = 0;
    for (const cell of cells) {
      for (const tag of cell.tags ?? []) {
        if (tag in out) out[tag] = (out[tag] ?? 0) + 1;
      }
    }
    return out;
  }, [cells]);
  const [open, setOpen] = useState(true);

  const toggle = (tag: string) => {
    onBadges((prev) => (prev.includes(tag) ? prev.filter((t) => t !== tag)
                                           : [...prev, tag]));
  };

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
      <div className="corpus-legend-head corpus-legend-subhead">
        <strong>Tags</strong>
        {badges.length > 0 && (
          <button type="button" onClick={() => onBadges(() => [])}>clear</button>
        )}
      </div>
      <ul className="corpus-legend-list">
        {Object.entries(ALL_BADGES).map(([tag, badge]) => (
          <li key={tag} className="corpus-legend-item">
            <button type="button" className="corpus-legend-row corpus-legend-badge-row"
                    aria-pressed={badges.includes(tag)}
                    data-picked={badges.includes(tag)}
                    data-highlighted={highlightTag === tag}
                    aria-label={`${tag}, ${badgeCounts[tag]!.toLocaleString()} parts`}
                    onClick={() => toggle(tag)}
                    onMouseEnter={() => onHighlightTag(tag)}
                    onMouseLeave={() => onHighlightTag(null)}
                    onFocus={() => onHighlightTag(tag)}
                    onBlur={() => onHighlightTag(null)}>
              <BadgeSwatch badge={badge} />
              <span className="corpus-legend-name">{tag}</span>
              <span className="corpus-legend-count">
                {badgeCounts[tag]!.toLocaleString()}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </FloatingPanel>
  );
}
