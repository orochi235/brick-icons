# Lab Contact Sheet and Golden Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render a whole corpus list as one job and review it as a grid, clicking any cell to open that part; and tell you, per part, whether its frozen goldens still match.

**Architecture:** A second labkit instrument whose job is `/api/batch` over a named list. Golden status is an exact comparison — the frozen digest is `sha256` of the SVG text — so the lab re-renders each combo the part appears in and compares digests, rather than guessing from a summary.

**Tech Stack:** Python, pytest; React 19, TypeScript, Vitest.

**Depends on:** `2026-08-31-lab-server.md` and `2026-08-31-lab-part-inspector.md`. `POST /api/batch`, `brick_icons/lab/corpus.py` and `brick_icons/lab/goldens_status.py` already exist.

**Spec:** `docs/superpowers/specs/2026-08-31-corpus-lab-design.md`

---

## What the golden hash actually is

`scripts/freeze-goldens.py` writes `hashes[case["id"]] = goldens.sha256(svg)` —
the SHA-256 of the SVG **text**, keyed by `<combo>__<part>`. Combos and their
argument lists live in `tests/goldens/manifest.toml` under `[combo.<name>]`,
each naming a `parts` list and an `args` array.

So a comparison is exact and needs no tolerance: render the part with that
combo's args, hash the SVG, compare strings. What it costs is a render per
combo the part belongs to, which is why it is a job rather than a GET.

---

## File Structure

| file | responsibility |
|---|---|
| `brick_icons/lab/corpus.py` (modify) | `combos()` — the manifest's combo definitions |
| `brick_icons/lab/goldens_status.py` (modify) | `cases_for` and `compare_case` |
| `brick_icons/lab/app.py` (modify) | `GET /api/combos`, `POST /api/goldens/check` |
| `lab/src/chrome/GoldenStatus.tsx` | the status-bar readout |
| `lab/src/instruments/contactSheet.tsx` | the grid instrument |
| `lab/src/instruments/sheetJob.ts` | its batch job |

---

## Task 1: Read the manifest's combos

**Files:**
- Modify: `brick_icons/lab/corpus.py`
- Test: `tests/test_lab_corpus.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lab_corpus.py`:

```python
def test_combos_come_from_the_manifest():
    names = {c["name"] for c in corpus.combos(root=ROOT)}
    assert {"outline-flat3", "outline", "wireframe"} <= names


def test_a_combo_carries_its_args():
    got = {c["name"]: c for c in corpus.combos(root=ROOT)}["outline"]
    assert "--shading" in got["args"]
    assert got["args"][got["args"].index("--shading") + 1] == "outline"


def test_a_combo_resolves_its_parts_list():
    got = {c["name"]: c for c in corpus.combos(root=ROOT)}["outline"]
    assert "3941" in got["parts"]
    assert "3941p01" not in got["parts"]      # `outline` runs unprinted only


def test_combos_are_empty_without_a_manifest(tmp_path):
    assert corpus.combos(root=tmp_path) == []


def test_combos_for_names_only_the_ones_a_part_is_in():
    names = {c["name"] for c in corpus.combos_for(ROOT, "3941p01")}
    assert "outline-flat3" in names
    assert "outline" not in names             # printed parts are out of that gate


def test_combos_for_an_unknown_part_is_empty():
    assert corpus.combos_for(ROOT, "not-a-part") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_corpus.py -k combo -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'combos'`

- [ ] **Step 3: Write the implementation**

Append to `brick_icons/lab/corpus.py`:

```python
def combos(root: Path | str = ".") -> list[dict]:
    """The manifest's combos: name, argument list, and the parts they cover.

    A combo names a parts list rather than repeating its ids, so the list is
    resolved here -- the manifest stays the one place a case is declared.
    """
    manifest = Path(root) / _MANIFEST
    if not manifest.exists():
        return []
    data = tomllib.loads(manifest.read_text())
    lists = data.get("parts", {})
    out = []
    for name, spec in data.get("combo", {}).items():
        parts = spec.get("parts")
        resolved = list(lists.get(parts, [])) if isinstance(parts, str) else list(parts or [])
        out.append({"name": name, "args": list(spec.get("args", [])),
                    "parts": resolved})
    return out


def combos_for(root: Path | str, part: str) -> list[dict]:
    """The combos a part is actually a case in."""
    return [c for c in combos(root) if part in c["parts"]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_corpus.py -v`
Expected: PASS, 11 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/corpus.py tests/test_lab_corpus.py
git commit -m "read the golden manifest's combo definitions"
```

---

## Task 2: Compare a part against its frozen goldens

**Files:**
- Modify: `brick_icons/lab/goldens_status.py`
- Test: `tests/test_lab_goldens_status.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lab_goldens_status.py`:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_cases_for_pairs_a_part_with_each_combos_argv():
    cases = goldens_status.cases_for(ROOT, "3941")
    names = {c["case"] for c in cases}
    assert "outline-flat3__3941" in names
    one = next(c for c in cases if c["case"] == "outline-flat3__3941")
    assert one["argv"][0] == "3941"
    assert "--shade-style" in one["argv"]


def test_cases_for_an_unknown_part_is_empty():
    assert goldens_status.cases_for(ROOT, "not-a-part") == []


def test_compare_case_reports_match_when_the_digest_is_equal(tmp_path):
    svg = tmp_path / "3005.svg"
    svg.write_text("<svg/>")
    from brick_icons import goldens
    got = goldens_status.compare_case(svg, goldens.sha256("<svg/>"))
    assert got == {"state": "match", "frozen": goldens.sha256("<svg/>"),
                   "fresh": goldens.sha256("<svg/>")}


def test_compare_case_reports_moved_when_it_is_not(tmp_path):
    svg = tmp_path / "3005.svg"
    svg.write_text("<svg/>")
    assert goldens_status.compare_case(svg, "deadbeef")["state"] == "moved"


def test_compare_case_reports_a_missing_render(tmp_path):
    assert goldens_status.compare_case(tmp_path / "gone.svg", "deadbeef")["state"] \
        == "missing"


def test_compare_case_reports_a_case_that_was_never_frozen(tmp_path):
    svg = tmp_path / "3005.svg"
    svg.write_text("<svg/>")
    assert goldens_status.compare_case(svg, None)["state"] == "unfrozen"


def test_summarize_counts_the_states():
    got = goldens_status.summarize([
        {"state": "match"}, {"state": "match"}, {"state": "moved"}])
    assert got == {"total": 3, "match": 2, "moved": 1, "missing": 0, "unfrozen": 0}


def test_summarize_of_nothing_is_all_zero():
    assert goldens_status.summarize([])["total"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_goldens_status.py -k "cases_for or compare_case or summarize" -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Write the implementation**

Add to the imports at the **top** of `brick_icons/lab/goldens_status.py`:

```python
from .. import goldens
from . import corpus
```

then append to the same file:

```python
def cases_for(root: Path | str, part: str) -> list[dict]:
    """Every golden case this part is in, with the argv that reproduces it."""
    return [{"case": f"{c['name']}__{part}", "combo": c["name"],
             "argv": [part, *c["args"]]}
            for c in corpus.combos_for(root, part)]


def compare_case(svg_path: Path | str, frozen_digest: str | None) -> dict:
    """One case: does a fresh render hash to what was frozen?

    The frozen digest is sha256 of the SVG text, so this is an exact string
    comparison with no tolerance to get wrong.
    """
    path = Path(svg_path)
    if not path.exists():
        return {"state": "missing", "frozen": frozen_digest, "fresh": None}
    fresh = goldens.sha256(path.read_text())
    if frozen_digest is None:
        return {"state": "unfrozen", "frozen": None, "fresh": fresh}
    state = "match" if fresh == frozen_digest else "moved"
    return {"state": state, "frozen": frozen_digest, "fresh": fresh}


def summarize(results: list[dict]) -> dict:
    counts = {"total": len(results), "match": 0, "moved": 0,
              "missing": 0, "unfrozen": 0}
    for result in results:
        counts[result["state"]] += 1
    return counts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_goldens_status.py -v`
Expected: PASS, 13 tests

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/goldens_status.py tests/test_lab_goldens_status.py
git commit -m "compare a part's fresh render against its frozen goldens"
```

---

## Task 3: The golden check route

**Files:**
- Modify: `brick_icons/lab/app.py`
- Test: `tests/test_lab_app.py`

Checking a part means rendering it once per combo, so this is a job, not a GET.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lab_app.py`:

```python
def test_combos_route_lists_them(client):
    body = client.get("/api/combos").json()
    assert any(c["name"] == "outline-flat3" for c in body["combos"])


def test_goldens_check_starts_a_job_over_the_parts_cases(client, ldraw_dir):
    body = client.post("/api/goldens/check", json={"part": "3005"}).json()
    done = _finish(client, body["job"], timeout=600)
    assert done["state"] == "done"
    states = {r["state"] for r in done["results"]}
    assert states <= {"match", "moved", "missing", "unfrozen"}


def test_goldens_check_names_each_case(client, ldraw_dir):
    body = client.post("/api/goldens/check", json={"part": "3005"}).json()
    done = _finish(client, body["job"], timeout=600)
    assert all(r["case"].endswith("__3005") for r in done["results"])


def test_goldens_check_on_a_part_with_no_cases_is_an_empty_job(client):
    body = client.post("/api/goldens/check", json={"part": "not-a-part"}).json()
    done = _finish(client, body["job"])
    assert done["total"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_app.py -k "combos or goldens_check" -v`
Expected: FAIL with 404

- [ ] **Step 3: Write the implementation**

In `brick_icons/lab/app.py`, add above `create_app`:

```python
class GoldenCheckRequest(BaseModel):
    part: str
```

and add the routes:

```python
    @app.get("/api/combos")
    def get_combos():
        return {"combos": corpus.combos(root=root)}

    @app.post("/api/goldens/check")
    def post_goldens_check(req: GoldenCheckRequest):
        frozen = goldens_status.frozen(root / goldens_status.DEFAULT_PATH)
        digests = frozen.get(req.part, {})
        cases = goldens_status.cases_for(root, req.part)

        def work(case, emit):
            result = runner.render(case["argv"], root=app.state.cache_root)
            svg = (app.state.cache_root / result["key"] / f"{req.part}.svg")
            compared = goldens_status.compare_case(svg, digests.get(case["combo"]))
            emit(f"{case['case']}: {compared['state']}")
            return {"case": case["case"], "combo": case["combo"], **compared}

        return {"job": app.state.jobs.start("goldens", cases, work),
                "count": len(cases)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_app.py -v`
Expected: PASS. The check tests render `3005` once per combo, so allow a
minute. If a case comes back `missing`, the combo's args produce a filename
other than `<part>.svg` — read `cli.process_one` for what that combo writes and
fix the path, not the test.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/app.py tests/test_lab_app.py
git commit -m "check a part's goldens as a job"
```

---

## Task 4: The golden readout

**Files:**
- Create: `lab/src/chrome/GoldenStatus.tsx`
- Modify: `lab/src/api/client.ts`
- Test: `lab/src/chrome/GoldenStatus.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `lab/src/chrome/GoldenStatus.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GoldenStatus, summarizeGoldens } from '@lab/chrome/GoldenStatus';
import type { LabClient } from '@lab/api/client';

describe('summarizeGoldens', () => {
  it('says goldens match when they all do', () => {
    expect(summarizeGoldens([{ state: 'match' }, { state: 'match' }]))
      .toBe('goldens: match (2)');
  });

  it('leads with what moved, which is the thing worth acting on', () => {
    expect(summarizeGoldens([{ state: 'match' }, { state: 'moved' }]))
      .toBe('goldens: 1 moved of 2');
  });

  it('counts a case that was never frozen separately from a failure', () => {
    expect(summarizeGoldens([{ state: 'unfrozen' }])).toBe('goldens: 1 unfrozen');
  });

  it('reports a missing render as missing, not as a move', () => {
    expect(summarizeGoldens([{ state: 'missing' }])).toBe('goldens: 1 missing');
  });

  it('says a part has no cases rather than implying it passed', () => {
    expect(summarizeGoldens([])).toBe('goldens: no cases');
  });
});

describe('GoldenStatus', () => {
  const client = (results: { state: string }[]) => ({
    checkGoldens: vi.fn(async () => ({ job: 'j1', count: results.length })),
    job: vi.fn(async () => ({
      id: 'j1', kind: 'goldens', state: 'done' as const, total: results.length,
      done: results.length, failed: 0, events: [], results,
    })),
  } as unknown as LabClient);

  it('does not check until asked, because a check re-renders', () => {
    const api = client([]);
    render(<GoldenStatus client={api} part="3941" />);
    expect(api.checkGoldens).not.toHaveBeenCalled();
  });

  it('reports the result after a check', async () => {
    render(<GoldenStatus client={client([{ state: 'match' }])} part="3941" />);
    fireEvent.click(screen.getByText(/check goldens/i));
    await waitFor(() => expect(screen.getByText(/goldens: match/)).toBeTruthy());
  });

  it('offers nothing to check without a part', () => {
    render(<GoldenStatus client={client([])} part="" />);
    expect(screen.queryByText(/check goldens/i)).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/chrome/GoldenStatus.test.tsx`
Expected: FAIL — cannot resolve `@lab/chrome/GoldenStatus`

- [ ] **Step 3: Write the implementation**

Add to `lab/src/api/client.ts`, inside the returned object:

```ts
    async checkGoldens(part: string) {
      return json<{ job: string; count: number }>(
        fetchImpl, at('/api/goldens/check'), post('/api/goldens/check', { part }));
    },

    async combos() {
      return (await json<{ combos: { name: string; args: string[]; parts: string[] }[] }>(
        fetchImpl, at('/api/combos'))).combos;
    },
```

Create `lab/src/chrome/GoldenStatus.tsx`:

```tsx
import { useState } from 'react';
import type { LabClient } from '@lab/api/client';

export interface CaseResult {
  state: string;
}

export function summarizeGoldens(results: CaseResult[]): string {
  if (results.length === 0) return 'goldens: no cases';
  const count = (state: string) => results.filter((r) => r.state === state).length;
  const moved = count('moved');
  if (moved > 0) return `goldens: ${moved} moved of ${results.length}`;
  const missing = count('missing');
  if (missing > 0) return `goldens: ${missing} missing`;
  const unfrozen = count('unfrozen');
  if (unfrozen > 0) return `goldens: ${unfrozen} unfrozen`;
  return `goldens: match (${results.length})`;
}

/** A check re-renders the part once per combo, so it is a button, not a
 *  subscription: nothing fires it on a config change. */
export function GoldenStatus({ client, part }: { client: LabClient; part: string }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);

  if (!part.trim()) return null;

  async function check() {
    setBusy(true);
    setText('checking…');
    try {
      const started = await client.checkGoldens(part);
      let state = await client.job(started.job);
      while (state.state === 'running') {
        await new Promise((r) => setTimeout(r, 250));
        state = await client.job(started.job);
      }
      setText(summarizeGoldens(state.results as unknown as CaseResult[]));
    } catch (e) {
      setText(`goldens: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="golden-status">
      {text ? <span>{text}</span> : null}
      <button type="button" disabled={busy} onClick={() => void check()}>
        check goldens
      </button>
    </span>
  );
}
```

- [ ] **Step 4: Wire it into the Part Inspector's chrome**

In `lab/src/instruments/partInspector.tsx`, import `GoldenStatus` and add a
third `status` contribution:

```tsx
      {
        id: 'golden-status',
        region: 'status',
        render: (ctx) => (
          <GoldenStatus
            client={client}
            part={String((ctx.config as Record<string, unknown>).part ?? '')}
          />
        ),
      },
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd lab && npx vitest run && npm run typecheck`
Expected: PASS throughout

- [ ] **Step 6: Commit**

```bash
git add lab/src && git commit -m "report a part's golden status in the trial"
```

---

## Task 5: The contact sheet's job

**Files:**
- Create: `lab/src/instruments/sheetJob.ts`
- Test: `lab/src/instruments/sheetJob.test.ts`

- [ ] **Step 1: Write the failing test**

Create `lab/src/instruments/sheetJob.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { runSheet } from '@lab/instruments/sheetJob';
import type { LabClient, RenderResult } from '@lab/api/client';

const result = (over: Partial<RenderResult> = {}): RenderResult => ({
  ok: true, cached: false, argv: ['3005'], command: '', key: 'k1',
  artifacts: [{ name: '3005.svg', bytes: 1 }], seconds: 1, error: null, ...over,
});

function fakeClient(results: RenderResult[], state = 'done') {
  return {
    startBatch: vi.fn(async () => ({ job: 'j1', count: results.length })),
    job: vi.fn(async () => ({
      id: 'j1', kind: 'batch', state, total: results.length,
      done: results.length, failed: 0, events: [], results,
    })),
  } as unknown as LabClient;
}

async function collect<T>(iter: AsyncIterable<T>): Promise<T[]> {
  const out: T[] = [];
  for await (const v of iter) out.push(v);
  return out;
}

describe('runSheet', () => {
  it('reports the total before any cell', async () => {
    const events = await collect(runSheet({
      client: fakeClient([result()]), parts: ['3005'], config: {},
      signal: new AbortController().signal, pollMs: 0,
    }));
    expect(events[0]).toEqual({ kind: 'total', total: 1 });
  });

  it('yields a cell per part, in the order asked', async () => {
    const client = fakeClient([result({ argv: ['3005'] }),
                               result({ argv: ['3024'], key: 'k2' })]);
    const events = await collect(runSheet({
      client, parts: ['3005', '3024'], config: {},
      signal: new AbortController().signal, pollMs: 0,
    }));
    const cells = events.filter((e) => e.kind === 'item');
    expect(cells.map((e) => (e as { item: { part: string } }).item.part))
      .toEqual(['3005', '3024']);
  });

  it('renders nothing for an empty list', async () => {
    const client = fakeClient([]);
    const events = await collect(runSheet({
      client, parts: [], config: {}, signal: new AbortController().signal, pollMs: 0,
    }));
    expect(client.startBatch).not.toHaveBeenCalled();
    expect(events).toEqual([{ kind: 'total', total: 0 }]);
  });

  it('carries a failed part through as a cell with its error', async () => {
    const client = fakeClient([result({ ok: false, error: 'boom' })]);
    const events = await collect(runSheet({
      client, parts: ['3005'], config: {},
      signal: new AbortController().signal, pollMs: 0,
    }));
    const cell = events.find((e) => e.kind === 'item') as
      { item: { error: string | null } };
    expect(cell.item.error).toBe('boom');
  });

  it('stops when the signal aborts', async () => {
    const controller = new AbortController();
    const client = {
      startBatch: vi.fn(async () => ({ job: 'j1', count: 1 })),
      job: vi.fn(async () => {
        controller.abort();
        return { id: 'j1', kind: 'batch', state: 'running', total: 1, done: 0,
                 failed: 0, events: [], results: [] };
      }),
    } as unknown as LabClient;
    const events = await collect(runSheet({
      client, parts: ['3005'], config: {}, signal: controller.signal, pollMs: 0,
    }));
    expect(events.filter((e) => e.kind === 'item')).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/instruments/sheetJob.test.ts`
Expected: FAIL — cannot resolve `@lab/instruments/sheetJob`

- [ ] **Step 3: Write the implementation**

Add to `lab/src/api/client.ts`, inside the returned object:

```ts
    async startBatch(parts: string[], config: Record<string, unknown>, force = false) {
      return json<{ job: string; count: number }>(
        fetchImpl, at('/api/batch'), post('/api/batch', { parts, config, force }));
    },
```

Create `lab/src/instruments/sheetJob.ts`:

```ts
import type { LabClient, RenderResult } from '@lab/api/client';

export interface SheetCell {
  part: string;
  key: string;
  svg: string | null;
  error: string | null;
  seconds: number;
}

export type SheetEvent =
  | { kind: 'total'; total: number }
  | { kind: 'item'; item: SheetCell };

export interface RunSheetArgs {
  client: LabClient;
  parts: string[];
  config: Record<string, unknown>;
  signal: AbortSignal;
  pollMs?: number;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function cellFrom(part: string, result: RenderResult): SheetCell {
  const svg = result.artifacts.find((a) => a.name.endsWith('.svg')
    && !a.name.includes('.unwrap.') && !a.name.includes('.decal.'));
  return {
    part,
    key: result.key,
    svg: svg ? svg.name : null,
    error: result.ok ? null : (result.error ?? 'render failed'),
    seconds: result.seconds,
  };
}

/** One batch job for the whole list. The server renders in order, so a result
 *  at index i belongs to `parts[i]`. */
export async function* runSheet(
  { client, parts, config, signal, pollMs = 400 }: RunSheetArgs,
): AsyncIterable<SheetEvent> {
  yield { kind: 'total', total: parts.length };
  if (parts.length === 0) return;

  const started = await client.startBatch(parts, config);
  let seen = 0;
  let state = await client.job(started.job);

  for (;;) {
    if (signal.aborted) return;
    while (seen < state.results.length) {
      const part = parts[seen];
      const result = state.results[seen];
      if (part && result) yield { kind: 'item', item: cellFrom(part, result) };
      seen += 1;
    }
    if (state.state !== 'running') return;
    await sleep(pollMs);
    if (signal.aborted) return;
    state = await client.job(started.job);
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/instruments/sheetJob.test.ts`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/instruments/sheetJob.ts lab/src/instruments/sheetJob.test.ts lab/src/api/client.ts
git commit -m "run a corpus list as one contact-sheet job"
```

---

## Task 6: The contact sheet instrument

**Files:**
- Create: `lab/src/instruments/contactSheet.tsx`, `lab/src/instruments/contactSheet.css`
- Test: `lab/src/instruments/contactSheet.test.ts`

- [ ] **Step 1: Write the failing test**

Create `lab/src/instruments/contactSheet.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { createContactSheet } from '@lab/instruments/contactSheet';
import type { LabClient } from '@lab/api/client';
import type { SchemaField } from '@lab/api/types';

const FIELDS: SchemaField[] = [
  { key: 'engine', flag: '--engine', type: 'str', choices: ['naive', 'occt'],
    help: '', nargs: null, default: null },
  { key: 'shading', flag: '--shading', type: 'str',
    choices: ['normal', 'cel', 'outline'], help: '', nargs: null, default: null },
];

const LISTS = [
  { name: 'specimens', source: 'specimens.txt', parts: ['3001', '3941'] },
  { name: 'parts', source: 'parts.txt', parts: ['3001'] },
];

const client = {} as LabClient;

describe('createContactSheet', () => {
  it('is named for the workspace', () => {
    expect(createContactSheet(FIELDS, LISTS, client).name).toBe('contact-sheet');
  });

  it('opens on the first list', () => {
    expect(createContactSheet(FIELDS, LISTS, client).defaultConfig().list)
      .toBe('specimens');
  });

  it('takes its render flags from the CLI schema', () => {
    const config = createContactSheet(FIELDS, LISTS, client).defaultConfig();
    expect(config.engine).toBe('naive');
  });

  it('starts with no cells', () => {
    const instrument = createContactSheet(FIELDS, LISTS, client);
    expect(instrument.initialState(instrument.defaultConfig()).cells).toEqual([]);
  });

  it('re-runs when the list changes', () => {
    const instrument = createContactSheet(FIELDS, LISTS, client);
    const base = instrument.defaultConfig();
    const state = instrument.initialState(base);
    expect(instrument.job!.key!(base, state))
      .not.toEqual(instrument.job!.key!({ ...base, list: 'parts' }, state));
  });

  it('re-runs when a render flag changes', () => {
    const instrument = createContactSheet(FIELDS, LISTS, client);
    const base = instrument.defaultConfig();
    const state = instrument.initialState(base);
    expect(instrument.job!.key!(base, state))
      .not.toEqual(instrument.job!.key!({ ...base, engine: 'occt' }, state));
  });

  it('appends each cell as it arrives, keeping order', () => {
    const instrument = createContactSheet(FIELDS, LISTS, client);
    let state = instrument.initialState(instrument.defaultConfig());
    state = instrument.job!.onItem(
      { part: '3001', key: 'k1', svg: '3001.svg', error: null, seconds: 1 }, state);
    state = instrument.job!.onItem(
      { part: '3941', key: 'k2', svg: '3941.svg', error: null, seconds: 2 }, state);
    expect(state.cells.map((c: { part: string }) => c.part)).toEqual(['3001', '3941']);
  });

  it('does not start on its own, since a list is many renders', () => {
    expect(createContactSheet(FIELDS, LISTS, client).job!.auto).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/instruments/contactSheet.test.ts`
Expected: FAIL — cannot resolve `@lab/instruments/contactSheet`

- [ ] **Step 3: Write the implementation**

Create `lab/src/instruments/contactSheet.css`:

```css
.sheet { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
         gap: 0.5rem; padding: 0.5rem; overflow: auto; height: 100%; }
.sheet-cell { display: flex; flex-direction: column; align-items: center;
              gap: 0.25rem; cursor: pointer; }
.sheet-cell img { width: 100%; background: #fff; }
.sheet-cell figcaption { font-size: 0.7rem; }
.sheet-cell-failed { color: var(--lk-danger, #d05098); }
```

Create `lab/src/instruments/contactSheet.tsx`:

```tsx
import { defineInstrument, f, useLabContext } from '@weasel-js/labkit';
import type { LabClient, SchemaField } from '@lab/api/client';
import { buildSchema, defaultsFor, renderConfig } from '@lab/config/nodes';
import { setPendingPart } from '@lab/config/pending';
import { runSheet, type SheetCell } from '@lab/instruments/sheetJob';
import '@lab/instruments/contactSheet.css';

export interface CorpusList {
  name: string;
  source: string;
  parts: string[];
}

export interface SheetState {
  cells: SheetCell[];
}

function Sheet({ ctx, client, lists }:
               { ctx: any; client: LabClient; lists: CorpusList[] }) {
  const { addTrial } = useLabContext();
  const cells = (ctx.state as SheetState).cells;
  const list = lists.find((l) => l.name === ctx.config.list);

  if (cells.length === 0) {
    return (
      <p>
        {list ? `${list.parts.length} parts in ${list.name}` : 'no list'} —
        {' '}press Run to render the sheet.
      </p>
    );
  }

  return (
    <div className="sheet">
      {cells.map((cell) => (
        <figure
          key={cell.part}
          className={`sheet-cell${cell.error ? ' sheet-cell-failed' : ''}`}
          role="button"
          tabIndex={0}
          onClick={() => { setPendingPart(cell.part); addTrial('part-inspector'); }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { setPendingPart(cell.part); addTrial('part-inspector'); }
          }}
        >
          {cell.svg
            ? <img src={client.artifactUrl(cell.key, cell.svg)} alt={cell.part} />
            : <span>{cell.error ?? 'no output'}</span>}
          <figcaption>{cell.part}</figcaption>
        </figure>
      ))}
    </div>
  );
}

export function createContactSheet(fields: SchemaField[], lists: CorpusList[],
                                   client: LabClient) {
  const nodes = buildSchema(fields);
  const defaults = defaultsFor(fields);
  const names = lists.map((l) => l.name);

  return defineInstrument<SheetState, Record<string, unknown>, SheetCell>({
    name: 'contact-sheet',

    config: f.schema({
      list: f.enum(names[0] ?? 'specimens', names.length > 0 ? names : ['specimens']),
      ...nodes,
    } as never) as never,

    defaultConfig: () => ({ ...defaults, list: names[0] ?? 'specimens' }),

    initialState: () => ({ cells: [] }),

    job: {
      // A list is dozens of renders. Nothing starts it but the Run control.
      auto: false,
      key: (config) => [config.list, JSON.stringify(renderConfig(config))],
      run: ({ config, signal }) => runSheet({
        client,
        parts: lists.find((l) => l.name === config.list)?.parts ?? [],
        config: renderConfig(config),
        signal,
      }),
      onItem: (item, state) => ({ cells: [...state.cells, item] }),
    },

    onConfigChange: () => ({ cells: [] }),

    render: (ctx) => <Sheet ctx={ctx} client={client} lists={lists} />,
  });
}
```

`onConfigChange` clears the cells: a sheet half from the old parameters and
half from the new is worse than an empty one, because nothing on screen says
which cell is which.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/instruments/contactSheet.test.ts`
Expected: PASS, 8 tests. `auto: false` means the job needs a start control —
labkit renders one into the trial chrome for a declared job; confirm in
Task 8's walkthrough that it is there, and if it is not, add a `toolbar`
contribution calling `ctx.job.start()`.

- [ ] **Step 5: Commit**

```bash
git add lab/src/instruments/contactSheet.tsx lab/src/instruments/contactSheet.css lab/src/instruments/contactSheet.test.ts
git commit -m "add the contact sheet instrument"
```

---

## Task 7: Register the second instrument

**Files:**
- Modify: `lab/src/main.tsx`, `lab/src/App.tsx`

- [ ] **Step 1: Fetch the lists at boot and build both instruments**

In `lab/src/main.tsx`, replace the bootstrap so it fetches both:

```tsx
Promise.all([client.schema(), client.lists()]).then(([fields, lists]) => {
  root.render(
    <App
      instruments={[
        createPartInspector(fields, client),
        createContactSheet(fields, lists, client),
      ]}
      client={client}
    />,
  );
}).catch((error: Error) => {
  root.render(
    <p>
      cannot reach the lab server — start it with
      <code> python -m brick_icons.lab</code> ({error.message})
    </p>,
  );
});
```

Add the import for `createContactSheet`, and add the `lists` method to
`lab/src/api/client.ts`:

```ts
    async lists() {
      return (await json<{ lists: { name: string; source: string; parts: string[] }[] }>(
        fetchImpl, at('/api/lists'))).lists;
    },
```

- [ ] **Step 2: Take a list of instruments in App**

In `lab/src/App.tsx`, change the prop from `instrument: Instrument` to
`instruments: Instrument[]` and pass it straight to `<Lab instruments={...}>`.
`defaultInstrument` stays `"part-inspector"` — the title-bar search adds that
one, and the contact sheet is added from labkit's own new-trial control.

- [ ] **Step 3: Typecheck, test and build**

Run: `cd lab && npm run typecheck && npx vitest run && npm run build`
Expected: PASS throughout

- [ ] **Step 4: Commit**

```bash
git add lab/src && git commit -m "register the contact sheet beside the Part Inspector"
```

---

## Task 8: See it work

**Files:** none — verification.

- [ ] **Step 1: Start both servers**

Run `.venv/bin/python -m brick_icons.lab &` and `cd lab && npm run dev`.

- [ ] **Step 2: Render a sheet**

Add a contact-sheet trial, pick `specimens`, press Run. Confirm:

1. cells appear one at a time rather than all at the end — the job yields per
   part, and a sheet that only appears when finished means the polling loop is
   waiting for `state !== 'running'` before emitting;
2. the server's terminal prints one progress line per part, with its position;
3. clicking a cell opens a Part Inspector trial on that part;
4. changing `--engine` clears the sheet and Run re-renders it.

- [ ] **Step 3: Check a part's goldens**

In a Part Inspector trial on `3941`, press "check goldens". Confirm it reports
`match` for a part you have not changed. Then confirm it is honest about a
move: run

```sh
.venv/bin/python -m brick_icons.cli 3941 --format svg --shading outline \
    --shade-style flat3 --out /tmp/probe
```

and compare `shasum -a 256 /tmp/probe/3941.svg` against the `outline-flat3__3941`
line in `tests/goldens/hashes.txt`. The lab's answer and that comparison must
agree. If they disagree, the lab is rendering with different arguments than the
combo declares — fix `cases_for`, not the manifest.

- [ ] **Step 4: Stop the servers**

Run: `kill %1`; Ctrl-C the Vite server.

---

## Task 9: Retire the shell script

**Files:**
- Modify: `scripts/render-contact-sheet.sh`, `README.md`

- [ ] **Step 1: Point the script at the lab**

The script still works and needs no `npm`, so it stays. Add to the top of
`scripts/render-contact-sheet.sh`, below the existing comment block:

```sh
# The lab's contact-sheet instrument does this interactively, with clickable
# cells: python -m brick_icons.lab. This script remains the headless path.
```

- [ ] **Step 2: Say the same in the README**

In the lab section of `README.md`, add:

```markdown
The contact-sheet instrument renders a whole corpus list and opens any cell as
a trial; `scripts/render-contact-sheet.sh` remains the headless equivalent.
```

- [ ] **Step 3: Commit**

```bash
git add scripts/render-contact-sheet.sh README.md
git commit -m "point the contact-sheet script at its interactive equivalent"
```

---

## Self-review notes

**Spec coverage.** Batch as one job with per-part progress (Tasks 5, 6); the
whole-corpus grid with cells that open a trial (Task 6); golden status per part
(Tasks 1, 2, 3, 4); `render-contact-sheet.sh` superseded but kept as the
headless path (Task 9).

**One thing this plan changes about the spec.** The spec put golden status in
the status bar as a passive readout. A real check re-renders the part once per
combo it appears in, which is seconds to minutes — too expensive to fire on
every config change. So it is a button that reports when pressed. The passive
reading of `hashes.txt` from the server plan stays available for "does this
part have goldens at all".

**What Task 8 step 3 is really for.** It is the only check that the lab's
golden answer means what `pytest` means. Everything else in this plan can be
green while `cases_for` builds argv the manifest never declared, and the lab
would then report `match` against a case that does not exist.
