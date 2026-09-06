import { useMemo } from 'react';
import { ControlPanel, fromConfigFields } from '@weasel-js/labkit';
import { PARAM_GROUPS, PARAM_UNITS, type Params } from '@lab/corpus/params';
import '@lab/corpus/ParamsPanel.css';

export interface ParamsPanelProps {
  params: Params;
  setParam: <K extends keyof Params>(key: K, value: Params[K]) => void;
  reset: () => void;
}

/** The wall's tuning constants, built entirely from labkit's
 *  `ControlPanel`/`ConfigField` vocabulary -- the same one `LabShell` already
 *  draws its own controls with. It sits in the sidebar beside the filters
 *  rather than floating over the wall, which is the thing it is tuning.
 *
 *  A color row's `setParam` still lands in `params`, for persistence and
 *  reset; `useParams` is what turns a color change into a CSS custom
 *  property, never a prop into the wall. */
export function ParamsPanel({ params, setParam, reset }: ParamsPanelProps) {
  // Resolved rather than handed over as `fields`, because that is the only
  // shape that carries a unit: `fromConfigFields` drops anything a legacy
  // `ConfigField` cannot express, and the row draws `suffix` as its unit.
  const schemas = useMemo(() => PARAM_GROUPS.map((group) => {
    const schema = fromConfigFields(group.fields);
    for (const [key, unit] of Object.entries(PARAM_UNITS)) {
      const leaf = schema.group.children[key] as { suffix?: string } | undefined;
      if (leaf) leaf.suffix = unit;
    }
    return { label: group.label, schema };
  }), []);

  return (
    <div className="corpus-params-panel">
      <h3>
        Params
        <button type="button" onClick={reset}>reset</button>
      </h3>
      <div className="corpus-params-body">
        {schemas.map(({ label, schema }) => (
          <section key={label} className="corpus-params-group">
            <h4>{label}</h4>
            <ControlPanel
              schema={schema}
              config={params as unknown as Record<string, unknown>}
              setConfig={(key, value) => setParam(key as keyof Params, value as never)}
            />
          </section>
        ))}
      </div>
    </div>
  );
}
