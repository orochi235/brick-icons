import { afterEach, describe, expect, it, vi } from 'vitest';
import { createClient } from '@lab/api/client';

function stub(routes: Record<string, unknown>) {
  return vi.fn(async (input: string | URL) => {
    const url = new URL(String(input), 'http://localhost');
    const body = routes[url.pathname];
    if (body === undefined) return new Response('null', { status: 404 });
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  });
}

afterEach(() => vi.restoreAllMocks());

describe('createClient', () => {
  it('reads the config schema', async () => {
    const fetchImpl = stub({ '/api/schema': { fields: [{ key: 'engine' }] } });
    const api = createClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    expect(await api.schema()).toEqual([{ key: 'engine' }]);
  });

  it('searches parts and passes the query through', async () => {
    const fetchImpl = stub({ '/api/parts': { results: [{ id: '3941' }] } });
    const api = createClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    expect(await api.searchParts('3941')).toEqual([{ id: '3941' }]);
    const called = new URL(String(fetchImpl.mock.calls[0]![0]), 'http://x');
    expect(called.searchParams.get('q')).toBe('3941');
  });

  it('builds an artifact URL without fetching', () => {
    const api = createClient({ fetchImpl: stub({}) as unknown as typeof fetch });
    expect(api.artifactUrl('abc123', '3941.svg')).toBe('/api/artifact/abc123/3941.svg');
  });

  it('reports the command for a part and config', async () => {
    const fetchImpl = stub({
      '/api/command': { argv: ['3941', '--engine', 'occt'],
                        command: 'brick-icons 3941 --engine occt' },
    });
    const api = createClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    const got = await api.command('3941', { engine: 'occt' });
    expect(got.command).toBe('brick-icons 3941 --engine occt');
  });

  it('throws with the server message on an error status', async () => {
    const fetchImpl = vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'not CLI flags' }), { status: 400 }));
    const api = createClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    await expect(api.schema()).rejects.toThrow(/not CLI flags/);
  });

  it('starts a render and returns the job id', async () => {
    const fetchImpl = stub({ '/api/render': { job: 'j1', argv: ['3941'],
                                              command: 'brick-icons 3941' } });
    const api = createClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    expect((await api.startRender('3941', {})).job).toBe('j1');
  });
});
