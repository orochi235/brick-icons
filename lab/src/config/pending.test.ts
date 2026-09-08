import { beforeEach, describe, expect, it } from 'vitest';
import type { TrialRecord } from '@weasel-js/labkit';
import { setPendingPart, takePendingPart, trialToAdopt } from '@lab/config/pending';

beforeEach(() => takePendingPart());

describe('pending part', () => {
  it('is empty when nothing was set', () => {
    expect(takePendingPart()).toBe('');
  });

  it('hands back what was set', () => {
    setPendingPart('3941');
    expect(takePendingPart()).toBe('3941');
  });

  it('is consumed by the first read, so the next trial opens empty', () => {
    setPendingPart('3941');
    takePendingPart();
    expect(takePendingPart()).toBe('');
  });

  it('the last write wins', () => {
    setPendingPart('3941');
    setPendingPart('4070');
    expect(takePendingPart()).toBe('4070');
  });

  it('trims what it is given', () => {
    setPendingPart('  3941 ');
    expect(takePendingPart()).toBe('3941');
  });
});

describe('trialToAdopt', () => {
  const trial = (id: string, part: string, instrumentName = 'part-inspector') =>
    ({ id, instrumentName, config: { part }, state: {}, view: {},
       undoStack: { past: [], future: [] } }) as unknown as TrialRecord;

  it('has nothing to adopt when no trial is open', () => {
    expect(trialToAdopt([])).toBeNull();
  });

  it('adopts a part inspector that has not been given a part', () => {
    expect(trialToAdopt([trial('t1', '')])).toBe('t1');
  });

  it('leaves a trial that is showing a part alone', () => {
    expect(trialToAdopt([trial('t1', '3005')])).toBeNull();
  });

  it('adopts the first empty one when several are open', () => {
    expect(trialToAdopt([trial('t1', '3005'), trial('t2', ''), trial('t3', '')]))
      .toBe('t2');
  });

  it('ignores an empty trial running another instrument', () => {
    expect(trialToAdopt([trial('t1', '', 'contact-sheet')])).toBeNull();
  });

  it('treats whitespace as no part', () => {
    expect(trialToAdopt([trial('t1', '   ')])).toBe('t1');
  });
});
