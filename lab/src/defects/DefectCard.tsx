import { STATUSES, type Defect, type DefectStatus } from '@lab/defects/useDefects';
import '@lab/defects/DefectCard.css';

export interface DefectCardProps {
  defect: Defect;
  onStatus: (id: string, status: DefectStatus) => void;
  onClose: () => void;
}

/** What one mark stands for, shown when its box is clicked. */
export function DefectCard({ defect, onStatus, onClose }: DefectCardProps) {
  const seen = Object.entries(defect.seen).map(([k, v]) => `${k} ${v}`).join(', ');

  return (
    <div className="defect-card">
      <div className="defect-card-head">
        <span className="defect-card-title">{defect.title}</span>
        <button type="button" aria-label="Close defect" onClick={onClose}>×</button>
      </div>
      <span className="defect-card-meta">
        {defect.engines.join(', ')} · filed {defect.filed}{seen ? ` · seen at ${seen}` : ''}
      </span>
      {defect.notes ? <p className="defect-card-notes">{defect.notes}</p> : null}
      <label>
        Status
        <select
          value={defect.status}
          onChange={(e) => onStatus(defect.id, e.target.value as DefectStatus)}
        >
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
    </div>
  );
}
