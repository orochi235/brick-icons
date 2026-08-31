import type { LabClient, PartHit } from '@lab/api/client';
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
 *  Each names a config key and the values it cycles between. */
export const QUICK_OPTIONS: { key: string; label: string; values: string[] }[] = [
  { key: 'engine', label: 'engine', values: ['naive', 'occt'] },
  { key: 'shading', label: 'shading', values: ['outline', 'cel', 'normal'] },
  { key: 'shade_style', label: 'fill', values: ['flat3', 'none'] },
  { key: 'layout', label: 'layout', values: ['split', 'stack'] },
];

export interface PoseBarProps {
  angle: string;
  config: Record<string, unknown>;
  setConfig: (key: string, value: unknown) => void;
}

export function PoseBar({ angle, config, setConfig }: PoseBarProps) {
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
      <div className="pose-bar-group" role="group" aria-label="Render options">
        {QUICK_OPTIONS.map((option) => (
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
