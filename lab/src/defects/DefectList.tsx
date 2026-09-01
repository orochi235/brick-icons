import { useState } from 'react';
import { STATUSES, type Defect, type DefectStatus } from '@lab/defects/useDefects';
import '@lab/defects/DefectList.css';

const RANK: Record<DefectStatus, number> = { open: 0, wontfix: 1, fixed: 2, notabug: 3 };

export function sortDefects(defects: Defect[]): Defect[] {
  return [...defects].sort((a, b) =>
    RANK[a.status] - RANK[b.status]
    || a.part.localeCompare(b.part)
    || a.id.localeCompare(b.id));
}

export interface DefectListProps {
  defects: Defect[];
  onOpen: (part: string, defectId: string) => void;
  onStatus: (id: string, status: DefectStatus) => void;
}

export function DefectList({ defects, onOpen, onStatus }: DefectListProps) {
  const [filter, setFilter] = useState<'all' | DefectStatus>('all');
  const shown = sortDefects(defects)
    .filter((d) => filter === 'all' || d.status === filter);

  return (
    <div className="defect-list">
      <label>
        Status
        <select value={filter} onChange={(e) => setFilter(e.target.value as never)}>
          <option value="all">all</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      {shown.length === 0 ? <p className="defect-list-empty">no defects</p> : (
        <ul>
          {shown.map((d) => (
            <li key={d.id}>
              <span
                className="defect-row"
                role="button"
                tabIndex={0}
                // A span with role=button is not on the list of elements
                // `FloatingPanel` exempts from its own drag, so without this
                // the panel captures the pointer, mouseup retargets to it and
                // no click is ever synthesized here.
                data-no-drag=""
                onClick={() => onOpen(d.part, d.id)}
                onKeyDown={(e) => { if (e.key === 'Enter') onOpen(d.part, d.id); }}
              >
                <strong>{d.part}</strong> {d.title}
              </span>
              <select
                aria-label={`state of ${d.title}`}
                value={d.status}
                onChange={(e) => onStatus(d.id, e.target.value as DefectStatus)}
              >
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
