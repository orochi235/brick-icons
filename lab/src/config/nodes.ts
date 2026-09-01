import { f } from '@weasel-js/labkit';
import type { SchemaField } from '@lab/api/types';
import { DEFAULT_SOURCES, type SourceId } from '@lab/panes/sources';

/** Flags that arrange a run rather than change what is drawn. They are the
 *  lab's own business: it decides where output goes and which part to draw. */
const PLUMBING = new Set(['out', 'root', 'config', 'list', 'debug_dir',
                          'list_colors', 'part_label']);

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

/** The lab's own fields, which no CLI flag corresponds to. Named once so
 *  `renderConfig` cannot forget one and send it to the CLI as a flag.
 *
 * `list` is the contact sheet's corpus list. The CLI does have a `--list`, but
 * it names a FILE of part ids -- so leaking this one through renders every
 * part with `--list manifest:spread` and fails the whole sheet with
 * `FileNotFoundError: 'manifest:spread'`. */
export const LAB_ONLY = new Set(['part', 'layout', 'sources', 'marking', 'list']);

/** How the panes are arranged. The lab's own flag, so unlike every other
 *  enum its values have no CLI `choices` to come from. */
export const LAYOUTS = ['grid', 'split', 'stack'] as const;

function labNodes() {
  return {
    layout: f.enum(LAYOUTS[0], [...LAYOUTS]).section('Panes'),
    sources: f.value<SourceId[]>([...DEFAULT_SOURCES]).section('Panes'),
    marking: f.boolean(false).section('Panes')
      .describe('A drag on a pane draws a defect mark instead of panning'),
  };
}

/** Which heading each flag lives under. A key absent here falls to `Other`,
 *  so a flag the CLI grows still appears -- just not filed. */
const SECTIONS: Record<string, string> = {
  engine: 'Render', shading: 'Render', shade_style: 'Render', angle: 'Render',
  wireframe: 'Render', weld_corners: 'Render', opacity: 'Render',
  part_color: 'Colour', light: 'Colour', svg_bg: 'Colour', mode: 'Colour',
  line_width: 'Strokes', silhouette_width: 'Strokes', line_mm: 'Strokes',
  silhouette_mm: 'Strokes',
  fmt: 'Output', render_px: 'Output', curve_quality: 'Output',
  scale: 'Output', scale_mode: 'Output', width: 'Output', height: 'Output',
  dpi: 'Output', margin: 'Output',
  dither: 'Bitmap', threshold: 'Bitmap', gamma: 'Bitmap', cel_levels: 'Bitmap',
  debug_colors: 'Debug',
};

const sectionOf = (key: string) => SECTIONS[key] ?? 'Other';

/** Apply the shared annotations every leaf gets.
 *
 * No `.pair()` here, though the couples are obvious (width/height,
 * dpi/margin): `ControlPanel` renders its leaves into a `PropertyList` at the
 * default `pack="auto-color"`, which pairs colour rows and nothing else, so a
 * pair annotation on any other kind is silently inert. */
function decorate<T extends { section: (s: string) => T; describe: (d: string) => T }>(
    node: T, field: SchemaField): T {
  return node.section(sectionOf(field.key)).describe(field.help);
}

export function buildSchema(fields: SchemaField[]) {
  const nodes: Record<string, unknown> = {};
  for (const field of fields) {
    if (!usable(field)) continue;
    if (field.choices && field.choices.length > 0) {
      const seed = typeof field.effective === 'string'
        && field.choices.includes(field.effective)
        ? field.effective : field.choices[0]!;
      nodes[field.key] = decorate(f.enum(seed, field.choices), field);
    } else if (field.type === 'bool') {
      nodes[field.key] = decorate(f.boolean(false), field);
    } else if (field.type === 'int' || field.type === 'float') {
      const seed = typeof field.effective === 'number' ? field.effective
        : (typeof field.default === 'number' ? field.default : 0);
      nodes[field.key] = decorate(f.number(seed), field);
    } else {
      const seed = typeof field.effective === 'string' ? field.effective
        : (typeof field.default === 'string' ? field.default : '');
      nodes[field.key] = decorate(f.string(seed), field);
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
  const out: Record<string, unknown> = { part: '', layout: 'grid',
                                         sources: [...DEFAULT_SOURCES],
                                         marking: false };
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
    if (LAB_ONLY.has(key)) continue;
    if (value === null || value === '') continue;
    out[key] = value;
  }
  return out;
}
