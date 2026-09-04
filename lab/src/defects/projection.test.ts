import { describe, expect, it } from 'vitest';
import type { Annotation, AnnotationInit } from '@weasel-js/labkit';
import { defectToMarks, markToDefectFields, projectDefects,
  type MarkStore } from '@lab/defects/projection';
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

function fakeStore(existing: Annotation[] = []) {
  const added: { init: AnnotationInit; snapshot: unknown }[] = [];
  const removed: string[] = [];
  const store: MarkStore = {
    query: () => existing,
    add: (init, snapshot) => { added.push({ init, snapshot }); return init.target; },
    remove: (id) => { removed.push(id); },
  };
  return { store, added, removed };
}

const drawn = (over: Partial<Annotation>): Annotation => ({
  id: 'pane:naive/n1', target: 'pane:naive', kind: 'rect',
  frac: { x: 0, y: 0, w: 0.1, h: 0.1 }, ...over,
});

describe('projectDefects', () => {
  // The whole point of a snapshot: a mark remade under today's config matches
  // it by construction and can never be reported stale.
  it('dates a mark by the pose the defect was filed at', () => {
    const { store, added } = fakeStore();
    projectDefects(store, [defect({ seen: { angle: 'front' } })], ['pane:naive']);
    expect(added).toHaveLength(1);
    expect(added[0]!.snapshot).toEqual({ angle: 'front' });
  });

  it('replaces the marks it made before, and leaves a hand-drawn one alone', () => {
    const { store, removed } = fakeStore([
      drawn({ id: 'pane:naive/n1', meta: { defectId: '3001-naive-missing-edge' } }),
      drawn({ id: 'pane:naive/n2' }),
    ]);
    projectDefects(store, [], ['pane:naive']);
    expect(removed).toEqual(['pane:naive/n1']);
  });
});
