import { useMemo } from 'react';
import { FloatingPanel } from '@weasel-js/labkit';
import { BadgeSwatch } from '@lab/corpus/BadgeSwatch';
import { ALL_BADGES, tally } from '@lab/corpus/paint';
import { CELL_STATES, DEFAULT_PALETTE, LEGEND_STATES, STATE_CSS_VAR,
         STATE_FAMILY, STATE_LABEL, STATE_SHAPE,
         type CellState } from '@lab/corpus/palette';
import type { Cell } from '@lab/corpus/types';
import '@lab/corpus/Legend.css';

export interface LegendProps {
  cells: Cell[];
  /** What the tag rows count over. They are filters as well as a readout, so
   *  counting them over `cells` collapses every other row to 0 the moment one
   *  is picked -- the menu destroys the information you would pick from next.
   *  Pass the wall narrowed by everything *except* the tag picks. Two tags
   *  picked will not sum to the wall's total; that is the price of the row
   *  staying a menu, and the sidebar's category counts already pay it. */
  tagCells?: Cell[];
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
  /** Dismissal is the topbar's to own: a legend that closed itself had no way
   *  back short of a reload. */
  onClose: () => void;
}

/** The wall's conditions, with a swatch, a name and a count over the wall.
 *  Hovering or focusing a row raises `highlight`; `Wall` dims every cell
 *  outside that row's family rather than brightening the ones in it. */
export function Legend({ cells, tagCells, highlight, onHighlight,
                        badges, onBadges,
                        highlightTag, onHighlightTag, onClose }: LegendProps) {
  const counts = useMemo(() => {
    // A row stands for its siblings too, so the rows still add up to the
    // wall: `timed out` counts the 1,930 parts that timed out in another
    // slot, which have no row of their own any more.
    const per = tally(cells);
    const out = Object.fromEntries(
      LEGEND_STATES.map((s) => [s, 0])) as Record<CellState, number>;
    for (const state of CELL_STATES) out[STATE_FAMILY[state]] += per[state];
    return out;
  }, [cells]);
  const forTags = tagCells ?? cells;
  const badgeCounts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const tag of Object.keys(ALL_BADGES)) out[tag] = 0;
    for (const cell of forTags) {
      for (const tag of cell.tags ?? []) {
        if (tag in out) out[tag] = (out[tag] ?? 0) + 1;
      }
    }
    return out;
  }, [forTags]);
  const toggle = (tag: string) => {
    onBadges((prev) => (prev.includes(tag) ? prev.filter((t) => t !== tag)
                                           : [...prev, tag]));
  };

  return (
    <FloatingPanel anchor="top-right" storageKey="brick-icons-lab.corpus-legend"
      className="corpus-legend">
      <div className="corpus-legend-head">
        <strong>Legend</strong>
        <button type="button" aria-label="Close legend" onClick={onClose}>
          x
        </button>
      </div>
      <ul className="corpus-legend-list">
        {/* Swatch colors come from the state table, not from a rule per
            state: the CSS enumerated seven of eleven and two states drew
            blank. `var(...)` rather than a literal keeps the params panel's
            live tuning reaching the swatch. */}
        {LEGEND_STATES.map((state) => (
          <li key={state} className="corpus-legend-item">
            <div className="corpus-legend-row" data-state={state}
                 data-struck={DEFAULT_PALETTE[state].border !== null}
                 data-shape={STATE_SHAPE[state]}
                 data-weight={DEFAULT_PALETTE[state].weight ?? 'none'}
                 style={{
                   ['--swatch-fill' as string]: `var(${STATE_CSS_VAR[state].fill})`,
                   ['--swatch-line' as string]: STATE_CSS_VAR[state].border === null
                     ? 'transparent' : `var(${STATE_CSS_VAR[state].border})`,
                 } as React.CSSProperties}
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
              <BadgeSwatch badge={badge} className="corpus-legend-badge" />
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
