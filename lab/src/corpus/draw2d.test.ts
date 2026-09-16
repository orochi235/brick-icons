import { expect, it } from 'vitest';
import { cornerBadgeAt, cornerBadgesAt } from '@lab/corpus/draw2d';
import { badgeGeometry, type CellBadge } from '@lab/corpus/paint';

const badge = (tag: string, corner: CellBadge['corner']): CellBadge =>
  ({ tag, corner, field: '#000', ink: '#fff' });

const BOX = { dx: 0, dy: 0, dw: 200, dh: 200 };

it('lays two discs sharing a corner out as a row, not one over the other', () => {
  // 145 parts wear two top-right badges -- 121 retired+replaces, 24
  // replaced+replaces -- and placed without an index they painted on top of
  // each other while the year caption had already shifted aside for both.
  const [first, second] = cornerBadgesAt(
    [badge('retired', 'tr'), badge('replaces', 'tr')], BOX);
  expect(first!.cx).not.toBe(second!.cx);
  expect(second!.cx).toBeLessThan(first!.cx);
  expect(second!.cy).toBe(first!.cy);
  // Far enough apart that the discs do not overlap.
  expect(first!.cx - second!.cx).toBeGreaterThanOrEqual(first!.radius * 2);
});

it('counts each corner separately, so one corner does not shift another', () => {
  const [tl, tr] = cornerBadgesAt(
    [badge('popular', 'tl'), badge('replaces', 'tr')], BOX);
  expect(tl!.cx).toBe(cornerBadgeAt(badge('popular', 'tl'), BOX).cx);
  expect(tr!.cx).toBe(cornerBadgeAt(badge('replaces', 'tr'), BOX).cx);
});

it('stacks a row too long for its half of the cell on its last place', () => {
  const many = Array.from({ length: 12 }, () => badge('replaces', 'tr'));
  const placed = cornerBadgesAt(many, BOX);
  const { inset, radius } = badgeGeometry(BOX.dw);
  // Nothing runs past the middle, where the facing corner's row starts.
  for (const disc of placed) expect(disc.cx).toBeGreaterThan(BOX.dw / 2 - inset - radius);
  expect(placed.at(-1)!.cx).toBe(placed.at(-2)!.cx);
});
