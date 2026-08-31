# Lab Defect Marking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drag a box on a render to file a defect, see every filed defect on the part you are looking at, and generate `HANDOFF.md`'s defect list from the store so the two cannot disagree.

**Architecture:** A mark is a rectangle in fractions of the render box, stored in `tests/goldens/defects.toml` next to the parameters it was seen at. The geometry that converts a drag into a mark lives in a plain module with tests, because a mark that lands in the wrong place looks exactly like a mark that landed in the right place.

**Tech Stack:** React 19, TypeScript, Vitest (frontend); Python, pytest (the generator).

**Depends on:** `2026-08-31-lab-server.md` and `2026-08-31-lab-part-inspector.md`, both complete. The defect routes (`GET`/`POST`/`PATCH /api/defects`) and `brick_icons/lab/defects.py` already exist.

**Spec:** `docs/superpowers/specs/2026-08-31-corpus-lab-design.md`

---

## File Structure

| file | responsibility |
|---|---|
| `lab/src/defects/geometry.ts` | drag ↔ mark ↔ screen rectangle conversion |
| `lab/src/defects/identity.ts` | a defect's id, and whether its `seen` matches the current config |
| `lab/src/defects/useDefects.ts` | load, add and patch a part's defects |
| `lab/src/defects/MarkLayer.tsx` | draws marks over a pane; drag creates one |
| `lab/src/defects/FileDefectDialog.tsx` | title, status and notes for a new mark |
| `lab/src/defects/DefectList.tsx` | every defect, filtered, click to open |
| `scripts/defects-to-handoff.py` | regenerate the handoff's list from the TOML |
| `tests/test_defects_to_handoff.py` | its tests |

---

## Task 1: Mark geometry

**Files:**
- Create: `lab/src/defects/geometry.ts`
- Test: `lab/src/defects/geometry.test.ts`

A mark is stored in fractions of the render box so it survives a change of
`--render-px`. The pane's stage fills its body, so the render box in screen
space is the body rect with the camera applied.

- [ ] **Step 1: Write the failing test**

Create `lab/src/defects/geometry.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { markFromDrag, markToScreen, normalizeMark } from '@lab/defects/geometry';
import { HOME } from '@lab/panes/camera';

const BOX = { width: 200, height: 100 };

describe('markFromDrag', () => {
  it('converts a drag to fractions of the render box', () => {
    const mark = markFromDrag({ x: 20, y: 10 }, { x: 60, y: 30 }, BOX, HOME);
    expect(mark).toEqual({ x: 0.1, y: 0.1, w: 0.2, h: 0.2 });
  });

  it('normalizes a drag made right-to-left', () => {
    const forward = markFromDrag({ x: 20, y: 10 }, { x: 60, y: 30 }, BOX, HOME);
    const backward = markFromDrag({ x: 60, y: 30 }, { x: 20, y: 10 }, BOX, HOME);
    expect(backward).toEqual(forward);
  });

  it('undoes the camera, so a mark made zoomed in lands where it was drawn', () => {
    const camera = { zoom: 2, pan: { x: -40, y: -20 } };
    // screen 0,0 is world 20,10 at this camera
    const mark = markFromDrag({ x: 0, y: 0 }, { x: 40, y: 40 }, BOX, camera);
    expect(mark).toEqual({ x: 0.1, y: 0.1, w: 0.1, h: 0.2 });
  });

  it('clamps to the render box', () => {
    const mark = markFromDrag({ x: -50, y: -50 }, { x: 400, y: 400 }, BOX, HOME);
    expect(mark).toEqual({ x: 0, y: 0, w: 1, h: 1 });
  });
});

describe('markToScreen', () => {
  it('is the inverse of markFromDrag at home', () => {
    const mark = markFromDrag({ x: 20, y: 10 }, { x: 60, y: 30 }, BOX, HOME);
    expect(markToScreen(mark, BOX, HOME))
      .toEqual({ left: 20, top: 10, width: 40, height: 20 });
  });

  it('is the inverse under a camera too', () => {
    const camera = { zoom: 3, pan: { x: 17, y: -9 } };
    const mark = markFromDrag({ x: 5, y: 5 }, { x: 65, y: 35 }, BOX, camera);
    const screen = markToScreen(mark, BOX, camera);
    expect(screen.left).toBeCloseTo(5);
    expect(screen.top).toBeCloseTo(5);
    expect(screen.width).toBeCloseTo(60);
    expect(screen.height).toBeCloseTo(30);
  });

  it('grows with zoom', () => {
    const mark = { x: 0.25, y: 0.25, w: 0.5, h: 0.5 };
    const at1 = markToScreen(mark, BOX, HOME);
    const at2 = markToScreen(mark, BOX, { zoom: 2, pan: { x: 0, y: 0 } });
    expect(at2.width).toBe(at1.width * 2);
  });
});

describe('normalizeMark', () => {
  it('rounds to four places, which is finer than a pixel on any render', () => {
    expect(normalizeMark({ x: 0.123456, y: 0.5, w: 0.2, h: 0.2 })!.x).toBe(0.1235);
  });

  it('rejects a zero-area mark', () => {
    expect(normalizeMark({ x: 0.1, y: 0.1, w: 0, h: 0.2 })).toBeNull();
  });

  it('rejects a mark below the minimum size, which is a stray click', () => {
    expect(normalizeMark({ x: 0.1, y: 0.1, w: 0.001, h: 0.001 })).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/defects/geometry.test.ts`
Expected: FAIL — cannot resolve `@lab/defects/geometry`

- [ ] **Step 3: Write the implementation**

Create `lab/src/defects/geometry.ts`:

```ts
import type { Camera } from '@lab/panes/camera';

/** A rectangle in fractions of the render box. Survives a change of
 *  --render-px; does NOT survive a change of --angle, which is why a defect
 *  also records the parameters it was seen at. */
export interface Mark {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Box {
  width: number;
  height: number;
}

export interface ScreenRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Smaller than this is a stray click, not a mark. */
const MIN_SIDE = 0.004;

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

function screenToFraction(point: { x: number; y: number }, box: Box, camera: Camera) {
  return {
    x: clamp01((point.x - camera.pan.x) / camera.zoom / box.width),
    y: clamp01((point.y - camera.pan.y) / camera.zoom / box.height),
  };
}

export function markFromDrag(start: { x: number; y: number },
                             end: { x: number; y: number },
                             box: Box, camera: Camera): Mark {
  const a = screenToFraction(start, box, camera);
  const b = screenToFraction(end, box, camera);
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    w: Math.abs(b.x - a.x),
    h: Math.abs(b.y - a.y),
  };
}

export function markToScreen(mark: Mark, box: Box, camera: Camera): ScreenRect {
  return {
    left: mark.x * box.width * camera.zoom + camera.pan.x,
    top: mark.y * box.height * camera.zoom + camera.pan.y,
    width: mark.w * box.width * camera.zoom,
    height: mark.h * box.height * camera.zoom,
  };
}

const round4 = (v: number) => Math.round(v * 10000) / 10000;

/** Null for a mark too small to have been meant. */
export function normalizeMark(mark: Mark): Mark | null {
  if (mark.w < MIN_SIDE || mark.h < MIN_SIDE) return null;
  return { x: round4(mark.x), y: round4(mark.y), w: round4(mark.w), h: round4(mark.h) };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/defects/geometry.test.ts`
Expected: PASS, 10 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/defects && git commit -m "convert a drag on a pane into a stored mark"
```

---

## Task 2: Defect identity and staleness

**Files:**
- Create: `lab/src/defects/identity.ts`
- Test: `lab/src/defects/identity.test.ts`

- [ ] **Step 1: Write the failing test**

Create `lab/src/defects/identity.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { defectId, seenFrom, seenMatches, slug } from '@lab/defects/identity';

describe('slug', () => {
  it('lowercases and hyphenates', () => {
    expect(slug('Borehole rim not drawn')).toBe('borehole-rim-not-drawn');
  });

  it('drops punctuation', () => {
    expect(slug('the "near" lip, missing')).toBe('the-near-lip-missing');
  });

  it('collapses runs of separators', () => {
    expect(slug('a   b -- c')).toBe('a-b-c');
  });

  it('truncates on a word boundary', () => {
    expect(slug('one two three four five six seven eight').length).toBeLessThanOrEqual(40);
    expect(slug('one two three four five six seven eight')).not.toMatch(/-$/);
  });
});

describe('defectId', () => {
  it('joins part, engine and slug', () => {
    expect(defectId('3941', ['occt'], 'borehole rim not drawn', []))
      .toBe('3941-occt-borehole-rim-not-drawn');
  });

  it('names multiple engines in order', () => {
    expect(defectId('3941', ['occt', 'naive'], 'x', []))
      .toBe('3941-naive-occt-x');
  });

  it('uses "both" for every engine at once', () => {
    expect(defectId('3941', ['naive', 'occt'], 'x', [], ['naive', 'occt']))
      .toBe('3941-both-x');
  });

  it('suffixes to avoid colliding with an existing id', () => {
    expect(defectId('3941', ['occt'], 'x', ['3941-occt-x'])).toBe('3941-occt-x-2');
  });

  it('keeps counting past the first collision', () => {
    expect(defectId('3941', ['occt'], 'x', ['3941-occt-x', '3941-occt-x-2']))
      .toBe('3941-occt-x-3');
  });
});

describe('seenFrom', () => {
  it('records only the parameters that move a mark', () => {
    expect(seenFrom({ angle: '30,25', shading: 'outline', shade_style: 'flat3',
                      part_color: '0xc91a09', render_px: 900 }))
      .toEqual({ angle: '30,25', shading: 'outline', shade_style: 'flat3' });
  });

  it('omits a parameter that is not set', () => {
    expect(seenFrom({ angle: '30,25' })).toEqual({ angle: '30,25' });
  });
});

describe('seenMatches', () => {
  it('is true when every recorded parameter still holds', () => {
    expect(seenMatches({ angle: '30,25' }, { angle: '30,25', engine: 'occt' })).toBe(true);
  });

  it('is false when the angle moved, because the mark moved with it', () => {
    expect(seenMatches({ angle: '30,25' }, { angle: '45,45' })).toBe(false);
  });

  it('is true for a defect with nothing recorded', () => {
    expect(seenMatches({}, { angle: '30,25' })).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/defects/identity.test.ts`
Expected: FAIL — cannot resolve `@lab/defects/identity`

- [ ] **Step 3: Write the implementation**

Create `lab/src/defects/identity.ts`:

```ts
/** The parameters a mark's position depends on. `--render-px` is absent on
 *  purpose: the mark is fractional, so resolution does not move it. */
const SEEN_KEYS = ['angle', 'shading', 'shade_style'] as const;

export type Seen = Partial<Record<(typeof SEEN_KEYS)[number], string>>;

export function slug(text: string, max = 40): string {
  const base = text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  if (base.length <= max) return base;
  const cut = base.slice(0, max);
  const boundary = cut.lastIndexOf('-');
  return (boundary > 0 ? cut.slice(0, boundary) : cut).replace(/-$/, '');
}

export function defectId(part: string, engines: string[], title: string,
                         existing: readonly string[],
                         allEngines: readonly string[] = []): string {
  const sorted = [...engines].sort();
  const named = allEngines.length > 0
    && sorted.length === allEngines.length
    && sorted.every((e) => allEngines.includes(e))
    ? 'both'
    : sorted.join('-');
  const base = [part, named, slug(title)].filter(Boolean).join('-');
  if (!existing.includes(base)) return base;
  let n = 2;
  while (existing.includes(`${base}-${n}`)) n += 1;
  return `${base}-${n}`;
}

export function seenFrom(config: Record<string, unknown>): Seen {
  const out: Seen = {};
  for (const key of SEEN_KEYS) {
    const value = config[key];
    if (typeof value === 'string' && value) out[key] = value;
  }
  return out;
}

/** Whether a defect's mark can be trusted against the render on screen. */
export function seenMatches(seen: Seen, config: Record<string, unknown>): boolean {
  return Object.entries(seen).every(([key, value]) => config[key] === value);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/defects/identity.test.ts`
Expected: PASS, 12 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/defects/identity.ts lab/src/defects/identity.test.ts
git commit -m "name a defect and tell when its mark has gone stale"
```

---

## Task 3: The defect hook

**Files:**
- Create: `lab/src/defects/useDefects.ts`
- Test: `lab/src/defects/useDefects.test.ts`

- [ ] **Step 1: Write the failing test**

Create `lab/src/defects/useDefects.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { buildDefect } from '@lab/defects/useDefects';

describe('buildDefect', () => {
  const args = {
    part: '3941',
    engines: ['occt'],
    title: 'borehole rim not drawn',
    notes: '',
    mark: { x: 0.42, y: 0.55, w: 0.11, h: 0.09 },
    config: { angle: '30,25', shading: 'outline', shade_style: 'flat3' },
    existing: [] as string[],
    today: '2026-08-31',
  };

  it('builds a record the server will accept', () => {
    const got = buildDefect(args);
    expect(got.id).toBe('3941-occt-borehole-rim-not-drawn');
    expect(got.part).toBe('3941');
    expect(got.engines).toEqual(['occt']);
    expect(got.status).toBe('open');
    expect(got.mark).toEqual(args.mark);
    expect(got.filed).toBe('2026-08-31');
  });

  it('records only the parameters that move the mark', () => {
    expect(buildDefect(args).seen)
      .toEqual({ angle: '30,25', shading: 'outline', shade_style: 'flat3' });
  });

  it('avoids an id already in use', () => {
    expect(buildDefect({ ...args, existing: ['3941-occt-borehole-rim-not-drawn'] }).id)
      .toBe('3941-occt-borehole-rim-not-drawn-2');
  });

  it('keeps notes when given', () => {
    expect(buildDefect({ ...args, notes: 'only at 30,25' }).notes).toBe('only at 30,25');
  });

  it('refuses an untitled defect, which nothing could later find', () => {
    expect(() => buildDefect({ ...args, title: '   ' })).toThrow(/title/i);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/defects/useDefects.test.ts`
Expected: FAIL — cannot resolve `@lab/defects/useDefects`

- [ ] **Step 3: Write the implementation**

Create `lab/src/defects/useDefects.ts`:

```ts
import { useCallback, useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { Mark } from '@lab/defects/geometry';
import { defectId, seenFrom, type Seen } from '@lab/defects/identity';

export type DefectStatus = 'open' | 'fixed' | 'wontfix' | 'notabug';

export interface Defect {
  id: string;
  part: string;
  engines: string[];
  status: DefectStatus;
  title: string;
  mark: Mark;
  seen: Seen;
  filed: string;
  notes: string;
}

export interface BuildDefectArgs {
  part: string;
  engines: string[];
  title: string;
  notes: string;
  mark: Mark;
  config: Record<string, unknown>;
  existing: readonly string[];
  today: string;
}

export function buildDefect(args: BuildDefectArgs): Defect {
  const title = args.title.trim();
  if (!title) throw new Error('a defect needs a title');
  return {
    id: defectId(args.part, args.engines, title, args.existing),
    part: args.part,
    engines: [...args.engines].sort(),
    status: 'open',
    title,
    mark: args.mark,
    seen: seenFrom(args.config),
    filed: args.today,
    notes: args.notes,
  };
}

/** A part's defects, and the two ways they change. */
export function useDefects(client: LabClient, part: string) {
  const [defects, setDefects] = useState<Defect[]>([]);

  const reload = useCallback(async () => {
    if (!part.trim()) {
      setDefects([]);
      return;
    }
    setDefects((await client.defects(part)) as Defect[]);
  }, [client, part]);

  useEffect(() => { void reload(); }, [reload]);

  const file = useCallback(async (record: Defect) => {
    await client.addDefect(record);
    await reload();
  }, [client, reload]);

  const setStatus = useCallback(async (id: string, status: DefectStatus) => {
    await client.patchDefect(id, { status });
    await reload();
  }, [client, reload]);

  return { defects, file, setStatus, reload };
}
```

- [ ] **Step 4: Add the two client methods the hook calls**

In `lab/src/api/client.ts`, add inside the returned object, after `defects`:

```ts
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd lab && npx vitest run src/defects/useDefects.test.ts`
Expected: PASS, 5 tests

- [ ] **Step 6: Commit**

```bash
git add lab/src/defects/useDefects.ts lab/src/defects/useDefects.test.ts lab/src/api/client.ts
git commit -m "build and post a defect from a mark"
```

---

## Task 4: The mark layer

**Files:**
- Create: `lab/src/defects/MarkLayer.tsx`, `lab/src/defects/MarkLayer.css`
- Test: `lab/src/defects/MarkLayer.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `lab/src/defects/MarkLayer.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MarkLayer } from '@lab/defects/MarkLayer';
import { HOME } from '@lab/panes/camera';
import type { Defect } from '@lab/defects/useDefects';

const defect = (over: Partial<Defect> = {}): Defect => ({
  id: 'd1', part: '3941', engines: ['occt'], status: 'open',
  title: 'borehole rim not drawn', mark: { x: 0.25, y: 0.25, w: 0.5, h: 0.5 },
  seen: { angle: '30,25' }, filed: '2026-08-31', notes: '', ...over,
});

const props = {
  box: { width: 200, height: 100 },
  camera: HOME,
  config: { angle: '30,25' },
  onDraw: () => {},
  onSelect: () => {},
};

describe('MarkLayer', () => {
  it('draws one box per defect', () => {
    const { container } = render(
      <MarkLayer {...props} defects={[defect(), defect({ id: 'd2' })]} />);
    expect(container.querySelectorAll('.mark')).toHaveLength(2);
  });

  it('places a mark where the geometry says', () => {
    const { container } = render(<MarkLayer {...props} defects={[defect()]} />);
    const box = container.querySelector('.mark') as HTMLElement;
    expect(box.style.left).toBe('50px');
    expect(box.style.width).toBe('100px');
  });

  it('marks a stale defect so it is not read as a hit', () => {
    const { container } = render(
      <MarkLayer {...props} config={{ angle: '45,45' }} defects={[defect()]} />);
    expect(container.querySelector('.mark-stale')).toBeTruthy();
  });

  it('labels a mark with its defect title', () => {
    render(<MarkLayer {...props} defects={[defect()]} />);
    expect(screen.getByTitle(/borehole rim not drawn/)).toBeTruthy();
  });

  it('selects a defect when its mark is clicked', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <MarkLayer {...props} onSelect={onSelect} defects={[defect()]} />);
    fireEvent.click(container.querySelector('.mark')!);
    expect(onSelect).toHaveBeenCalledWith('d1');
  });

  it('reports a completed drag as a mark', () => {
    const onDraw = vi.fn();
    const { container } = render(
      <MarkLayer {...props} onDraw={onDraw} defects={[]} />);
    const surface = container.querySelector('.mark-layer')!;
    fireEvent.pointerDown(surface, { clientX: 20, clientY: 10 });
    fireEvent.pointerMove(surface, { clientX: 60, clientY: 30 });
    fireEvent.pointerUp(surface, { clientX: 60, clientY: 30 });
    expect(onDraw).toHaveBeenCalledWith({ x: 0.1, y: 0.1, w: 0.2, h: 0.2 });
  });

  it('ignores a click that drew nothing', () => {
    const onDraw = vi.fn();
    const { container } = render(
      <MarkLayer {...props} onDraw={onDraw} defects={[]} />);
    const surface = container.querySelector('.mark-layer')!;
    fireEvent.pointerDown(surface, { clientX: 20, clientY: 10 });
    fireEvent.pointerUp(surface, { clientX: 20, clientY: 10 });
    expect(onDraw).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/defects/MarkLayer.test.tsx`
Expected: FAIL — cannot resolve `@lab/defects/MarkLayer`

- [ ] **Step 3: Write the implementation**

Create `lab/src/defects/MarkLayer.css`:

```css
.mark-layer { position: absolute; inset: 0; }

.mark {
  position: absolute;
  border: 1px solid var(--lk-danger, #d05098);
  background: color-mix(in srgb, var(--lk-danger, #d05098) 12%, transparent);
  cursor: pointer;
}

.mark-stale { opacity: 0.35; border-style: dashed; }
.mark-fixed { border-color: var(--lk-ok, #58ab41); }
.mark-drawing { position: absolute; border: 1px dashed currentColor; }
```

Create `lab/src/defects/MarkLayer.tsx`:

```tsx
import { useRef, useState } from 'react';
import type { Camera } from '@lab/panes/camera';
import { type Box, type Mark, markFromDrag, markToScreen, normalizeMark }
  from '@lab/defects/geometry';
import { seenMatches } from '@lab/defects/identity';
import type { Defect } from '@lab/defects/useDefects';
import '@lab/defects/MarkLayer.css';

export interface MarkLayerProps {
  defects: Defect[];
  box: Box;
  camera: Camera;
  config: Record<string, unknown>;
  onDraw: (mark: Mark) => void;
  onSelect: (id: string) => void;
}

export function MarkLayer({ defects, box, camera, config, onDraw, onSelect }: MarkLayerProps) {
  const start = useRef<{ x: number; y: number } | null>(null);
  const [drawing, setDrawing] = useState<Mark | null>(null);

  const local = (e: { clientX: number; clientY: number; currentTarget: Element }) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  return (
    <div
      className="mark-layer"
      onPointerDown={(e) => {
        start.current = local(e);
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (start.current) setDrawing(markFromDrag(start.current, local(e), box, camera));
      }}
      onPointerUp={(e) => {
        const from = start.current;
        start.current = null;
        setDrawing(null);
        if (!from) return;
        const mark = normalizeMark(markFromDrag(from, local(e), box, camera));
        if (mark) onDraw(mark);
      }}
    >
      {defects.map((d) => {
        const rect = markToScreen(d.mark, box, camera);
        const stale = !seenMatches(d.seen, config);
        const classes = ['mark', stale ? 'mark-stale' : '',
                         d.status === 'fixed' ? 'mark-fixed' : ''].filter(Boolean);
        return (
          <div
            key={d.id}
            className={classes.join(' ')}
            title={stale ? `${d.title} (seen at other settings)` : d.title}
            role="button"
            tabIndex={0}
            style={{ left: `${rect.left}px`, top: `${rect.top}px`,
                     width: `${rect.width}px`, height: `${rect.height}px` }}
            onClick={(e) => { e.stopPropagation(); onSelect(d.id); }}
            onKeyDown={(e) => { if (e.key === 'Enter') onSelect(d.id); }}
          />
        );
      })}
      {drawing ? (
        <div className="mark-drawing"
          style={(() => {
            const r = markToScreen(drawing, box, camera);
            return { left: `${r.left}px`, top: `${r.top}px`,
                     width: `${r.width}px`, height: `${r.height}px` };
          })()} />
      ) : null}
    </div>
  );
}
```

Positions are inline styles because they are per-mark values that change with
the camera; a class cannot carry them.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/defects/MarkLayer.test.tsx`
Expected: PASS, 7 tests. If the drag test fails because jsdom does not
implement `setPointerCapture`, add to `lab/src/test-setup.ts` (creating it, and
referencing it from `vite.config.ts` as `test.setupFiles`):

```ts
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
}
```

- [ ] **Step 5: Commit**

```bash
git add lab/src/defects lab/src/test-setup.ts lab/vite.config.ts
git commit -m "draw and create defect marks over a pane"
```

---

## Task 5: The file-a-defect dialog

**Files:**
- Create: `lab/src/defects/FileDefectDialog.tsx`
- Test: `lab/src/defects/FileDefectDialog.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `lab/src/defects/FileDefectDialog.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FileDefectDialog } from '@lab/defects/FileDefectDialog';

const props = {
  part: '3941',
  mark: { x: 0.1, y: 0.1, w: 0.2, h: 0.2 },
  engines: ['naive', 'occt'],
  onCancel: () => {},
  onFile: () => {},
};

describe('FileDefectDialog', () => {
  it('names the part it is filing against', () => {
    render(<FileDefectDialog {...props} />);
    expect(screen.getByText(/3941/)).toBeTruthy();
  });

  it('offers each visible engine', () => {
    render(<FileDefectDialog {...props} />);
    expect(screen.getByLabelText('naive')).toBeTruthy();
    expect(screen.getByLabelText('occt')).toBeTruthy();
  });

  it('files with the title, notes and checked engines', () => {
    const onFile = vi.fn();
    render(<FileDefectDialog {...props} onFile={onFile} />);
    fireEvent.change(screen.getByLabelText(/title/i),
      { target: { value: 'borehole rim not drawn' } });
    fireEvent.change(screen.getByLabelText(/notes/i), { target: { value: 'only at 30,25' } });
    fireEvent.click(screen.getByLabelText('naive'));   // leave only occt checked
    fireEvent.click(screen.getByText(/^file$/i));
    expect(onFile).toHaveBeenCalledWith({
      title: 'borehole rim not drawn', notes: 'only at 30,25', engines: ['occt'],
    });
  });

  it('will not file without a title', () => {
    const onFile = vi.fn();
    render(<FileDefectDialog {...props} onFile={onFile} />);
    fireEvent.click(screen.getByText(/^file$/i));
    expect(onFile).not.toHaveBeenCalled();
  });

  it('will not file with no engine selected', () => {
    const onFile = vi.fn();
    render(<FileDefectDialog {...props} onFile={onFile} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: 'x' } });
    fireEvent.click(screen.getByLabelText('naive'));
    fireEvent.click(screen.getByLabelText('occt'));
    fireEvent.click(screen.getByText(/^file$/i));
    expect(onFile).not.toHaveBeenCalled();
  });

  it('cancels', () => {
    const onCancel = vi.fn();
    render(<FileDefectDialog {...props} onCancel={onCancel} />);
    fireEvent.click(screen.getByText(/cancel/i));
    expect(onCancel).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/defects/FileDefectDialog.test.tsx`
Expected: FAIL — cannot resolve `@lab/defects/FileDefectDialog`

- [ ] **Step 3: Write the implementation**

Create `lab/src/defects/FileDefectDialog.tsx`:

```tsx
import { useState } from 'react';
import type { Mark } from '@lab/defects/geometry';

export interface FileDefectDialogProps {
  part: string;
  mark: Mark;
  /** The engines whose panes are on screen. */
  engines: string[];
  onCancel: () => void;
  onFile: (fields: { title: string; notes: string; engines: string[] }) => void;
}

export function FileDefectDialog({ part, engines, onCancel, onFile }: FileDefectDialogProps) {
  const [title, setTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [checked, setChecked] = useState<string[]>(engines);

  const ready = title.trim().length > 0 && checked.length > 0;

  return (
    <div className="file-defect">
      <h3>New defect on {part}</h3>
      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <fieldset>
        <legend>Engines</legend>
        {engines.map((engine) => (
          <label key={engine}>
            <input
              type="checkbox"
              checked={checked.includes(engine)}
              onChange={() => setChecked((prev) => prev.includes(engine)
                ? prev.filter((e) => e !== engine)
                : [...prev, engine])}
            />
            {engine}
          </label>
        ))}
      </fieldset>
      <label>
        Notes
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <button type="button" onClick={onCancel}>Cancel</button>
      <button
        type="button"
        disabled={!ready}
        onClick={() => {
          if (!ready) return;
          onFile({ title: title.trim(), notes, engines: [...checked].sort() });
        }}
      >
        File
      </button>
    </div>
  );
}
```

These are real `<button>` and `<input>` elements: each carries role, name and
keyboard operability for free, and none of them wraps a multi-line run of text.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/defects/FileDefectDialog.test.tsx`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/defects/FileDefectDialog.tsx lab/src/defects/FileDefectDialog.test.tsx
git commit -m "add the file-a-defect dialog"
```

---

## Task 6: The defect list

**Files:**
- Create: `lab/src/defects/DefectList.tsx`
- Test: `lab/src/defects/DefectList.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `lab/src/defects/DefectList.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DefectList, sortDefects } from '@lab/defects/DefectList';
import type { Defect } from '@lab/defects/useDefects';

const d = (over: Partial<Defect>): Defect => ({
  id: 'd1', part: '3941', engines: ['occt'], status: 'open', title: 'a',
  mark: { x: 0, y: 0, w: 1, h: 1 }, seen: {}, filed: '2026-08-31', notes: '',
  ...over,
});

describe('sortDefects', () => {
  it('puts open before fixed', () => {
    const got = sortDefects([d({ id: 'a', status: 'fixed' }), d({ id: 'b' })]);
    expect(got.map((x) => x.id)).toEqual(['b', 'a']);
  });

  it('orders by part within a status', () => {
    const got = sortDefects([d({ id: 'a', part: '4070' }), d({ id: 'b', part: '3941' })]);
    expect(got.map((x) => x.id)).toEqual(['b', 'a']);
  });

  it('puts notabug last, since it is not work', () => {
    const got = sortDefects([d({ id: 'a', status: 'notabug' }),
                             d({ id: 'b', status: 'wontfix' })]);
    expect(got.map((x) => x.id)).toEqual(['b', 'a']);
  });
});

describe('DefectList', () => {
  const props = { onOpen: () => {}, onStatus: () => {} };

  it('lists every defect', () => {
    render(<DefectList {...props} defects={[d({ id: 'a', title: 'one' }),
                                            d({ id: 'b', title: 'two' })]} />);
    expect(screen.getByText('one')).toBeTruthy();
    expect(screen.getByText('two')).toBeTruthy();
  });

  it('says so when there are none', () => {
    render(<DefectList {...props} defects={[]} />);
    expect(screen.getByText(/no defects/i)).toBeTruthy();
  });

  it('filters by status', () => {
    render(<DefectList {...props} defects={[d({ id: 'a', title: 'one' }),
      d({ id: 'b', title: 'two', status: 'fixed' })]} />);
    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: 'fixed' } });
    expect(screen.queryByText('one')).toBeNull();
    expect(screen.getByText('two')).toBeTruthy();
  });

  it('opens the part when a row is activated', () => {
    const onOpen = vi.fn();
    render(<DefectList {...props} onOpen={onOpen} defects={[d({ part: '4070' })]} />);
    fireEvent.click(screen.getByText('a'));
    expect(onOpen).toHaveBeenCalledWith('4070', 'd1');
  });

  it('changes a status', () => {
    const onStatus = vi.fn();
    render(<DefectList {...props} onStatus={onStatus} defects={[d({})]} />);
    fireEvent.change(screen.getAllByLabelText(/state of/i)[0]!,
      { target: { value: 'fixed' } });
    expect(onStatus).toHaveBeenCalledWith('d1', 'fixed');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/defects/DefectList.test.tsx`
Expected: FAIL — cannot resolve `@lab/defects/DefectList`

- [ ] **Step 3: Write the implementation**

Create `lab/src/defects/DefectList.tsx`:

```tsx
import { useState } from 'react';
import type { Defect, DefectStatus } from '@lab/defects/useDefects';

const RANK: Record<DefectStatus, number> = { open: 0, wontfix: 1, fixed: 2, notabug: 3 };
const STATUSES: DefectStatus[] = ['open', 'fixed', 'wontfix', 'notabug'];

export function sortDefects(defects: Defect[]): Defect[] {
  return [...defects].sort((a, b) =>
    RANK[a.status] - RANK[b.status]
    || a.part.localeCompare(b.part)
    || a.id.localeCompare(b.id));
}

export interface DefectListProps {
  defects: Defect[];
  onOpen: (part: string, defectId: string) => void;
  onStatus: (id: string, status: DefectStatus) => void;
}

export function DefectList({ defects, onOpen, onStatus }: DefectListProps) {
  const [filter, setFilter] = useState<'all' | DefectStatus>('all');
  const shown = sortDefects(defects)
    .filter((d) => filter === 'all' || d.status === filter);

  return (
    <div className="defect-list">
      <label>
        Status
        <select value={filter} onChange={(e) => setFilter(e.target.value as never)}>
          <option value="all">all</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      {shown.length === 0 ? <p>no defects</p> : (
        <ul>
          {shown.map((d) => (
            <li key={d.id}>
              <span
                role="button"
                tabIndex={0}
                onClick={() => onOpen(d.part, d.id)}
                onKeyDown={(e) => { if (e.key === 'Enter') onOpen(d.part, d.id); }}
              >
                <strong>{d.part}</strong> {d.title}
              </span>
              <select
                aria-label={`state of ${d.title}`}
                value={d.status}
                onChange={(e) => onStatus(d.id, e.target.value as DefectStatus)}
              >
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

The row's click target is a `<span>` inside the `<li>`, not the `<li>`: a list
item's box and role belong to the list. The status control is a native
`<select>`, which carries role, name and keyboard operability without being
written by hand.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/defects/DefectList.test.tsx`
Expected: PASS, 8 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/defects/DefectList.tsx lab/src/defects/DefectList.test.tsx
git commit -m "list every filed defect"
```

---

## Task 7: Wire marking into the Part Inspector

**Files:**
- Modify: `lab/src/panes/SourcePane.tsx`, `lab/src/instruments/partInspector.tsx`
- Test: `lab/src/panes/SourcePane.test.tsx`

- [ ] **Step 1: Write the failing test**

Append to `lab/src/panes/SourcePane.test.tsx`:

```tsx
it('renders an overlay when one is given', () => {
  const { container } = render(
    <SourcePane {...props} source={SOURCES.naive} state={{ kind: 'idle' }}
      overlay={<div className="probe" />} />);
  expect(container.querySelector('.probe')).toBeTruthy();
});

it('reports its body size so an overlay can place marks', () => {
  const onBox = vi.fn();
  render(<SourcePane {...props} source={SOURCES.naive} state={{ kind: 'idle' }}
    onBox={onBox} />);
  expect(onBox).toHaveBeenCalled();
});
```

Add `vi` to the file's `vitest` import.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/panes/SourcePane.test.tsx`
Expected: FAIL — `overlay` is not a prop

- [ ] **Step 3: Give the pane an overlay slot**

In `lab/src/panes/SourcePane.tsx`, extend the props:

```tsx
export interface SourcePaneProps {
  source: Source;
  state: PaneState;
  camera: Camera;
  onCamera: (next: Camera) => void;
  /** Drawn above the stage, in body coordinates. */
  overlay?: ReactNode;
  /** The body's pixel size, reported when it is measured or changes. */
  onBox?: (box: { width: number; height: number }) => void;
}
```

Import `useEffect`, `useRef` and `type ReactNode` from `react`, add a ref on
the body element, and report its size:

```tsx
  const body = useRef<HTMLDivElement | null>(null);
  // The callback goes through a ref so the effect does not re-subscribe when
  // the caller passes a fresh arrow each render -- which it will, because it
  // is written inline inside a map over the sources.
  const report = useRef(onBox);
  report.current = onBox;

  useEffect(() => {
    const el = body.current;
    if (!el) return;
    const emit = () => report.current?.({ width: el.clientWidth, height: el.clientHeight });
    emit();
    const observer = new ResizeObserver(emit);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
```

Put `ref={body}` on the `.pane-body` div and render `{overlay}` as its last
child, after `.pane-stage`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/panes/SourcePane.test.tsx`
Expected: PASS, 9 tests. If jsdom lacks `ResizeObserver`, add to
`lab/src/test-setup.ts`:

```ts
if (!('ResizeObserver' in globalThis)) {
  (globalThis as { ResizeObserver?: unknown }).ResizeObserver = class {
    observe() {} unobserve() {} disconnect() {}
  };
}
```

- [ ] **Step 5: Wire the mark layer into the instrument**

In `lab/src/instruments/partInspector.tsx`, inside the `Panes` component, add
state and the overlay. Add the imports:

```tsx
import { useState } from 'react';
import { MarkLayer } from '@lab/defects/MarkLayer';
import { FileDefectDialog } from '@lab/defects/FileDefectDialog';
import { buildDefect, useDefects } from '@lab/defects/useDefects';
import type { Mark } from '@lab/defects/geometry';
```

and inside `Panes`, above the return:

```tsx
  const part = String(config.part ?? '');
  const { defects, file } = useDefects(client, part);
  const [boxes, setBoxes] = useState<Record<string, { width: number; height: number }>>({});
  const [pendingMark, setPendingMark] = useState<Mark | null>(null);

  const engineIds = sources.filter((s) => s.kind === 'engine').map((s) => s.id);
```

Give each `<SourcePane>` its overlay and box reporter. The reporter is a plain
inline arrow — **not** a `useCallback`, which inside this `map` would be a hook
in a loop:

```tsx
          onBox={(box) => setBoxes((prev) => ({ ...prev, [source.id]: box }))}
          overlay={
            <MarkLayer
              defects={defects.filter((d) => d.engines.includes(source.id))}
              box={boxes[source.id] ?? { width: 1, height: 1 }}
              camera={camera}
              config={config}
              onDraw={setPendingMark}
              onSelect={() => {}}
            />
          }
```

and after the panes, inside the wrapper div:

```tsx
      {pendingMark ? (
        <FileDefectDialog
          part={part}
          mark={pendingMark}
          engines={engineIds}
          onCancel={() => setPendingMark(null)}
          onFile={async (fields) => {
            await file(buildDefect({
              part, engines: fields.engines, title: fields.title, notes: fields.notes,
              mark: pendingMark, config,
              existing: defects.map((d) => d.id),
              today: new Date().toISOString().slice(0, 10),
            }));
            setPendingMark(null);
          }}
        />
      ) : null}
```

- [ ] **Step 6: Add the defect count to the status bar**

In the instrument's `chrome` array, add a second contribution:

```tsx
      {
        id: 'defect-count',
        region: 'status',
        render: (ctx) => (
          <DefectCount
            client={client}
            part={String((ctx.config as Record<string, unknown>).part ?? '')}
          />
        ),
      },
```

and define, above `createPartInspector`:

```tsx
function DefectCount({ client, part }: { client: LabClient; part: string }) {
  const { defects } = useDefects(client, part);
  const open = defects.filter((d) => d.status === 'open').length;
  if (defects.length === 0) return <span>no defects</span>;
  return <span>{open} open / {defects.length} filed</span>;
}
```

- [ ] **Step 7: Run every test**

Run: `cd lab && npx vitest run && npm run typecheck`
Expected: PASS throughout

- [ ] **Step 8: Commit**

```bash
git add lab/src && git commit -m "file a defect by dragging a box on a render"
```

---

## Task 8: The defect panel in the lab

**Files:**
- Modify: `lab/src/App.tsx`
- Test: manual, in Task 10

- [ ] **Step 1: Add the panel**

In `lab/src/App.tsx`, add the imports:

```tsx
import { useEffect, useState } from 'react';
import { FloatingPanel } from '@weasel-js/labkit';
import { DefectList } from '@lab/defects/DefectList';
import type { Defect, DefectStatus } from '@lab/defects/useDefects';
import { setPendingPart } from '@lab/config/pending';
```

Add the component:

```tsx
function AllDefects({ client }: { client: LabClient }) {
  const { addTrial } = useLabContext();
  const [defects, setDefects] = useState<Defect[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (open) void client.defects().then((rows) => setDefects(rows as Defect[]));
  }, [open, client]);

  if (!open) {
    return <button type="button" onClick={() => setOpen(true)}>Defects</button>;
  }

  return (
    <FloatingPanel title="Defects" onClose={() => setOpen(false)}>
      <DefectList
        defects={defects}
        onOpen={(part) => { setPendingPart(part); addTrial('part-inspector'); }}
        onStatus={async (id: string, status: DefectStatus) => {
          await client.patchDefect(id, { status });
          setDefects((await client.defects()) as Defect[]);
        }}
      />
    </FloatingPanel>
  );
}
```

Render it beside the search field in `TitleBar`:

```tsx
  return (
    <>
      <PartSearch client={client} onOpen={() => addTrial('part-inspector')} />
      <AllDefects client={client} />
    </>
  );
```

- [ ] **Step 2: Typecheck**

Run: `cd lab && npm run typecheck`
Expected: no errors. If `FloatingPanel` does not take `onClose`, read its props
in `node_modules/@weasel-js/labkit/dist/index.d.ts` and pass what it does take
— the panel is a container, and only its dismissal wiring matters here.

- [ ] **Step 3: Commit**

```bash
git add lab/src/App.tsx && git commit -m "open the defect list from the title bar"
```

---

## Task 9: Generate the handoff's defect list

**Files:**
- Create: `scripts/defects-to-handoff.py`
- Test: `tests/test_defects_to_handoff.py`
- Modify: `HANDOFF.md`

- [ ] **Step 1: Write the failing test**

Create `tests/test_defects_to_handoff.py`:

```python
"""The handoff's defect list is generated, so it cannot disagree with the
store. A hand edit inside the markers is overwritten, which is the point."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import importlib
d2h = importlib.import_module("defects-to-handoff")

ONE = {
    "id": "3941-occt-borehole", "part": "3941", "engines": ["occt"],
    "status": "open", "title": "borehole rim not drawn",
    "mark": {"x": 0.4, "y": 0.5, "w": 0.1, "h": 0.1},
    "seen": {"angle": "30,25"}, "filed": "2026-08-31", "notes": "",
}

MARKED = """# Handoff

## Open

<!-- defects:begin -->
stale text
<!-- defects:end -->

## Traps
"""


def test_renders_a_defect_as_a_bullet():
    text = d2h.render([ONE])
    assert "**`3941`" in text
    assert "borehole rim not drawn" in text
    assert "occt" in text


def test_groups_by_status_with_open_first():
    fixed = {**ONE, "id": "x", "status": "fixed", "title": "done one"}
    text = d2h.render([fixed, ONE])
    assert text.index("borehole rim not drawn") < text.index("done one")


def test_omits_a_status_with_no_defects():
    assert "wontfix" not in d2h.render([ONE])


def test_says_so_when_there_are_none():
    assert "no defects" in d2h.render([]).lower()


def test_notes_are_carried_but_indented():
    text = d2h.render([{**ONE, "notes": "only at 30,25"}])
    assert "  only at 30,25" in text


def test_replaces_only_between_the_markers(tmp_path):
    path = tmp_path / "HANDOFF.md"
    path.write_text(MARKED)
    d2h.write_into(path, [ONE])
    got = path.read_text()
    assert "stale text" not in got
    assert got.startswith("# Handoff")
    assert "## Traps" in got
    assert "borehole rim not drawn" in got


def test_is_idempotent(tmp_path):
    path = tmp_path / "HANDOFF.md"
    path.write_text(MARKED)
    d2h.write_into(path, [ONE])
    once = path.read_text()
    d2h.write_into(path, [ONE])
    assert path.read_text() == once


def test_a_missing_begin_marker_is_an_error(tmp_path):
    path = tmp_path / "HANDOFF.md"
    path.write_text("# Handoff\n\nno markers here\n")
    with pytest.raises(SystemExit):
        d2h.write_into(path, [ONE])


def test_markers_out_of_order_is_an_error(tmp_path):
    path = tmp_path / "HANDOFF.md"
    path.write_text("<!-- defects:end -->\n<!-- defects:begin -->\n")
    with pytest.raises(SystemExit):
        d2h.write_into(path, [ONE])


def test_the_repo_handoff_has_the_markers():
    """The generator is useless against a handoff that never got them."""
    text = (Path(__file__).resolve().parent.parent / "HANDOFF.md").read_text()
    assert text.count("<!-- defects:begin -->") == 1
    assert text.count("<!-- defects:end -->") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_defects_to_handoff.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'defects-to-handoff'`

- [ ] **Step 3: Write the implementation**

Create `scripts/defects-to-handoff.py`:

```python
#!/usr/bin/env python3
"""Regenerate the handoff's defect list from tests/goldens/defects.toml.

    python scripts/defects-to-handoff.py

The list in HANDOFF.md is generated so that it cannot drift from the store the
lab writes. Everything between the markers is replaced; a hand edit inside them
is lost on the next run, which is why the store is the place to edit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from brick_icons.lab import defects  # noqa: E402

BEGIN = "<!-- defects:begin -->"
END = "<!-- defects:end -->"
HEADING = {"open": "Open", "fixed": "Fixed", "wontfix": "Won't fix",
           "notabug": "Not a bug"}


def _bullet(record: dict) -> str:
    engines = ", ".join(record.get("engines", [])) or "both"
    seen = record.get("seen", {})
    at = f" at `{seen['angle']}`" if seen.get("angle") else ""
    line = f"- **`{record['part']}`** ({engines}){at} — {record['title']}"
    notes = (record.get("notes") or "").strip()
    if notes:
        body = "\n".join(f"  {ln}" for ln in notes.splitlines())
        line = f"{line}\n{body}"
    return line


def render(records: list[dict]) -> str:
    if not records:
        return "No defects filed.\n"
    chunks = []
    for status in ("open", "fixed", "wontfix", "notabug"):
        rows = [r for r in records if r.get("status") == status]
        if not rows:
            continue
        rows.sort(key=lambda r: (r["part"], r["id"]))
        chunks.append(f"### {HEADING[status]}\n\n"
                      + "\n".join(_bullet(r) for r in rows) + "\n")
    return "\n".join(chunks)


def write_into(path: Path, records: list[dict]) -> None:
    text = path.read_text()
    start, end = text.find(BEGIN), text.find(END)
    if start < 0 or end < 0:
        raise SystemExit(f"{path}: missing {BEGIN} / {END} markers")
    if end < start:
        raise SystemExit(f"{path}: {END} appears before {BEGIN}")
    body = render(records)
    path.write_text(f"{text[:start + len(BEGIN)]}\n\n{body}\n{text[end:]}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="defects-to-handoff")
    p.add_argument("--defects", type=Path, default=Path("tests/goldens/defects.toml"))
    p.add_argument("--handoff", type=Path, default=Path("HANDOFF.md"))
    args = p.parse_args(argv)
    records = defects.load(args.defects)
    write_into(args.handoff, records)
    print(f"{args.handoff}: wrote {len(records)} defects", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add the markers to HANDOFF.md**

Find the `## Open` section of `HANDOFF.md`. Immediately under that heading,
insert:

```markdown
<!-- defects:begin -->
<!-- defects:end -->
```

Leave the prose already in that section above the markers — the generated list
is an addition to it, not a replacement for the narrative around it.

Do this with an editor or a Python script, **not** `sed -i`: `HANDOFF.md`
contains non-ASCII characters and macOS `sed` corrupts them.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_defects_to_handoff.py -v`
Expected: PASS, 10 tests

- [ ] **Step 6: Run the generator once**

Run: `.venv/bin/python scripts/defects-to-handoff.py`
Expected: `HANDOFF.md: wrote 0 defects` — the store is empty until defects are
filed, and the markers now bracket "No defects filed."

- [ ] **Step 7: Commit**

```bash
git add scripts/defects-to-handoff.py tests/test_defects_to_handoff.py HANDOFF.md
git commit -m "generate the handoff's defect list from the store"
```

---

## Task 10: See it work

**Files:** none — verification.

- [ ] **Step 1: Start both servers**

Run: `.venv/bin/python -m brick_icons.lab &` and, in `lab/`, `npm run dev`.

- [ ] **Step 2: File a defect**

Open the lab, search `3941`, wait for both panes, then drag a box over the
`occt` pane's axle hole. Confirm:

1. the dialog opens naming `3941`;
2. filing with a title writes to `tests/goldens/defects.toml` — check with
   `git diff tests/goldens/defects.toml`;
3. the mark redraws on the pane and stays put through a pan and a zoom;
4. the status bar reads `1 open / 1 filed`;
5. changing `--angle` dims the mark, because it was recorded at the old one.

- [ ] **Step 3: Check the generator against a real defect**

Run: `.venv/bin/python scripts/defects-to-handoff.py && git diff HANDOFF.md`
Expected: the defect appears as a bullet under `### Open`, between the markers.

- [ ] **Step 4: Decide what to keep**

The defect filed in step 2 is test data unless it is real. If it is not, delete
its entry from `tests/goldens/defects.toml`, re-run the generator, and check
`git status` is clean apart from intended changes.

- [ ] **Step 5: Stop the servers**

Run: `kill %1`; Ctrl-C the Vite server.

---

## Self-review notes

**Spec coverage.** Drag a box to file (Tasks 1, 4, 5, 7); fractional marks with
`seen` recorded and staleness shown (Tasks 1, 2, 4); the store as git-tracked
TOML (already built — this plan only calls it); the lab-level panel with
filters that opens a part (Tasks 6, 8); `scripts/defects-to-handoff.py`
(Task 9).

**Deliberately absent.** No delete route: `notabug` records that something was
looked at and dismissed, which is worth more than a row vanishing. No crop PNG
written to disk — the mark plus `seen` re-derives the view, and committed
binaries were the cost the spec declined.

**The judgement call in Task 2.** `seen` records `angle`, `shading` and
`shade_style` and not `--render-px`, because a fractional mark is invariant to
resolution but not to any of those three. If a future parameter moves geometry
on screen, it belongs in `SEEN_KEYS`, and a mark filed before that change will
read as fresh when it is not.
