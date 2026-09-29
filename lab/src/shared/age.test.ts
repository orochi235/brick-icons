import { expect, it } from 'vitest';
import { age } from '@lab/shared/age';

const NOW = new Date('2026-09-28T12:00:00Z');
const ago = (ms: number) => age(new Date(NOW.getTime() - ms).toISOString(), NOW);
const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

it('names the largest whole unit, rounded down', () => {
  expect(ago(5 * MIN)).toBe('5m');
  expect(ago(59 * MIN + 59_000)).toBe('59m');
  expect(ago(2 * HOUR + 59 * MIN)).toBe('2h');
  expect(ago(23 * HOUR)).toBe('23h');
  expect(ago(3 * DAY)).toBe('3d');
  expect(ago(6 * DAY + 23 * HOUR)).toBe('6d');
  expect(ago(5 * 7 * DAY)).toBe('5w');
  expect(ago(364 * DAY)).toBe('52w');
  expect(ago(365 * DAY)).toBe('1y');
  expect(ago(3 * 365 * DAY)).toBe('3y');
});

it('reads under a minute, and a clock running ahead, as now', () => {
  expect(ago(30_000)).toBe('now');
  expect(ago(-5 * MIN)).toBe('now');
});

it('takes the stamp format the server writes', () => {
  expect(age('2026-09-28T10:00:00+00:00', NOW)).toBe('2h');
});

it('has no answer for a string that is not a time', () => {
  expect(age('never', NOW)).toBeNull();
});
