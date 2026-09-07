import { expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { OPEN_TO_DEPTH, PhaseTree, openTo, secs } from '@lab/stats/PhaseTree';
import type { PhaseNode } from '@lab/stats/types';

const node = (name: string, path: string, s: number,
              children: PhaseNode[] = [], n?: number): PhaseNode =>
  ({ name, path, secs: s, children, ...(n === undefined ? {} : { n }) });

const TREE: PhaseNode[] = [
  node('render', 'render', 10, [
    node('geometry', 'render/geometry', 8, [
      node('engine', 'render/geometry/engine', 6, [
        node('hlr', 'render/geometry/engine/hlr', 5),
      ]),
      node('flatten', 'render/geometry/flatten', 2),
    ]),
    node('rest', 'render/rest', 2),
  ]),
];

it('opens far enough to show which stage is slow, and no further', () => {
  render(<PhaseTree nodes={TREE} />);
  expect(screen.getByText('geometry')).toBeTruthy();
  // `engine` is at depth 2, so it is a row; `hlr` beneath it is not yet.
  expect(screen.getByText('engine')).toBeTruthy();
  expect(screen.queryByText('hlr')).toBeNull();
});

it('opens a deeper level when its row is clicked, and closes it again', () => {
  render(<PhaseTree nodes={TREE} />);
  fireEvent.click(screen.getByRole('button', { name: /engine/ }));
  expect(screen.getByText('hlr')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /engine/ }));
  expect(screen.queryByText('hlr')).toBeNull();
});

it('measures every row against the whole render, not against its parent', () => {
  // engine is 6 of the 10s render. Against its parent it would read 75% and
  // a lone child would always draw a full bar.
  render(<PhaseTree nodes={TREE} />);
  expect(screen.getByTitle(/engine — 6.0s, 60.0%/)).toBeTruthy();
  expect(screen.getByTitle(/geometry — 8.0s, 80.0%/)).toBeTruthy();
});

it('marks the unnamed leftover so it does not read as a stage', () => {
  render(<PhaseTree nodes={TREE} />);
  const rest = document.querySelector('[data-rest="true"]')!;
  expect(rest.textContent).toContain('rest');
});

it('gives a node with children a control and a leaf none', () => {
  render(<PhaseTree nodes={TREE} />);
  expect(screen.queryByRole('button', { name: /rest/ })).toBeNull();
  expect(screen.getByRole('button', { name: /geometry/ })).toBeTruthy();
});

it('says how many parts reached a stage when the tree is a summed one', () => {
  render(<PhaseTree nodes={[node('render', 'render', 10, [
    node('geometry', 'render/geometry', 8, [], 40)], 100)]} />);
  expect(screen.getByText('100')).toBeTruthy();
  expect(screen.getByText('40')).toBeTruthy();
});

it('says so rather than drawing an empty figure', () => {
  render(<PhaseTree nodes={[]} />);
  expect(screen.getByText(/named no stages/)).toBeTruthy();
});

it('opens only nodes that have something under them', () => {
  const open = openTo(TREE, OPEN_TO_DEPTH);
  expect(open.has('render')).toBe(true);
  expect(open.has('render/geometry')).toBe(true);
  expect(open.has('render/rest')).toBe(false);
  expect(open.has('render/geometry/engine')).toBe(false);
});

it('scales a duration to the unit that keeps it readable', () => {
  expect(secs(0.004)).toBe('4ms');
  expect(secs(1.13)).toBe('1.1s');
  expect(secs(90)).toBe('2m');
  expect(secs(7200)).toBe('2.0h');
});
