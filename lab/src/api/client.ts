import type { Artifact, JobState, LabConfig, PartHit, RenderResult, SchemaField } from '@lab/api/types';

export interface ClientOptions {
  base?: string;
  fetchImpl?: typeof fetch;
}

async function json<T>(fetchImpl: typeof fetch, url: string, init?: RequestInit): Promise<T> {
  const response = await fetchImpl(url, init);
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* a non-JSON error body is still an error; the status carries it */
    }
    throw new Error(`${url}: ${detail}`);
  }
  return (await response.json()) as T;
}

export function createClient({ base = '', fetchImpl = fetch }: ClientOptions = {}) {
  const at = (path: string) => `${base}${path}`;
  const post = (path: string, body: unknown): RequestInit => ({
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });

  return {
    async schema(): Promise<SchemaField[]> {
      return (await json<{ fields: SchemaField[] }>(fetchImpl, at('/api/schema'))).fields;
    },

    async searchParts(q: string, limit = 25): Promise<PartHit[]> {
      const url = at(`/api/parts?q=${encodeURIComponent(q)}&limit=${limit}`);
      return (await json<{ results: PartHit[] }>(fetchImpl, url)).results;
    },

    /** The argv the server would run. Asked for rather than mirrored: a second
     *  argv builder in TypeScript is exactly the divergence the lab exists to
     *  avoid. */
    async command(part: string, config: LabConfig): Promise<{ argv: string[]; command: string }> {
      const url = at(`/api/command?part=${encodeURIComponent(part)}`
        + `&config=${encodeURIComponent(JSON.stringify(config))}`);
      return json(fetchImpl, url);
    },

    async startRender(part: string, config: LabConfig, force = false) {
      return json<{ job: string; argv: string[]; command: string }>(
        fetchImpl, at('/api/render'), post('/api/render', { part, config, force }));
    },

    async job(id: string): Promise<JobState> {
      return json<JobState>(fetchImpl, at(`/api/jobs/${id}`));
    },

    async cancelJob(id: string): Promise<void> {
      await json(fetchImpl, at(`/api/jobs/${id}/cancel`), post('', {}));
    },

    async diff(aKey: string, aName: string, bKey: string, bName: string) {
      const params = new URLSearchParams({ a_key: aKey, a_name: aName,
                                           b_key: bKey, b_name: bName });
      return json<{ components: number; sizes: number[]; pixels: number; url: string }>(
        fetchImpl, at(`/api/diff?${params}`));
    },

    artifactUrl(key: string, name: string): string {
      return at(`/api/artifact/${key}/${name}`);
    },

    async defects(part?: string) {
      const url = at(part ? `/api/defects?part=${encodeURIComponent(part)}` : '/api/defects');
      return (await json<{ defects: unknown[] }>(fetchImpl, url)).defects;
    },

    async addDefect(record: unknown) {
      return json<unknown>(fetchImpl, at('/api/defects'), post('/api/defects', record));
    },

    async patchDefect(id: string, changes: Record<string, unknown>) {
      return json<unknown>(fetchImpl, at(`/api/defects/${id}`), {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(changes),
      });
    },

    async reference(part: string, angle: string, partColor?: string) {
      const params = new URLSearchParams({ part, angle });
      if (partColor) params.set('part_color', partColor);
      return json<{ url: string; cached: boolean }>(
        fetchImpl, at(`/api/reference?${params}`));
    },

    async decal(part: string) {
      return json<{ urls: string[]; names: string[]; cached: boolean }>(
        fetchImpl, at(`/api/decal?part=${encodeURIComponent(part)}`));
    },

    async checkGoldens(part: string) {
      return json<{ job: string; count: number }>(
        fetchImpl, at('/api/goldens/check'), post('/api/goldens/check', { part }));
    },

    async combos() {
      return (await json<{ combos: { name: string; args: string[]; parts: string[] }[] }>(
        fetchImpl, at('/api/combos'))).combos;
    },

    async startBatch(parts: string[], config: Record<string, unknown>, force = false) {
      return json<{ job: string; count: number }>(
        fetchImpl, at('/api/batch'), post('/api/batch', { parts, config, force }));
    },

    async lists() {
      return (await json<{ lists: { name: string; source: string; parts: string[] }[] }>(
        fetchImpl, at('/api/lists'))).lists;
    },

    async goldens(part: string) {
      return json<{ part: string; cases: Record<string, string>; known: boolean }>(
        fetchImpl, at(`/api/goldens?part=${encodeURIComponent(part)}`));
    },
  };
}

export type LabClient = ReturnType<typeof createClient>;
export type { Artifact, RenderResult, JobState, SchemaField, PartHit, LabConfig };
