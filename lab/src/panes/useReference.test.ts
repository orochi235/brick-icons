import { describe, expect, it } from 'vitest';
import { referenceState } from '@lab/panes/useReference';

describe('referenceState', () => {
  it('is idle without a part', () => {
    expect(referenceState({ part: '', url: null, error: null, loading: false }))
      .toEqual({ kind: 'idle' });
  });

  it('is running while a frame is in flight', () => {
    expect(referenceState({ part: '3941', url: null, error: null, loading: true }))
      .toEqual({ kind: 'running' });
  });

  it('is an image once a frame arrives', () => {
    expect(referenceState({ part: '3941', url: '/api/reference-artifact/k/3941.png',
                            error: null, loading: false }))
      .toEqual({ kind: 'image', src: '/api/reference-artifact/k/3941.png' });
  });

  it('reports a missing LDView as the pane\'s error', () => {
    expect(referenceState({ part: '3941', url: null, loading: false,
                            error: 'LDView is not installed — run scripts/setup-ldview.sh' }))
      .toEqual({ kind: 'error',
                 message: 'LDView is not installed — run scripts/setup-ldview.sh' });
  });

  it('prefers the error over a stale frame', () => {
    expect(referenceState({ part: '3941', url: '/old.png', error: 'boom', loading: false }).kind)
      .toBe('error');
  });
});
