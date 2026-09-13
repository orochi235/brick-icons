import { describe, expect, it } from 'vitest';
import { compileSpec } from '@castleblack/wall/src/cel';
import { DEFAULT_SHOWN } from '@lab/corpus/criteria';
import { RAMP_NAMES } from '@lab/corpus/tint';
import { openingState, stateHash } from '@lab/wall/hash';
import { SPEC } from '@lab/wall/host';

describe('the wall hash', () => {
  const state = {
    slot: 'occt',
    opened: '3001',
    selection: {
      sort: 'secs', filter: 'errors',
      shown: { ...DEFAULT_SHOWN, obsolete: !DEFAULT_SHOWN.obsolete },
      exclude: { category: ['Brick', 'Plate'] }, tags: ['retired'],
      tint: 'secs', gradient: RAMP_NAMES.find((n) => n !== 'ember')!,
      grouping: 'release', desc: false,
    },
  };

  it('opens WallView where it left off', () => {
    expect(openingState(stateHash(state), '')).toEqual(state);
  });

  it('lets a hand-off link outrank the hash', () => {
    const opening = openingState('#source=occt&filter=all&excl=Tile',
                                 '?source=ldview&filter=errors&excluded=Brick');
    expect(opening.slot).toBe('ldview');
    expect(opening.selection).toMatchObject({ filter: 'errors', exclude: { category: ['Brick'] } });
  });

  it('names nothing a bare URL leaves unsaid, so the defaults stand', () => {
    expect(openingState('', '')).toEqual({ selection: {} });
  });
});

it('compiles brick-icons spec with its mark art', () => {
  expect(compileSpec(SPEC).errors).toEqual([]);
});
