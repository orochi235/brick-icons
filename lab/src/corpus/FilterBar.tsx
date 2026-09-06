import { CLASS_LABEL, CLASSES, FILTERS, SORTS, type Selection } from '@lab/corpus/select';
import '@lab/corpus/FilterBar.css';

export function FilterBar({ selection, onChange, shown, total,
                            sources, source, onSource }: {
  selection: Selection;
  onChange: (next: Selection) => void;
  shown: number;
  total: number;
  sources: { source: string; n: number }[];
  source: string;
  onSource: (next: string) => void;
}) {
  return (
    <div className="corpus-bar">
      <label>
        Slot
        <select value={source} onChange={(e) => onSource(e.target.value)}>
          {sources.map((s) => (
            <option key={s.source} value={s.source}>{s.source} ({s.n})</option>
          ))}
        </select>
      </label>
      <label>
        Sort
        <select value={selection.sort}
                onChange={(e) => onChange({ ...selection,
                                            sort: e.target.value as Selection['sort'] })}>
          {SORTS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      <label>
        Show
        <select value={selection.filter}
                onChange={(e) => onChange({ ...selection,
                                            filter: e.target.value as Selection['filter'] })}>
          {FILTERS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </label>
      {CLASSES.map((cls) => (
        <label key={cls} className="corpus-bar-check">
          <input type="checkbox" checked={selection.shown[cls]}
                 onChange={(e) => onChange({
                   ...selection,
                   shown: { ...selection.shown, [cls]: e.target.checked },
                 })} />
          {CLASS_LABEL[cls]}
        </label>
      ))}
      <span className="corpus-count">{shown} of {total}</span>
    </div>
  );
}
