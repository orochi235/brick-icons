import { describe, expect, it } from 'vitest';
import { changeOf, outcomeOf } from '@lab/ingest/change';

describe('outcomeOf', () => {
  it('reads a store run row off its state', () => {
    expect(outcomeOf({ state: 'stored', error: null })).toBe('stored');
  });

  it('reads a failure off its error, whatever the state says', () => {
    expect(outcomeOf({ state: 'stored', error: 'TimeoutError' })).toBe('TimeoutError');
  });

  it('calls a clean measurement drawn, which is what prior calls one', () => {
    expect(outcomeOf({ state: null, error: null })).toBe('drawn');
  });
});

describe('changeOf', () => {
  it('marks a part the run met first', () => {
    expect(changeOf(null, 'stored')).toBe('first');
  });

  it('says nothing about a part that did what it did last time', () => {
    expect(changeOf('stored', 'stored')).toBeNull();
    expect(changeOf('TimeoutError', 'TimeoutError')).toBeNull();
  });

  it('does not call a store run followed by a census a change', () => {
    // `stored` and `drawn` are the two tables' words for the same success,
    // and 3 rows of one 38-row run are exactly that pair.
    expect(changeOf('stored', 'drawn')).toBeNull();
    expect(changeOf('drawn', 'stored')).toBeNull();
  });

  it('marks a slot that started drawing a part', () => {
    expect(changeOf('TimeoutError', 'drawn')).toBe('fixed');
    expect(changeOf('ProcessDied', 'stored')).toBe('fixed');
  });

  it('marks a slot that stopped drawing one', () => {
    expect(changeOf('drawn', 'TimeoutError')).toBe('broke');
  });

  it('ranks an empty result between a drawing and a failure', () => {
    // The decal finder reports `none` for a part it found no decoration on.
    // Finding one is a gain; losing one is a loss; neither is an error.
    expect(changeOf('none', 'stored')).toBe('fixed');
    expect(changeOf('stored', 'none')).toBe('broke');
    expect(changeOf('none', 'TimeoutError')).toBe('broke');
  });

  it('marks one failure swapped for another as a change, not a fix', () => {
    expect(changeOf('TimeoutError', 'ProcessDied')).toBe('changed');
  });

  it('treats an error name it has never seen as a failure', () => {
    expect(changeOf('stored', 'SomeNewError')).toBe('broke');
    expect(changeOf('SomeNewError', 'stored')).toBe('fixed');
  });
});
