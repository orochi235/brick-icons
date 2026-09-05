import { expect, it } from 'vitest';
import { isStale, sourceBox } from '@lab/corpus/sheet';
import type { SheetManifest } from '@lab/corpus/types';

const manifest: SheetManifest = {
  level: 32, gutter: 2, pitch: 36, cols: 2, rows: 2, count: 4, size: 72,
  baked: { a: 'sha-a', b: 'sha-b' },
};

it('finds a cell row-major inside its gutter', () => {
  expect(sourceBox(manifest, 0)).toEqual({ sx: 2, sy: 2, sw: 32, sh: 32 });
  expect(sourceBox(manifest, 1)).toEqual({ sx: 38, sy: 2, sw: 32, sh: 32 });
  expect(sourceBox(manifest, 2)).toEqual({ sx: 2, sy: 38, sw: 32, sh: 32 });
});

it('has no box for an index outside the sheet', () => {
  expect(sourceBox(manifest, 4)).toBeNull();
  expect(sourceBox(manifest, -1)).toBeNull();
});

it('calls a cell stale when the store has moved past the bake', () => {
  expect(isStale(manifest, { id: 'a', sha: 'sha-a' })).toBe(false);
  expect(isStale(manifest, { id: 'a', sha: 'sha-new' })).toBe(true);
  expect(isStale(manifest, { id: 'c', sha: 'sha-c' })).toBe(true);
});

it('does not call an unrendered cell stale', () => {
  expect(isStale(manifest, { id: 'c', sha: null })).toBe(false);
});
