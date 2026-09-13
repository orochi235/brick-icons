import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { ControlPanel, f, resolveConfigSchema } from '@weasel-js/labkit';
import { buildSchema, defaultsFor } from '@lab/config/nodes';
import { rowsFor } from '@lab/config/rows';
import type { SchemaField } from '@lab/api/types';

const field = (over: Partial<SchemaField>): SchemaField => ({
  key: 'engine', flag: '--engine', type: 'str', choices: null,
  help: '', nargs: null, default: null, effective: null, ...over,
});

const FIELDS = [
  field({ key: 'engine', choices: ['naive', 'occt'], effective: 'occt' }),
  field({ key: 'line_width', type: 'int', effective: 2 }),
];

/** The panel has to survive every node `buildSchema` hands it.
 *
 *  `ControlPanel` sorts a node into a leaf or a group and has no third case:
 *  one with neither a kind nor children reaches `Object.keys(undefined)` and
 *  takes the whole page down, which is what a `f.value` node did -- its kind
 *  comes from the rule chain and nothing assigns `sources` one.
 */
describe('the lab config schema against labkit', () => {
  it('renders every node buildSchema produces', () => {
    const nodes = buildSchema(FIELDS);
    const schema = f.schema({ part: f.string(''), ...nodes } as never);
    const resolved = resolveConfigSchema(schema as never);
    expect(() => render(
      <ControlPanel
        schema={resolved as never}
        config={defaultsFor(FIELDS) as Record<string, unknown>}
        setConfig={() => {}}
        renderers={rowsFor({} as never)}
      />,
    )).not.toThrow();
  });
});
