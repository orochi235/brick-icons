import { expect, it } from 'vitest';
import { humanBytes, share } from '@lab/stats/bytes';

it('scales to the unit a reader would say', () => {
  expect(humanBytes(0)).toBe('0 B');
  expect(humanBytes(512)).toBe('512 B');
  expect(humanBytes(1024)).toBe('1.0 KB');
  expect(humanBytes(641_000_000)).toBe('611 MB');
  expect(humanBytes(3_126_000_000)).toBe('2.9 GB');
});

it('agrees with `du -h`, which is what anyone checking by hand will run', () => {
  // du reports out/thumbs as 586M; the same blocks in powers of 1024.
  expect(humanBytes(615_000_000)).toBe('587 MB');
});

it('keeps three significant figures rather than a fixed decimal', () => {
  expect(humanBytes(9.5 * 1024 ** 3)).toBe('9.5 GB');
  expect(humanBytes(95 * 1024 ** 3)).toBe('95 GB');
});

it('never claims a share of nothing', () => {
  expect(share(0, 0)).toBeNull();
  expect(share(5, 0)).toBeNull();
  expect(share(1, 4)).toBe(25);
});
