# Defects on labkit annotations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the lab's hand-rolled defect mark layer with `@weasel-js/labkit`'s annotations capability, keeping the Python server as the record of truth.

**Architecture:** The instrument declares an `annotations` capability whose `targets` read a mutable registry that the `Panes` component keeps current — the capability is defined at module scope in `createPartInspector`, while refs and the camera only exist per-render, and `targets` is handed only `(state, config)`. A pure projection module maps `Defect[]` into labkit marks on load and a drawn mark back into a `Defect` on file.

**Tech Stack:** React 19, TypeScript, vitest + @testing-library/react, `@weasel-js/labkit@1.4.0-pre.0`, a Python lab server behind `LabClient`.

Read `docs/superpowers/specs/2026-09-03-defects-on-annotations-design.md` first. All paths below are relative to `/Users/mike/src/brick-icons`.

Run tests from `lab/`: `cd /Users/mike/src/brick-icons/lab && npx vitest run <path>`.

---

## Two hazards found while planning — read before starting

**Existing marks may move.** Today `markFromDrag` divides by the *measured pane body*, so a stored fraction is a fraction of whatever box the layout gave the pane. labkit's `content` is the intrinsic render box (`render_px` square). Where a pane body is not square, reprojecting an existing defect into render space shifts it. Task 4 measures this before anything depends on it.

**A mark drawn on the diff pane can never be seen.** `paneSpec` gives the diff pane `marks: true`, but `FileDefectDialog` only offers engine-kind sources as checkboxes, and the layer filters with `d.engines.includes(source.id)` — `'diff'` is never in `engines`. So today you can draw on the diff pane and the mark vanishes on reload. Task 6 decides this deliberately rather than porting the bug.

**`noUncheckedIndexedAccess` is on.** `const [x] = someArray` types `x` as `T | undefined`, so every property access after it fails `TS18048` even though the test passes. Write `const x = someArray[0]!` — the convention the existing tests already use (`src/panes/threeModel.test.ts`, `src/api/client.test.ts`).

**There are no `jest-dom` matchers here.** `lab/src/test-setup.ts` imports none, and no existing test uses them. `toHaveClass`, `toBeInTheDocument` and friends throw `Invalid Chai property` — which reads as a broken test rather than a failing one, so a test written with them can never fail honestly. Assert on `classList.contains(...)`, `textContent`, and `querySelector(...)` instead. Only vitest's own matchers are available.

---

### Task 1: Let a caller reach a pane's body element

labkit's `AnnotationTarget.ref` needs the element the overlay measures and takes input from. `SourcePane` already holds `.pane-body` in a private ref; expose it without taking the ref away from the ResizeObserver.

**Files:**
- Modify: `lab/src/panes/SourcePane.tsx`
- Test: `lab/src/panes/SourcePane.test.tsx`

- [ ] **Step 1: Write the failing test**

Append to `lab/src/panes/SourcePane.test.tsx`:

```tsx
it('hands the pane body to a caller-supplied ref', () => {
  const bodyRef = createRef<HTMLDivElement>();
  render(
    <SourcePane
      source={{ id: 'naive', label: 'naive', kind: 'engine' }}
      state={{ kind: 'idle' }}
      camera={HOME}
      onCamera={() => {}}
      bodyRef={bodyRef}
    />,
  );
  expect(bodyRef.current).not.toBeNull();
  expect(bodyRef.current).toHaveClass('pane-body');
});
```

Add to that file's imports: `import { createRef } from 'react';` and `import { HOME } from '@lab/panes/camera';` (skip either if already present).

- [ ] **Step 2: Run it and watch it fail**

Run: `cd /Users/mike/src/brick-icons/lab && npx vitest run src/panes/SourcePane.test.tsx -t 'caller-supplied ref'`
Expected: FAIL — `bodyRef.current` is `null`, because `SourcePaneProps` has no `bodyRef` and the prop is ignored.

- [ ] **Step 3: Add the prop**

In `lab/src/panes/SourcePane.tsx`, add to `SourcePaneProps`:

```tsx
  /** The pane body, for a caller that must measure it or mount over it. */
  bodyRef?: RefObject<HTMLDivElement | null>;
```

Add `RefObject` to the existing `react` type import. Add `bodyRef` to the destructured parameter list, and replace `ref={body}` on the `.pane-body` div with a callback ref that feeds both:

```tsx
        ref={(el) => {
          body.current = el;
          if (bodyRef) bodyRef.current = el;
        }}
```

- [ ] **Step 4: Run it and watch it pass**

Run: `cd /Users/mike/src/brick-icons/lab && npx vitest run src/panes/SourcePane.test.tsx`
Expected: PASS, every test in the file — the ResizeObserver effect still reads `body.current`.

- [ ] **Step 5: Commit**

```bash
cd /Users/mike/src/brick-icons
git add lab/src/panes/SourcePane.tsx lab/src/panes/SourcePane.test.tsx
git commit -m "expose a pane's body element to its caller"
```

---

### Task 2: The target registry

`annotations.targets` is called with `(state, config)` and nothing else, but it must return per-pane refs and the live camera. A module-scoped mutable registry, written by `Panes` on every render and read by `targets`, is the bridge. labkit re-invokes `targets` rather than caching it, so a mutable read is live.

**Files:**
- Create: `lab/src/defects/targets.ts`
- Test: `lab/src/defects/targets.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { createRef } from 'react';
import { describe, expect, it } from 'vitest';
import { createTargetRegistry } from '@lab/defects/targets';
import { HOME } from '@lab/panes/camera';

describe('createTargetRegistry', () => {
  it('has no targets before a render reports any', () => {
    expect(createTargetRegistry().targets()).toEqual([]);
  });

  it('returns what the last publish gave it', () => {
    const reg = createTargetRegistry();
    const ref = createRef<HTMLDivElement>();
    reg.publish({
      camera: HOME,
      content: { w: 900, h: 900 },
      panes: [{ id: 'naive', ref }],
    });
    const [t] = reg.targets();
    expect(t.id).toBe('pane:naive');
    expect(t.ref).toBe(ref);
    expect(t.content).toEqual({ w: 900, h: 900 });
    expect(t.view).toBe(HOME);
    expect(t.positionDependsOn).toEqual(['angle', 'shading', 'shade_style']);
  });

  it('reads the camera live, so a pan after publish is seen', () => {
    const reg = createTargetRegistry();
    reg.publish({ camera: HOME, content: { w: 900, h: 900 }, panes: [] });
    const moved = { zoom: 2, pan: { x: 10, y: 20 } };
    reg.publish({ camera: moved, content: { w: 900, h: 900 }, panes: [{ id: 'occt', ref: createRef() }] });
    expect(reg.targets()[0]?.view).toBe(moved);
  });

  it('drops panes that are no longer shown', () => {
    const reg = createTargetRegistry();
    reg.publish({ camera: HOME, content: { w: 900, h: 900 }, panes: [{ id: 'naive', ref: createRef() }] });
    reg.publish({ camera: HOME, content: { w: 900, h: 900 }, panes: [] });
    expect(reg.targets()).toEqual([]);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd /Users/mike/src/brick-icons/lab && npx vitest run src/defects/targets.test.ts`
Expected: FAIL — cannot resolve `@lab/defects/targets`.

- [ ] **Step 3: Write the registry**

Create `lab/src/defects/targets.ts`:

```ts
import type { RefObject } from 'react';
import type { AnnotationTarget } from '@weasel-js/labkit';
import type { Camera } from '@lab/panes/camera';
import type { SourceId } from '@lab/panes/sources';
import type { CaptureSource } from '@weasel-js/labkit';

/** The config keys whose change means a stored fraction no longer points at
 *  the same picture. labkit snapshots these onto every mark and answers
 *  `isStale` from them, which is why the lab no longer computes staleness. */
export const POSITION_DEPENDS_ON = ['angle', 'shading', 'shade_style'] as const;

export interface PaneEntry {
  id: SourceId;
  ref: RefObject<HTMLElement | null>;
  base?: () => CaptureSource;
}

export interface TargetSnapshot {
  camera: Camera;
  content: { w: number; h: number };
  panes: readonly PaneEntry[];
}

export interface TargetRegistry {
  publish: (snapshot: TargetSnapshot) => void;
  targets: () => readonly AnnotationTarget[];
}

/** `annotations.targets` is handed only `(state, config)`, so it cannot reach
 *  the pane refs or the trial's camera. The instrument holds one of these and
 *  `Panes` republishes on every render. */
export function createTargetRegistry(): TargetRegistry {
  let current: TargetSnapshot | null = null;
  return {
    publish: (snapshot) => { current = snapshot; },
    targets: () => {
      if (!current) return [];
      const { camera, content, panes } = current;
      return panes.map((p) => ({
        id: `pane:${p.id}`,
        ref: p.ref,
        content,
        view: camera,
        positionDependsOn: POSITION_DEPENDS_ON,
        ...(p.base ? { base: p.base } : {}),
      }));
    },
  };
}
```

- [ ] **Step 4: Run it and watch it pass**

Run: `cd /Users/mike/src/brick-icons/lab && npx vitest run src/defects/targets.test.ts`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
cd /Users/mike/src/brick-icons
git add lab/src/defects/targets.ts lab/src/defects/targets.test.ts
git commit -m "bridge pane refs and the camera to the annotations capability"
```

---

### Task 3: Carry geometry on a Defect

`Defect.mark` stays the bounds rect. `kind` and `points` are added alongside so a mark can be a line, and an existing record with neither reads as a rect.

**Files:**
- Modify: `lab/src/defects/useDefects.ts`
- Test: `lab/src/defects/useDefects.test.ts`

- [ ] **Step 1: Write the failing test**

Append to `lab/src/defects/useDefects.test.ts`:

```ts
it('carries a mark kind and its points', () => {
  const d = buildDefect({
    part: '3001', engines: ['naive'], title: 'missing edge', notes: '',
    mark: { x: 0.1, y: 0.1, w: 0.3, h: 0.2 },
    kind: 'line',
    points: [{ x: 0.1, y: 0.1 }, { x: 0.4, y: 0.3 }],
    config: {}, existing: [], today: '2026-09-03',
  });
  expect(d.kind).toBe('line');
  expect(d.points).toHaveLength(2);
});

it('leaves kind and points off a plain rectangle', () => {
  const d = buildDefect({
    part: '3001', engines: ['naive'], title: 'blob', notes: '',
    mark: { x: 0, y: 0, w: 0.2, h: 0.2 },
    config: {}, existing: [], today: '2026-09-03',
  });
  expect(d.kind).toBeUndefined();
  expect(d.points).toBeUndefined();
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd /Users/mike/src/brick-icons/lab && npx vitest run src/defects/useDefects.test.ts -t 'mark kind'`
Expected: FAIL — `d.kind` is `undefined` on the first test; `BuildDefectArgs` has no `kind`.

- [ ] **Step 3: Widen the type and the builder**

In `lab/src/defects/useDefects.ts`, add to `Defect`:

```ts
  /** Absent means a rectangle — every defect filed before marks could be
   *  anything else. */
  kind?: MarkKind;
  /** Vertices for a kind a bounding box cannot describe. Absent for a rect. */
  points?: { x: number; y: number }[];
```

Add above it:

```ts
export type MarkKind = 'rect' | 'line' | 'arrow' | 'ellipse' | 'stroke' | 'text';
```

Add the same two optional fields to `BuildDefectArgs`, and in `buildDefect`'s returned object spread them only when present:

```ts
    ...(args.kind && args.kind !== 'rect' ? { kind: args.kind } : {}),
    ...(args.points?.length ? { points: args.points } : {}),
```

- [ ] **Step 4: Run it and watch it pass**

Run: `cd /Users/mike/src/brick-icons/lab && npx vitest run src/defects/useDefects.test.ts`
Expected: PASS, every test in the file.

- [ ] **Step 5: Teach the server the two fields**

Defects are git-tracked TOML written in a fixed field order. In `brick_icons/lab/defects.py`, add both fields to `_ORDER`, after `mark` so geometry stays together:

```python
_ORDER = ("id", "part", "engines", "status", "title", "mark", "kind", "points",
          "seen", "filed", "notes")
```

Nothing else is needed to serialize them — `_dump_value` already handles a list of dicts, which is what `points` is. There is no field whitelist rejecting unknown keys; `add` only validates `status` and id uniqueness, so no validation change either.

Fix the module's `_HEADER` in the same edit. It currently tells the reader:

> `mark` is in fractions of the render box, so it survives a change of --render-px but not of --angle -- which is what `seen` records.

The first half is false — `markFromDrag` divides by the measured pane body, not the render box (Task 4 proves it). The second half is now labkit's job. Replace with:

```python
# Written by brick_icons.lab; hand edits are kept but reformatted on the next
# write. `mark` is in fractions of the pane box it was drawn on. `kind` and
# `points` are absent on a plain rectangle, which is every defect filed before
# 2026-09. `seen` is retained for records that carry it; the lab now asks
# labkit whether a mark is stale.
```

- [ ] **Step 6: Prove the round-trip**

Add to the server's defect tests (find them with `grep -rln "defects" --include="*.py" /Users/mike/src/brick-icons | grep test`):

```python
def test_a_line_defect_round_trips(tmp_path):
    path = tmp_path / "defects.toml"
    record = {"id": "3001-naive-edge", "part": "3001", "engines": ["naive"],
              "status": "open", "title": "missing edge",
              "mark": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4},
              "kind": "line",
              "points": [{"x": 0.1, "y": 0.2}, {"x": 0.4, "y": 0.6}],
              "seen": {}, "filed": "2026-09-03", "notes": ""}
    defects.add(path, record)
    [back] = defects.load(path)
    assert back["kind"] == "line"
    assert back["points"] == record["points"]


def test_a_defect_with_no_kind_still_loads(tmp_path):
    path = tmp_path / "defects.toml"
    defects.add(path, {"id": "3001-naive-blob", "part": "3001",
                       "engines": ["naive"], "status": "open", "title": "blob",
                       "mark": {"x": 0, "y": 0, "w": 0.2, "h": 0.2},
                       "seen": {}, "filed": "2026-09-03", "notes": ""})
    [back] = defects.load(path)
    assert "kind" not in back
```

Run: `cd /Users/mike/src/brick-icons && python -m pytest -k defect -q`
Expected: PASS, including the two new tests.

- [ ] **Step 6: Commit**

```bash
cd /Users/mike/src/brick-icons
git add lab/src/defects/useDefects.ts lab/src/defects/useDefects.test.ts
git add -u   # the server schema file
git commit -m "let a defect carry geometry richer than a rectangle"
```

---

### Task 4: Measure whether existing marks move

Before the projection is trusted, establish what `content` must be. Today's fractions are of the measured pane body; labkit's are of `content`.

**Files:**
- Create: `lab/src/defects/projection.contract.test.ts`

- [ ] **Step 1: Write the test that states the contract**

```ts
import { describe, expect, it } from 'vitest';
import { markToScreen } from '@lab/defects/geometry';
import { fracToWorld } from '@weasel-js/labkit';
import { HOME } from '@lab/panes/camera';

describe('a stored fraction means the same thing on both sides', () => {
  const mark = { x: 0.25, y: 0.5, w: 0.1, h: 0.2 };

  it('agrees when the pane body is square, as the render is', () => {
    const box = { width: 900, height: 900 };
    const screen = markToScreen(mark, box, HOME);
    const world = fracToWorld(mark, { w: 900, h: 900 });
    expect(world.x).toBeCloseTo(screen.left);
    expect(world.y).toBeCloseTo(screen.top);
    expect(world.width).toBeCloseTo(screen.width);
  });

  it('DISAGREES when the pane body is not square — this is the hazard', () => {
    const box = { width: 1200, height: 600 };
    const screen = markToScreen(mark, box, HOME);
    const world = fracToWorld(mark, { w: 900, h: 900 });
    expect(world.x).not.toBeCloseTo(screen.left);
  });
});
```

- [ ] **Step 2: Run it**

Run: `cd /Users/mike/src/brick-icons/lab && npx vitest run src/defects/projection.contract.test.ts`
Expected: PASS, both tests. The second passing is the point — it pins the hazard as a known, tested fact rather than a surprise in the browser.

- [ ] **Step 3: Choose `content` and record why**

Pass the **measured pane body** as `content`, not `render_px`. It reproduces today's stored meaning exactly, so no existing defect moves. Add this comment above the `content` value in Task 5's wiring:

```tsx
        // The measured body, not `render_px`: a stored fraction has always
        // been a fraction of the box the layout gave the pane, and passing the
        // render size instead silently moves every defect filed before today.
```

- [ ] **Step 4: Commit**

```bash
cd /Users/mike/src/brick-icons
git add lab/src/defects/projection.contract.test.ts
git commit -m "pin what a stored defect fraction is a fraction of"
```

---

### Task 5: The projection

Pure functions both ways. This is where the migration's correctness lives, and it is fully testable in jsdom.

**Files:**
- Create: `lab/src/defects/projection.ts`
- Test: `lab/src/defects/projection.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from 'vitest';
import { defectToMarks, markToDefectFields } from '@lab/defects/projection';
import type { Defect } from '@lab/defects/useDefects';

const defect = (over: Partial<Defect> = {}): Defect => ({
  id: '3001-naive-missing-edge', part: '3001', engines: ['naive'], status: 'open',
  title: 'missing edge', mark: { x: 0.1, y: 0.2, w: 0.3, h: 0.4 }, seen: {},
  filed: '2026-09-03', notes: '', ...over,
});

describe('defectToMarks', () => {
  it('puts one mark on each engine the defect names', () => {
    const marks = defectToMarks(defect({ engines: ['naive', 'occt'] }), ['pane:naive', 'pane:occt']);
    expect(marks.map((m) => m.target)).toEqual(['pane:naive', 'pane:occt']);
  });

  it('skips an engine whose pane is not shown', () => {
    const marks = defectToMarks(defect({ engines: ['naive', 'occt'] }), ['pane:naive']);
    expect(marks).toHaveLength(1);
  });

  it('carries the defect id so a mark can be traced back', () => {
    const m = defectToMarks(defect(), ['pane:naive'])[0]!;
    expect(m.meta).toEqual({ defectId: '3001-naive-missing-edge' });
  });

  it('reads a defect with no kind as a rectangle', () => {
    const m = defectToMarks(defect(), ['pane:naive'])[0]!;
    expect(m.kind).toBe('rect');
    expect(m.points).toBeUndefined();
  });

  it('carries a line through with its points', () => {
    const m = defectToMarks(
      defect({ kind: 'line', points: [{ x: 0.1, y: 0.2 }, { x: 0.4, y: 0.6 }] }),
      ['pane:naive'],
    )[0]!;
    expect(m.kind).toBe('line');
    expect(m.points).toHaveLength(2);
  });

  it('carries title and status so a mark paints by its meaning', () => {
    const m = defectToMarks(defect({ status: 'fixed' }), ['pane:naive'])[0]!;
    expect(m.title).toBe('missing edge');
    expect(m.status).toBe('fixed');
  });
});

describe('markToDefectFields', () => {
  it('turns a drawn mark back into the geometry a defect stores', () => {
    const fields = markToDefectFields({
      id: 'pane:naive/n1', target: 'pane:naive', kind: 'line',
      frac: { x: 0.1, y: 0.2, w: 0.3, h: 0.4 },
      points: [{ x: 0.1, y: 0.2 }, { x: 0.4, y: 0.6 }],
    });
    expect(fields.mark).toEqual({ x: 0.1, y: 0.2, w: 0.3, h: 0.4 });
    expect(fields.kind).toBe('line');
    expect(fields.points).toHaveLength(2);
  });

  it('leaves points off a rectangle', () => {
    const fields = markToDefectFields({
      id: 'pane:naive/n1', target: 'pane:naive', kind: 'rect',
      frac: { x: 0, y: 0, w: 0.2, h: 0.2 },
    });
    expect(fields.points).toBeUndefined();
  });

  it('names the engine the mark was drawn on', () => {
    const fields = markToDefectFields({
      id: 'pane:occt/n2', target: 'pane:occt', kind: 'rect',
      frac: { x: 0, y: 0, w: 0.2, h: 0.2 },
    });
    expect(fields.engine).toBe('occt');
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd /Users/mike/src/brick-icons/lab && npx vitest run src/defects/projection.test.ts`
Expected: FAIL — cannot resolve `@lab/defects/projection`.

- [ ] **Step 3: Write the projection**

Create `lab/src/defects/projection.ts`:

```ts
import type { AnnotationInit } from '@weasel-js/labkit';
import type { Defect, MarkKind } from '@lab/defects/useDefects';
import type { Mark } from '@lab/defects/geometry';
import type { SourceId } from '@lab/panes/sources';

/** What the lab writes into a mark's `meta`, and reads back to trace a mark
 *  to the record the server owns. */
export interface MarkMeta {
  defectId: string;
}

export const targetId = (source: string) => `pane:${source}`;
export const sourceOfTarget = (target: string) => target.replace(/^pane:/, '') as SourceId;

/** One mark per engine the defect names that currently has a pane. The server
 *  owns the record; these are its projection, remade on every reload. */
export function defectToMarks(
  defect: Defect,
  shown: readonly string[],
): AnnotationInit[] {
  const meta: MarkMeta = { defectId: defect.id };
  return defect.engines
    .map(targetId)
    .filter((t) => shown.includes(t))
    .map((target) => ({
      target,
      kind: (defect.kind ?? 'rect') as MarkKind,
      frac: defect.mark,
      ...(defect.points?.length ? { points: defect.points } : {}),
      title: defect.title,
      status: defect.status,
      meta,
    }));
}

/** The geometry half of a defect, taken off a mark the user just drew. The
 *  meaning half comes from the file dialog. */
export function markToDefectFields(mark: {
  id: string;
  target: string;
  kind: MarkKind;
  frac: Mark;
  points?: readonly { x: number; y: number }[];
}): {
  mark: Mark;
  engine: SourceId;
  kind?: MarkKind;
  points?: { x: number; y: number }[];
} {
  return {
    mark: mark.frac,
    engine: sourceOfTarget(mark.target),
    ...(mark.kind !== 'rect' ? { kind: mark.kind } : {}),
    ...(mark.points?.length ? { points: [...mark.points] } : {}),
  };
}
```

- [ ] **Step 4: Run it and watch it pass**

Run: `cd /Users/mike/src/brick-icons/lab && npx vitest run src/defects/projection.test.ts`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
cd /Users/mike/src/brick-icons
git add lab/src/defects/projection.ts lab/src/defects/projection.test.ts
git commit -m "project defects into marks and a drawn mark back"
```

---

### Task 6: Declare the capability and decide the diff pane

**Files:**
- Modify: `lab/src/instruments/partInspector.tsx`
- Modify: `lab/src/panes/paneSpec.ts`

- [ ] **Step 1: Stop offering marks on a pane that cannot keep them**

In `lab/src/panes/paneSpec.ts`, change the `diff` case to `marks: false`:

```ts
    case 'diff':
      // A defect names engines, and `diff` is not one, so a mark drawn here
      // could never be found again. It comes back when a defect can name a
      // pane rather than an engine.
      return { state: deps.diff.pane, busy: false, note: deps.diff.note,
               marks: false, followsCamera: true };
```

- [ ] **Step 2: Run the pane tests**

Run: `cd /Users/mike/src/brick-icons/lab && npx vitest run src/panes/`
Expected: PASS. If a test asserts the diff pane takes marks, update it to assert it does not, and note why in the test name.

- [ ] **Step 3: Build the registry and declare the capability**

In `createPartInspector`, above the `return defineInstrument(...)`:

```tsx
  // One registry per instrument, written by `Panes` and read by `targets`.
  const registry = createTargetRegistry();
```

Add to the `defineInstrument` object, beside `chrome` and `job`:

```tsx
    annotations: {
      targets: () => registry.targets(),
      meaning: {
        statuses: STATUSES.map((id) => ({ id, label: id })),
      },
    },
```

Add imports:

```tsx
import { createTargetRegistry, type TargetRegistry } from '@lab/defects/targets';
import { STATUSES } from '@lab/defects/useDefects';
```

Pass `registry` into `Panes`: change `render: (ctx) => <Panes ctx={ctx} client={client} />` to `render: (ctx) => <Panes ctx={ctx} client={client} registry={registry} />`, and widen `Panes`' props to `{ ctx: any; client: LabClient; registry: TargetRegistry }`.

- [ ] **Step 4: Typecheck**

Run: `cd /Users/mike/src/brick-icons/lab && npm run typecheck`
Expected: errors only about `Panes` not yet using `registry` if `noUnusedParameters` is on — fixed in Task 7. Any error naming `annotations` means the capability shape is wrong; re-read `AnnotationsCapability` in the spec.

- [ ] **Step 5: Commit**

```bash
cd /Users/mike/src/brick-icons
git add lab/src/instruments/partInspector.tsx lab/src/panes/paneSpec.ts
git commit -m "declare the annotations capability on the part inspector"
```

---

### Task 7: Wire Panes and drop MarkLayer

**Files:**
- Modify: `lab/src/instruments/partInspector.tsx`

- [ ] **Step 1: Publish the snapshot each render**

Inside `Panes`, after `const camera = readView(ctx.trial.view);`, add:

```tsx
  const paneRefs = useRef<Record<string, RefObject<HTMLDivElement | null>>>({});
  const refFor = (id: SourceId) => {
    paneRefs.current[id] ??= createRef<HTMLDivElement>();
    return paneRefs.current[id];
  };
```

Then, **after `const deps: PaneDeps = { ... }` is defined** — `paneSpec` takes `deps`, and reading it earlier hits the temporal dead zone — publish:

```tsx
  const markable = sources.filter((s) => paneSpec(s, deps).marks);
  registry.publish({
    camera,
    // The measured body, not `render_px`: a stored fraction has always been a
    // fraction of the box the layout gave the pane, and passing the render
    // size instead silently moves every defect filed before today.
    content: (() => {
      const box = boxes[markable[0]?.id ?? ''] ?? { width: 1, height: 1 };
      return { w: box.width, h: box.height };
    })(),
    panes: markable.map((s) => ({
      id: s.id,
      ref: refFor(s.id),
      base: () => baseOf(deps, s),
    })),
  });
```

Add `createRef`, `useRef` and `RefObject` to the react imports.

- [ ] **Step 2: Hand a pane its base**

Add above `Panes`:

```tsx
/** What a capture composites the marks over. A pane already holds exactly the
 *  two shapes `CaptureSource` takes. */
function baseOf(deps: PaneDeps, source: Source): CaptureSource {
  const state = paneSpec(source, deps).state;
  if (state.kind === 'svg') return { kind: 'svg', markup: state.markup };
  if (state.kind === 'image') return { kind: 'image', src: state.src };
  return { kind: 'svg', markup: '<svg xmlns="http://www.w3.org/2000/svg"/>' };
}
```

Import `type { CaptureSource } from '@weasel-js/labkit'`.

- [ ] **Step 3: Give each pane its ref and remove the layer**

In the `sources.map`, add `bodyRef={spec.marks ? refFor(source.id) : undefined}` to `<SourcePane>`, and replace the `overlay` prop's contents with just `{spec.overlay}` — delete the whole `{spec.marks ? <MarkLayer .../> : null}` block.

- [ ] **Step 4: File from an unfiled mark**

Replace the `pendingMark` state with a subscription. After the `useDefects` call:

```tsx
  const marks = useAnnotations();
  const [pending, setPending] = useState<Annotation | null>(null);

  useEffect(() => marks.subscribe(() => {
    // No delta comes with the callback, so the unfiled mark is found by the
    // absence of the id the projection stamps on every mark it makes.
    const loose = marks.query().find((a) => !(a.meta as MarkMeta | undefined)?.defectId);
    setPending(loose ?? null);
  }), [marks]);
```

Import `useAnnotations` and `type Annotation` from `@weasel-js/labkit`, `type MarkMeta` from `@lab/defects/projection`, and `useEffect` from react.

Change the dialog to read `pending`:

```tsx
      {pending ? (
        <FileDefectDialog
          part={part}
          mark={pending.frac}
          engines={engineIds}
          onCancel={() => { marks.remove(pending.id); setPending(null); }}
          onFile={async (fields) => {
            const geometry = markToDefectFields({
              id: pending.id, target: pending.target,
              kind: pending.kind, frac: pending.frac, points: pending.points,
            });
            await file(buildDefect({
              part, engines: fields.engines, title: fields.title, notes: fields.notes,
              mark: geometry.mark, kind: geometry.kind, points: geometry.points,
              config,
              existing: defects.map((d) => d.id),
              today: new Date().toISOString().slice(0, 10),
            }));
            // The server owns it now; the projection remakes it on reload.
            marks.remove(pending.id);
            setPending(null);
          }}
        />
      ) : null}
```

- [ ] **Step 5: Project the server's defects into the store**

After the subscription effect:

```tsx
  const shownTargets = markable.map((s) => targetId(s.id));
  useEffect(() => {
    for (const a of marks.query()) {
      if ((a.meta as MarkMeta | undefined)?.defectId) marks.remove(a.id);
    }
    for (const d of defects) {
      for (const init of defectToMarks(d, shownTargets)) marks.add(init, config);
    }
  }, [defects, shownTargets.join(','), marks, config]);
```

Import `defectToMarks` and `targetId` from `@lab/defects/projection`.

- [ ] **Step 6: Typecheck and run the whole suite**

Run: `cd /Users/mike/src/brick-icons/lab && npm run typecheck && npx vitest run`
Expected: typecheck clean. `MarkLayer.test.tsx` still passes (its subject is deleted in Task 8); everything else passes.

- [ ] **Step 7: Commit**

```bash
cd /Users/mike/src/brick-icons
git add lab/src/instruments/partInspector.tsx
git commit -m "draw defect marks with labkit's annotations overlay"
```

---

### Task 8: Delete what labkit now owns

**Files:**
- Delete: `lab/src/defects/MarkLayer.tsx`, `MarkLayer.css`, `MarkLayer.test.tsx`, `geometry.ts`, `geometry.test.ts`
- Modify: `lab/src/defects/identity.ts`, `identity.test.ts`

- [ ] **Step 1: Move the Mark type before deleting its file**

`Mark` is still the shape `Defect.mark` stores. Move it into `lab/src/defects/useDefects.ts`:

```ts
/** A rectangle in fractions of the pane box it was drawn on. */
export interface Mark { x: number; y: number; w: number; h: number; }
```

Update every `from '@lab/defects/geometry'` import to `from '@lab/defects/useDefects'`. Find them:

Run: `cd /Users/mike/src/brick-icons/lab && grep -rn "defects/geometry" src/`

- [ ] **Step 2: Delete the files**

```bash
cd /Users/mike/src/brick-icons/lab
git rm src/defects/MarkLayer.tsx src/defects/MarkLayer.css src/defects/MarkLayer.test.tsx \
       src/defects/geometry.ts src/defects/geometry.test.ts
```

Note: `projection.contract.test.ts` from Task 4 imports `markToScreen` from the deleted file. Delete that test too — it has served its purpose, and Task 4's decision is recorded as a comment in the code:

```bash
git rm src/defects/projection.contract.test.ts
```

- [ ] **Step 3: Strip identity.ts to its id half**

Delete `SEEN_KEYS`, `Seen`, `seenFrom` and `seenMatches` from `lab/src/defects/identity.ts`. Keep `slug` and `defectId`. In `useDefects.ts`, `Defect.seen` stays a stored field (old records carry it and the server returns it) but `buildDefect` no longer computes it — delete the `seen: seenFrom(config)` line and give it `seen: {}`, with:

```ts
  /** Kept so an existing record round-trips. labkit answers staleness now,
   *  from the target's `positionDependsOn`. */
  seen: Seen;
```

Move `export type Seen = Record<string, string>;` into `useDefects.ts`.

Delete the `seenFrom` and `seenMatches` cases from `identity.test.ts`.

- [ ] **Step 4: Run everything**

Run: `cd /Users/mike/src/brick-icons/lab && npm run typecheck && npx vitest run`
Expected: typecheck clean, all remaining tests pass. `DefectCard` reads `defect.seen` for its "seen at" line — that still works on stored records and shows nothing for new ones.

- [ ] **Step 5: Commit**

```bash
cd /Users/mike/src/brick-icons
git add -A lab/src/defects
git commit -m "delete the mark layer and geometry labkit now owns"
```

---

### Task 9: Verify in a browser — jsdom cannot see any of this

The overlay portals into labkit's shared GL surface. Every test above passes with the overlay completely broken.

- [ ] **Step 1: Start the lab**

```bash
cd /Users/mike/src/brick-icons && python -m brick_icons.lab &
cd /Users/mike/src/brick-icons/lab && npm run dev
```

- [ ] **Step 2: Check each of these and fix what fails**

- A mark drawn on the naive pane appears on the naive pane **and not on occt**, until it is filed against both.
- Pan and zoom the panes: marks stay on the feature they were drawn on. If they swim, `view` is not reaching the target — check `registry.publish` runs on the render that changes the camera.
- Change `angle`: existing marks show labkit's stale styling. If nothing goes stale, `positionDependsOn` is not reaching the target.
- Draw a **line** on a missing edge. It renders as a line, not as its bounding box.
- Open a part that already has defects filed before this change. They land where they did before. If they moved, Task 4's `content` decision is wrong for this layout.
- Export from the toolbar: PNG and SVG both download, with marks over the pane's picture.

- [ ] **Step 3: Commit any fixes, then merge**

```bash
cd /Users/mike/src/brick-icons
git add -A && git commit -m "fix what only a browser could show"
```

---

### Task 10: Report back to weasel

The three API frictions are now proven or disproven. Fold them into weasel's arc 5 section at `/Users/mike/src/weasel/.claude/worktrees/trunk/docs/superpowers/specs/2026-09-02-labkit-annotations-design.md`, replacing the "Arc 5 — brick-icons migrates" section's future tense with what actually happened, and retire the arc 5 entry from `docs/TODO.md` in the same change.

- [ ] **Step 1: Rewrite the arc 5 section** with: whether `subscribe()` without a delta forced snapshot diffing (it did — Task 7 Step 4), whether `AnnotationStorage.load` being synchronous blocked using it (it did — the whole projection exists because of it), and whether `targets(state, config)` not reaching the trial view forced the registry (it did — Task 2).

- [ ] **Step 2: Write a changeset** at `/Users/mike/src/weasel/.claude/worktrees/trunk/.changeset/<name>.md` with `'@weasel-js/labkit': patch` if any labkit change came out of this. `patch` only.

- [ ] **Step 3: Commit in both repos. Do not push either without asking.**
