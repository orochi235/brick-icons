import type { Artifact, JobState, LabConfig, LdrawColor, PartHit, RenderResult,
  SchemaField } from '@lab/api/types';
import type { Footprint, Stats } from '@lab/stats/types';
import type { CellsBody, PartDetail, SheetManifest } from '@lab/corpus/types';
import type { IngestAttempts, IngestRun } from '@lab/ingest/types';
import type { ReviewEntry, ReviewList, ReviewView, Verdict } from '@lab/review/types';

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

    /** The LDraw palette, by code. Cached by the server, small enough to take
     *  whole -- `--part-color` accepts a name, a code or hex, so the field
     *  needs every row to match against. */
    async colors(): Promise<LdrawColor[]> {
      return (await json<{ colors: LdrawColor[] }>(fetchImpl, at('/api/colors'))).colors;
    },

    async searchParts(q: string, limit = 25, signal?: AbortSignal): Promise<PartHit[]> {
      const url = at(`/api/parts?q=${encodeURIComponent(q)}&limit=${limit}`);
      return (await json<{ results: PartHit[] }>(fetchImpl, url,
                                                 signal ? { signal } : undefined)).results;
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

    /** Ask for a part to be drawn again in one slot. A cheap slot draws now,
     *  as a job; anything slower is queued for the slot's next fleet round. */
    async redraw(part: string, source: string) {
      return json<{ local: boolean; job?: string; requested_at?: string;
                    secs: number | null }>(
        fetchImpl, at('/api/corpus/redraw'), post('/api/corpus/redraw', { part, source }));
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

    async cells(source: string, since?: string): Promise<CellsBody> {
      const q = new URLSearchParams({ source });
      if (since) q.set('since', since);
      return json(fetchImpl, at(`/api/corpus/cells?${q}`));
    },

    async corpusSources(): Promise<{ sources: { source: string; n: number }[] }> {
      return json(fetchImpl, at('/api/corpus/sources'));
    },

    async corpusStats(query: URLSearchParams): Promise<Stats> {
      const q = query.toString();
      return json(fetchImpl, at(`/api/corpus/stats${q ? `?${q}` : ''}`));
    },

    async corpusSizes(refresh = false): Promise<Footprint> {
      return json(fetchImpl, at(`/api/corpus/sizes${refresh ? '?refresh=1' : ''}`));
    },

    async corpusPart(id: string): Promise<PartDetail> {
      return json(fetchImpl, at(`/api/corpus/part/${encodeURIComponent(id)}`));
    },

    /** Every ingest, newest first. */
    async ingestRuns(): Promise<IngestRun[]> {
      return (await json<{ runs: IngestRun[] }>(fetchImpl, at('/api/ingest/runs'))).runs;
    },

    async ingestAttempts(runId: number, failed = false): Promise<IngestAttempts> {
      return json(fetchImpl, at(`/api/ingest/runs/${runId}/attempts${failed ? '?failed=1' : ''}`));
    },

    /** Renders that displaced an older one. `linked` keeps the ones an open
     *  defect or a redraw request speaks to; `all` keeps every one whose diff
     *  has at least `minComponents` components, and the unmeasured. */
    async review(view: ReviewView, minComponents = 1, judged = false,
                 limit = 200): Promise<ReviewList> {
      const q = new URLSearchParams({ view, min_components: String(minComponents),
                                      judged: judged ? '1' : '0', limit: String(limit) });
      return json<ReviewList>(fetchImpl, at(`/api/review?${q}`));
    },

    async reviewEntry(id: string): Promise<ReviewEntry> {
      return json<ReviewEntry>(fetchImpl, at(`/api/review/${id}`));
    },

    async judge(id: string, verdict: Verdict, note: string): Promise<ReviewEntry> {
      return json<ReviewEntry>(fetchImpl, at(`/api/review/${id}/verdict`),
                               post(`/api/review/${id}/verdict`, { verdict, note }));
    },

    /** Take a verdict back: the entry returns to the queue and every
     *  defect it stamped goes back to what it held before. */
    async undoJudgement(id: string): Promise<ReviewEntry> {
      return json<ReviewEntry>(fetchImpl, at(`/api/review/${id}/undo`),
                               { method: 'POST' });
    },

    async measureReview(limit = 20): Promise<{ measured: number; failed: { id: string; error: string }[] }> {
      return json(fetchImpl, at(`/api/review/measure?limit=${limit}`), { method: 'POST' });
    },

    async sheetManifest(source: string, level: number): Promise<SheetManifest> {
      return json(fetchImpl, at(`/api/thumbs/${source}/sheet-${level}.json`));
    },
  };
}

export type LabClient = ReturnType<typeof createClient>;
export type { Artifact, RenderResult, JobState, SchemaField, PartHit, LabConfig };
