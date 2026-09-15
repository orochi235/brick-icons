import { expect, it } from 'vitest';
import { searchNotice } from '@lab/wall/searchNotice';

it('says why a searched part did not open, and nothing when it did', () => {
  expect(searchNotice('3001', 'shown')).toBeNull();
  expect(searchNotice('3001', 'filtered')).toBe('3001 is hidden by the current filter');
  expect(searchNotice('3001', 'absent')).toBe('3001 is not drawn in this slot');
});
