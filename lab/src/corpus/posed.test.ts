import { describe, expect, it } from 'vitest';

import { poseNote } from '@lab/corpus/posed';

describe('poseNote', () => {
  it('names the half turn 357 parts declare', () => {
    // 87544dq0 and the rest of the sticker shortcuts.
    expect(poseNote('16 0 0 0 -1 0 0 0 1 0 0 0 -1')).toBe('half turn about Y');
  });

  it('names a quarter turn', () => {
    expect(poseNote('16 0 0 0 0 0 1 0 1 0 -1 0 0')).toBe('quarter turn about Y');
  });

  it('names a turn about X', () => {
    expect(poseNote('16 0 0 0 1 0 0 0 -1 0 0 0 -1')).toBe('half turn about X');
  });

  it('says nothing for a part that declares no turn', () => {
    expect(poseNote(null)).toBeNull();
    expect(poseNote(undefined)).toBeNull();
    expect(poseNote('')).toBeNull();
  });

  it('says nothing for an identity, which is not a pose', () => {
    expect(poseNote('16 0 0 0 1 0 0 0 1 0 0 0 1')).toBeNull();
  });

  it('survives a line it cannot read rather than blanking the view', () => {
    expect(poseNote('16 0 0')).toBeNull();
    expect(poseNote('16 0 0 0 x 0 0 0 1 0 0 0 1')).toBeNull();
  });
});
