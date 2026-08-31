import { describe, expect, it, vi } from 'vitest';
import { svgArtifactName, fetchSvgMarkup } from '@lab/panes/useArtifactSvg';

describe('svgArtifactName', () => {
  it('picks the SVG out of the artifact list', () => {
    expect(svgArtifactName([{ name: '3941.gray.png', bytes: 1 },
                            { name: '3941.svg', bytes: 2 }])).toBe('3941.svg');
  });

  it('is null when the render wrote no SVG', () => {
    expect(svgArtifactName([{ name: '3941.mono.png', bytes: 1 }])).toBeNull();
  });

  it('ignores an unwrap or decal SVG, which is not the render', () => {
    expect(svgArtifactName([{ name: '3941.unwrap.svg', bytes: 1 }])).toBeNull();
  });
});

describe('fetchSvgMarkup', () => {
  it('returns the body text', async () => {
    const fetchImpl = vi.fn(async () => new Response('<svg/>', { status: 200 }));
    expect(await fetchSvgMarkup('/api/artifact/k/3941.svg', fetchImpl)).toBe('<svg/>');
  });

  it('returns null on an error status rather than throwing', async () => {
    const fetchImpl = vi.fn(async () => new Response('', { status: 404 }));
    expect(await fetchSvgMarkup('/api/artifact/k/x.svg', fetchImpl)).toBeNull();
  });
});
