import '@lab/corpus/FilterBar.css';

export function FilterBar({ sources, source, onSource }: {
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
    </div>
  );
}
