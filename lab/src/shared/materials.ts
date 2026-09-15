export type Finish = 'solid' | 'trans' | 'metallic' | 'print';

export interface Material {
  color: string;
  finish: Finish;
  opacity: number;
  /** A 1px outline, or none. */
  stroke: string | null;
}

const BLUE = '#0055BF';
const ORANGE = '#FE8A18';
const WHITE = '#F2F3F2';

/** Each material resembles the render setting its slot stands for. */
export const MATERIALS: Record<string, Material> = {
  'occt':              { color: BLUE,      finish: 'solid',    opacity: 1,    stroke: '#000000' },
  'white-occt':        { color: WHITE,     finish: 'solid',    opacity: 1,    stroke: BLUE },
  'silhouette-occt':   { color: BLUE,      finish: 'solid',    opacity: 1,    stroke: null },
  'translucent-occt':  { color: BLUE,      finish: 'trans',    opacity: 0.45, stroke: null },
  'naive':             { color: ORANGE,    finish: 'solid',    opacity: 1,    stroke: '#000000' },
  'white-naive':       { color: WHITE,     finish: 'solid',    opacity: 1,    stroke: ORANGE },
  'silhouette-naive':  { color: ORANGE,    finish: 'solid',    opacity: 1,    stroke: null },
  'translucent-naive': { color: '#FF8A00', finish: 'trans',    opacity: 0.7,  stroke: null },
  'reference':         { color: '#DBAC34', finish: 'metallic', opacity: 1,    stroke: '#000000' },
  'decal':             { color: '#C870A0', finish: 'print',    opacity: 1,    stroke: '#8E4570' },
};

const FALLBACK: Material = { color: '#8A8C85', finish: 'solid', opacity: 1, stroke: '#000000' };

export function materialOf(source: string): Material {
  return MATERIALS[source] ?? FALLBACK;
}

/** The one color that says which family a material belongs to. */
export function familyInk(material: Material): string {
  return material.color === WHITE && material.stroke ? material.stroke : material.color;
}

export const CHART_ORDER = [
  'occt', 'naive', 'reference',
  'translucent-occt', 'translucent-naive',
  'silhouette-occt', 'silhouette-naive',
  'white-occt', 'white-naive',
  'decal',
] as const;

/** A slot the order does not list sorts just before decal. */
export function chartRank(source: string): number {
  const i = (CHART_ORDER as readonly string[]).indexOf(source);
  return i === -1 ? CHART_ORDER.length - 1.5 : i;
}

/** `hex` with its HLS lightness moved by `amount`, clamped to [0, 1]. */
export function shade(hex: string, amount: number): string {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255) as
    [number, number, number];
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0;
  let s = 0;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    h /= 6;
  }
  const lit = Math.min(1, Math.max(0, l + amount));
  const channel = (p: number, q: number, t: number) => {
    const u = t < 0 ? t + 1 : t > 1 ? t - 1 : t;
    if (u < 1 / 6) return p + (q - p) * 6 * u;
    if (u < 1 / 2) return q;
    if (u < 2 / 3) return p + (q - p) * (2 / 3 - u) * 6;
    return p;
  };
  let rgb: number[];
  if (s === 0) {
    rgb = [lit, lit, lit];
  } else {
    const q = lit < 0.5 ? lit * (1 + s) : lit + s - lit * s;
    const p = 2 * lit - q;
    rgb = [channel(p, q, h + 1 / 3), channel(p, q, h), channel(p, q, h - 1 / 3)];
  }
  return `#${rgb.map((v) => Math.round(v * 255).toString(16).padStart(2, '0')).join('')}`;
}
