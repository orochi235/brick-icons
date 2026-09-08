/// <reference types="vite/client" />
import { expect, it } from 'vitest';
import { paintCommands } from '@lab/corpus/paint';
import { scenarios } from '@lab/corpus/goldens.fixture';

// Read through Vite rather than `fs`: under vitest `import.meta.url` is an
// http URL, so a path derived from it is not a file path.
const captured = import.meta.glob<{ default: unknown }>('./goldens/*.json', { eager: true });

for (const { name, input } of scenarios()) {
  it(`paints ${name} as captured`, () => {
    const golden = captured[`./goldens/${name}.json`];
    expect(golden, `no golden for ${name}`).toBeDefined();
    // A command of kind `image` carries a live CanvasImageSource; only the
    // serialized form is comparable.
    expect(JSON.parse(JSON.stringify(paintCommands(input)))).toEqual(golden!.default);
  });
}
