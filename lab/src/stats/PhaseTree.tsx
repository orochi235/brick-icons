import { useState } from 'react';
import type { PhaseNode } from '@lab/stats/types';

/** How deep the tree opens before a reader has to ask. Two levels is
 *  `render` and its stages; the engine's internals are a click away, so the
 *  common question -- which stage is slow -- is answered without one. */
export const OPEN_TO_DEPTH = 2;

/** Below this a row's bar is drawn but its label is not: at a few tenths of a
 *  percent the text is longer than the thing it describes. */
const LABEL_FLOOR = 3;

export function secs(v: number): string {
  if (v >= 3600) return `${(v / 3600).toFixed(1)}h`;
  if (v >= 60) return `${(v / 60).toFixed(0)}m`;
  if (v >= 1) return `${v.toFixed(1)}s`;
  return `${(v * 1000).toFixed(0)}ms`;
}

/** Every path in `nodes` whose depth is under `depth`, as the initial open
 *  set. Separate from the component so the default is testable without a
 *  render. */
export function openTo(nodes: PhaseNode[], depth = OPEN_TO_DEPTH): Set<string> {
  const open = new Set<string>();
  const walk = (list: PhaseNode[], at: number) => {
    for (const node of list) {
      if (at < depth && node.children.length > 0) open.add(node.path);
      walk(node.children, at + 1);
    }
  };
  walk(nodes, 0);
  return open;
}

/** `node`'s share of the whole tree, which is what makes two rows at
 *  different depths comparable. A share of the parent would draw every only
 *  child as a full bar. */
const share = (v: number, whole: number) => (whole > 0 ? (v / whole) * 100 : 0);

function Row({ node, whole, depth, open, toggle }: {
  node: PhaseNode;
  whole: number;
  depth: number;
  open: Set<string>;
  toggle: (path: string) => void;
}) {
  const expandable = node.children.length > 0;
  const shown = open.has(node.path);
  const width = share(node.secs, whole);
  const label = `${node.name} — ${secs(node.secs)}, ${width.toFixed(1)}% of the render`;

  return (
    <>
      <li className="stats-phase-row" data-depth={depth} data-rest={node.name === 'rest'}>
        <span className="stats-phase-name" style={{ paddingLeft: `${depth}rem` }}>
          {expandable ? (
            <button type="button" className="stats-phase-toggle"
                    aria-expanded={shown} onClick={() => toggle(node.path)}>
              <span aria-hidden="true">{shown ? '▾' : '▸'}</span> {node.name}
            </button>
          ) : <span className="stats-phase-leaf">{node.name}</span>}
        </span>
        <span className="stats-phase-secs">{secs(node.secs)}</span>
        <span className="stats-phase-bar" role="img" aria-label={label} title={label}>
          <span className="stats-phase-fill" style={{ width: `${width}%` }} />
        </span>
        <span className="stats-phase-pct">{width.toFixed(1)}%</span>
        <span className="stats-phase-n">
          {node.n === undefined ? '' : node.n.toLocaleString()}
        </span>
      </li>
      {shown && node.children.map((child) => (
        <Row key={child.path} node={child} whole={whole} depth={depth + 1}
             open={open} toggle={toggle} />
      ))}
    </>
  );
}

/** Where a render's seconds went, at whatever depth the engine named.
 *
 *  A node's time includes everything under it, so a row's bar is its share of
 *  the whole render rather than of its parent -- the only reading under which
 *  two rows at different depths mean the same thing. What a level does not
 *  name arrives from the server as a `rest` child, which is how an
 *  un-instrumented stage shows up as a gap instead of as nothing at all.
 */
export function PhaseTree({ nodes, caption }: {
  nodes: PhaseNode[];
  caption?: string;
}) {
  const [open, setOpen] = useState(() => openTo(nodes));
  if (nodes.length === 0) {
    return <p className="stats-empty">this row named no stages</p>;
  }
  const whole = nodes.reduce((a, n) => a + n.secs, 0);
  const toggle = (path: string) => setOpen((prev) => {
    const next = new Set(prev);
    if (!next.delete(path)) next.add(path);
    return next;
  });

  return (
    <figure className="stats-phase-tree">
      {caption && <figcaption className="stats-muted">{caption}</figcaption>}
      <ul className="stats-phase-rows">
        {nodes.map((node) => (
          <Row key={node.path} node={node} whole={whole} depth={0}
               open={open} toggle={toggle} />
        ))}
      </ul>
    </figure>
  );
}
