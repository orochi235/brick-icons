import { expect, it } from 'vitest';
import { ALL_PARAM_FIELDS, DEFAULT_PARAMS, type Params } from '@lab/corpus/params';

// The values every one of these fields replaced -- CELL/GAP in
// CorpusWall.tsx, the six-state palette in palette.ts/corpus.css, the border
// and dim constants in paint.ts, DRAG_THRESHOLD_PX in Wall.tsx, the 1.5/0.67
// hysteresis factors in levels.ts, and POLL_MS in useCells.ts. A panel that
// silently changes the wall's look on first load is worse than no panel.
const PRE_TASK_LITERALS: Params = {
  cell: 32,
  gap: 4,
  cols: 0,

  unknownFill: '#3a3a3f',
  // No pre-task literal: the out-of-scope state was added after this
  // snapshot, so what it pins is that the state kept the color it shipped with.
  outOfScopeFill: '#241a38',
  timeoutFill: '#26383f',
  timeoutBorder: '#30b0d0',
  failedFill: '#4a2626',
  failedBorder: '#e03030',
  defectFill: '#453c27',
  defectBorder: '#daa520',
  problemElsewhereFill: '#26383f',
  problemElsewhereBorder: '#97bcc5',
  defectElsewhereFill: '#453c27',
  defectElsewhereBorder: '#c7b78f',
  caretColor: '#ffffff',

  thickBorderFactor: 0.18,
  thinBorderFactor: 0.09,
  maxBorderPx: 6,
  dimAlpha: 0.25,
  // Post-snapshot, like the out-of-scope fill: the wash replaced a ground
  // that used to be baked into the sprites.
  retiredWash: 0.35,

  dragThresholdPx: 4,
  levelUpHysteresis: 1.5,
  levelDownHysteresis: 0.67,
  pollMs: 10_000,
};

it('matches the wall\'s appearance and feel from before this schema existed', () => {
  expect(DEFAULT_PARAMS).toEqual(PRE_TASK_LITERALS);
});

it('gives every Params key exactly one field, each pointing at the default', () => {
  const fieldKeys = ALL_PARAM_FIELDS.map((f) => f.key).sort();
  const paramKeys = Object.keys(DEFAULT_PARAMS).sort();
  expect(fieldKeys).toEqual(paramKeys);
  for (const f of ALL_PARAM_FIELDS) {
    expect(f.default).toBe(DEFAULT_PARAMS[f.key as keyof Params]);
  }
});

it('leaves no field without a default', () => {
  for (const f of ALL_PARAM_FIELDS) {
    expect(f.default).not.toBeUndefined();
  }
});
