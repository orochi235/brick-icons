import type { Grouping } from '@lab/corpus/facts';
import { CLASS_LABEL, CLASSES, FILTERS, SORTS, type Selection } from '@lab/corpus/select';
import { TINT_MODES } from '@lab/corpus/tint';
import '@lab/corpus/Sidebar.css';

const GROUPINGS: { id: Grouping; label: string }[] = [
  { id: 'none', label: 'nothing' },
  { id: 'coverage', label: 'coverage' },
  { id: 'category', label: 'category' },
  { id: 'release', label: 'release year' },
];

export function Sidebar({ selection, counts, shown, total, onChange }: {
  selection: Selection;
  counts: Map<string, number>;
  shown: number;
  total: number;
  onChange: (next: Selection) => void;
}) {
  const off = new Set(selection.excluded);
  const ordered = [...counts.keys()].sort(
    (a, b) => (counts.get(b) ?? 0) - (counts.get(a) ?? 0) || a.localeCompare(b));

  const toggle = (name: string) => {
    const next = new Set(off);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChange({ ...selection, excluded: ordered.filter((c) => next.has(c)) });
  };

  return (
    <aside className="corpus-side">
      <label>Group
        <select value={selection.grouping}
                onChange={(e) => onChange({ ...selection,
                                            grouping: e.target.value as Grouping })}>
          {GROUPINGS.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
        </select>
      </label>

      {selection.grouping === 'release' && (
        <label className="corpus-side__check">
          <input type="checkbox" checked={selection.desc}
                 onChange={(e) => onChange({ ...selection, desc: e.target.checked })} />
          Newest first
        </label>
      )}

      <label>Order
        <select value={selection.sort}
                onChange={(e) => onChange({ ...selection,
                                            sort: e.target.value as Selection['sort'] })}>
          {SORTS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>

      <label>Color
        <select value={selection.tint}
                onChange={(e) => onChange({ ...selection,
                                            tint: e.target.value as Selection['tint'] })}>
          {TINT_MODES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </label>

      <label>Show
        <select value={selection.filter}
                onChange={(e) => onChange({ ...selection,
                                            filter: e.target.value as Selection['filter'] })}>
          {FILTERS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </label>

      <h3>
        Categories
        <button type="button" onClick={() => onChange({ ...selection, excluded: [] })}>all</button>
        <button type="button"
                onClick={() => onChange({ ...selection, excluded: ordered })}>none</button>
      </h3>
      <ul className="corpus-side__facets">
        {ordered.map((name) => (
          <li key={name}>
            <label>
              <input type="checkbox" name={name} checked={!off.has(name)}
                     onChange={() => toggle(name)} />
              <span>{name}</span>
              <em>{(counts.get(name) ?? 0).toLocaleString()}</em>
            </label>
          </li>
        ))}
      </ul>

      <h3>Classes</h3>
      <ul className="corpus-side__facets">
        {CLASSES.map((cls) => (
          <li key={cls}>
            <label>
              <input type="checkbox" name={cls} checked={selection.shown[cls]}
                     onChange={(e) => onChange({
                       ...selection,
                       shown: { ...selection.shown, [cls]: e.target.checked },
                     })} />
              <span>{CLASS_LABEL[cls]}</span>
            </label>
          </li>
        ))}
      </ul>

      <p className="corpus-side__count">{shown} of {total}</p>
    </aside>
  );
}
