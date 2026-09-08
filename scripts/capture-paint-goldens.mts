import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { fileURLToPath, URL } from 'node:url';
import { paintCommands } from '@lab/corpus/paint';
import { scenarios } from '@lab/corpus/goldens.fixture';

const dir = fileURLToPath(new URL('../lab/src/corpus/goldens', import.meta.url));
rmSync(dir, { recursive: true, force: true });
mkdirSync(dir, { recursive: true });

const all = scenarios();
all.forEach(({ name, input }, i) => {
  const commands = JSON.parse(JSON.stringify(paintCommands(input)));
  writeFileSync(`${dir}/${name}.json`, `${JSON.stringify(commands, null, 2)}\n`);
  console.log(`${i + 1}/${all.length} ${name} — ${commands.length} commands`);
});
console.log(`wrote ${all.length} goldens to ${dir}`);
