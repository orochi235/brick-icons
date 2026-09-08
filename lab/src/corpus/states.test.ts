import { expect, it } from 'vitest';
import {
  BY_PRECEDENCE, STATES, cssVarTable, labelTable, paramKeys, stateKeys, styleTable,
  type StateFacts,
} from '@lab/corpus/states';

const clean: StateFacts = {
  out_of_scope: false, open_defects: 0, error: null, accepted_defects: 0,
  open_defects_elsewhere: 0, error_elsewhere: false,
};

const everything: StateFacts = {
  out_of_scope: true, open_defects: 3, error: 'TimeoutError', accepted_defects: 2,
  open_defects_elsewhere: 4, error_elsewhere: true,
};

it('lists the states in legend order, unknown first', () => {
  expect(stateKeys()).toEqual([
    'unknown', 'outOfScope', 'timeout', 'failed', 'defect', 'accepted',
    'problemElsewhere', 'defectElsewhere',
  ]);
});

it('matches in a different order from the one it lists, worst first', () => {
  expect(BY_PRECEDENCE.map((s) => s.key)).toEqual([
    'outOfScope', 'defect', 'timeout', 'failed', 'accepted',
    'defectElsewhere', 'problemElsewhere', 'unknown',
  ]);
});

it('gives every state its own precedence', () => {
  const seen = new Set(STATES.map((s) => s.precedence));
  expect(seen.size).toBe(STATES.length);
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
  const by = (key: string) => STATES.find((s) => s.key === key)!;
  expect(by('outOfScope').match({ ...clean, out_of_scope: true })).toBe(true);
  expect(by('outOfScope').match(clean)).toBe(false);
  expect(by('defect').match({ ...clean, open_defects: 1 })).toBe(true);
  expect(by('defect').match(clean)).toBe(false);
  expect(by('timeout').match({ ...clean, error: 'TimeoutError' })).toBe(true);
  expect(by('timeout').match({ ...clean, error: 'GEOSException' })).toBe(false);
  expect(by('failed').match({ ...clean, error: 'GEOSException' })).toBe(true);
  expect(by('failed').match(clean)).toBe(false);
  expect(by('accepted').match({ ...clean, accepted_defects: 1 })).toBe(true);
  expect(by('accepted').match(clean)).toBe(false);
  expect(by('defectElsewhere').match({ ...clean, open_defects_elsewhere: 1 })).toBe(true);
  expect(by('defectElsewhere').match(clean)).toBe(false);
  expect(by('problemElsewhere').match({ ...clean, error_elsewhere: true })).toBe(true);
  expect(by('problemElsewhere').match(clean)).toBe(false);
});

it('carries the tuned colors and weights', () => {
  expect(styleTable()).toEqual({
    unknown: { fill: '#3a3a3f', border: null, weight: null },
    outOfScope: { fill: '#b2a3dd', border: null, weight: null },
    timeout: { fill: '#26383f', border: '#30b0d0', weight: 'thick' },
    failed: { fill: '#4a2626', border: '#e03030', weight: 'thick' },
    defect: { fill: '#453c27', border: '#daa520', weight: 'thick' },
    accepted: { fill: '#26382c', border: '#6f9e78', weight: 'thin' },
    problemElsewhere: { fill: '#26383f', border: '#97bcc5', weight: 'thin' },
    defectElsewhere: { fill: '#453c27', border: '#c7b78f', weight: 'thin' },
  });
});

it('names every state the way the legend does', () => {
  expect(labelTable()).toEqual({
    unknown: 'unknown',
    outOfScope: 'currently out of scope',
    timeout: 'timed out',
    failed: 'render error',
    defect: 'open defect',
    accepted: 'known issue, not fixing',
    problemElsewhere: 'problem in another slot',
    defectElsewhere: 'defect in another slot',
  });
});

it('generates the CSS custom property names the stylesheet already uses', () => {
  expect(cssVarTable()).toEqual({
    unknown: { fill: '--corpus-cell-unknown-fill', border: null },
    outOfScope: { fill: '--corpus-cell-out-of-scope-fill', border: null },
    timeout: { fill: '--corpus-cell-timeout-fill', border: '--corpus-cell-timeout-border' },
    failed: { fill: '--corpus-cell-failed-fill', border: '--corpus-cell-failed-border' },
    defect: { fill: '--corpus-cell-defect-fill', border: '--corpus-cell-defect-border' },
    accepted: { fill: '--corpus-cell-accepted-fill', border: '--corpus-cell-accepted-border' },
    problemElsewhere: { fill: '--corpus-cell-problem-elsewhere-fill',
                        border: '--corpus-cell-problem-elsewhere-border' },
    defectElsewhere: { fill: '--corpus-cell-defect-elsewhere-fill',
                       border: '--corpus-cell-defect-elsewhere-border' },
  });
});

it('names a state\'s color params, and no border param where there is no border', () => {
  const by = (key: string) => STATES.find((s) => s.key === key)!;
  expect(paramKeys(by('timeout'))).toEqual({ fill: 'timeoutFill', border: 'timeoutBorder' });
  expect(paramKeys(by('problemElsewhere')))
    .toEqual({ fill: 'problemElsewhereFill', border: 'problemElsewhereBorder' });
  expect(paramKeys(by('unknown'))).toEqual({ fill: 'unknownFill', border: null });
  expect(paramKeys(by('outOfScope'))).toEqual({ fill: 'outOfScopeFill', border: null });
});
