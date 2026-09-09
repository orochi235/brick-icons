import { useId } from 'react';
import { BADGE_FACE, BADGE_WEIGHT, LABEL_GAP, LABEL_PAD, LABEL_WEIGHT,
  markInk, ringWidth, washToward } from '@lab/corpus/badges';
import { MARK_SHAPES, type MarkShape } from '@lab/corpus/markShapes';
import type { CellBadge } from '@lab/corpus/paint';
import '@lab/corpus/BadgeSwatch.css';

/** Sized so a badge comes out the same 14px across as the legend's state
 *  swatches -- the two halves of that panel are one list to read down. */
export const SWATCH_BOX = 14;

/** A badge as HTML: the field and the word in CSS, the mark as inline SVG.
 *
 *  What a detail view and a cell must share is the *data* -- the palette
 *  record in `paint.ts` and the geometry in `markShapes.ts` -- not the
 *  rasterizer. Drawing this through the wall's canvas instead hand-computed a
 *  text baseline the browser already knows, and set the word 7.5 device px
 *  above the field's center.
 */
export function BadgeSwatch({ badge, label, box = SWATCH_BOX, className }:
                            { badge: CellBadge; label?: string; box?: number;
                              className?: string }) {
  const radius = box / 2;
  // The type size the canvas derives from a disc of this radius, so a swatch
  // and a cell badge set their words at one size.
  const size = radius / 0.72;
  const scale = badge.scale ?? 1;
  const shapes = badge.mark ? MARK_SHAPES[badge.mark] : undefined;
  const disc = shapes != null || badge.text != null;
  const cut = cutMask(shapes, box, radius * 0.66 * scale);
  const labelled = label != null;
  const field = labelled
    ? badge.labelField ?? washToward(badge.field) : badge.field;
  const vars = {
    '--badge-box': `${box}px`,
    '--badge-field': field,
    '--badge-disc-field': badge.field,
    '--badge-stroke': badge.stroke ?? field,
    '--badge-ink': labelled ? badge.labelInk ?? badge.ink : badge.ink,
    '--badge-mark-ink': badge.ink,
    '--badge-line': `${ringWidth(radius, badge)}px`,
    '--badge-face': BADGE_FACE,
    '--badge-weight': `${badge.weight ?? BADGE_WEIGHT}`,
    '--badge-label-weight': `${LABEL_WEIGHT}`,
    '--badge-text': `${size * 0.92}px`,
    // Mark to word, and word to the end of the field.
    '--badge-gap': `${size * LABEL_GAP}px`,
    '--badge-pad': `${size * LABEL_PAD}px`,
    '--badge-glyph-face': badge.font ?? BADGE_FACE,
    '--badge-glyph': `${size * scale}px`,
    '--badge-glyph-style': badge.style ?? 'normal',
    '--badge-dx': `${size * (badge.dx ?? 0)}px`,
    '--badge-dy': `${size * (badge.dy ?? 0)}px`,
    ...(cut ? { '--badge-cut': cut } : {}),
  } as React.CSSProperties;
  return (
    <span className={`corpus-badge ${className ?? ''}`} style={vars}
          data-disc={disc} data-label={label != null} data-cut={cut != null}
          data-ring={badge.ringOnDisc ? 'disc' : 'field'}
          aria-hidden="true">
      {disc && (
        <span className="corpus-badge-disc">
          {shapes && <BadgeArt badge={badge} shapes={shapes} box={box} />}
          {badge.text && <span className="corpus-badge-glyph">{badge.text}</span>}
        </span>
      )}
      {label != null && <span className="corpus-badge-label">{label}</span>}
    </span>
  );
}

/** The mark, in px against a `box`-wide viewBox -- the frame `drawBadge`
 *  works in too, so the two read off the same numbers. */
function BadgeArt({ badge, shapes, box }:
                  { badge: CellBadge; shapes: readonly MarkShape[]; box: number }) {
  const id = useId();
  const radius = box / 2;
  // The mark's unit box: 1 unit is 0.66 of the radius, so a mark may run out
  // past the field's edge, where the disc clips it.
  const m = radius * 0.66 * (badge.scale ?? 1);
  return (
    <svg className="corpus-badge-art" viewBox={`0 0 ${box} ${box}`}
         xmlns="http://www.w3.org/2000/svg" focusable="false">
      <clipPath id={id} clipPathUnits="userSpaceOnUse">
        <circle cx={radius} cy={radius} r={radius} />
      </clipPath>
      <g clipPath={`url(#${id})`}>
        <g transform={`translate(${radius} ${radius}) scale(${m})`}>
          {shapes.filter((s) => !s.punch)
                 .map((s, i) => <MarkPath key={i} shape={s} badge={badge} />)}
        </g>
      </g>
    </svg>
  );
}

/** A mark that erases part of its own badge -- a sticker's peel -- as a mask
 *  image for the whole pill. On the canvas the same path is a
 *  `destination-out` fill; here it is subtracted from the field, so the hole
 *  shows the page rather than a patch of another color.
 *
 *  Its own image rather than an SVG `<mask>` because what it cuts is the CSS
 *  field, which the disc's `<svg>` does not paint. */
function cutMask(shapes: readonly MarkShape[] | undefined, box: number,
                 m: number): string | undefined {
  const cut = shapes?.filter((s) => s.punch) ?? [];
  if (cut.length === 0) return undefined;
  const r = box / 2;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${box} ${box}">`
    + `<g transform="translate(${r} ${r}) scale(${m})">`
    + cut.map((s) => `<path d="${s.d}"/>`).join('')
    + '</g></svg>';
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}

function MarkPath({ shape, badge }: { shape: MarkShape; badge: CellBadge }) {
  const stroke = shape.stroke ? markInk(badge, shape.stroke) : null;
  return (
    <path d={shape.d}
          fill={markInk(badge, shape.fill ?? 'ink') ?? 'none'}
          fillRule={shape.rule}
          fillOpacity={shape.alpha}
          stroke={stroke ?? undefined}
          strokeWidth={stroke ? shape.width ?? 0.1 : undefined}
          strokeLinejoin={shape.join}
          strokeLinecap={shape.cap}
          strokeOpacity={stroke ? shape.alpha : undefined}
          transform={shape.transform
            ? `matrix(${shape.transform.join(' ')})` : undefined} />
  );
}
