import { expect, it } from 'vitest';
import {
  ALL_PARAM_FIELDS, APPEARANCE_FIELDS, COLOR_PARAM_KEYS, DEFAULT_PARAMS, type Params,
} from '@lab/corpus/params';
import { STATES, paramKeys } from '@lab/corpus/states';

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
  outOfScopeFill: '#b2a3dd',
  timeoutFill: '#26383f',
  timeoutBorder: '#30b0d0',
  failedFill: '#4a2626',
  failedBorder: '#e03030',
  defectFill: '#453c27',
  defectBorder: '#daa520',
  // Post-snapshot: a fault we decided to live with needed a color of its own.
  acceptedFill: '#26382c',
  acceptedBorder: '#6f9e78',
  // Post-snapshot: a defect claimed fixed and redrawn, waiting to be judged.
  reviewFill: '#3a2740',
  reviewBorder: '#d070c0',
  // Every `*Elsewhere` border is derived from its own condition's -- see
  // `washOut` in states.ts -- so these pin the output of that formula, not a
  // color anyone picked. The two that predate it moved by at most 4/255.
  reviewElsewhereFill: '#3a2740',
  reviewElsewhereBorder: '#c593bd',
  defectElsewhereFill: '#453c27',
  defectElsewhereBorder: '#c5b793',
  timeoutElsewhereFill: '#26383f',
  timeoutElsewhereBorder: '#93bbc5',
  failedElsewhereFill: '#4a2626',
  failedElsewhereBorder: '#c59393',
  caretColor: '#ffffff',

  // Both post-snapshot, and both on: a cell wore its badges and captions
  // before there was a switch, so the switch has to arrive already flipped.
  showBadges: true,
  showCaptions: true,

  thickBorderFactor: 0.18,
  thinBorderFactor: 0.09,
  maxBorderPx: 6,
  dimAlpha: 0.25,
  // Post-snapshot, like the out-of-scope fill: the wash replaced a ground
  // that used to be baked into the sprites. Deepened from 0.35 on request --
  // a retired part was not reading as retired across a wall.
  retiredWash: 0.5,

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

it('gives every color a state declares one param, and carries no orphans', () => {
  const expected = [
    ...STATES.flatMap((spec) => {
      const param = paramKeys(spec);
      return param.border === null ? [param.fill] : [param.fill, param.border];
    }),
    'caretColor',
  ];
  expect([...COLOR_PARAM_KEYS]).toEqual(expected);
});

it('defaults every state color to the table\'s own value', () => {
  for (const spec of STATES) {
    const param = paramKeys(spec);
    expect(DEFAULT_PARAMS[param.fill as keyof Params]).toBe(spec.fill);
    if (param.border !== null) {
      expect(DEFAULT_PARAMS[param.border as keyof Params]).toBe(spec.border);
    }
  }
});

it('gives every color param a labelled row in the appearance panel', () => {
  const rows = new Map(APPEARANCE_FIELDS.map((f) => [f.key, f.label]));
  for (const key of COLOR_PARAM_KEYS) {
    const label = rows.get(key);
    expect(label, `no appearance row for ${key}`).toBeTruthy();
    expect(label).not.toBe(key);
  }
});

it('keeps the color row labels the panel already showed', () => {
  const rows = new Map(APPEARANCE_FIELDS.map((f) => [f.key, f.label]));
  expect(COLOR_PARAM_KEYS.map((key) => rows.get(key))).toEqual([
    'Unknown fill', 'Out-of-scope fill', 'Review fill', 'Review border',
    'Defect fill', 'Defect border', 'Timeout fill', 'Timeout border',
    'Failed fill', 'Failed border', 'Accepted fill', 'Accepted border',
    'Review-elsewhere fill', 'Review-elsewhere border',
    'Defect-elsewhere fill', 'Defect-elsewhere border',
    'Timeout-elsewhere fill', 'Timeout-elsewhere border',
    'Failed-elsewhere fill', 'Failed-elsewhere border',
    'Caret color',
  ]);
});
