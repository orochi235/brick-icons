import type { LabClient, PartHit, SchemaField } from '@lab/api/client';
import { LAYOUTS } from '@lab/config/nodes';
import { SOURCE_ORDER } from '@lab/panes/sources';
import { useEffect, useState } from 'react';

/** The `--angle` presets `brick_icons/render.py` names, in a viewing order
 *  rather than its declaration order. `iso` first because it is the default. */
export const POSES: { id: string; label: string }[] = [
  { id: 'iso', label: 'iso' },
  { id: 'front', label: 'front' },
  { id: 'back', label: 'back' },
  { id: 'left', label: 'left' },
  { id: 'right', label: 'right' },
  { id: 'top', label: 'top' },
  { id: 'bottom', label: 'bottom' },
];

/** Render options worth a click, rather than a trip into the settings panel.
 *  Each names a config key; the values it cycles between are the CLI's own
 *  `choices`, so a flag that grows a value grows this control too. */
const QUICK_KEYS: { key: string; label: string; values?: readonly string[] }[] = [
  { key: 'engine', label: 'engine' },
  { key: 'shading', label: 'shading' },
  { key: 'shade_style', label: 'fill' },
  { key: 'layout', label: 'layout', values: LAYOUTS },
];

export interface QuickOption { key: string; label: string; values: readonly string[] }

/** A key the CLI no longer offers drops its control rather than drawing an
 *  empty select. */
export function quickOptions(fields: SchemaField[]): QuickOption[] {
  const choices = new Map(fields.map((field) => [field.key, field.choices ?? []]));
  return QUICK_KEYS
    .map(({ key, label, values }) =>
      ({ key, label, values: values ?? choices.get(key) ?? [] }))
    .filter((option) => option.values.length > 0);
}

export interface PoseBarProps {
  angle: string;
  config: Record<string, unknown>;
  fields: SchemaField[];
  setConfig: (key: string, value: unknown) => void;
}

export function PoseBar({ angle, config, fields, setConfig }: PoseBarProps) {
  const sources = (config.sources as string[]) ?? [];
  const toggle = (id: string) => setConfig('sources',
    sources.includes(id) ? sources.filter((s) => s !== id) : [...sources, id]);

  return (
    <div className="pose-bar">
      <div className="pose-bar-group" role="group" aria-label="Pose">
        {POSES.map((pose) => (
          <button
            key={pose.id}
            type="button"
            className={angle === pose.id ? 'pose is-on' : 'pose'}
            aria-pressed={angle === pose.id}
            onClick={() => setConfig('angle', pose.id)}
          >
            {pose.label}
          </button>
        ))}
      </div>
      <div className="pose-bar-group" role="group" aria-label="Panes">
        {SOURCE_ORDER.map((source) => (
          <button
            key={source.id}
            type="button"
            className={sources.includes(source.id) ? 'pose is-on' : 'pose'}
            aria-pressed={sources.includes(source.id)}
            onClick={() => toggle(source.id)}
          >
            {source.label}
          </button>
        ))}
      </div>
      <div className="pose-bar-group" role="group" aria-label="Defects">
        <button
          type="button"
          className={config.marking ? 'pose is-on' : 'pose'}
          aria-pressed={Boolean(config.marking)}
          title="Drag on a pane to mark a defect. Off, a drag pans."
          onClick={() => setConfig('marking', !config.marking)}
        >
          mark
        </button>
      </div>
      <div className="pose-bar-group" role="group" aria-label="Render options">
        {quickOptions(fields).map((option) => (
          <label key={option.key} className="quick-option">
            <span>{option.label}</span>
            <select
              value={String(config[option.key] ?? option.values[0])}
              onChange={(e) => setConfig(option.key, e.target.value)}
            >
              {option.values.map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
          </label>
        ))}
      </div>
    </div>
  );
}

/** `<part id> - <description>`, for the trial's title bar. Falls back to the
 *  bare id while the lookup is in flight or when the part is not in the
 *  library, so the title never reads as empty. */
export function PartTitle({ client, part }: { client: LabClient; part: string }) {
  const [name, setName] = useState('');

  useEffect(() => {
    if (!part.trim()) {
      setName('');
      return;
    }
    let live = true;
    client.searchParts(part, 5)
      .then((hits: PartHit[]) => {
        const exact = hits.find((h) => h.id === part);
        if (live) setName(exact?.description ?? '');
      })
      .catch(() => { if (live) setName(''); });
    return () => { live = false; };
  }, [client, part]);

  if (!part.trim()) return <span className="part-title">no part</span>;
  return <span className="part-title">{name ? `${part} - ${name}` : part}</span>;
}
