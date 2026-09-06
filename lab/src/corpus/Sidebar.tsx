import { useState } from 'react';
import type { Grouping } from '@lab/corpus/facts';
import { familyFacets, type Family, type FamilyFacet } from '@lab/corpus/families';
import { CLASS_LABEL, CLASSES, FILTERS, SORTS, type Selection } from '@lab/corpus/select';
import { TINT_MODES } from '@lab/corpus/tint';
import '@lab/corpus/Sidebar.css';

const GROUPINGS: { id: Grouping; label: string }[] = [
  { id: 'none', label: 'nothing' },
  { id: 'coverage', label: 'coverage' },
  { id: 'category', label: 'category' },
  { id: 'release', label: 'release year' },
];

/** A box that is neither on nor off, which HTML can only be told through the
 *  DOM node -- there is no attribute for it. */
function triState(on: boolean, partly: boolean) {
  return (node: HTMLInputElement | null) => {
    if (node) node.indeterminate = partly && !on;
  };
}

function FamilyRow({ facet, off, open, onOpen, onToggle }: {
  facet: FamilyFacet;
  off: ReadonlySet<string>;
  open: boolean;
  onOpen: () => void;
  onToggle: () => void;
}) {
  const anyOn = facet.members.some((m) => !off.has(m.name));
  const allOn = facet.members.every((m) => !off.has(m.name));
  return (
    <div className="corpus-side__fam">
      <button type="button" className="corpus-side__twisty" aria-expanded={open}
              aria-label={`${facet.family} categories`} onClick={onOpen}>
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
          <path d="M4 2.5 L8.5 6 L4 9.5 Z" />
        </svg>
      </button>
      <label>
        <input type="checkbox" name={facet.family} checked={allOn}
               ref={triState(allOn, anyOn)} onChange={onToggle} />
        <span>{facet.family}</span>
        <em>{facet.total.toLocaleString()}</em>
      </label>
    </div>
  );
}

export function Sidebar({ selection, counts, shown, total, onChange }: {
  selection: Selection;
  counts: Map<string, number>;
  shown: number;
  total: number;
  onChange: (next: Selection) => void;
}) {
  const [open, setOpen] = useState<ReadonlySet<Family>>(new Set());
  const off = new Set(selection.excluded);
  const facets = familyFacets(counts);
  // One canonical order for `excluded`, so the same set of cleared boxes
  // always writes the same list and the URL does not churn.
  const ordered = facets.flatMap((f) => f.members.map((m) => m.name));

  const exclude = (next: Set<string>) =>
    onChange({ ...selection, excluded: ordered.filter((c) => next.has(c)) });

  const toggleCategory = (name: string) => {
    const next = new Set(off);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    exclude(next);
  };

  // A family box clears the whole family unless it is already clear, which is
  // the only reading under which one click always changes something.
  const toggleFamily = (facet: FamilyFacet) => {
    const next = new Set(off);
    const anyOn = facet.members.some((m) => !next.has(m.name));
    for (const m of facet.members) {
      if (anyOn) next.add(m.name);
      else next.delete(m.name);
    }
    exclude(next);
  };

  const toggleOpen = (family: Family) => setOpen((was) => {
    const next = new Set(was);
    if (next.has(family)) next.delete(family);
    else next.add(family);
    return next;
  });

  return (
    <aside className="corpus-side">
      <label className="corpus-side__row">Group
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

      <label className="corpus-side__row">Order
        <select value={selection.sort}
                onChange={(e) => onChange({ ...selection,
                                            sort: e.target.value as Selection['sort'] })}>
          {SORTS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>

      <label className="corpus-side__row">Color
        <select value={selection.tint}
                onChange={(e) => onChange({ ...selection,
                                            tint: e.target.value as Selection['tint'] })}>
          {TINT_MODES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </label>

      <label className="corpus-side__row">Show
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
        {facets.map((facet) => (
          <li key={facet.family}>
            <FamilyRow facet={facet} off={off} open={open.has(facet.family)}
                       onOpen={() => toggleOpen(facet.family)}
                       onToggle={() => toggleFamily(facet)} />
            {open.has(facet.family) && (
              <ul className="corpus-side__members">
                {facet.members.map((m) => (
                  <li key={m.name}>
                    <label>
                      <input type="checkbox" name={m.name} checked={!off.has(m.name)}
                             onChange={() => toggleCategory(m.name)} />
                      <span>{m.name}</span>
                      <em>{m.n.toLocaleString()}</em>
                    </label>
                  </li>
                ))}
              </ul>
            )}
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
