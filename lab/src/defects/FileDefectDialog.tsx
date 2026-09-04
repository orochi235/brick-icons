import { useState } from 'react';
import type { Mark } from '@lab/defects/useDefects';
import '@lab/defects/FileDefectDialog.css';

export interface FileDefectDialogProps {
  part: string;
  mark: Mark;
  /** The engines whose panes are on screen. */
  engines: string[];
  onCancel: () => void;
  onFile: (fields: { title: string; notes: string; engines: string[] }) => void;
}

export function FileDefectDialog({ part, engines, onCancel, onFile }: FileDefectDialogProps) {
  const [title, setTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [checked, setChecked] = useState<string[]>(engines);

  const named = part.trim();
  const ready = named.length > 0 && title.trim().length > 0 && checked.length > 0;

  return (
    <div className="file-defect">
      <h3>{named ? `New defect on ${named}` : 'New defect'}</h3>
      {named ? null : (
        <p className="file-defect-blocked">
          Load a part first — a defect is stored under its part, and one filed
          without a part is never listed again.
        </p>
      )}
      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <fieldset>
        <legend>Engines</legend>
        {engines.map((engine) => (
          <label key={engine}>
            <input
              type="checkbox"
              checked={checked.includes(engine)}
              onChange={() => setChecked((prev) => prev.includes(engine)
                ? prev.filter((e) => e !== engine)
                : [...prev, engine])}
            />
            {engine}
          </label>
        ))}
      </fieldset>
      <label>
        Notes
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <div className="file-defect-actions">
        <button type="button" onClick={onCancel}>Cancel</button>
        <button
          type="button"
          disabled={!ready}
          onClick={() => {
            if (!ready) return;
            onFile({ title: title.trim(), notes, engines: [...checked].sort() });
          }}
        >
          File
        </button>
      </div>
    </div>
  );
}
