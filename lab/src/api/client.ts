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

    artifactUrl(key: string, name: string): string {
      return at(`/api/artifact/${key}/${name}`);
    },

    async defects(part?: string) {
      const url = at(part ? `/api/defects?part=${encodeURIComponent(part)}` : '/api/defects');
      return (await json<{ defects: unknown[] }>(fetchImpl, url)).defects;
    },

    async goldens(part: string) {
      return json<{ part: string; cases: Record<string, string>; known: boolean }>(
        fetchImpl, at(`/api/goldens?part=${encodeURIComponent(part)}`));
    },
  };
}

export type LabClient = ReturnType<typeof createClient>;
export type { Artifact, RenderResult, JobState, SchemaField, PartHit, LabConfig };
