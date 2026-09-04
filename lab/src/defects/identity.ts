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
