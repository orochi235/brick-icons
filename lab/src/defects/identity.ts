/** The parameters a mark's position depends on. `--render-px` is absent on
 *  purpose: the mark is fractional, so resolution does not move it. */
const SEEN_KEYS = ['angle', 'shading', 'shade_style'] as const;

export type Seen = Partial<Record<(typeof SEEN_KEYS)[number], string>>;

export function slug(text: string, max = 40): string {
  const base = text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  if (base.length <= max) return base;
  const cut = base.slice(0, max);
  const boundary = cut.lastIndexOf('-');
  return (boundary > 0 ? cut.slice(0, boundary) : cut).replace(/-$/, '');
}

export function defectId(part: string, engines: string[], title: string,
                         existing: readonly string[],
                         allEngines: readonly string[] = []): string {
  const sorted = [...engines].sort();
  const named = allEngines.length > 0
    && sorted.length === allEngines.length
    && sorted.every((e) => allEngines.includes(e))
    ? 'both'
    : sorted.join('-');
  const base = [part, named, slug(title)].filter(Boolean).join('-');
  if (!existing.includes(base)) return base;
  let n = 2;
  while (existing.includes(`${base}-${n}`)) n += 1;
  return `${base}-${n}`;
}

export function seenFrom(config: Record<string, unknown>): Seen {
  const out: Seen = {};
  for (const key of SEEN_KEYS) {
    const value = config[key];
    if (typeof value === 'string' && value) out[key] = value;
  }
  return out;
}

/** Whether a defect's mark can be trusted against the render on screen. */
export function seenMatches(seen: Seen, config: Record<string, unknown>): boolean {
  return Object.entries(seen).every(([key, value]) => config[key] === value);
}
