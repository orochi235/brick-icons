import { useState } from 'react';
import { ControlPanel, FloatingPanel } from '@weasel-js/labkit';
import { PARAM_GROUPS, type Params } from '@lab/corpus/params';
import '@lab/corpus/ParamsPanel.css';

export interface ParamsPanelProps {
  params: Params;
  setParam: <K extends keyof Params>(key: K, value: Params[K]) => void;
  reset: () => void;
}

/** The wall's tuning constants, in one floating panel -- built entirely from
 *  labkit's `ControlPanel`/`ConfigField` vocabulary, the same one `LabShell`
 *  already draws its own controls with. A color row's `setParam` still lands
 *  in `params`, for persistence and reset; `useParams` is what turns a color
 *  change into a CSS custom property, never a prop into the wall. */
export function ParamsPanel({ params, setParam, reset }: ParamsPanelProps) {
  const [open, setOpen] = useState(true);

  if (!open) return null;

  return (
    <FloatingPanel anchor="top-left" storageKey="brick-icons-lab.corpus-params-panel"
      className="corpus-params-panel">
      <div className="corpus-params-head">
        <strong>Params</strong>
        <div className="corpus-params-head-actions">
          <button type="button" onClick={reset}>Reset</button>
          <button type="button" aria-label="Close params" onClick={() => setOpen(false)}>
            x
          </button>
        </div>
      </div>
      <div className="corpus-params-body">
        {PARAM_GROUPS.map((group) => (
          <section key={group.label} className="corpus-params-group">
            <h3>{group.label}</h3>
            <ControlPanel
              fields={group.fields}
              config={params as unknown as Record<string, unknown>}
              setConfig={(key, value) => setParam(key as keyof Params, value as never)}
            />
          </section>
        ))}
      </div>
    </FloatingPanel>
  );
}
