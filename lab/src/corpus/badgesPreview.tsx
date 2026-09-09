import { StrictMode, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import '@weasel-js/labkit/styles.css';
import { BADGE_FACE, BADGE_WEIGHT, drawBadge } from '@lab/corpus/badges';
import { BadgeSwatch } from '@lab/corpus/BadgeSwatch';
import { CORNER_BADGES, STRIP_BADGES, type CellBadge } from '@lab/corpus/paint';
import { Tags } from '@lab/corpus/tags';
import { STATUS_BADGES } from '@lab/defects/statusBadges';
import '@lab/corpus/badgesPreview.css';

/** Every badge at the sizes the wall actually draws them, on one shared
 *  baseline. The marks are canvas geometry, so a test cannot tell you a
 *  horseshoe reads as a letter U -- only looking can, and reloading the wall
 *  to look costs a full corpus fetch and a bake. */

/** `size` runs 9..20 on the wall and the strip sets at the caption's 10..18;
 *  the last is a magnifier, not a size the wall reaches. */
const SIZES = [10, 14, 18, 44];
const COL = 150;
const ROW = 130;
const WEIGHT = 400;
const FACE = 'ui-monospace, monospace';

function draw(canvas: HTMLCanvasElement, entries: [string, CellBadge][]) {
  const dpr = window.devicePixelRatio || 1;
  const w = COL * entries.length;
  const h = ROW * SIZES.length + 40;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.scale(dpr, dpr);
  // The sheet's ground follows the theme rather than being paper-white: a
  // white badge on a white page is a badge you cannot see.
  const dark = document.documentElement.dataset.wzlMode === 'dark'
    || (!document.documentElement.dataset.wzlMode
        && window.matchMedia('(prefers-color-scheme: dark)').matches);
  ctx.fillStyle = dark ? '#000000' : '#ffffff';
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = dark ? '#cccccc' : '#333333';
  ctx.font = `13px ${BADGE_FACE}`;
  ctx.textAlign = 'center';
  entries.forEach(([name], i) => ctx.fillText(name, i * COL + COL / 2, 22));

  for (const [r, size] of SIZES.entries()) {
    const radius = size * 0.72;
    const mid = 40 + r * ROW + ROW / 2;
    ctx.save();
    ctx.font = `${BADGE_WEIGHT} ${size}px ${BADGE_FACE}`;
    const baseline = mid + ctx.measureText('H').actualBoundingBoxAscent / 2;
    ctx.restore();
    entries.forEach(([, badge], i) => {
      // Through the wall's own drawBadge, never a copy of it: a preview that
      // forks the draw path stops being evidence about the wall, which is
      // how duplo's ring went on looking a size larger than every other
      // badge after the wall had stopped drawing it that way.
      drawBadge(ctx, badge, {
        cx: i * COL + COL / 2, cy: mid, size, radius, baseline,
      });
    });
  }
}

/** The same badges the sheet above draws, as the DOM builds them. Both read
 *  `MARK_SHAPES`, so a mark that differs between the two rows is drift, and
 *  the point of the page is that you can see it without measuring. */
const DOM_SIZES = [14, 17, 24, 44];

function BadgeRows({ entries, ground }:
                   { entries: [string, CellBadge][]; ground: 'light' | 'dark' }) {
  return (
    <div className="badge-dom" data-ground={ground}>
      {DOM_SIZES.map((box) => (
        <div key={box} className="badge-dom-row">
          <span className="badge-dom-size">{box}px</span>
          {entries.map(([tag, badge]) => (
            <BadgeSwatch key={tag} badge={badge} label={tag} box={box} />
          ))}
        </div>
      ))}
      <div className="badge-dom-row">
        <span className="badge-dom-size">bare</span>
        {entries.map(([tag, badge]) => (
          <BadgeSwatch key={tag} badge={badge} box={17} />
        ))}
      </div>
      <div className="badge-dom-row">
        <span className="badge-dom-size">status</span>
        {Object.entries(STATUS_BADGES).map(([status, badge]) => (
          badge && <BadgeSwatch key={status} badge={badge} label={status} box={17} />
        ))}
      </div>
      {/* The tag row as a detail view builds it, wrapper CSS and all. */}
      <div className="badge-dom-row">
        <span className="badge-dom-size">tags</span>
        <Tags tags={['retired', 'sticker', 'technic', 'brittle']} />
      </div>
    </div>
  );
}

function BadgeSheet() {
  const ref = useRef<HTMLCanvasElement>(null);
  const entries: [string, CellBadge][] = [
    ...Object.entries(CORNER_BADGES), ...Object.entries(STRIP_BADGES),
  ];
  useEffect(() => {
    if (ref.current) draw(ref.current, entries);
  });
  return (
    <>
      <BadgeRows entries={entries} ground="light" />
      <BadgeRows entries={entries} ground="dark" />
      <canvas ref={ref} />
    </>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode><BadgeSheet /></StrictMode>,
);
