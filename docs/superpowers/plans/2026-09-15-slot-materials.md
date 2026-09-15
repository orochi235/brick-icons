# Slot Materials Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every render slot a material, draw the lightbox's secs as material bars beside a shaded table, and order the lightbox's slots occt → naive → reference → others → decal.

**Architecture:** `lab/src/shared/materials.ts` holds the per-slot table, the chart order and an HLS `shade` helper. `lab/src/shared/MaterialBar.tsx` is the only thing that draws a material, as a small SVG at any size. `lab/src/corpus/Measurements.tsx` replaces the lightbox's Measurements table; `Lightbox.tsx` sorts its slots by chart order and puts a chip before each slot name.

**Tech Stack:** React 19, TypeScript, vitest + @testing-library/react (jsdom), plain CSS. Spec: `docs/superpowers/specs/2026-09-15-slot-materials-design.md`.

---

**Conventions for every task**

- Run commands from `lab/`. One test file: `npx vitest run <path>`. Never the whole suite while iterating.
- This checkout is shared with other sessions (`lab/src/wall/BrickWall.tsx` and `tests/goldens/defects.toml` carry someone else's uncommitted edits). Stage explicit paths only, then read `git diff --cached --stat` before committing; it must list only this task's files.
- Follow the `prepare-js-commit` skill before each commit.
- Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## File map

| file | change | responsibility |
|---|---|---|
| `lab/src/shared/materials.ts` | create | material table, fallback, `familyInk`, `CHART_ORDER`, `chartRank`, `shade` |
| `lab/src/shared/materials.test.ts` | create | |
| `lab/src/shared/MaterialBar.tsx` | create | draws one bar or chip: finishes, top face, timed-out outline |
| `lab/src/shared/MaterialBar.css` | create | |
| `lab/src/shared/MaterialBar.test.tsx` | create | |
| `lab/src/corpus/Measurements.tsx` | create | the Measurements section: cutoffs, `tier`, rows |
| `lab/src/corpus/Measurements.css` | create | |
| `lab/src/corpus/Measurements.test.tsx` | create | |
| `lab/src/corpus/Lightbox.tsx` | modify | use `Measurements`, sort slots, chip in tile names |
| `lab/src/corpus/Lightbox.css` | modify | tile name lays out chip + name |
| `lab/src/corpus/Lightbox.test.tsx` | modify | new slot order, formatted d99 |
| `lab/src/stats/charts.tsx` | modify | delete unused `SLOT_COLOR` |

---

### Task 1: Materials table, chart order, `shade`

**Files:**
- Create: `lab/src/shared/materials.ts`
- Test: `lab/src/shared/materials.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { expect, it } from 'vitest';
import { CHART_ORDER, chartRank, familyInk, materialOf, shade } from '@lab/shared/materials';

it('gives every family member its family color', () => {
  expect(materialOf('silhouette-occt').color).toBe(materialOf('occt').color);
  expect(materialOf('silhouette-naive').color).toBe(materialOf('naive').color);
  expect(materialOf('white-occt').stroke).toBe(materialOf('occt').color);
});

it('draws a slot it does not know as gray plastic', () => {
  expect(materialOf('ldview')).toEqual(
    { color: '#8A8C85', finish: 'solid', opacity: 1, stroke: '#000000' });
});

it('inks white with its stroke and everything else with its color', () => {
  expect(familyInk(materialOf('white-naive'))).toBe('#FE8A18');
  expect(familyInk(materialOf('silhouette-occt'))).toBe('#0055BF');
});

it('orders occt, naive, reference, the rest, then decal', () => {
  const shuffled = ['decal', 'white-naive', 'occt', 'mystery', 'reference',
                    'naive', 'translucent-occt'];
  expect([...shuffled].sort((a, b) => chartRank(a) - chartRank(b))).toEqual(
    ['occt', 'naive', 'reference', 'translucent-occt', 'white-naive', 'mystery', 'decal']);
  expect(CHART_ORDER.at(-1)).toBe('decal');
});

it('shifts HLS lightness and clamps it', () => {
  expect(shade('#0055BF', 0)).toBe('#0055bf');
  expect(shade('#808080', 1)).toBe('#ffffff');
  expect(shade('#808080', -1)).toBe('#000000');
  // Same answer as Python's colorsys, which the mockups were drawn with.
  expect(shade('#0055BF', 0.34)).toBe('#6daeff');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/shared/materials.test.ts`
Expected: FAIL, `Failed to resolve import "@lab/shared/materials"`.

- [ ] **Step 3: Write the implementation**

```ts
export type Finish = 'solid' | 'trans' | 'metallic' | 'print';

export interface Material {
  color: string;
  finish: Finish;
  opacity: number;
  /** A 1px outline, or none. */
  stroke: string | null;
}

const BLUE = '#0055BF';
const ORANGE = '#FE8A18';
const WHITE = '#F2F3F2';

/** Each material resembles the render setting its slot stands for. */
export const MATERIALS: Record<string, Material> = {
  'occt':              { color: BLUE,      finish: 'solid',    opacity: 1,    stroke: '#000000' },
  'white-occt':        { color: WHITE,     finish: 'solid',    opacity: 1,    stroke: BLUE },
  'silhouette-occt':   { color: BLUE,      finish: 'solid',    opacity: 1,    stroke: null },
  'translucent-occt':  { color: BLUE,      finish: 'trans',    opacity: 0.45, stroke: null },
  'naive':             { color: ORANGE,    finish: 'solid',    opacity: 1,    stroke: '#000000' },
  'white-naive':       { color: WHITE,     finish: 'solid',    opacity: 1,    stroke: ORANGE },
  'silhouette-naive':  { color: ORANGE,    finish: 'solid',    opacity: 1,    stroke: null },
  'translucent-naive': { color: '#FF8A00', finish: 'trans',    opacity: 0.7,  stroke: null },
  'reference':         { color: '#DBAC34', finish: 'metallic', opacity: 1,    stroke: '#000000' },
  'decal':             { color: '#C870A0', finish: 'print',    opacity: 1,    stroke: '#8E4570' },
};

const FALLBACK: Material = { color: '#8A8C85', finish: 'solid', opacity: 1, stroke: '#000000' };

export function materialOf(source: string): Material {
  return MATERIALS[source] ?? FALLBACK;
}

/** The one color that says which family a material belongs to. */
export function familyInk(material: Material): string {
  return material.color === WHITE && material.stroke ? material.stroke : material.color;
}

export const CHART_ORDER = [
  'occt', 'naive', 'reference',
  'translucent-occt', 'translucent-naive',
  'silhouette-occt', 'silhouette-naive',
  'white-occt', 'white-naive',
  'decal',
] as const;

/** A slot the order does not list sorts just before decal. */
export function chartRank(source: string): number {
  const i = (CHART_ORDER as readonly string[]).indexOf(source);
  return i === -1 ? CHART_ORDER.length - 1.5 : i;
}

/** `hex` with its HLS lightness moved by `amount`, clamped to [0, 1]. */
export function shade(hex: string, amount: number): string {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255) as
    [number, number, number];
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0;
  let s = 0;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    h /= 6;
  }
  const lit = Math.min(1, Math.max(0, l + amount));
  const channel = (p: number, q: number, t: number) => {
    const u = t < 0 ? t + 1 : t > 1 ? t - 1 : t;
    if (u < 1 / 6) return p + (q - p) * 6 * u;
    if (u < 1 / 2) return q;
    if (u < 2 / 3) return p + (q - p) * (2 / 3 - u) * 6;
    return p;
  };
  let rgb: number[];
  if (s === 0) {
    rgb = [lit, lit, lit];
  } else {
    const q = lit < 0.5 ? lit * (1 + s) : lit + s - lit * s;
    const p = 2 * lit - q;
    rgb = [channel(p, q, h + 1 / 3), channel(p, q, h), channel(p, q, h - 1 / 3)];
  }
  return `#${rgb.map((v) => Math.round(v * 255).toString(16).padStart(2, '0')).join('')}`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/shared/materials.test.ts`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/src/shared/materials.ts lab/src/shared/materials.test.ts
git diff --cached --stat
git commit -m "define a material and a chart position for every render slot"
```

---

### Task 2: `MaterialBar`

**Files:**
- Create: `lab/src/shared/MaterialBar.tsx`, `lab/src/shared/MaterialBar.css`
- Test: `lab/src/shared/MaterialBar.test.tsx`

Geometry, from the spec: the bar is seen slightly from above. A 3px top face sits over the front face; its far end steps in 2px; the near end is square. Everything is inset half a pixel so a 1px stroke is not clipped.

- [ ] **Step 1: Write the failing test**

```tsx
import { expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { MaterialBar } from '@lab/shared/MaterialBar';

const bar = (source: string, extra: Record<string, unknown> = {}) =>
  render(<MaterialBar source={source} width={120} height={18} {...extra} />).container;

it('draws a top face and a front face, outlined where the material has a stroke', () => {
  const svg = bar('occt');
  expect(svg.querySelectorAll('polygon')).toHaveLength(1);
  const front = svg.querySelector('rect')!;
  expect(front.getAttribute('stroke')).toBe('#000000');
  expect(front.getAttribute('fill')).toMatch(/^url\(#/);
});

it('leaves a silhouette unoutlined', () => {
  expect(bar('silhouette-occt').querySelector('rect')!.hasAttribute('stroke')).toBe(false);
});

it('gives translucent plastic a blurred highlight clipped to the front', () => {
  const svg = bar('translucent-naive');
  expect(svg.querySelector('filter feGaussianBlur')).not.toBeNull();
  expect(svg.querySelector('g[clip-path] g[filter]')?.querySelectorAll('rect')).toHaveLength(2);
});

it('hatches a print on both faces', () => {
  const groups = bar('decal').querySelectorAll('g[clip-path]');
  expect(groups).toHaveLength(2);
  groups.forEach((g) => expect(g.querySelectorAll('polygon').length).toBeGreaterThan(3));
});

it('draws a timed-out bar as a dashed outline with no fill', () => {
  const svg = bar('silhouette-naive', { timedOut: true });
  const dashed = svg.querySelector('g[stroke-dasharray]')!;
  expect(dashed.getAttribute('fill')).toBe('none');
  expect(dashed.getAttribute('stroke')).toBe('#FE8A18');
  expect(svg.querySelector('linearGradient')).toBeNull();
});

it('never lets two bars share a gradient, clip or filter id', () => {
  const { container } = render(
    <>
      <MaterialBar source="translucent-occt" width={80} height={18} />
      <MaterialBar source="translucent-occt" width={40} height={18} />
      <MaterialBar source="decal" width={80} height={18} />
      <MaterialBar source="decal" width={40} height={18} />
    </>);
  const ids = [...container.querySelectorAll('[id]')].map((el) => el.id);
  expect(new Set(ids).size).toBe(ids.length);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/shared/MaterialBar.test.tsx`
Expected: FAIL, `Failed to resolve import "@lab/shared/MaterialBar"`.

- [ ] **Step 3: Write the implementation**

`lab/src/shared/MaterialBar.css`:

```css
.material-bar {
  display: block;
  flex: none;
}
```

`lab/src/shared/MaterialBar.tsx`:

```tsx
import { useId, type ReactNode } from 'react';
import { familyInk, materialOf, shade, type Material } from '@lab/shared/materials';
import '@lab/shared/MaterialBar.css';

const LID = 3;
const STEP = 2;
const STRIPE_PERIOD = 16;
const STRIPE_WIDTH = 9;

type Stop = [offset: number, color: string, opacity: number];

function frontStops({ color, finish, opacity }: Material): Stop[] {
  if (finish === 'metallic') {
    return [[0, shade(color, 0.02), 1], [0.4, shade(color, 0.14), 1],
            [0.75, shade(color, -0.06), 1], [1, shade(color, -0.16), 1]];
  }
  if (finish === 'trans') {
    // Brightened by opacity, not lightness: lightening turns orange to cream.
    return [[0, shade(color, 0.04), opacity],
            [0.45, shade(color, 0.08), Math.min(1, opacity + 0.3)],
            [0.6, shade(color, 0.056), Math.min(1, opacity + 0.2)],
            [1, shade(color, -0.06), opacity]];
  }
  return [[0, shade(color, 0.08), opacity], [0.3, shade(color, 0.03), opacity],
          [0.6, color, opacity], [1, shade(color, -0.18), opacity]];
}

function Gradient({ id, stops }: { id: string; stops: Stop[] }) {
  return (
    <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
      {stops.map(([offset, color, opacity]) => (
        <stop key={offset} offset={offset} stopColor={color} stopOpacity={opacity} />
      ))}
    </linearGradient>
  );
}

export function MaterialBar({ source, width, height, timedOut = false }: {
  source: string;
  width: number;
  height: number;
  /** The run stopped at its time limit, so the length is a limit, not a cost. */
  timedOut?: boolean;
}) {
  const id = `mb${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;
  const material = materialOf(source);
  const x = 0.5;
  const y = 0.5;
  const w = Math.max(0, width - 1);
  const top = y + LID;
  const frontH = Math.max(0, height - 1 - LID);
  const step = Math.min(STEP, w / 4);
  const lid = `${x},${y} ${x + w - step},${y} ${x + w},${top} ${x},${top}`;
  const edge = material.stroke
    ? { stroke: material.stroke, strokeWidth: 1, strokeLinejoin: 'round' as const } : {};

  let body: ReactNode;
  if (timedOut) {
    body = (
      <g fill="none" stroke={familyInk(material)} strokeWidth={1.2} strokeDasharray="4 3">
        <polyline points={`${x},${y} ${x + w - step},${y} ${x + w},${top}`} />
        <rect x={x} y={top} width={w} height={frontH} />
      </g>
    );
  } else if (material.finish === 'print') {
    // Each top-face stripe starts where its front stripe meets the edge and
    // narrows with the face toward the far end.
    const ink = shade(material.color, 0.2);
    const back = (px: number) => x + (px - x) * (w ? (w - step) / w : 1);
    const front: ReactNode[] = [];
    const lidStripes: ReactNode[] = [];
    for (let x0 = x - Math.ceil(frontH / STRIPE_PERIOD + 1) * STRIPE_PERIOD;
         x0 < x + w + frontH; x0 += STRIPE_PERIOD) {
      const x1 = x0 + STRIPE_WIDTH;
      front.push(<polygon key={x0} points={
        `${x0},${top} ${x1},${top} ${x1 - frontH},${top + frontH} ${x0 - frontH},${top + frontH}`} />);
      lidStripes.push(<polygon key={x0} points={
        `${x0},${top} ${x1},${top} ${back(x1)},${y} ${back(x0)},${y}`} />);
    }
    body = (
      <>
        <defs>
          <clipPath id={`${id}-front`}><rect x={x} y={top} width={w} height={frontH} /></clipPath>
          <clipPath id={`${id}-lid`}><polygon points={lid} /></clipPath>
        </defs>
        <polygon points={lid} fill="#ffffff" />
        <rect x={x} y={top} width={w} height={frontH} fill="#ffffff" />
        <g clipPath={`url(#${id}-front)`} fill={ink}>{front}</g>
        <g clipPath={`url(#${id}-lid)`} fill={ink}>{lidStripes}</g>
        <polygon points={lid} fill="none" {...edge} />
        <rect x={x} y={top} width={w} height={frontH} fill="none" {...edge} />
      </>
    );
  } else {
    const trans = material.finish === 'trans';
    const pad = Math.min(4, w / 6);
    body = (
      <>
        <defs>
          <Gradient id={`${id}-fill`} stops={frontStops(material)} />
          {trans && (
            <>
              <Gradient id={`${id}-wash`} stops={
                [[0, '#ffffff', 0.75], [0.25, '#ffffff', 0.35], [1, '#ffffff', 0]]} />
              <Gradient id={`${id}-glow`} stops={[[0, shade(material.color, 0.3), 0],
                [0.6, shade(material.color, 0.3), 0.55], [1, shade(material.color, 0.3), 0]]} />
              <filter id={`${id}-soft`} x="-10%" y="-60%" width="120%" height="220%">
                <feGaussianBlur stdDeviation={1.4} />
              </filter>
              <clipPath id={`${id}-clip`}>
                <rect x={x} y={top} width={w} height={frontH} />
              </clipPath>
            </>
          )}
        </defs>
        <polygon points={lid} fill={shade(material.color, 0.34)}
                 fillOpacity={material.opacity} {...edge} />
        <rect x={x} y={top} width={w} height={frontH} fill={`url(#${id}-fill)`} {...edge} />
        {trans && (
          // Runs off the near end: the bar grows out of its axis, so that end
          // has no edge to show.
          <g clipPath={`url(#${id}-clip)`}>
            <g filter={`url(#${id}-soft)`}>
              <rect x={x - 6} y={top + 1} width={Math.max(0, w + 6 - pad)}
                    height={frontH * 0.6} fill={`url(#${id}-wash)`} />
              <rect x={x - 6} y={top + frontH * 0.55} width={Math.max(0, w + 6 - pad * 1.6)}
                    height={frontH * 0.38} fill={`url(#${id}-glow)`} />
            </g>
            <line x1={x} y1={top + 2} x2={x + w - pad} y2={top + 2} stroke="#ffffff"
                  strokeOpacity={0.6} strokeWidth={0.8} strokeLinecap="round" />
          </g>
        )}
      </>
    );
  }

  return (
    <svg className="material-bar" width={width} height={height}
         viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      {body}
    </svg>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/shared/MaterialBar.test.tsx`
Expected: PASS, 6 tests.

- [ ] **Step 5: Typecheck**

Run: `npm run typecheck`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add lab/src/shared/MaterialBar.tsx lab/src/shared/MaterialBar.css lab/src/shared/MaterialBar.test.tsx
git diff --cached --stat
git commit -m "draw a render slot's material as a bar or a chip"
```

---

### Task 3: The Measurements section

**Files:**
- Create: `lab/src/corpus/Measurements.tsx`, `lab/src/corpus/Measurements.css`
- Test: `lab/src/corpus/Measurements.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { Measurements, tier } from '@lab/corpus/Measurements';

const finding = (source: string, extra: Record<string, unknown> = {}) => ({
  part_id: '4449-f1', engine: source.endsWith('naive') ? 'naive' : 'occt', source,
  extra_d99: 1.01, missing_px: 0, missing_comps: 0, secs: 30, error: null, ...extra,
});

const rowsOf = (container: HTMLElement) =>
  [...container.querySelectorAll('tbody tr')].map((tr) => tr.getAttribute('data-slot'));

it('orders rows occt, naive, reference, the rest, then decal', () => {
  const { container } = render(<Measurements findings={[
    finding('decal'), finding('white-naive'), finding('occt'),
    finding('reference'), finding('naive')]} />);
  expect(rowsOf(container)).toEqual(['occt', 'naive', 'reference', 'white-naive', 'decal']);
});

it('names a row by engine when an older API sends no source', () => {
  const { container } = render(<Measurements findings={[
    { ...finding('naive'), source: undefined }]} />);
  expect(rowsOf(container)).toEqual(['naive']);
});

it('marks a value at the corpus p90 warm and at p99 hot', () => {
  expect(tier('extra_d99', 1.40)).toBeUndefined();
  expect(tier('extra_d99', 1.41)).toBe('warm');
  expect(tier('extra_d99', 7.44)).toBe('hot');
  expect(tier('missing_comps', 0)).toBeUndefined();
  expect(tier('missing_comps', 1)).toBe('warm');
  expect(tier('missing_px', 61026)).toBe('hot');
  expect(tier('missing_px', null)).toBeUndefined();
});

it('shades the cells that are remarkable, and only those', () => {
  const { container } = render(<Measurements findings={[
    finding('occt', { missing_px: 2927, missing_comps: 6 })]} />);
  const tiers = [...container.querySelectorAll('tbody td.corpus-measure-num')]
    .map((td) => td.getAttribute('data-tier'));
  expect(tiers).toEqual([null, 'warm', 'hot']);
  expect(container.textContent).toContain('2,927');
});

it('says what stopped a slot across the three number cells', () => {
  const { container } = render(<Measurements findings={[
    finding('occt', { extra_d99: null, missing_px: null, missing_comps: null,
                      error: 'OCCError' })]} />);
  const cell = container.querySelector('td.corpus-measure-error')!;
  expect(cell.getAttribute('colspan')).toBe('3');
  expect(cell.textContent).toBe('OCCError');
});

it('scales secs to the slowest slot and puts the value right after the bar', () => {
  const { container } = render(<Measurements findings={[
    finding('occt', { secs: 30 }), finding('naive', { secs: 120 })]} />);
  const widths = [...container.querySelectorAll('.corpus-measure-bar .material-bar')]
    .map((svg) => Number(svg.getAttribute('width')));
  expect(widths).toEqual([75, 300]);
  expect(container.querySelector('.corpus-measure-bar .material-bar + .corpus-measure-value')
    ?.textContent).toBe('30.0s');
});

it('draws a timeout as a dashed bar with its value dimmed', () => {
  const { container } = render(<Measurements findings={[
    finding('silhouette-occt', { secs: 120.1, error: 'TimeoutError' })]} />);
  expect(container.querySelector('.corpus-measure-bar g[stroke-dasharray]')).not.toBeNull();
  expect(container.querySelector('.corpus-measure-value')?.hasAttribute('data-timed-out'))
    .toBe(true);
});

it('puts a chip before each slot name', () => {
  const { container } = render(<Measurements findings={[finding('reference')]} />);
  const label = container.querySelector('tbody th .corpus-chip-label')!;
  expect(label.firstElementChild?.classList.contains('material-bar')).toBe(true);
  expect(label.textContent).toBe('reference');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/corpus/Measurements.test.tsx`
Expected: FAIL, `Failed to resolve import "@lab/corpus/Measurements"`.

- [ ] **Step 3: Write the implementation**

`lab/src/corpus/Measurements.css`:

```css
.corpus-measures {
  border-collapse: collapse;
  font-family: var(--wzl-font-ui);
  font-variant-numeric: tabular-nums;
}

.corpus-lightbox .corpus-measures th,
.corpus-lightbox .corpus-measures td {
  padding: 0.05rem 0.35rem;
  height: 1.5rem;
}

.corpus-measures thead th {
  vertical-align: bottom;
  line-height: 1.15;
}

.corpus-lightbox .corpus-measures .corpus-measure-num {
  min-width: 3.2em;
  text-align: right;
}
.corpus-measures thead .corpus-measure-num { max-width: 4.6em; }

/* Light cells on the dark panel, so the number on them is near-black. */
.corpus-measure-num[data-tier='warm'] { background: #f6dfa6; color: #1a1a1a; }
.corpus-measure-num[data-tier='hot'] { background: #e8998d; color: #1a1a1a; font-weight: 700; }

.corpus-measure-slot { font-weight: 400; }
.corpus-chip-label {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
}
.corpus-chip-label .material-bar { margin-top: 0.2em; }

.corpus-measure-error { color: var(--corpus-cell-failed-border, #e03030); }

.corpus-measure-bar {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.corpus-measure-value[data-timed-out] { color: var(--wzl-fg-muted); }
```

`lab/src/corpus/Measurements.tsx`:

```tsx
import type { PartDetail } from '@lab/corpus/types';
import { MaterialBar } from '@lab/shared/MaterialBar';
import { chartRank } from '@lab/shared/materials';
import '@lab/corpus/Measurements.css';

type Finding = PartDetail['findings'][number];
type Measure = 'extra_d99' | 'missing_px' | 'missing_comps';

// Latest measurement per part and slot in corpus.db, 2026-09-15.
export const CUTOFFS: Record<Measure, readonly [p90: number, p99: number]> = {
  extra_d99: [1.41, 7.44],
  missing_px: [724, 61026],
  missing_comps: [1, 6],
};

export function tier(measure: Measure, value: number | null | undefined):
    'warm' | 'hot' | undefined {
  if (value == null) return undefined;
  const [p90, p99] = CUTOFFS[measure];
  return value >= p99 ? 'hot' : value >= p90 ? 'warm' : undefined;
}

const COLUMNS: { key: Measure; label: string; format: (v: number) => string }[] = [
  { key: 'extra_d99', label: 'extra d99', format: (v) => v.toFixed(2) },
  { key: 'missing_px', label: 'missing px', format: (v) => v.toLocaleString('en-US') },
  { key: 'missing_comps', label: 'missing comps', format: (v) => String(v) },
];

const TRACK = 300;
const CHIP = { width: 34, height: 14 };

const slotOf = (f: Finding) => f.source ?? f.engine;

export function Measurements({ findings }: { findings: Finding[] }) {
  const rows = [...findings].sort((a, b) => chartRank(slotOf(a)) - chartRank(slotOf(b)));
  const slowest = Math.max(0, ...rows.map((f) => f.secs ?? 0)) || 1;
  return (
    <table className="corpus-measures">
      <thead>
        <tr>
          <th><span className="corpus-visually-hidden">slot</span></th>
          {COLUMNS.map((c) => <th key={c.key} className="corpus-measure-num">{c.label}</th>)}
          <th>secs</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((f) => {
          const slot = slotOf(f);
          const timedOut = /timeout/i.test(f.error ?? '');
          return (
            <tr key={slot} data-slot={slot}>
              <th scope="row" className="corpus-measure-slot">
                <span className="corpus-chip-label">
                  <MaterialBar source={slot} {...CHIP} />{slot}
                </span>
              </th>
              {f.error ? (
                <td colSpan={COLUMNS.length} className="corpus-measure-error">{f.error}</td>
              ) : COLUMNS.map((c) => {
                const value = f[c.key];
                return (
                  <td key={c.key} className="corpus-measure-num" data-tier={tier(c.key, value)}>
                    {value == null ? '—' : c.format(value)}
                  </td>
                );
              })}
              <td>
                <span className="corpus-measure-bar">
                  {f.secs != null && (
                    <MaterialBar source={slot} width={Math.max(3, (f.secs / slowest) * TRACK)}
                                 height={18} timedOut={timedOut} />
                  )}
                  <span className="corpus-measure-value" data-timed-out={timedOut || undefined}>
                    {f.secs == null ? '—' : `${f.secs.toFixed(1)}s`}
                  </span>
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/corpus/Measurements.test.tsx`
Expected: PASS, 8 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/src/corpus/Measurements.tsx lab/src/corpus/Measurements.css lab/src/corpus/Measurements.test.tsx
git diff --cached --stat
git commit -m "draw a part's render times as material bars beside its shaded measurements"
```

---

### Task 4: Wire it into the lightbox

**Files:**
- Modify: `lab/src/corpus/Lightbox.tsx` (imports; `slots` at ~line 128; slot name at ~line 280; Measurements table at ~lines 336-354)
- Modify: `lab/src/corpus/Lightbox.css:108`
- Test: `lab/src/corpus/Lightbox.test.tsx`

- [ ] **Step 1: Update the tests to the new order and format**

In `lab/src/corpus/Lightbox.test.tsx`:

The first test, `shows the part title and the part as every slot drew it`:

```tsx
  expect(srcs).toEqual([
    '/api/corpus/render/naive/3001.svg?v=deadbeef',
    '/api/corpus/render/silhouette-occt/3001.svg?v=cafebabe',
  ]);
```

`lists each engine measurement`:

```tsx
it('lists each engine measurement', async () => {
  render(box());
  await waitFor(() => screen.getByText('1.50'));
});
```

`names each slot on its own row, so the decal one can be grounded differently`:

```tsx
  expect(sources).toEqual(['naive', 'silhouette-occt', 'decal']);
```

`does not offer a slot with nothing to draw for this part`:

```tsx
  expect(screen.getAllByRole('radio').map((r) => r.getAttribute('aria-label')))
    .toEqual(['naive', 'silhouette-occt']);
```

`keeps the slot you arrived on, even where it does not apply`:

```tsx
  expect(screen.getAllByRole('radio').map((r) => r.getAttribute('aria-label')))
    .toEqual(['naive', 'silhouette-occt', 'decal']);
```

Add a test after `lists each engine measurement`:

```tsx
it('puts a material chip before each slot name', async () => {
  render(box());
  await screen.findByRole('radio', { name: 'naive' });
  const names = [...document.querySelectorAll('.corpus-slot-name')];
  expect(names.map((el) => el.firstElementChild?.classList.contains('material-bar')))
    .toEqual([true, true]);
  expect(names.map((el) => el.textContent)).toEqual(['naive', 'silhouette-occt']);
});
```

- [ ] **Step 2: Run the file to verify the changed tests fail**

Run: `npx vitest run src/corpus/Lightbox.test.tsx`
Expected: FAIL in exactly the six tests edited or added above; every other test passes.

- [ ] **Step 3: Change `Lightbox.tsx`**

Add to the imports, beside the other `@lab/corpus` ones:

```tsx
import { Measurements } from '@lab/corpus/Measurements';
import { MaterialBar } from '@lab/shared/MaterialBar';
import { chartRank } from '@lab/shared/materials';
```

Replace the `slots` declaration:

```tsx
  const slots = (detail?.slots ?? [])
    .filter((slot) => !slot.not_applicable || slot.source === shown)
    .sort((a, b) => chartRank(a.source) - chartRank(b.source));
```

Replace the slot name span inside the tile label:

```tsx
                  <span className="corpus-slot-name">
                    <MaterialBar source={slot.source} width={34} height={14} />
                    {slot.source}
                  </span>
```

Replace the Measurements table (from `<table>` through its `</table>`, keeping the `<h3>Measurements</h3>` above it):

```tsx
          <Measurements findings={detail.findings} />
```

- [ ] **Step 4: Change `Lightbox.css`**

Replace line 108, `.corpus-slot-name { color: var(--wzl-fg-muted); }`, with:

```css
/* Top-aligned, so a name that wraps keeps its chip on the first line. */
.corpus-slot-name {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  color: var(--wzl-fg-muted);
  font-family: var(--wzl-font-ui);
}
.corpus-slot-name .material-bar { margin-top: 0.2em; }
```

- [ ] **Step 5: Run the file to verify it passes**

Run: `npx vitest run src/corpus/Lightbox.test.tsx src/corpus/Measurements.test.tsx`
Expected: PASS, all tests in both files.

- [ ] **Step 6: Typecheck**

Run: `npm run typecheck`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add lab/src/corpus/Lightbox.tsx lab/src/corpus/Lightbox.css lab/src/corpus/Lightbox.test.tsx
git diff --cached --stat
git commit -m "order the lightbox's slots occt first and decal last, each with its material"
```

---

### Task 5: Delete the unused `SLOT_COLOR`

**Files:**
- Modify: `lab/src/stats/charts.tsx:452-469`

- [ ] **Step 1: Confirm nothing reads it**

Run: `grep -rn "SLOT_COLOR" src`
Expected: one hit, its definition in `src/stats/charts.tsx`.

- [ ] **Step 2: Delete it**

Replace the comment and both constants:

```tsx
/** The slots the failure chart follows, in a fixed order, each keeping its hue
 *  however many are on screen. Color follows the SLOT, never its rank: a
 *  filter that drops one must not repaint the others.
 *
 *  Categorical, not the status palette above -- these say which slot, not how
 *  bad, and `--stats-failed` red is reserved for the state. Dark steps of the
 *  default eight-hue theme; validated against this page's sunken surface, all
 *  six checks pass (worst adjacent CVD dE 8.4, normal-vision 19.3). */
export const SLOT_ORDER = ['occt', 'white-occt', 'silhouette-occt',
                           'translucent-occt', 'decal'] as const;

export const SLOT_COLOR: Record<string, string> = {
  'occt': '#3987e5',
  'white-occt': '#d95926',
  'silhouette-occt': '#199e70',
  'translucent-occt': '#c98500',
  'decal': '#d55181',
};
```

with:

```tsx
/** The slots the failure chart follows, in a fixed order. Each line's hue is
 *  `--slot-<name>` in stats.css, keyed by slot and never by rank, so a filter
 *  that drops one must not repaint the others. Not the slot materials: three
 *  occt slots share one material color, and this chart needs a hue apiece. */
export const SLOT_ORDER = ['occt', 'white-occt', 'silhouette-occt',
                           'translucent-occt', 'decal'] as const;
```

- [ ] **Step 3: Run the stats tests that cover this file, and typecheck**

Run: `npx vitest run src/stats/StatsPage.test.tsx && npm run typecheck`
Expected: PASS, no type errors.

- [ ] **Step 4: Commit**

```bash
git add lab/src/stats/charts.tsx
git diff --cached --stat
git commit -m "remove SLOT_COLOR, which nothing read"
```

---

### Task 6: Look at it

**Files:** none changed unless the render shows a fault.

- [ ] **Step 1: Make sure the lab API and dev server are up**

Run: `curl -s -o /dev/null -m 5 -w 'api %{http_code}\n' http://localhost:5178/api/corpus/part/4449-f1; curl -s -o /dev/null -m 5 -w 'ui %{http_code}\n' http://localhost:5178/corpus`
Expected: `api 200` and `ui 200`. Probe a real endpoint, not `/`: the lab serves nothing at its root, so `/` answers 404 and a `curl -sf` check there reports the API down while it is running. If the API really is down, start it from the repo root with `.venv/bin/python -m brick_icons.lab` in the background; if the UI is down, run `npm run dev` in `lab/` in the background. Check `lsof -nP -iTCP:8792 -sTCP:LISTEN` before starting one — another session may already be running it.

- [ ] **Step 2: Screenshot the lightbox on two parts, headless**

```bash
for part in 4449-f1 30298; do
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu \
    --hide-scrollbars --virtual-time-budget=10000 --force-device-scale-factor=2 \
    --window-size=1400,2200 --screenshot="$TMPDIR/lightbox-$part.png" \
    "http://localhost:5178/corpus#part=$part&source=occt"
done
```

Between them the two parts hit both shading tiers, a timeout in each family, and every material but decal.

- [ ] **Step 3: Read both screenshots and check against the spec**

Check each of these by eye, and fix any that fail before going on:
- tiles and rows run naive-before-silhouette, occt first, decal (if present) last
- each tile name and each row has a chip before it, top-aligned
- the timed-out row shows a dashed outline in its family color, value dimmed
- warm and hot cells are shaded; 4449-f1's translucent-occt missing comps (6) is hot
- secs values sit just past each bar's end
- translucent bars read as orange and blue on the dark panel
- all table text is in the theme font

- [ ] **Step 4: Put the result on the wall**

Run: `~/src/slopboard/bin/slop "$TMPDIR/lightbox-4449-f1.png" && ~/src/slopboard/bin/slop "$TMPDIR/lightbox-30298.png"`

- [ ] **Step 5: Mark the spec built**

In `docs/superpowers/specs/2026-09-15-slot-materials-design.md`, replace `**Status: designed 2026-09-15, not built.**` with `**Status: built 2026-09-15.**`, then:

```bash
git add docs/superpowers/specs/2026-09-15-slot-materials-design.md
git diff --cached --stat
git commit -m "mark the slot materials design built"
```
