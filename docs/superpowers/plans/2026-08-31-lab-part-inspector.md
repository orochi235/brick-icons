# Lab Shell and Part Inspector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The lab's frontend: type a part id in the workspace title bar, get a trial that renders that part and shows the engines side by side, with the equivalent CLI command visible at all times.

**Architecture:** A Vite + React app in `lab/`, built on `@weasel-js/labkit`. The Part Inspector instrument's config schema is fetched from the server at boot and turned into labkit config nodes, so the control panel is the CLI's flag set. Renders run through labkit's `job` capability. Panes are DOM — inline SVG for engine output — under one shared camera held in the trial's view.

**Tech Stack:** React 19, TypeScript, Vite, Vitest, `@weasel-js/labkit` 1.3.0.

**Depends on:** `docs/superpowers/plans/2026-08-31-lab-server.md` (Tasks 1–16) must be complete — this plan calls `/api/schema`, `/api/parts`, `/api/render`, `/api/jobs/{id}` and `/api/artifact/...`.

**Spec:** `docs/superpowers/specs/2026-08-31-corpus-lab-design.md`

---

## What labkit gives us, in its own vocabulary

Read this before Task 1; the rest of the plan uses these words.

- **instrument** — one kind of experiment, declared with `defineInstrument({...})`.
- **trial** — one running instance: its own `config`, `state`, and `view`.
- **workspace** — the grid of open trials.
- **capability** — a field on the instrument spec that makes the runtime provide chrome. This plan uses two:
  - `job` — `{ key, auto, run, onItem }`. `run` is an **async generator** yielding `{kind:'total'|'item'|'failed'}` events; the runtime aborts it on unmount and whenever `key(config, state)` changes element-wise, and exposes `ctx.job` (`status`, `done`, `total`, `start`, `cancel`).
  - `layers` — `{ ids }`, which gives the trial a `<LayerList>` of show/hide toggles.
- **contribution** — `instrument.chrome` is a `TrialContribution[]`, each keyed to a `region` (`titlebar`, `toolbar`, `sidebar`, `viewport`, `status`) and carrying either a typed `item` or a `render(ctx)` escape hatch.
- **view** — the trial's camera. labkit persists it and hands it back without reading into it; `ctx.trial.view` / `ctx.trial.setView`.

The full type surface is in `node_modules/@weasel-js/labkit/dist/index.d.ts` after Task 1.

---

## File Structure

| file | responsibility |
|---|---|
| `lab/package.json`, `vite.config.ts`, `tsconfig.json` | the app, its proxy and its `@lab/*` alias |
| `lab/src/api/client.ts` | typed calls to the server; nothing else fetches |
| `lab/src/api/types.ts` | the shapes the server returns |
| `lab/src/config/nodes.ts` | server schema fields → labkit config nodes |
| `lab/src/config/pending.ts` | the part a new trial opens on |
| `lab/src/panes/camera.ts` | pan/zoom math over the trial view |
| `lab/src/panes/SourcePane.tsx` | one pane: label, framing, camera transform |
| `lab/src/panes/sources.ts` | the source list and how each fetches |
| `lab/src/instruments/partInspector.tsx` | the instrument: config, job, chrome, render |
| `lab/src/chrome/PartSearch.tsx` | the title-bar search field |
| `lab/src/chrome/CommandLine.tsx` | the always-visible CLI command |
| `lab/src/main.tsx` | boot: fetch schema, build instrument, mount `<Lab>` |

Logic lives in `.ts` modules with tests; `.tsx` files render what those return. That split is what makes the camera math and the argv plumbing testable without a browser.

---

## Task 1: Scaffold the app

**Files:**
- Create: `lab/package.json`, `lab/tsconfig.json`, `lab/vite.config.ts`, `lab/index.html`, `lab/src/main.tsx`, `lab/.gitignore`
- Modify: `.gitignore`

- [ ] **Step 1: Create the package manifest**

Create `lab/package.json`:

```json
{
  "name": "brick-icons-lab",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run",
    "typecheck": "tsc -b --noEmit"
  },
  "dependencies": {
    "@weasel-js/labkit": "1.3.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "jsdom": "^25.0.0",
    "typescript": "^5.6.0",
    "vite": "^6.0.0",
    "vitest": "^2.1.0"
  }
}
```

- [ ] **Step 2: Create the TypeScript config**

Create `lab/tsconfig.json`. The `@lab/*` alias is deliberate: an import block full of `../../../` says nothing about where a module lives and breaks the moment a file moves.

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noEmit": true,
    "skipLibCheck": true,
    "baseUrl": ".",
    "paths": { "@lab/*": ["src/*"] }
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Create the Vite config**

Create `lab/vite.config.ts`. The proxy is what lets the dev server call the Python server without CORS.

```ts
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

const API = 'http://127.0.0.1:8791';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@lab': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5178,
    proxy: { '/api': API, '/ldraw': API },
  },
  build: { outDir: 'dist' },
  test: { environment: 'jsdom', globals: true },
});
```

- [ ] **Step 4: Create the entry HTML and a placeholder entry point**

Create `lab/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>brick-icons lab</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `lab/src/main.tsx`:

```tsx
import { createRoot } from 'react-dom/client';

createRoot(document.getElementById('root')!).render(<p>lab</p>);
```

Create `lab/.gitignore`:

```
node_modules/
dist/
```

- [ ] **Step 5: Install and confirm it builds**

Run: `cd lab && npm install && npm run build`
Expected: `vite build` writes `lab/dist/index.html`. If `npm install` reports a peer conflict on React, check that `@weasel-js/labkit@1.3.0` resolved — it declares `react ^19.0.0` as a peer and bundles its own `@weasel-js/*` dependencies.

- [ ] **Step 6: Commit**

```bash
git add lab/ && git commit -m "scaffold the lab frontend"
```

---

## Task 2: The API client

**Files:**
- Create: `lab/src/api/types.ts`, `lab/src/api/client.ts`
- Test: `lab/src/api/client.test.ts`

Nothing else in the app calls `fetch`. One module means one place where a route
name or a response shape is written down.

- [ ] **Step 1: Write the failing test**

Create `lab/src/api/client.test.ts`:

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/api/client.test.ts`
Expected: FAIL — cannot resolve `@lab/api/client`

- [ ] **Step 3: Write the implementation**

Create `lab/src/api/types.ts`:

```ts
/** One flag of the CLI, as the server derived it from argparse. */
export interface SchemaField {
  key: string;
  flag: string;
  type: 'int' | 'float' | 'str' | 'bool';
  choices: string[] | null;
  help: string;
  nargs: number | null;
  default: unknown;
}

export interface PartHit {
  id: string;
  description: string;
  printed: boolean;
}

export interface Artifact {
  name: string;
  bytes: number;
}

/** What `runner.render` returned for one argv. */
export interface RenderResult {
  ok: boolean;
  cached: boolean;
  argv: string[];
  command: string;
  key: string;
  artifacts: Artifact[];
  seconds: number;
  error: string | null;
}

export interface JobState {
  id: string;
  kind: string;
  state: 'running' | 'done' | 'failed' | 'cancelled';
  total: number;
  done: number;
  failed: number;
  events: { index: number; total: number; message: string; ok: boolean }[];
  results: RenderResult[];
}

export type LabConfig = Record<string, unknown>;
```

Create `lab/src/api/client.ts`:

```ts
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/api/client.test.ts`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/api && git commit -m "add the lab API client"
```

---

## Task 3: The `/api/command` route

**Files:**
- Modify: `brick_icons/lab/app.py`
- Test: `tests/test_lab_app.py`

The frontend needs the command for a config without paying for a render. It
asks the server rather than building argv itself — a TypeScript copy of
`to_argv` is the divergence this whole design exists to prevent.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lab_app.py`:

```python
def test_command_route_returns_argv_without_rendering(client):
    body = client.get("/api/command", params={
        "part": "3941",
        "config": '{"engine": "occt", "shading": "outline"}',
    }).json()
    assert body["argv"] == ["3941", "--shading", "outline", "--engine", "occt"]
    assert body["command"] == "brick-icons 3941 --shading outline --engine occt"


def test_command_route_rejects_an_unknown_key(client):
    r = client.get("/api/command", params={"part": "3941",
                                           "config": '{"not_a_flag": 1}'})
    assert r.status_code == 400


def test_command_route_rejects_unparseable_config(client):
    r = client.get("/api/command", params={"part": "3941", "config": "{oops"})
    assert r.status_code == 400
```

Note the expected flag order: it follows the parser's declaration order, in
which `--shading` precedes `--engine`. If the parser changes, fix this
assertion to the new order — the order is the CLI's, not the lab's.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_app.py -k command -v`
Expected: FAIL with 404

- [ ] **Step 3: Write the implementation**

In `brick_icons/lab/app.py`, add `import json` at the top, and add this route
beside `/api/render`:

```python
    @app.get("/api/command")
    def get_command(part: str, config: str = "{}"):
        try:
            parsed = json.loads(config)
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"bad config JSON: {e}") from None
        try:
            argv = schema.to_argv(part, parsed)
        except KeyError as e:
            raise HTTPException(400, str(e)) from None
        return {"argv": argv, "command": " ".join(["brick-icons", *argv])}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_app.py -v`
Expected: PASS, 25 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/app.py tests/test_lab_app.py
git commit -m "serve the CLI command for a config without rendering"
```

---

## Task 4: Server schema fields → labkit config nodes

**Files:**
- Create: `lab/src/config/nodes.ts`
- Test: `lab/src/config/nodes.test.ts`

- [ ] **Step 1: Write the failing test**

Create `lab/src/config/nodes.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { buildSchema, defaultsFor, RENDER_KEYS } from '@lab/config/nodes';
import type { SchemaField } from '@lab/api/types';

const field = (over: Partial<SchemaField>): SchemaField => ({
  key: 'engine', flag: '--engine', type: 'str', choices: null,
  help: '', nargs: null, default: null, ...over,
});

/** `buildSchema` also adds the lab's own fields; these tests are about the
 *  CLI-derived ones. */
const cliKeys = (schema: Record<string, unknown>) =>
  Object.keys(schema).filter((k) => k !== 'layout' && k !== 'sources');

describe('buildSchema', () => {
  it('turns a choices field into an enum node', () => {
    const s = buildSchema([field({ key: 'engine', choices: ['naive', 'occt'] })]);
    expect(s).toHaveProperty('engine');
  });

  it('keeps only the CLI keys that change a render', () => {
    const s = buildSchema([
      field({ key: 'engine', choices: ['naive', 'occt'] }),
      field({ key: 'out', type: 'str' }),
      field({ key: 'debug_dir', type: 'str' }),
      field({ key: 'list_colors', type: 'bool' }),
    ]);
    expect(cliKeys(s)).toEqual(['engine']);
  });

  it('drops a multi-value flag, which has no single control', () => {
    const s = buildSchema([
      field({ key: 'engine', choices: ['naive', 'occt'] }),
      field({ key: 'label_mm', type: 'float', nargs: 2 }),
    ]);
    expect(cliKeys(s)).toEqual(['engine']);
  });

  it('includes the lab-only source and layout fields', () => {
    const s = buildSchema([field({ key: 'engine', choices: ['naive', 'occt'] })]);
    expect(s).toHaveProperty('layout');
    expect(s).toHaveProperty('sources');
  });
});

describe('defaultsFor', () => {
  it('takes a value from the field default when it has one', () => {
    const d = defaultsFor([field({ key: 'render_px', type: 'int', default: 900 })]);
    expect(d.render_px).toBe(900);
  });

  it('takes the first choice when the default is null', () => {
    const d = defaultsFor([field({ key: 'engine', choices: ['naive', 'occt'] })]);
    expect(d.engine).toBe('naive');
  });

  it('defaults a switch to false', () => {
    const d = defaultsFor([field({ key: 'weld_corners', type: 'bool' })]);
    expect(d.weld_corners).toBe(false);
  });

  it('carries the part and the lab-only fields', () => {
    const d = defaultsFor([field({ key: 'engine', choices: ['naive', 'occt'] })]);
    expect(d.part).toBe('');
    expect(d.layout).toBe('split');
    expect(d.sources).toContain('occt');
  });
});

describe('RENDER_KEYS', () => {
  it('excludes the plumbing flags', () => {
    for (const key of ['out', 'root', 'config', 'list', 'debug_dir', 'list_colors']) {
      expect(RENDER_KEYS.has(key)).toBe(false);
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/config/nodes.test.ts`
Expected: FAIL — cannot resolve `@lab/config/nodes`

- [ ] **Step 3: Write the implementation**

Create `lab/src/config/nodes.ts`:

```ts
import { f } from '@weasel-js/labkit';
import type { SchemaField } from '@lab/api/types';

/** Flags that arrange a run rather than change what is drawn. They are the
 *  lab's own business: it decides where output goes and which part to draw. */
const PLUMBING = new Set(['out', 'root', 'config', 'list', 'debug_dir',
                          'list_colors', 'part_label']);

export const SOURCE_IDS = ['naive', 'occt', 'reference', '3d', 'diff'] as const;
export type SourceId = (typeof SOURCE_IDS)[number];

export const RENDER_KEYS = {
  has(key: string) {
    return !PLUMBING.has(key);
  },
};

function usable(field: SchemaField): boolean {
  // A multi-value flag has no single control, and none of them change what the
  // drawing shows -- they are page geometry.
  return RENDER_KEYS.has(field.key) && field.nargs === null;
}

/** The lab's own fields, which no CLI flag corresponds to. */
function labNodes() {
  return {
    layout: f.enum('split', ['split', 'stack']),
    sources: f.value<SourceId[]>(['naive', 'occt']),
  };
}

export function buildSchema(fields: SchemaField[]) {
  const nodes: Record<string, unknown> = {};
  for (const field of fields) {
    if (!usable(field)) continue;
    if (field.choices && field.choices.length > 0) {
      nodes[field.key] = f.enum(field.choices[0]!, field.choices);
    } else if (field.type === 'bool') {
      nodes[field.key] = f.boolean(false);
    } else if (field.type === 'int' || field.type === 'float') {
      nodes[field.key] = f.number(typeof field.default === 'number' ? field.default : 0);
    } else {
      nodes[field.key] = f.string(typeof field.default === 'string' ? field.default : '');
    }
  }
  return { ...nodes, ...labNodes() } as Record<string, unknown>;
}

export function defaultsFor(fields: SchemaField[]): Record<string, unknown> {
  const out: Record<string, unknown> = { part: '', layout: 'split',
                                         sources: ['naive', 'occt'] };
  for (const field of fields) {
    if (!usable(field)) continue;
    if (field.default !== null && field.default !== undefined) {
      out[field.key] = field.default;
    } else if (field.choices && field.choices.length > 0) {
      out[field.key] = field.choices[0];
    } else if (field.type === 'bool') {
      out[field.key] = false;
    } else {
      out[field.key] = null;
    }
  }
  return out;
}

/** The subset of a trial's config that is a CLI flag: what goes to the server
 *  as `config`. A null means "leave it to labels.toml". */
export function renderConfig(config: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(config)) {
    if (key === 'part' || key === 'layout' || key === 'sources') continue;
    if (value === null || value === '') continue;
    out[key] = value;
  }
  return out;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/config/nodes.test.ts`
Expected: PASS, 9 tests

- [ ] **Step 5: Add the `renderConfig` tests**

Append to `lab/src/config/nodes.test.ts`:

```ts
import { renderConfig } from '@lab/config/nodes';

describe('renderConfig', () => {
  it('drops the lab-only fields', () => {
    const got = renderConfig({ part: '3941', layout: 'split',
                               sources: ['occt'], engine: 'occt' });
    expect(got).toEqual({ engine: 'occt' });
  });

  it('drops nulls and empty strings so the config file still decides', () => {
    expect(renderConfig({ engine: 'occt', angle: null, part_color: '' }))
      .toEqual({ engine: 'occt' });
  });

  it('keeps a false switch, which is a real value', () => {
    expect(renderConfig({ weld_corners: false })).toEqual({ weld_corners: false });
  });
});
```

Run: `cd lab && npx vitest run src/config/nodes.test.ts`
Expected: PASS, 12 tests

- [ ] **Step 6: Commit**

```bash
git add lab/src/config && git commit -m "map the server's CLI schema onto labkit config nodes"
```

---

## Task 5: The camera

**Files:**
- Create: `lab/src/panes/camera.ts`
- Test: `lab/src/panes/camera.test.ts`

Every pane shares one camera so a difference between two engines lands on the
same screen pixel. The math is here, separate from the DOM, because it is the
part that can be wrong in a way a screenshot will not show.

- [ ] **Step 1: Write the failing test**

Create `lab/src/panes/camera.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { HOME, cssTransform, panBy, readView, zoomAt } from '@lab/panes/camera';

describe('readView', () => {
  it('returns home for a view it does not recognise', () => {
    expect(readView(undefined)).toEqual(HOME);
    expect(readView({ orbit: 1 })).toEqual(HOME);
  });

  it('passes a well-formed view through', () => {
    const v = { zoom: 2, pan: { x: 10, y: -4 } };
    expect(readView(v)).toEqual(v);
  });

  it('rejects a non-finite zoom rather than propagating NaN', () => {
    expect(readView({ zoom: Number.NaN, pan: { x: 0, y: 0 } })).toEqual(HOME);
  });
});

describe('panBy', () => {
  it('adds the delta in screen pixels', () => {
    expect(panBy(HOME, 5, -3).pan).toEqual({ x: 5, y: -3 });
  });

  it('leaves zoom alone', () => {
    expect(panBy({ zoom: 3, pan: { x: 0, y: 0 } }, 1, 1).zoom).toBe(3);
  });
});

describe('zoomAt', () => {
  it('scales by the factor', () => {
    expect(zoomAt(HOME, 2, 0, 0).zoom).toBe(2);
  });

  it('keeps the cursor point fixed', () => {
    const next = zoomAt(HOME, 2, 100, 50);
    // the world point under (100,50) must still be under (100,50)
    expect(next.pan).toEqual({ x: -100, y: -50 });
  });

  it('clamps to the zoom range', () => {
    expect(zoomAt(HOME, 1000, 0, 0).zoom).toBe(64);
    expect(zoomAt(HOME, 0.0001, 0, 0).zoom).toBe(0.1);
  });

  it('composes: zooming in then out returns to home', () => {
    const there = zoomAt(HOME, 2, 40, 40);
    expect(zoomAt(there, 0.5, 40, 40)).toEqual(HOME);
  });
});

describe('cssTransform', () => {
  it('translates before it scales', () => {
    expect(cssTransform({ zoom: 2, pan: { x: 8, y: 4 } }))
      .toBe('translate(8px, 4px) scale(2)');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/panes/camera.test.ts`
Expected: FAIL — cannot resolve `@lab/panes/camera`

- [ ] **Step 3: Write the implementation**

Create `lab/src/panes/camera.ts`:

```ts
/** The shared 2D camera for a trial's panes.
 *
 * Kept out of the DOM so the fixed-point rule -- the world point under the
 * cursor stays under the cursor across a zoom -- is checked by a test rather
 * than by eye.
 */
export interface Camera {
  zoom: number;
  pan: { x: number; y: number };
}

export const HOME: Camera = { zoom: 1, pan: { x: 0, y: 0 } };
export const MIN_ZOOM = 0.1;
export const MAX_ZOOM = 64;

/** labkit hands the view back opaquely, so anything may be in it. */
export function readView(view: unknown): Camera {
  const v = view as Partial<Camera> | undefined;
  if (!v || typeof v.zoom !== 'number' || !Number.isFinite(v.zoom)) return HOME;
  const pan = v.pan;
  if (!pan || !Number.isFinite(pan.x) || !Number.isFinite(pan.y)) return HOME;
  return { zoom: v.zoom, pan: { x: pan.x, y: pan.y } };
}

export function panBy(camera: Camera, dx: number, dy: number): Camera {
  return { zoom: camera.zoom, pan: { x: camera.pan.x + dx, y: camera.pan.y + dy } };
}

/** Scale about a screen point, keeping the world point under it fixed. */
export function zoomAt(camera: Camera, factor: number, sx: number, sy: number): Camera {
  const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, camera.zoom * factor));
  const applied = zoom / camera.zoom;
  return {
    zoom,
    pan: {
      x: sx - (sx - camera.pan.x) * applied,
      y: sy - (sy - camera.pan.y) * applied,
    },
  };
}

export function cssTransform(camera: Camera): string {
  return `translate(${camera.pan.x}px, ${camera.pan.y}px) scale(${camera.zoom})`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/panes/camera.test.ts`
Expected: PASS, 10 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/panes && git commit -m "add the shared pane camera"
```

---

## Task 6: The source list

**Files:**
- Create: `lab/src/panes/sources.ts`
- Test: `lab/src/panes/sources.test.ts`

A source is one thing a pane can show. Declaring them as data is what lets the
3D and reference panes arrive later as entries rather than as a rewrite.

- [ ] **Step 1: Write the failing test**

Create `lab/src/panes/sources.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { SOURCES, enabledSources, sourceConfig } from '@lab/panes/sources';

describe('SOURCES', () => {
  it('declares naive and occt as engine sources', () => {
    expect(SOURCES.naive.kind).toBe('engine');
    expect(SOURCES.occt.kind).toBe('engine');
  });

  it('labels every source', () => {
    for (const source of Object.values(SOURCES)) expect(source.label).toBeTruthy();
  });

  it('warns that occt draws no fills', () => {
    expect(SOURCES.occt.caveat).toMatch(/outline/i);
  });

  it('warns that the 3D pane is an independent parse', () => {
    expect(SOURCES['3d'].caveat).toMatch(/not the engine/i);
  });
});

describe('enabledSources', () => {
  it('returns the declared sources in declaration order', () => {
    expect(enabledSources(['occt', 'naive']).map((s) => s.id))
      .toEqual(['naive', 'occt']);
  });

  it('ignores an unknown id rather than throwing', () => {
    expect(enabledSources(['naive', 'nope'] as never).map((s) => s.id))
      .toEqual(['naive']);
  });

  it('is empty for an empty selection', () => {
    expect(enabledSources([])).toEqual([]);
  });
});

describe('sourceConfig', () => {
  it('pins the engine for an engine source', () => {
    expect(sourceConfig(SOURCES.occt, { engine: 'naive', shading: 'outline' }))
      .toEqual({ engine: 'occt', shading: 'outline' });
  });

  it('leaves a non-engine source config alone', () => {
    const base = { engine: 'naive' };
    expect(sourceConfig(SOURCES['3d'], base)).toEqual(base);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/panes/sources.test.ts`
Expected: FAIL — cannot resolve `@lab/panes/sources`

- [ ] **Step 3: Write the implementation**

Create `lab/src/panes/sources.ts`:

```ts
import type { SourceId } from '@lab/config/nodes';

export interface Source {
  id: SourceId;
  label: string;
  /** `engine` sources render through the CLI with `--engine` pinned. */
  kind: 'engine' | 'reference' | '3d' | 'diff';
  /** Shown on the pane. Names a way the pane can look wrong while being right. */
  caveat?: string;
}

export const SOURCES: Record<SourceId, Source> = {
  naive: { id: 'naive', label: 'naive', kind: 'engine' },
  occt: {
    id: 'occt', label: 'occt', kind: 'engine',
    caveat: 'strokes only — every filled mode degrades to an outline',
  },
  reference: { id: 'reference', label: 'LDView', kind: 'reference' },
  '3d': {
    id: '3d', label: '3D', kind: '3d',
    caveat: 'LDrawLoader’s own parse — not the engine’s geometry, not LDView',
  },
  diff: { id: 'diff', label: 'diff', kind: 'diff' },
};

const ORDER: SourceId[] = ['naive', 'occt', 'reference', '3d', 'diff'];

export function enabledSources(ids: readonly SourceId[]): Source[] {
  const wanted = new Set(ids);
  return ORDER.filter((id) => wanted.has(id)).map((id) => SOURCES[id]);
}

/** The render config for one source: an engine source pins `--engine` to
 *  itself, so two panes of one trial differ in exactly that flag. */
export function sourceConfig(source: Source, config: Record<string, unknown>) {
  if (source.kind !== 'engine') return config;
  return { ...config, engine: source.id };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/panes/sources.test.ts`
Expected: PASS, 9 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/panes/sources.ts lab/src/panes/sources.test.ts
git commit -m "declare the pane sources as data"
```

---

## Task 7: The pending part

**Files:**
- Create: `lab/src/config/pending.ts`
- Test: `lab/src/config/pending.test.ts`

labkit 1.3.0's `addTrial(instrumentName)` takes no initial config, so the
search field cannot hand the part in directly. `addTrial` calls the
instrument's `defaultConfig()` synchronously, so a one-slot box set immediately
before the call is read by exactly that trial. This is the workaround the spec
records; the upstream ask is `addTrial(name, { config })`.

- [ ] **Step 1: Write the failing test**

Create `lab/src/config/pending.test.ts`:

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/config/pending.test.ts`
Expected: FAIL — cannot resolve `@lab/config/pending`

- [ ] **Step 3: Write the implementation**

Create `lab/src/config/pending.ts`:

```ts
/** The part a trial about to be added should open on.
 *
 * labkit's `addTrial(name)` takes no initial config, and calls the
 * instrument's `defaultConfig()` synchronously -- so a value set immediately
 * before the call is read by that trial and no other. Consumed on read, so a
 * trial added any other way opens empty.
 *
 * Remove this once labkit accepts `addTrial(name, { config })`.
 */
let pending = '';

export function setPendingPart(part: string): void {
  pending = part.trim();
}

export function takePendingPart(): string {
  const part = pending;
  pending = '';
  return part;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/config/pending.test.ts`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/config/pending.ts lab/src/config/pending.test.ts
git commit -m "carry the searched part into the trial being added"
```

---

## Task 8: The render job

**Files:**
- Create: `lab/src/instruments/renderJob.ts`
- Test: `lab/src/instruments/renderJob.test.ts`

labkit's `job` capability wants an async generator of events. This module is
that generator: it starts one render per enabled engine source, polls the job
route, and yields a result per source. The runtime aborts it on unmount and
whenever the key changes, which is why it checks `signal` between polls.

- [ ] **Step 1: Write the failing test**

Create `lab/src/instruments/renderJob.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { runRenders } from '@lab/instruments/renderJob';
import type { LabClient, RenderResult } from '@lab/api/client';

function result(over: Partial<RenderResult> = {}): RenderResult {
  return {
    ok: true, cached: false, argv: ['3941'], command: 'brick-icons 3941',
    key: 'k1', artifacts: [{ name: '3941.svg', bytes: 10 }], seconds: 1,
    error: null, ...over,
  };
}

function fakeClient(over: Partial<LabClient> = {}): LabClient {
  return {
    startRender: vi.fn(async () => ({ job: 'j1', argv: [], command: '' })),
    job: vi.fn(async () => ({
      id: 'j1', kind: 'render', state: 'done' as const, total: 1, done: 1,
      failed: 0, events: [], results: [result()],
    })),
    cancelJob: vi.fn(async () => {}),
    ...over,
  } as unknown as LabClient;
}

async function collect<T>(iter: AsyncIterable<T>): Promise<T[]> {
  const out: T[] = [];
  for await (const value of iter) out.push(value);
  return out;
}

describe('runRenders', () => {
  it('yields a total before any item', async () => {
    const events = await collect(runRenders({
      client: fakeClient(), part: '3941', config: {},
      sources: ['naive', 'occt'], signal: new AbortController().signal, pollMs: 0,
    }));
    expect(events[0]).toEqual({ kind: 'total', total: 2 });
  });

  it('yields one item per engine source, tagged with its source', async () => {
    const events = await collect(runRenders({
      client: fakeClient(), part: '3941', config: {},
      sources: ['naive', 'occt'], signal: new AbortController().signal, pollMs: 0,
    }));
    const items = events.filter((e) => e.kind === 'item');
    expect(items.map((e) => (e as { item: { source: string } }).item.source))
      .toEqual(['naive', 'occt']);
  });

  it('pins each render to its own engine', async () => {
    const startRender = vi.fn(async () => ({ job: 'j1', argv: [], command: '' }));
    await collect(runRenders({
      client: fakeClient({ startRender }), part: '3941',
      config: { shading: 'outline' }, sources: ['naive', 'occt'],
      signal: new AbortController().signal, pollMs: 0,
    }));
    expect(startRender.mock.calls.map((c) => (c[1] as { engine: string }).engine))
      .toEqual(['naive', 'occt']);
  });

  it('renders nothing when the part is empty', async () => {
    const startRender = vi.fn();
    const events = await collect(runRenders({
      client: fakeClient({ startRender }), part: '', config: {},
      sources: ['naive'], signal: new AbortController().signal, pollMs: 0,
    }));
    expect(startRender).not.toHaveBeenCalled();
    expect(events).toEqual([{ kind: 'total', total: 0 }]);
  });

  it('reports a failed render as a failed event AND an item the pane can show', async () => {
    const client = fakeClient({
      job: vi.fn(async () => ({
        id: 'j1', kind: 'render', state: 'done' as const, total: 1, done: 0,
        failed: 1, events: [], results: [result({ ok: false, error: 'boom' })],
      })),
    } as never);
    const events = await collect(runRenders({
      client, part: '3941', config: {}, sources: ['naive'],
      signal: new AbortController().signal, pollMs: 0,
    }));
    expect(events.some((e) => e.kind === 'failed')).toBe(true);
    const item = events.find((e) => e.kind === 'item') as
      { item: { result: { ok: boolean; error: string | null } } } | undefined;
    expect(item?.item.result.ok).toBe(false);
    expect(item?.item.result.error).toBe('boom');
  });

  it('stops when the signal aborts', async () => {
    const controller = new AbortController();
    const client = fakeClient({
      job: vi.fn(async () => {
        controller.abort();
        return { id: 'j1', kind: 'render', state: 'running' as const, total: 1,
                 done: 0, failed: 0, events: [], results: [] };
      }),
    } as never);
    const events = await collect(runRenders({
      client, part: '3941', config: {}, sources: ['naive'],
      signal: controller.signal, pollMs: 0,
    }));
    expect(events.filter((e) => e.kind === 'item')).toEqual([]);
  });

  it('skips a non-engine source, which does not render through the CLI', async () => {
    const startRender = vi.fn(async () => ({ job: 'j1', argv: [], command: '' }));
    await collect(runRenders({
      client: fakeClient({ startRender }), part: '3941', config: {},
      sources: ['naive', '3d'], signal: new AbortController().signal, pollMs: 0,
    }));
    expect(startRender).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/instruments/renderJob.test.ts`
Expected: FAIL — cannot resolve `@lab/instruments/renderJob`

- [ ] **Step 3: Write the implementation**

Create `lab/src/instruments/renderJob.ts`:

```ts
import type { LabClient, RenderResult } from '@lab/api/client';
import type { SourceId } from '@lab/config/nodes';
import { SOURCES, sourceConfig } from '@lab/panes/sources';

/** One finished render, tagged with the pane it belongs to. */
export interface SourceRender {
  source: SourceId;
  result: RenderResult;
}

export type RenderEvent =
  | { kind: 'total'; total: number }
  | { kind: 'item'; item: SourceRender }
  | { kind: 'failed'; index: number; error: string };

export interface RunRendersArgs {
  client: LabClient;
  part: string;
  config: Record<string, unknown>;
  sources: readonly SourceId[];
  signal: AbortSignal;
  /** Poll interval. Zero in tests; the app leaves it at the default. */
  pollMs?: number;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function* runRenders(
  { client, part, config, sources, signal, pollMs = 250 }: RunRendersArgs,
): AsyncIterable<RenderEvent> {
  const engines = sources.filter((id) => SOURCES[id]?.kind === 'engine');
  const wanted = part.trim() ? engines : [];
  yield { kind: 'total', total: wanted.length };

  for (const [index, id] of wanted.entries()) {
    if (signal.aborted) return;
    const started = await client.startRender(part, sourceConfig(SOURCES[id]!, config));

    let state = await client.job(started.job);
    while (state.state === 'running') {
      if (signal.aborted) return;
      await sleep(pollMs);
      if (signal.aborted) return;
      state = await client.job(started.job);
    }
    if (signal.aborted) return;

    const result = state.results[0] ?? {
      ok: false, cached: false, argv: [], command: '', key: '', artifacts: [],
      seconds: 0, error: 'the job finished without a result',
    };
    if (!result.ok) {
      // Both: `failed` so the trial chrome counts it, and `item` so the pane
      // can show the message. A failure the runtime counts but nothing
      // displays is the silent-`[]` failure in another costume.
      yield { kind: 'failed', index, error: result.error ?? 'render failed' };
    }
    yield { kind: 'item', item: { source: id, result } };
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/instruments/renderJob.test.ts`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/instruments && git commit -m "run one render per engine source as a labkit job"
```

---

## Task 9: The pane component

**Files:**
- Create: `lab/src/panes/SourcePane.tsx`, `lab/src/panes/SourcePane.css`
- Test: `lab/src/panes/SourcePane.test.tsx`

Engine output is the SVG itself, not a raster of it: the SVG is the artifact
under test, and it stays sharp however far the camera zooms.

- [ ] **Step 1: Add the testing-library dependencies**

Run: `cd lab && npm install -D @testing-library/react@^16 @testing-library/dom@^10`
Expected: both install.

- [ ] **Step 2: Write the failing test**

Create `lab/src/panes/SourcePane.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SourcePane } from '@lab/panes/SourcePane';
import { HOME } from '@lab/panes/camera';
import { SOURCES } from '@lab/panes/sources';

const props = { camera: HOME, onCamera: () => {} };

describe('SourcePane', () => {
  it('labels itself with the source', () => {
    render(<SourcePane {...props} source={SOURCES.naive} state={{ kind: 'idle' }} />);
    expect(screen.getByText('naive')).toBeTruthy();
  });

  it('shows the caveat when the source has one', () => {
    render(<SourcePane {...props} source={SOURCES.occt} state={{ kind: 'idle' }} />);
    expect(screen.getByText(/strokes only/)).toBeTruthy();
  });

  it('renders the SVG inline rather than as an image', () => {
    const { container } = render(
      <SourcePane {...props} source={SOURCES.naive}
        state={{ kind: 'svg', markup: '<svg viewBox="0 0 4 4"><rect/></svg>' }} />);
    expect(container.querySelector('svg')).toBeTruthy();
    expect(container.querySelector('img')).toBeNull();
  });

  it('renders a raster source as an image', () => {
    const { container } = render(
      <SourcePane {...props} source={SOURCES.reference}
        state={{ kind: 'image', src: '/api/artifact/k/r.png' }} />);
    expect(container.querySelector('img')?.getAttribute('src'))
      .toBe('/api/artifact/k/r.png');
  });

  it('shows the error when a render failed', () => {
    render(<SourcePane {...props} source={SOURCES.occt}
      state={{ kind: 'error', message: 'TopologyException' }} />);
    expect(screen.getByText(/TopologyException/)).toBeTruthy();
  });

  it('applies the camera as a transform', () => {
    const { container } = render(
      <SourcePane {...props} camera={{ zoom: 2, pan: { x: 8, y: 4 } }}
        source={SOURCES.naive}
        state={{ kind: 'svg', markup: '<svg viewBox="0 0 4 4"></svg>' }} />);
    const stage = container.querySelector('.pane-stage') as HTMLElement;
    expect(stage.style.transform).toBe('translate(8px, 4px) scale(2)');
  });

  it('says so while a render is in flight', () => {
    render(<SourcePane {...props} source={SOURCES.naive} state={{ kind: 'running' }} />);
    expect(screen.getByText(/rendering/i)).toBeTruthy();
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd lab && npx vitest run src/panes/SourcePane.test.tsx`
Expected: FAIL — cannot resolve `@lab/panes/SourcePane`

- [ ] **Step 4: Write the implementation**

Create `lab/src/panes/SourcePane.css`:

```css
.pane {
  display: flex;
  flex-direction: column;
  min-width: 0;
  border: 1px solid var(--lk-border, #3a3a3a);
  border-radius: 4px;
  overflow: hidden;
}

.pane-head {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
}

.pane-caveat { opacity: 0.7; font-style: italic; }
.pane-error { color: var(--lk-danger, #d05098); padding: 0.5rem; font-size: 0.75rem; }

.pane-body {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  touch-action: none;
}

.pane-stage {
  position: absolute;
  inset: 0;
  transform-origin: 0 0;
}

.pane-stage svg,
.pane-stage img { width: 100%; height: 100%; }
```

Create `lab/src/panes/SourcePane.tsx`:

```tsx
import { useRef } from 'react';
import { type Camera, cssTransform, panBy, zoomAt } from '@lab/panes/camera';
import type { Source } from '@lab/panes/sources';
import '@lab/panes/SourcePane.css';

export type PaneState =
  | { kind: 'idle' }
  | { kind: 'running' }
  | { kind: 'svg'; markup: string }
  | { kind: 'image'; src: string }
  | { kind: 'error'; message: string };

export interface SourcePaneProps {
  source: Source;
  state: PaneState;
  camera: Camera;
  onCamera: (next: Camera) => void;
}

export function SourcePane({ source, state, camera, onCamera }: SourcePaneProps) {
  const dragging = useRef(false);

  return (
    <section className="pane">
      <header className="pane-head">
        <strong>{source.label}</strong>
        {source.caveat ? <span className="pane-caveat">{source.caveat}</span> : null}
      </header>
      {state.kind === 'error' ? <p className="pane-error">{state.message}</p> : null}
      <div
        className="pane-body"
        onPointerDown={(e) => {
          dragging.current = true;
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerUp={() => { dragging.current = false; }}
        onPointerMove={(e) => {
          if (dragging.current) onCamera(panBy(camera, e.movementX, e.movementY));
        }}
        onWheel={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
          onCamera(zoomAt(camera, factor, e.clientX - box.left, e.clientY - box.top));
        }}
      >
        <div className="pane-stage" style={{ transform: cssTransform(camera) }}>
          {state.kind === 'svg' ? (
            // The SVG is the artifact under test; a raster of it would be a proxy.
            <div dangerouslySetInnerHTML={{ __html: state.markup }} />
          ) : null}
          {state.kind === 'image' ? <img src={state.src} alt={source.label} /> : null}
          {state.kind === 'running' ? <p>rendering…</p> : null}
        </div>
      </div>
    </section>
  );
}
```

The `style` attribute here is the one place an inline style is unavoidable: the
transform changes on every pointer move, and a CSS class cannot carry a value
that changes per frame.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd lab && npx vitest run src/panes/SourcePane.test.tsx`
Expected: PASS, 7 tests

- [ ] **Step 6: Commit**

```bash
git add lab/src/panes && git commit -m "render one source as a pane"
```

---

## Task 10: The command line readout

**Files:**
- Create: `lab/src/chrome/CommandLine.tsx`
- Test: `lab/src/chrome/CommandLine.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `lab/src/chrome/CommandLine.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CommandLine } from '@lab/chrome/CommandLine';
import type { LabClient } from '@lab/api/client';

const client = (command: string) => ({
  command: vi.fn(async () => ({ argv: command.split(' ').slice(1), command })),
} as unknown as LabClient);

describe('CommandLine', () => {
  it('shows the command the server reports', async () => {
    render(<CommandLine client={client('brick-icons 3941 --engine occt')}
      part="3941" config={{ engine: 'occt' }} />);
    await waitFor(() =>
      expect(screen.getByText('brick-icons 3941 --engine occt')).toBeTruthy());
  });

  it('shows nothing to run when no part is chosen', () => {
    const api = client('');
    render(<CommandLine client={api} part="" config={{}} />);
    expect(api.command).not.toHaveBeenCalled();
    expect(screen.getByText(/no part/i)).toBeTruthy();
  });

  it('asks the server again when the config changes', async () => {
    const api = client('brick-icons 3941');
    const { rerender } = render(
      <CommandLine client={api} part="3941" config={{ engine: 'naive' }} />);
    await waitFor(() => expect(api.command).toHaveBeenCalledTimes(1));
    rerender(<CommandLine client={api} part="3941" config={{ engine: 'occt' }} />);
    await waitFor(() => expect(api.command).toHaveBeenCalledTimes(2));
  });

  it('does not ask again when nothing changed', async () => {
    const api = client('brick-icons 3941');
    const { rerender } = render(
      <CommandLine client={api} part="3941" config={{ engine: 'occt' }} />);
    await waitFor(() => expect(api.command).toHaveBeenCalledTimes(1));
    rerender(<CommandLine client={api} part="3941" config={{ engine: 'occt' }} />);
    expect(api.command).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/chrome/CommandLine.test.tsx`
Expected: FAIL — cannot resolve `@lab/chrome/CommandLine`

- [ ] **Step 3: Write the implementation**

Create `lab/src/chrome/CommandLine.tsx`:

```tsx
import { useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';

export interface CommandLineProps {
  client: LabClient;
  part: string;
  config: Record<string, unknown>;
}

/** The CLI command this trial is equivalent to, always on screen.
 *
 * The argv comes from the server, which builds it with the same function the
 * render uses. Building it here instead would be a second answer to what a
 * flag means. */
export function CommandLine({ client, part, config }: CommandLineProps) {
  const [command, setCommand] = useState('');
  const signature = `${part} ${JSON.stringify(config)}`;

  useEffect(() => {
    if (!part.trim()) {
      setCommand('');
      return;
    }
    let live = true;
    client.command(part, config).then((got) => {
      if (live) setCommand(got.command);
    }).catch(() => { if (live) setCommand(''); });
    return () => { live = false; };
  }, [signature]);

  if (!part.trim()) return <code className="command-line">no part chosen</code>;

  return (
    <code
      className="command-line"
      title="click to copy"
      role="button"
      tabIndex={0}
      onClick={() => navigator.clipboard?.writeText(command)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') navigator.clipboard?.writeText(command);
      }}
    >
      {command}
    </code>
  );
}
```

The click target is a `<code>` with `role="button"` and a key handler rather
than a `<button>`: a button is an atomic inline-block that reports its last
line's baseline, and this sits inline in a status bar beside other text.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/chrome/CommandLine.test.tsx`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/chrome && git commit -m "keep the equivalent CLI command on screen"
```

---

## Task 11: The Part Inspector instrument

**Files:**
- Create: `lab/src/instruments/partInspector.tsx`
- Test: `lab/src/instruments/partInspector.test.ts`

- [ ] **Step 1: Write the failing test**

Create `lab/src/instruments/partInspector.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { createPartInspector } from '@lab/instruments/partInspector';
import { setPendingPart } from '@lab/config/pending';
import type { LabClient } from '@lab/api/client';
import type { SchemaField } from '@lab/api/types';

const FIELDS: SchemaField[] = [
  { key: 'engine', flag: '--engine', type: 'str', choices: ['naive', 'occt'],
    help: '', nargs: null, default: null },
  { key: 'shading', flag: '--shading', type: 'str',
    choices: ['normal', 'cel', 'outline'], help: '', nargs: null, default: null },
];

const client = {} as LabClient;

describe('createPartInspector', () => {
  it('is named for the workspace', () => {
    expect(createPartInspector(FIELDS, client).name).toBe('part-inspector');
  });

  it('opens on the pending part', () => {
    setPendingPart('3941');
    expect(createPartInspector(FIELDS, client).defaultConfig().part).toBe('3941');
  });

  it('opens empty when nothing is pending', () => {
    expect(createPartInspector(FIELDS, client).defaultConfig().part).toBe('');
  });

  it('takes its config keys from the schema it was given', () => {
    const config = createPartInspector(FIELDS, client).defaultConfig();
    expect(config.engine).toBe('naive');
    expect(config.shading).toBe('normal');
  });

  it('declares the sources as layers', () => {
    const ids = createPartInspector(FIELDS, client).layers?.ids ?? [];
    expect(ids).toContain('naive');
    expect(ids).toContain('occt');
  });

  it('re-runs the job when the part changes', () => {
    const instrument = createPartInspector(FIELDS, client);
    const state = instrument.initialState(instrument.defaultConfig());
    const before = instrument.job!.key!({ ...instrument.defaultConfig(), part: '3941' }, state);
    const after = instrument.job!.key!({ ...instrument.defaultConfig(), part: '4070' }, state);
    expect(before).not.toEqual(after);
  });

  it('re-runs the job when a render flag changes', () => {
    const instrument = createPartInspector(FIELDS, client);
    const base = { ...instrument.defaultConfig(), part: '3941' };
    const state = instrument.initialState(base);
    expect(instrument.job!.key!(base, state))
      .not.toEqual(instrument.job!.key!({ ...base, shading: 'outline' }, state));
  });

  it('does not re-run the job when only the layout changes', () => {
    const instrument = createPartInspector(FIELDS, client);
    const base = { ...instrument.defaultConfig(), part: '3941' };
    const state = instrument.initialState(base);
    expect(instrument.job!.key!(base, state))
      .toEqual(instrument.job!.key!({ ...base, layout: 'stack' }, state));
  });

  it('records a failed render as the pane\'s error', () => {
    const instrument = createPartInspector(FIELDS, client);
    const state = instrument.initialState(instrument.defaultConfig());
    const next = instrument.job!.onItem(
      { source: 'occt', result: { ok: false, cached: false, argv: [], command: '',
        key: '', artifacts: [], seconds: 0, error: 'TopologyException' } },
      state);
    expect(next.errors.occt).toBe('TopologyException');
  });

  it('folds a finished render into state under its source', () => {
    const instrument = createPartInspector(FIELDS, client);
    const state = instrument.initialState(instrument.defaultConfig());
    const next = instrument.job!.onItem(
      { source: 'occt', result: { ok: true, cached: false, argv: [], command: '',
        key: 'k1', artifacts: [{ name: '3941.svg', bytes: 1 }], seconds: 2,
        error: null } },
      state);
    expect(next.renders.occt?.key).toBe('k1');
  });

  it('contributes the command line to the chrome', () => {
    const ids = (createPartInspector(FIELDS, client).chrome ?? []).map((c) => c.id);
    expect(ids).toContain('command-line');
  });

  it('starts the job automatically', () => {
    expect(createPartInspector(FIELDS, client).job!.auto).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/instruments/partInspector.test.ts`
Expected: FAIL — cannot resolve `@lab/instruments/partInspector`

- [ ] **Step 3: Write the implementation**

Create `lab/src/instruments/partInspector.tsx`:

```tsx
import { defineInstrument, f } from '@weasel-js/labkit';
import type { LabClient, RenderResult, SchemaField } from '@lab/api/client';
import { buildSchema, defaultsFor, renderConfig, type SourceId } from '@lab/config/nodes';
import { takePendingPart } from '@lab/config/pending';
import { CommandLine } from '@lab/chrome/CommandLine';
import { SourcePane, type PaneState } from '@lab/panes/SourcePane';
import { readView } from '@lab/panes/camera';
import { SOURCES, enabledSources } from '@lab/panes/sources';
import { runRenders, type SourceRender } from '@lab/instruments/renderJob';

export interface InspectorState {
  renders: Partial<Record<SourceId, RenderResult>>;
  errors: Partial<Record<SourceId, string>>;
}

function paneState(source: SourceId, state: InspectorState,
                   svg: Partial<Record<SourceId, string>>): PaneState {
  if (state.errors[source]) return { kind: 'error', message: state.errors[source]! };
  const markup = svg[source];
  if (markup) return { kind: 'svg', markup };
  if (state.renders[source]) return { kind: 'running' };
  return { kind: 'idle' };
}

export function createPartInspector(fields: SchemaField[], client: LabClient) {
  const nodes = buildSchema(fields);
  const defaults = defaultsFor(fields);

  return defineInstrument<InspectorState, Record<string, unknown>, SourceRender>({
    name: 'part-inspector',

    config: f.schema({ part: f.string(''), ...nodes } as never) as never,

    // Both `config` and `defaultConfig` are supplied. `defineInstrument`
    // synthesizes the latter only when it is absent, and `addTrial` calls it,
    // which is how the pending part reaches the new trial. Task 15's
    // walkthrough is what confirms this at runtime.
    defaultConfig: () => ({ ...defaults, part: takePendingPart() }),

    initialState: () => ({ renders: {}, errors: {} }),

    layers: { ids: Object.values(SOURCES).map((s) => s.id) },

    chrome: [
      {
        id: 'command-line',
        region: 'status',
        render: (ctx) => (
          <CommandLine
            client={client}
            part={String((ctx.config as Record<string, unknown>).part ?? '')}
            config={renderConfig(ctx.config as Record<string, unknown>)}
          />
        ),
      },
    ],

    job: {
      auto: true,
      // Only what changes a render: the layout toggle rearranges panes that
      // are already drawn, and re-running on it would throw them away.
      key: (config) => [
        config.part,
        JSON.stringify(renderConfig(config)),
        (config.sources as SourceId[]).join(','),
      ],
      run: ({ config, signal }) => runRenders({
        client,
        part: String(config.part ?? ''),
        config: renderConfig(config),
        sources: (config.sources as SourceId[]) ?? [],
        signal,
      }),
      onItem: (item, state) => ({
        renders: { ...state.renders, [item.source]: item.result },
        errors: {
          ...state.errors,
          [item.source]: item.result.ok ? undefined : (item.result.error ?? 'render failed'),
        },
      }),
    },

    render: (ctx) => {
      const config = ctx.config as Record<string, unknown>;
      const camera = readView(ctx.trial.view);
      const sources = enabledSources((config.sources as SourceId[]) ?? []);
      const stack = config.layout === 'stack';

      return (
        <div className={stack ? 'panes panes-stack' : 'panes panes-split'}>
          {sources.map((source) => (
            <SourcePane
              key={source.id}
              source={source}
              state={paneState(source.id, ctx.state, {})}
              camera={camera}
              onCamera={(next) => ctx.trial.setView(next)}
            />
          ))}
        </div>
      );
    },
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/instruments/partInspector.test.ts`
Expected: PASS, 12 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/instruments/partInspector.tsx lab/src/instruments/partInspector.test.ts
git commit -m "add the Part Inspector instrument"
```

---

## Task 12: Fetch and show the SVG markup

**Files:**
- Create: `lab/src/panes/useArtifactSvg.ts`
- Modify: `lab/src/instruments/partInspector.tsx`
- Test: `lab/src/panes/useArtifactSvg.test.ts`

Task 11 left `paneState` reading an empty markup map — the render result names
an artifact but nobody has fetched its text. This closes that.

- [ ] **Step 1: Write the failing test**

Create `lab/src/panes/useArtifactSvg.test.ts`:

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/panes/useArtifactSvg.test.ts`
Expected: FAIL — cannot resolve `@lab/panes/useArtifactSvg`

- [ ] **Step 3: Write the implementation**

Create `lab/src/panes/useArtifactSvg.ts`:

```ts
import { useEffect, useState } from 'react';
import type { Artifact, LabClient, RenderResult } from '@lab/api/client';
import type { SourceId } from '@lab/config/nodes';

/** The render's own SVG. `.unwrap.svg` and `.decal.svg` are debug output from
 *  other stages and are not what the pane shows. */
export function svgArtifactName(artifacts: Artifact[]): string | null {
  const hit = artifacts.find((a) => a.name.endsWith('.svg')
    && !a.name.includes('.unwrap.') && !a.name.includes('.decal.'));
  return hit ? hit.name : null;
}

export async function fetchSvgMarkup(url: string,
                                     fetchImpl: typeof fetch = fetch): Promise<string | null> {
  const response = await fetchImpl(url);
  if (!response.ok) return null;
  return response.text();
}

/** SVG markup for each finished render, keyed by source. */
export function useArtifactSvg(client: LabClient,
                               renders: Partial<Record<SourceId, RenderResult>>) {
  const [markup, setMarkup] = useState<Partial<Record<SourceId, string>>>({});

  const signature = Object.entries(renders)
    .map(([id, r]) => `${id}:${r?.key ?? ''}`).sort().join('|');

  useEffect(() => {
    let live = true;
    (async () => {
      const next: Partial<Record<SourceId, string>> = {};
      for (const [id, result] of Object.entries(renders)) {
        if (!result) continue;
        const name = svgArtifactName(result.artifacts);
        if (!name) continue;
        const text = await fetchSvgMarkup(client.artifactUrl(result.key, name));
        if (text) next[id as SourceId] = text;
      }
      if (live) setMarkup(next);
    })();
    return () => { live = false; };
    // `signature` is the whole dependency: the render keys are what change.
  }, [signature]);

  return markup;
}
```

- [ ] **Step 4: Wire it into the instrument**

In `lab/src/instruments/partInspector.tsx`, add the import:

```tsx
import { useArtifactSvg } from '@lab/panes/useArtifactSvg';
```

Replace the body of `render` with a component, because a hook cannot be called
in `render(ctx)` directly:

```tsx
    render: (ctx) => <Panes ctx={ctx} client={client} />,
```

and add above `createPartInspector`:

```tsx
function Panes({ ctx, client }: { ctx: any; client: LabClient }) {
  const config = ctx.config as Record<string, unknown>;
  const camera = readView(ctx.trial.view);
  const sources = enabledSources((config.sources as SourceId[]) ?? []);
  const markup = useArtifactSvg(client, (ctx.state as InspectorState).renders);
  const stack = config.layout === 'stack';

  return (
    <div className={stack ? 'panes panes-stack' : 'panes panes-split'}>
      {sources.map((source) => (
        <SourcePane
          key={source.id}
          source={source}
          state={paneState(source.id, ctx.state as InspectorState, markup)}
          camera={camera}
          onCamera={(next) => ctx.trial.setView(next)}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Run the tests**

Run: `cd lab && npx vitest run`
Expected: PASS, every suite

- [ ] **Step 6: Commit**

```bash
git add lab/src && git commit -m "show each render's SVG in its pane"
```

---

## Task 13: The title-bar part search

**Files:**
- Create: `lab/src/chrome/PartSearch.tsx`
- Test: `lab/src/chrome/PartSearch.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `lab/src/chrome/PartSearch.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PartSearch } from '@lab/chrome/PartSearch';
import { takePendingPart } from '@lab/config/pending';
import type { LabClient } from '@lab/api/client';

const client = (results: { id: string; description: string; printed: boolean }[]) =>
  ({ searchParts: vi.fn(async () => results) } as unknown as LabClient);

describe('PartSearch', () => {
  it('opens a trial on the typed part when Enter is pressed', () => {
    const onOpen = vi.fn();
    render(<PartSearch client={client([])} onOpen={onOpen} />);
    const input = screen.getByPlaceholderText(/part/i);
    fireEvent.change(input, { target: { value: '3941' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onOpen).toHaveBeenCalledWith('3941');
  });

  it('leaves the part pending for the trial about to be added', () => {
    render(<PartSearch client={client([])} onOpen={() => {}} />);
    const input = screen.getByPlaceholderText(/part/i);
    fireEvent.change(input, { target: { value: '4070' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(takePendingPart()).toBe('4070');
  });

  it('does nothing on Enter with an empty field', () => {
    const onOpen = vi.fn();
    render(<PartSearch client={client([])} onOpen={onOpen} />);
    fireEvent.keyDown(screen.getByPlaceholderText(/part/i), { key: 'Enter' });
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('lists typeahead hits with their descriptions', async () => {
    const api = client([{ id: '3001', description: 'Brick  2 x  4', printed: false }]);
    render(<PartSearch client={api} onOpen={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText(/part/i),
      { target: { value: 'brick 2 x 4' } });
    await waitFor(() => expect(screen.getByText(/Brick  2 x  4/)).toBeTruthy());
  });

  it('opens the part a hit names when the hit is clicked', async () => {
    const onOpen = vi.fn();
    const api = client([{ id: '3001', description: 'Brick  2 x  4', printed: false }]);
    render(<PartSearch client={api} onOpen={onOpen} />);
    fireEvent.change(screen.getByPlaceholderText(/part/i), { target: { value: 'brick' } });
    await waitFor(() => screen.getByText(/Brick  2 x  4/));
    fireEvent.click(screen.getByText(/Brick  2 x  4/));
    expect(onOpen).toHaveBeenCalledWith('3001');
  });

  it('does not search on an empty query', () => {
    const api = client([]);
    render(<PartSearch client={api} onOpen={() => {}} />);
    expect(api.searchParts).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/chrome/PartSearch.test.tsx`
Expected: FAIL — cannot resolve `@lab/chrome/PartSearch`

- [ ] **Step 3: Write the implementation**

Create `lab/src/chrome/PartSearch.tsx`:

```tsx
import { useEffect, useState } from 'react';
import type { LabClient, PartHit } from '@lab/api/client';
import { setPendingPart } from '@lab/config/pending';

export interface PartSearchProps {
  client: LabClient;
  /** Called with the part id after the pending slot is set. */
  onOpen: (part: string) => void;
}

export function PartSearch({ client, onOpen }: PartSearchProps) {
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<PartHit[]>([]);

  useEffect(() => {
    if (!query.trim()) {
      setHits([]);
      return;
    }
    let live = true;
    const timer = setTimeout(() => {
      client.searchParts(query).then((found) => { if (live) setHits(found); })
        .catch(() => { if (live) setHits([]); });
    }, 120);
    return () => { live = false; clearTimeout(timer); };
  }, [query]);

  function open(part: string) {
    if (!part.trim()) return;
    setPendingPart(part);
    onOpen(part.trim());
    setQuery('');
    setHits([]);
  }

  return (
    <div className="part-search">
      <input
        type="search"
        placeholder="part id or description"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') open(query); }}
      />
      {hits.length > 0 ? (
        <ul className="part-search-hits">
          {hits.map((hit) => (
            <li key={hit.id}>
              <span
                role="button"
                tabIndex={0}
                onClick={() => open(hit.id)}
                onKeyDown={(e) => { if (e.key === 'Enter') open(hit.id); }}
              >
                <strong>{hit.id}</strong> {hit.description}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
```

The hit's click target is a `<span>` inside the `<li>`, not the `<li>` itself:
a list item's box and role belong to the list, so interaction hangs on a child.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/chrome/PartSearch.test.tsx`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/chrome/PartSearch.tsx lab/src/chrome/PartSearch.test.tsx
git commit -m "search parts from the workspace title bar"
```

---

## Task 14: Boot the lab

**Files:**
- Modify: `lab/src/main.tsx`
- Create: `lab/src/App.tsx`, `lab/src/app.css`

The schema arrives from the server, and `defineInstrument` needs it before the
first render — so the fetch happens before React mounts. That is what makes the
control panel genuinely the CLI's flag set rather than a copy of it.

- [ ] **Step 1: Write the app shell**

Create `lab/src/App.tsx`:

```tsx
import { Lab, LabShell, Workspace, useLabContext } from '@weasel-js/labkit';
import type { Instrument } from '@weasel-js/labkit';
import type { LabClient } from '@lab/api/client';
import { PartSearch } from '@lab/chrome/PartSearch';
import '@lab/app.css';

function TitleBar({ client }: { client: LabClient }) {
  const { addTrial } = useLabContext();
  // `addTrial` reads the pending part through the instrument's defaultConfig;
  // see src/config/pending.ts.
  return <PartSearch client={client} onOpen={() => addTrial('part-inspector')} />;
}

export function App({ instrument, client }: { instrument: Instrument; client: LabClient }) {
  return (
    <Lab
      instruments={[instrument]}
      defaultInstrument="part-inspector"
      storageKey="brick-icons-lab"
      title="brick-icons lab"
    >
      <LabShell title="brick-icons lab" header={<TitleBar client={client} />}>
        <Workspace />
      </LabShell>
    </Lab>
  );
}
```

Create `lab/src/app.css`:

```css
.panes { display: flex; gap: 0.5rem; width: 100%; height: 100%; }
.panes-split > .pane { flex: 1 1 0; }
.panes-stack { display: grid; }
.panes-stack > .pane { grid-area: 1 / 1; }

.part-search { position: relative; }
.part-search input { min-width: 18rem; }

.part-search-hits {
  position: absolute;
  z-index: 10;
  margin: 0;
  padding: 0.25rem 0;
  list-style: none;
  max-height: 20rem;
  overflow-y: auto;
  background: var(--lk-surface, #1b1b1b);
  border: 1px solid var(--lk-border, #3a3a3a);
}

.part-search-hits li > span { display: block; padding: 0.15rem 0.5rem; cursor: pointer; }
.part-search-hits li > span:hover { background: var(--lk-surface-hover, #2a2a2a); }

.command-line { cursor: pointer; font-size: 0.75rem; }
```

- [ ] **Step 2: Write the entry point**

Replace `lab/src/main.tsx`:

```tsx
import { createRoot } from 'react-dom/client';
import '@weasel-js/labkit/styles.css';
import { createClient } from '@lab/api/client';
import { createPartInspector } from '@lab/instruments/partInspector';
import { App } from '@lab/App';

const root = createRoot(document.getElementById('root')!);
const client = createClient();

// The schema is fetched before mount because `defineInstrument` needs it: the
// control panel is the CLI's flag set, not a copy of it.
client.schema().then((fields) => {
  root.render(<App instrument={createPartInspector(fields, client)} client={client} />);
}).catch((error: Error) => {
  root.render(
    <p>
      cannot reach the lab server — start it with
      <code> python -m brick_icons.lab</code> ({error.message})
    </p>,
  );
});
```

- [ ] **Step 3: Typecheck and test**

Run: `cd lab && npm run typecheck && npx vitest run`
Expected: no type errors; every suite passes. If `defineInstrument`'s generics
reject the dynamically-built schema, keep the `as never` casts already in
`partInspector.tsx` — the schema's shape is only known at runtime, which is the
one place the type system cannot help.

- [ ] **Step 4: Commit**

```bash
git add lab/src && git commit -m "boot the lab against the server's schema"
```

---

## Task 15: See it work

**Files:** none — this is the verification step.

- [ ] **Step 1: Start the server**

Run: `.venv/bin/python -m brick_icons.lab &`
Expected: `lab on http://127.0.0.1:8765`

- [ ] **Step 2: Start the frontend**

Run: `cd lab && npm run dev`
Expected: Vite serves on `http://localhost:5178`.

- [ ] **Step 3: Drive it**

Open `http://localhost:5178`, type `3941` in the title-bar field and press
Enter. Confirm, in order:

1. a trial appears;
2. the status bar reads `brick-icons 3941 --format svg --shading outline …`
   with whatever the defaults are;
3. two panes appear, labeled `naive` and `occt`, the `occt` one carrying its
   strokes-only caveat;
4. both panes draw the part;
5. dragging in one pane pans both, and the wheel zooms both about the cursor;
6. changing `--shading` in the control panel re-renders both panes and updates
   the command.

Then confirm the command is the truth: copy it out of the status bar, run it in
a terminal, and check the SVG it writes matches what the pane shows.

- [ ] **Step 4: Stop the servers**

Run: `kill %1` for the Python server; Ctrl-C the Vite one.

- [ ] **Step 5: Commit anything the walkthrough forced**

If step 3 turned up a defect, fix it, add the test that would have caught it,
and commit. If it did not, there is nothing to commit here.

---

## Task 16: Document the frontend

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Extend the lab section**

Add to the `## Lab server` section of `README.md`:

````markdown
The frontend lives in `lab/`:

```sh
cd lab && npm install
npm run dev            # http://localhost:5178, proxying /api to the server
```

Type a part id in the title bar to open a trial. Its control panel is built
from `/api/schema` at boot, so it is the CLI's flag set; the command in the
status bar is the argv the server ran, and running it yourself gives the same
SVG the pane shows.
````

- [ ] **Step 2: Commit**

```bash
git add README.md && git commit -m "document the lab frontend"
```

---

## Self-review notes

**Spec coverage.** Title-bar search (Tasks 7, 13), the trial's config as the
CLI's argv (Tasks 3, 4, 10), split and stack layouts (Tasks 6, 11, 14), shared
camera across panes (Tasks 5, 9), inline SVG for engine output (Tasks 9, 12),
the `job` capability driving renders with cancel (Task 8), `layers` for the
source toggles (Task 11), the occt strokes-only caveat and the 3D pane's
caveat (Task 6).

**Not in this plan.** Marking a defect on a pane, the defect panel and
`scripts/defects-to-handoff.py`; the reference and 3D sources; the contact
sheet and golden status readouts. They are declared in `sources.ts` and
`layers.ids` so the panes exist as toggles, but only the two engine sources
render — the rest arrive in plans 3, 4 and 5.

**The workaround this plan carries.** `lab/src/config/pending.ts` exists only
because labkit 1.3.0's `addTrial(instrumentName)` takes no initial config. It
is one module with one test file, and deleting it is the whole of the
follow-up once `addTrial(name, { config })` lands.
