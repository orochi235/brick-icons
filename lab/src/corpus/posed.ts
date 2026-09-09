/** What LDraw's `!PREVIEW` line says, in words.
 *
 *  A part declaring one is the library stating the view it should be shown
 *  from, which the wall's single global angle ignores -- so the note beside a
 *  render is a warning that the drawing may be of the part's blank side.
 *
 *  Every one of the 394 declarations in the library is a 90 degree multiple,
 *  which is why naming the axis and the quarter is enough and no general
 *  formatting of an arbitrary angle is wanted.
 */

/** `!PREVIEW <color> <x> <y> <z> <a..i>` -- the same shape as a type-1
 *  line's transform, so the 3x3 starts at the fifth number. */
const MATRIX_AT = 4;
const TERMS = MATRIX_AT + 9;

const AXIS_NAMES = ['X', 'Y', 'Z'];

const QUARTERS: Record<number, string> = {
  90: 'quarter turn', 180: 'half turn', 270: 'three quarter turn',
};

export function poseNote(preview: string | null | undefined): string | null {
  const nums = (preview ?? '').trim().split(/\s+/).filter((t) => t.length > 0)
    .map(Number);
  if (nums.length < TERMS || nums.some((n) => !Number.isFinite(n))) return null;
  const [a = 0, b = 0, c = 0, d = 0, e = 0, f = 0, g = 0, h = 0, i = 0] =
    nums.slice(MATRIX_AT, TERMS);

  const cos = Math.min(1, Math.max(-1, (a + e + i - 1) / 2));
  const degrees = Math.round((Math.acos(cos) * 180) / Math.PI);
  if (degrees === 0) return null;

  // For a half turn the usual (h-f, c-g, d-b) axis is all zeros, so it comes
  // off the diagonal instead: the k'th entry is 2*axis[k]^2 - 1.
  const axis = degrees === 180
    ? [(a + 1) / 2, (e + 1) / 2, (i + 1) / 2]
    : [h - f, c - g, d - b].map(Math.abs);
  let best = 0;
  for (let k = 1; k < 3; k += 1) if ((axis[k] ?? 0) > (axis[best] ?? 0)) best = k;

  const turn = QUARTERS[degrees] ?? `${degrees} degree turn`;
  return `${turn} about ${AXIS_NAMES[best]}`;
}
