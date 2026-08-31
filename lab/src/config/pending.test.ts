import { beforeEach, describe, expect, it } from 'vitest';
import { setPendingPart, takePendingPart } from '@lab/config/pending';

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
