import type { ConfigField } from '@weasel-js/labkit';

/** The wall's view parameters -- every tuning constant that governs layout,
 *  color or feel, and was a literal scattered across `CorpusWall.tsx`,
 *  `palette.ts`, `paint.ts`, `Wall.tsx`, `levels.ts` and `useCells.ts` until
 *  this schema existed. These are view parameters, not the CLI's render
 *  flags -- `lab/src/config/nodes.ts` is a different schema for a different
 *  world and this one never touches it. */
export interface Params {
  cell: number;
  gap: number;
  /** 0 means auto: `ceil(sqrt(n))`. */
  cols: number;

  unknownFill: string;
  timeoutFill: string;
  timeoutBorder: string;
  failedFill: string;
  failedBorder: string;
  defectFill: string;
  defectBorder: string;
  problemElsewhereFill: string;
  problemElsewhereBorder: string;
  defectElsewhereFill: string;
  defectElsewhereBorder: string;
  caretColor: string;

  thickBorderFactor: number;
  thinBorderFactor: number;
  maxBorderPx: number;
  dimAlpha: number;

  dragThresholdPx: number;
  levelUpHysteresis: number;
  levelDownHysteresis: number;
  pollMs: number;
}

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

  unknownFill: '#3a3a3f',
  timeoutFill: '#26383f',
  timeoutBorder: '#30b0d0',
  failedFill: '#4a2626',
  failedBorder: '#e03030',
  defectFill: '#453c27',
  defectBorder: '#daa520',
  problemElsewhereFill: '#26383f',
  problemElsewhereBorder: '#97bcc5',
  defectElsewhereFill: '#453c27',
  defectElsewhereBorder: '#c7b78f',
  caretColor: '#ffffff',

  thickBorderFactor: 0.18,
  thinBorderFactor: 0.09,
  maxBorderPx: 6,
  dimAlpha: 0.25,

  dragThresholdPx: 4,
  levelUpHysteresis: 1.5,
  levelDownHysteresis: 0.67,
  pollMs: 10_000,
};

/** The params a color row writes as a CSS custom property on `.lk-root`
 *  instead of passing down as a prop -- see `useParams` and `palette.ts`'s
 *  `PARAM_CSS_VAR`. */
export const COLOR_PARAM_KEYS = [
  'unknownFill', 'timeoutFill', 'timeoutBorder', 'failedFill', 'failedBorder',
  'defectFill', 'defectBorder', 'problemElsewhereFill', 'problemElsewhereBorder',
  'defectElsewhereFill', 'defectElsewhereBorder', 'caretColor',
] as const satisfies readonly (keyof Params)[];

export type ColorParamKey = (typeof COLOR_PARAM_KEYS)[number];

const COLOR_LABEL: Record<ColorParamKey, string> = {
  unknownFill: 'Unknown fill',
  timeoutFill: 'Timeout fill',
  timeoutBorder: 'Timeout border',
  failedFill: 'Failed fill',
  failedBorder: 'Failed border',
  defectFill: 'Defect fill',
  defectBorder: 'Defect border',
  problemElsewhereFill: 'Problem-elsewhere fill',
  problemElsewhereBorder: 'Problem-elsewhere border',
  defectElsewhereFill: 'Defect-elsewhere fill',
  defectElsewhereBorder: 'Defect-elsewhere border',
  caretColor: 'Caret color',
};

export const LAYOUT_FIELDS: ConfigField[] = [
  { key: 'cell', label: 'Cell size (px)', type: 'slider',
    default: DEFAULT_PARAMS.cell, min: 8, max: 128, step: 4 },
  { key: 'gap', label: 'Gap (px)', type: 'slider',
    default: DEFAULT_PARAMS.gap, min: 0, max: 32, step: 1 },
  { key: 'cols', label: 'Columns (0 = auto)', type: 'number',
    default: DEFAULT_PARAMS.cols, min: 0, max: 64, step: 1 },
];

export const APPEARANCE_FIELDS: ConfigField[] = [
  ...COLOR_PARAM_KEYS.map((key): ConfigField => ({
    key, label: COLOR_LABEL[key], type: 'color', default: DEFAULT_PARAMS[key],
  })),
  { key: 'thickBorderFactor', label: 'Thick border factor', type: 'slider',
    default: DEFAULT_PARAMS.thickBorderFactor, min: 0, max: 0.5, step: 0.01 },
  { key: 'thinBorderFactor', label: 'Thin border factor', type: 'slider',
    default: DEFAULT_PARAMS.thinBorderFactor, min: 0, max: 0.5, step: 0.01 },
  { key: 'maxBorderPx', label: 'Max border (px)', type: 'slider',
    default: DEFAULT_PARAMS.maxBorderPx, min: 1, max: 20, step: 1 },
  { key: 'dimAlpha', label: 'Dim alpha', type: 'slider',
    default: DEFAULT_PARAMS.dimAlpha, min: 0, max: 1, step: 0.05 },
];

export const FEEL_FIELDS: ConfigField[] = [
  { key: 'dragThresholdPx', label: 'Drag threshold (px)', type: 'slider',
    default: DEFAULT_PARAMS.dragThresholdPx, min: 0, max: 20, step: 1 },
  { key: 'levelUpHysteresis', label: 'Level-up hysteresis', type: 'slider',
    default: DEFAULT_PARAMS.levelUpHysteresis, min: 1, max: 3, step: 0.05 },
  { key: 'levelDownHysteresis', label: 'Level-down hysteresis', type: 'slider',
    default: DEFAULT_PARAMS.levelDownHysteresis, min: 0.3, max: 1, step: 0.01 },
  { key: 'pollMs', label: 'Poll interval (ms)', type: 'number',
    default: DEFAULT_PARAMS.pollMs, min: 1000, max: 60_000, step: 1000 },
];

export interface ParamGroup { label: string; fields: ConfigField[] }

export const PARAM_GROUPS: ParamGroup[] = [
  { label: 'Layout', fields: LAYOUT_FIELDS },
  { label: 'Appearance', fields: APPEARANCE_FIELDS },
  { label: 'Feel', fields: FEEL_FIELDS },
];

export const ALL_PARAM_FIELDS: ConfigField[] = PARAM_GROUPS.flatMap((g) => g.fields);
