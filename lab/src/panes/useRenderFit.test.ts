import { describe, expect, it, vi } from 'vitest';
import type { RenderResult } from '@lab/api/client';
import type { SourceId } from '@lab/panes/sources';
import { fetchFit, fitArtifactName, registrationSource } from '@lab/panes/useRenderFit';

const FIT = {
  right: [1, 0, 0], up: [0, 1, 0], fwd: [0, 0, 1],
  k: 2, kx: 3, ky: 4, width: 256, height: 170,
};

function render(key: string, names: string[], ok = true): RenderResult {
  return {
    ok, cached: false, argv: [], command: '', key,
    artifacts: names.map((name) => ({ name, bytes: 1 })),
    seconds: 0, error: ok ? null : 'boom',
  };
}

describe('fitArtifactName', () => {
  it('picks the sidecar out of the artifact list', () => {
    expect(fitArtifactName([{ name: '3941.svg', bytes: 1 },
                            { name: '3941.fit.json', bytes: 2 }])).toBe('3941.fit.json');
  });

  it('is null for a render that wrote none, so the pane stays unregistered', () => {
    expect(fitArtifactName([{ name: '3941.mono.png', bytes: 1 }])).toBeNull();
  });
});

describe('registrationSource', () => {
  it('takes the first engine pane in layout order, not the first to finish', () => {
    const renders: Partial<Record<SourceId, RenderResult>> = {
      occt: render('b', ['3941.fit.json']),
      naive: render('a', ['3941.fit.json']),
    };
    expect(registrationSource(renders)).toBe('naive');
  });

  it('skips an engine whose render failed', () => {
    expect(registrationSource({ naive: render('a', [], false),
                                occt: render('b', ['3941.fit.json']) })).toBe('occt');
  });

  it('is null when no engine pane is showing', () => {
    expect(registrationSource({ reference: render('r', ['ref.png']) })).toBeNull();
  });
});

describe('fetchFit', () => {
  it('returns the parsed sidecar', async () => {
    const fetchImpl = vi.fn(async () => Response.json(FIT));
    expect(await fetchFit('/api/artifact/k/3941.fit.json', fetchImpl)).toEqual(FIT);
  });

  it('is null on an error status', async () => {
    const fetchImpl = vi.fn(async () => new Response('', { status: 404 }));
    expect(await fetchFit('/api/artifact/k/x.fit.json', fetchImpl)).toBeNull();
  });

  it('is null for a body that is not a fit, rather than framing with NaN', async () => {
    const fetchImpl = vi.fn(async () => Response.json({ k: 1 }));
    expect(await fetchFit('/api/artifact/k/x.fit.json', fetchImpl)).toBeNull();
  });
});
