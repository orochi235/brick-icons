import { DEFAULT_PARAMS } from '@lab/corpus/params';

/** Not a raster size -- the rung above the 128px loose PNG, where a cell
 *  draws its live SVG instead of upscaling that PNG. */
export const VECTOR_LEVEL = 512;

/** The on-screen cell size each BAKED level is meant to cover. Past the last
 *  raster rung a cell wants the vector instead of a bigger bake, so the
 *  vector is the fall-through rather than a band of its own -- which is what
 *  lets the last rung's top be inclusive. */
const BANDS: readonly [number, number][] = [[8, 16], [32, 64], [128, 128]];

/** The level a cell of `px` on screen wants, ignoring what is loaded.
 *
 *  The last raster rung owns its own size. The cell-size slider's maximum IS
 *  128, and a strict `<` there sent the top notch to the vector rung and
 *  skipped the 128px bake entirely. */
export function levelFor(px: number): number {
  const last = BANDS.length - 1;
  for (let i = 0; i < BANDS.length; i++) {
    const [level, top] = BANDS[i]!;
    if (i === last ? px <= top : px < top) return level;
  }
  return VECTOR_LEVEL;
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
