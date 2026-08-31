import { f } from '@weasel-js/labkit';
import type { SchemaField } from '@lab/api/types';

/** Flags that arrange a run rather than change what is drawn. They are the
 *  lab's own business: it decides where output goes and which part to draw. */
const PLUMBING = new Set(['out', 'root', 'config', 'list', 'debug_dir',
                          'list_colors', 'part_label']);

export const SOURCE_IDS = ['naive', 'occt', 'reference', '3d', 'diff'] as const;
export type SourceId = (typeof SOURCE_IDS)[number];

export const RENDER_KEYS = {
  has(key: string) {
    return !PLUMBING.has(key);
  },
};

function usable(field: SchemaField): boolean {
  // A multi-value flag has no single control, and none of them change what the
  // drawing shows -- they are page geometry.
  return RENDER_KEYS.has(field.key) && field.nargs === null;
}

/** The lab's own fields, which no CLI flag corresponds to. */
function labNodes() {
  return {
    layout: f.enum('split', ['split', 'stack']),
    sources: f.value<SourceId[]>(['naive', 'occt']),
  };
}

export function buildSchema(fields: SchemaField[]) {
  const nodes: Record<string, unknown> = {};
  for (const field of fields) {
    if (!usable(field)) continue;
    if (field.choices && field.choices.length > 0) {
      const seed = typeof field.effective === 'string'
        && field.choices.includes(field.effective)
        ? field.effective : field.choices[0]!;
      nodes[field.key] = f.enum(seed, field.choices);
    } else if (field.type === 'bool') {
      nodes[field.key] = f.boolean(false);
    } else if (field.type === 'int' || field.type === 'float') {
      const seed = typeof field.effective === 'number' ? field.effective
        : (typeof field.default === 'number' ? field.default : 0);
      nodes[field.key] = f.number(seed);
    } else {
      const seed = typeof field.effective === 'string' ? field.effective
        : (typeof field.default === 'string' ? field.default : '');
      nodes[field.key] = f.string(seed);
    }
  }
  return { ...nodes, ...labNodes() } as Record<string, unknown>;
}

/** What the lab opens on, over and above the CLI's own defaults.
 *
 * A pane displays the render's SVG, and the CLI's default is a PNG with no
 * hidden-line pass -- so at the CLI's defaults every pane is empty and the
 * lab looks broken. These three flags are the lab's opinion about what it is
 * for, and they show in the command line like any other choice.
 */
export const OPENING_COMBO: Record<string, unknown> = {
  fmt: 'svg',
  shading: 'outline',
  shade_style: 'flat3',
};

export function defaultsFor(fields: SchemaField[]): Record<string, unknown> {
  const out: Record<string, unknown> = { part: '', layout: 'split',
                                         sources: ['naive', 'occt'] };
  for (const field of fields) {
    if (!usable(field)) continue;
    // `effective` is what labels.toml resolved to; argparse's own default is
    // None for nearly every flag, and guessing from `choices` puts the lab on
    // settings the CLI would never use.
    if (field.effective === false && field.type !== 'bool') {
      // A non-switch flag whose resolved value is `false` means "off", not the
      // string "False": `--debug-colors False` is a parse error, and the whole
      // render fails on a flag nobody asked for.
      out[field.key] = null;
    } else if (field.effective !== null && field.effective !== undefined) {
      out[field.key] = field.effective;
    } else if (field.default !== null && field.default !== undefined) {
      out[field.key] = field.default;
    } else if (field.type === 'bool') {
      out[field.key] = false;
    } else {
      out[field.key] = null;
    }
  }
  return { ...out, ...OPENING_COMBO };
}

/** The subset of a trial's config that is a CLI flag: what goes to the server
 *  as `config`. A null means "leave it to labels.toml". */
export function renderConfig(config: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(config)) {
    if (key === 'part' || key === 'layout' || key === 'sources') continue;
    if (value === null || value === '') continue;
    out[key] = value;
  }
  return out;
}
