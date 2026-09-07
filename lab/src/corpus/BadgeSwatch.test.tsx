import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { BadgeSwatch } from '@lab/corpus/BadgeSwatch';
import { MARK_SHAPES } from '@lab/corpus/markShapes';
import { ALL_BADGES } from '@lab/corpus/paint';
import { STATUS_BADGES } from '@lab/defects/statusBadges';

/** Every mark reaches the DOM as path data. A shape that came out empty --
 *  a frame or a clip that stopped producing points -- draws nothing and looks
 *  like a badge that simply has no mark. */
test('every mark is path data, and none of it is degenerate', () => {
  for (const [name, shapes] of Object.entries(MARK_SHAPES)) {
    expect(shapes.length, name).toBeGreaterThan(0);
    for (const shape of shapes) {
      expect(shape.d, `${name}: ${JSON.stringify(shape)}`).toMatch(/^M-?[\d.]/);
      expect(shape.d, name).not.toMatch(/NaN|Infinity|undefined/);
    }
  }
});

test('a badge with a mark draws it as SVG, in the badge\'s own inks', () => {
  const { container } = render(<BadgeSwatch badge={ALL_BADGES.magnet!}
                                            label="magnet" />);
  const paths = [...container.querySelectorAll('path')];
  expect(paths.length).toBe(MARK_SHAPES.magnet!.length);
  // The horseshoe in the ink, its poles in the accent.
  expect(paths.map((p) => p.getAttribute('fill')))
    .toEqual([ALL_BADGES.magnet!.ink, ALL_BADGES.magnet!.accent]);
  expect(container.querySelector('canvas')).toBeNull();
});

test('a badge with a letter sets it as text, not as artwork', () => {
  render(<BadgeSwatch badge={ALL_BADGES.weird!} label="weird" />);
  // The badge is aria-hidden, so the glyph is found by its text alone.
  expect(screen.getByText('Ψ')).toBeTruthy();
  expect(screen.getByText('weird')).toBeTruthy();
});

/** A status carries neither a mark nor a letter, so it has no disc to hold
 *  the word off -- and must not reserve one. */
test('a markless badge gets no disc', () => {
  const { container } = render(<BadgeSwatch badge={STATUS_BADGES.open!}
                                            label="open" />);
  expect(container.querySelector('.corpus-badge')!.getAttribute('data-disc'))
    .toBe('false');
  expect(container.querySelector('.corpus-badge-disc')).toBeNull();
});

/** The sticker's peel is a hole, not a patch of another color: on the canvas
 *  a `destination-out` fill, here a mask over the whole pill. */
test('a mark that erases part of its badge becomes a mask', () => {
  const { container } = render(<BadgeSwatch badge={ALL_BADGES.sticker!}
                                            label="sticker" />);
  const badge = container.querySelector('.corpus-badge') as HTMLElement;
  expect(badge.getAttribute('data-cut')).toBe('true');
  expect(badge.style.getPropertyValue('--badge-cut')).toContain('image/svg+xml');
  // The punch is drawn by the mask, never painted into the disc.
  expect(container.querySelectorAll('svg.corpus-badge-art path').length)
    .toBe(MARK_SHAPES.stickerPolice!.filter((s) => !s.punch).length);
});
