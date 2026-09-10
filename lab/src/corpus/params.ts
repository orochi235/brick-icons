import type { ConfigField } from '@weasel-js/labkit';
import { STATES, kebabKey, paramKeys,
         type BorderedKey, type StateKey } from '@lab/corpus/states';

/** The params a color row writes as a CSS custom property on `.lk-root`
 *  instead of passing down as a prop -- see `useParams` and `palette.ts`'s
 *  `PARAM_CSS_VAR`. One per color a state declares, so a borderless state
 *  gets no border row; `caretColor` is chrome rather than a state. */
export type ColorParamKey =
  | `${StateKey}Fill`
  | `${BorderedKey}Border`
  | 'caretColor';

interface ColorRow {
  key: ColorParamKey;
  /** The state's own name, kebab-cased the way the CSS properties spell it. */
  name: string;
  kind: 'fill' | 'border';
  color: string;
}

/** Every color param of every state, in legend order, fill before border. */
function colorRows(): ColorRow[] {
  return STATES.flatMap((spec) => {
    const param = paramKeys(spec);
    const name = kebabKey(spec.key);
    const rows: ColorRow[] = [
      { key: param.fill as ColorParamKey, name, kind: 'fill', color: spec.fill },
    ];
    if (param.border !== null && spec.border !== null) {
      rows.push({ key: param.border as ColorParamKey, name, kind: 'border',
                  color: spec.border });
    }
    return rows;
  });
}

/** The wall's view parameters -- every tuning constant that governs layout,
 *  color or feel, and was a literal scattered across `CorpusWall.tsx`,
 *  `palette.ts`, `paint.ts`, `Wall.tsx`, `levels.ts` and `useCells.ts` until
 *  this schema existed. These are view parameters, not the CLI's render
 *  flags -- `lab/src/config/nodes.ts` is a different schema for a different
 *  world and this one never touches it. */
interface FixedParams {
  cell: number;
  gap: number;
  /** 0 means auto: `ceil(sqrt(n))`. */
  cols: number;

  showBadges: boolean;
  showCaptions: boolean;
  washRetired: boolean;

  thickBorderFactor: number;
  thinBorderFactor: number;
  maxBorderPx: number;
  dimAlpha: number;
  retiredWash: number;

  dragThresholdPx: number;
  /** Paint cell bodies with weasel's WebGL2 renderer instead of Canvas2D.
   *  The overlays stay on Canvas2D either way. Off by default: the renderer
   *  only wins against a weasel carrying the batch work, which no release
   *  does yet -- run the lab with `WEASEL_SRC` to get it. */
  sceneRenderer: boolean;
  levelUpHysteresis: number;
  levelDownHysteresis: number;
  pollMs: number;
}

/** The fixed fields stay a strict interface -- widening the whole shape to
 *  admit generated color keys would cost `params.cell` its `number`. */
export type Params = FixedParams & Record<ColorParamKey, string>;

const COLOR_DEFAULTS = Object.fromEntries([
  ...colorRows().map((row) => [row.key, row.color]),
  ['caretColor', '#ffffff'],
]) as Record<ColorParamKey, string>;

/**
 * What every field above used to be hard-coded to. The single source of
 * truth: every literal this schema replaces now imports its default from
 * here, and the fields below point back at these same values rather than
 * repeating the numbers a second time.
 */
export const DEFAULT_PARAMS: Params = {
  cell: 32,
  gap: 4,
  cols: 0,

  ...COLOR_DEFAULTS,

  showBadges: true,
  showCaptions: true,
  washRetired: false,

  thickBorderFactor: 0.18,
  thinBorderFactor: 0.09,
  maxBorderPx: 6,
  dimAlpha: 0.25,
  retiredWash: 0.75,

  dragThresholdPx: 4,
  sceneRenderer: false,
  levelUpHysteresis: 1.5,
  levelDownHysteresis: 0.67,
  pollMs: 10_000,
};

export const COLOR_PARAM_KEYS: readonly ColorParamKey[] =
  [...colorRows().map((row) => row.key), 'caretColor'];

const COLOR_LABEL = Object.fromEntries([
  ...colorRows().map((row) => [
    row.key, `${row.name.charAt(0).toUpperCase()}${row.name.slice(1)} ${row.kind}`,
  ]),
  ['caretColor', 'Caret color'],
]) as Record<ColorParamKey, string>;

/** The unit each numeric row shows after its value. A legacy `ConfigField`
 *  cannot carry one -- `ParamsPanel` resolves the fields and annotates them
 *  -- and the row reserves the space whether or not a unit is set, so a
 *  label spelling out `(px)` pays twice for it. */
export const PARAM_UNITS: Partial<Record<keyof Params, string>> = {
  cell: 'px',
  gap: 'px',
  maxBorderPx: 'px',
  dragThresholdPx: 'px',
  pollMs: 'ms',
};

export const LAYOUT_FIELDS: ConfigField[] = [
  { key: 'cell', label: 'Cell size', type: 'slider',
    default: DEFAULT_PARAMS.cell, min: 8, max: 128, step: 4 },
  { key: 'gap', label: 'Gap', type: 'slider',
    default: DEFAULT_PARAMS.gap, min: 0, max: 32, step: 1 },
  { key: 'cols', label: 'Columns (0 = auto)', type: 'number',
    default: DEFAULT_PARAMS.cols, min: 0, max: 64, step: 1 },
];

export const CELL_FIELDS: ConfigField[] = [
  { key: 'showBadges', label: 'Badges', type: 'checkbox',
    default: DEFAULT_PARAMS.showBadges },
  { key: 'showCaptions', label: 'Captions', type: 'checkbox',
    default: DEFAULT_PARAMS.showCaptions },
  { key: 'washRetired', label: 'Wash retired', type: 'checkbox',
    default: DEFAULT_PARAMS.washRetired },
];

export const APPEARANCE_FIELDS: ConfigField[] = [
  ...COLOR_PARAM_KEYS.map((key): ConfigField => ({
    key, label: COLOR_LABEL[key], type: 'color', default: DEFAULT_PARAMS[key],
  })),
  { key: 'thickBorderFactor', label: 'Thick border factor', type: 'slider',
    default: DEFAULT_PARAMS.thickBorderFactor, min: 0, max: 0.5, step: 0.01 },
  { key: 'thinBorderFactor', label: 'Thin border factor', type: 'slider',
    default: DEFAULT_PARAMS.thinBorderFactor, min: 0, max: 0.5, step: 0.01 },
  { key: 'maxBorderPx', label: 'Max border', type: 'slider',
    default: DEFAULT_PARAMS.maxBorderPx, min: 1, max: 20, step: 1 },
  { key: 'dimAlpha', label: 'Dim alpha', type: 'slider',
    default: DEFAULT_PARAMS.dimAlpha, min: 0, max: 1, step: 0.05 },
  { key: 'retiredWash', label: 'Retired wash strength', type: 'slider',
    default: DEFAULT_PARAMS.retiredWash, min: 0, max: 1, step: 0.05 },
];

export const FEEL_FIELDS: ConfigField[] = [
  { key: 'dragThresholdPx', label: 'Drag threshold', type: 'slider',
    default: DEFAULT_PARAMS.dragThresholdPx, min: 0, max: 20, step: 1 },
  { key: 'sceneRenderer', label: 'WebGL cell bodies', type: 'checkbox',
    default: DEFAULT_PARAMS.sceneRenderer },
  { key: 'levelUpHysteresis', label: 'Level-up hysteresis', type: 'slider',
    default: DEFAULT_PARAMS.levelUpHysteresis, min: 1, max: 3, step: 0.05 },
  { key: 'levelDownHysteresis', label: 'Level-down hysteresis', type: 'slider',
    default: DEFAULT_PARAMS.levelDownHysteresis, min: 0.3, max: 1, step: 0.01 },
  { key: 'pollMs', label: 'Poll interval', type: 'number',
    default: DEFAULT_PARAMS.pollMs, min: 1000, max: 60_000, step: 1000 },
];

export interface ParamGroup { label: string; fields: ConfigField[] }

export const PARAM_GROUPS: ParamGroup[] = [
  { label: 'Layout', fields: LAYOUT_FIELDS },
  { label: 'Cell', fields: CELL_FIELDS },
  { label: 'Appearance', fields: APPEARANCE_FIELDS },
  { label: 'Feel', fields: FEEL_FIELDS },
];

export const ALL_PARAM_FIELDS: ConfigField[] = PARAM_GROUPS.flatMap((g) => g.fields);
