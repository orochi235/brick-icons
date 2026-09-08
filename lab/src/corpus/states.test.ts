import { expect, it } from 'vitest';
import {
  BY_PRECEDENCE, STATES, cssVarTable, labelTable, paramKeys, stateKeys,
  styleTable, washOut, type StateFacts,
} from '@lab/corpus/states';

const clean: StateFacts = {
  out_of_scope: false, open_defects: 0, review_defects: 0, error: null,
  accepted_defects: 0, elsewhere: [],
};

const everything: StateFacts = {
  out_of_scope: true, open_defects: 3, review_defects: 1,
  error: 'TimeoutError', accepted_defects: 2,
  elsewhere: ['defect', 'failed', 'timeout', 'review'],
};

const by = (key: string) => STATES.find((s) => s.key === key)!;

it('lists the states in legend order: every condition, then every sibling', () => {
  expect(stateKeys()).toEqual([
    'unknown', 'outOfScope', 'review', 'defect', 'timeout', 'failed', 'accepted',
    'reviewElsewhere', 'defectElsewhere', 'timeoutElsewhere', 'failedElsewhere',
  ]);
});

it('matches in a different order from the one it lists, worst first', () => {
  expect(BY_PRECEDENCE.map((s) => s.key)).toEqual([
    'outOfScope', 'review', 'defect', 'timeout', 'failed', 'accepted',
    'reviewElsewhere', 'defectElsewhere', 'timeoutElsewhere', 'failedElsewhere',
    'unknown',
  ]);
});

it('gives every state its own precedence', () => {
  const seen = new Set(STATES.map((s) => s.precedence));
  expect(seen.size).toBe(STATES.length);
});

// The point of the whole table: a condition and its "in another slot" twin
// are one fact drawn twice, so the twin is computed and can never be given
// the wrong parent's color by hand.
it('derives each sibling from its own condition', () => {
  for (const key of ['review', 'defect', 'timeout', 'failed'] as const) {
    const here = by(key);
    const there = by(`${key}Elsewhere`);
    expect(there.fill).toBe(here.fill);
    expect(there.border).toBe(washOut(here.border!));
    expect(there.weight).toBe('thin');
    expect(there.precedence).toBe(here.precedence + 40);
  }
});

// Both elsewhere colors were hand-picked before the formula existed; it has to
// land on them, or applying it would restyle two states nobody asked to change.
it('reproduces the two hand-written elsewhere colors', () => {
  const near = (got: string, want: string) => {
    for (let i = 1; i < 7; i += 2) {
      expect(Math.abs(parseInt(got.slice(i, i + 2), 16)
                    - parseInt(want.slice(i, i + 2), 16))).toBeLessThanOrEqual(4);
    }
  };
  near(by('defectElsewhere').border!, '#c7b78f');
  near(by('timeoutElsewhere').border!, '#97bcc5');
});

// The bug this table was rebuilt to kill: `problemElsewhere` stood for a
// render error and wore the cyan of `timeout`, because the pair was typed out
// rather than derived.
it('draws an error in another slot in the red of an error, not the blue of a timeout', () => {
  expect(by('failedElsewhere').border).toBe(washOut('#e03030'));
  expect(by('failedElsewhere').border).not.toBe(by('timeoutElsewhere').border);
  expect(by('failedElsewhere').fill).toBe(by('failed').fill);
});

it('keeps the hue and only washes out saturation and lightness', () => {
  expect(washOut('#e03030')).toMatch(/^#[0-9a-f]{6}$/);
  // Pure red in, a desaturated red out: the green and blue channels rise to
  // meet the red rather than the red falling to meet them.
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(washOut('#e03030').slice(i, i + 2), 16));
  expect(r).toBeGreaterThan(g!);
  expect(g).toBe(b);
});

// `cellState` takes the first match and asserts it found one; both halves of
// that rest on these two facts.
it('ends the match order with unknown, which matches anything', () => {
  const last = BY_PRECEDENCE[BY_PRECEDENCE.length - 1]!;
  expect(last.key).toBe('unknown');
  expect(last.match(clean)).toBe(true);
  expect(last.match(everything)).toBe(true);
});

it('gives each state the predicate the wall colors by', () => {
  expect(by('outOfScope').match({ ...clean, out_of_scope: true })).toBe(true);
  expect(by('outOfScope').match(clean)).toBe(false);
  expect(by('review').match({ ...clean, review_defects: 1 })).toBe(true);
  expect(by('review').match(clean)).toBe(false);
  expect(by('defect').match({ ...clean, open_defects: 1 })).toBe(true);
  expect(by('defect').match(clean)).toBe(false);
  expect(by('timeout').match({ ...clean, error: 'TimeoutError' })).toBe(true);
  expect(by('timeout').match({ ...clean, error: 'GEOSException' })).toBe(false);
  expect(by('failed').match({ ...clean, error: 'GEOSException' })).toBe(true);
  expect(by('failed').match(clean)).toBe(false);
  expect(by('accepted').match({ ...clean, accepted_defects: 1 })).toBe(true);
  expect(by('accepted').match(clean)).toBe(false);
});

it('matches a sibling on the condition key the server reported', () => {
  for (const key of ['review', 'defect', 'timeout', 'failed'] as const) {
    expect(by(`${key}Elsewhere`).match({ ...clean, elsewhere: [key] })).toBe(true);
    expect(by(`${key}Elsewhere`).match(clean)).toBe(false);
  }
});

// A part is out of scope everywhere at once, and a fault accepted in another
// slot says nothing about this one.
it('gives no sibling to the two conditions that cannot hold elsewhere', () => {
  expect(stateKeys()).not.toContain('outOfScopeElsewhere');
  expect(stateKeys()).not.toContain('acceptedElsewhere');
  expect(stateKeys()).not.toContain('unknownElsewhere');
});

it('carries the tuned colors and weights of the conditions', () => {
  expect(styleTable()).toMatchObject({
    unknown: { fill: '#3a3a3f', border: null, weight: null },
    outOfScope: { fill: '#b2a3dd', border: null, weight: null },
    review: { fill: '#3a2740', border: '#d070c0', weight: 'thick' },
    timeout: { fill: '#26383f', border: '#30b0d0', weight: 'thick' },
    failed: { fill: '#4a2626', border: '#e03030', weight: 'thick' },
    defect: { fill: '#453c27', border: '#daa520', weight: 'thick' },
    accepted: { fill: '#26382c', border: '#6f9e78', weight: 'thin' },
  });
});

it('names every state the way the legend does', () => {
  expect(labelTable()).toMatchObject({
    unknown: 'unknown',
    outOfScope: 'currently out of scope',
    review: 'fix claimed, needs a look',
    timeout: 'timed out',
    failed: 'render error',
    defect: 'open defect',
    accepted: 'known issue, not fixing',
    defectElsewhere: 'open defect, in another slot',
    failedElsewhere: 'render error, in another slot',
  });
});

it('generates the CSS custom property names the stylesheet already uses', () => {
  expect(cssVarTable()).toMatchObject({
    unknown: { fill: '--corpus-cell-unknown-fill', border: null },
    outOfScope: { fill: '--corpus-cell-out-of-scope-fill', border: null },
    timeout: { fill: '--corpus-cell-timeout-fill', border: '--corpus-cell-timeout-border' },
    defectElsewhere: { fill: '--corpus-cell-defect-elsewhere-fill',
                       border: '--corpus-cell-defect-elsewhere-border' },
    failedElsewhere: { fill: '--corpus-cell-failed-elsewhere-fill',
                       border: '--corpus-cell-failed-elsewhere-border' },
  });
});

it("names a state's color params, and no border param where there is no border", () => {
  expect(paramKeys(by('timeout'))).toEqual({ fill: 'timeoutFill', border: 'timeoutBorder' });
  expect(paramKeys(by('failedElsewhere')))
    .toEqual({ fill: 'failedElsewhereFill', border: 'failedElsewhereBorder' });
  expect(paramKeys(by('unknown'))).toEqual({ fill: 'unknownFill', border: null });
  expect(paramKeys(by('outOfScope'))).toEqual({ fill: 'outOfScopeFill', border: null });
});
