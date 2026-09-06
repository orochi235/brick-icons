import { DEFAULT_PARAMS } from '@lab/corpus/params';

/** The on-screen cell size each baked level is meant to cover. */
const BANDS: readonly [number, number][] = [[8, 16], [32, 64], [128, Infinity]];

/** The level a cell of `px` on screen wants, ignoring what is loaded. */
export function levelFor(px: number): number {
  for (const [level, top] of BANDS) if (px < top) return level;
  return BANDS[BANDS.length - 1]![0];
}

/** The level to actually use, given the one in hand.
 *
 *  Straight thresholds re-upload every frame when a zoom parks on a boundary,
 *  so a level is kept until the cell size is half again past its band.
 *  `upFactor`/`downFactor` default to the params panel's own tuned values. */
export function pickLevel(current: number, px: number,
                          upFactor = DEFAULT_PARAMS.levelUpHysteresis,
                          downFactor = DEFAULT_PARAMS.levelDownHysteresis): number {
  const wanted = levelFor(px);
  if (wanted === current) return current;
  return wanted > current
    ? (levelFor(px / upFactor) > current ? wanted : current)
    : (levelFor(px / downFactor) < current ? wanted : current);
}
