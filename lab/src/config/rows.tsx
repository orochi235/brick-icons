import { PropertyRow } from '@weasel-js/labkit';
import type { ControlRenderer } from '@weasel-js/labkit';

/**
 * Compact rows for the settings panel.
 *
 * `ControlPanel` draws every leaf as a `PropertyRow` at its default
 * `layout="block"` — label stacked above control — and exposes no way to ask
 * for `layout="inline"`. With 38 CLI flags that is a very long panel, so these
 * re-declare one row per leaf kind with the label beside the control instead.
 *
 * They are keyed by kind rather than by config path, so a flag the CLI grows
 * picks up the compact row without being named here. Delete the lot if labkit
 * gains a density option on `ControlPanel`.
 */

/** What a resolved leaf carries that a row needs. `ToolPrefLeaf` is a union
 *  over every kind; a renderer registered for one kind knows its own shape. */
interface Leaf {
  label?: string;
  description?: string;
  options?: readonly { value: string; label?: string }[];
  min?: number;
  max?: number;
  step?: number;
}

const leafOf = (pref: unknown): Leaf => (pref ?? {}) as Leaf;

const numberRow: ControlRenderer = ({ path, pref, value, setValue }) => {
  const leaf = leafOf(pref);
  return (
    <PropertyRow layout="inline" label={leaf.label ?? path} description={leaf.description}>
      <input
        className="row-input"
        type="number"
        value={value === null || value === undefined ? '' : String(value)}
        min={leaf.min}
        max={leaf.max}
        step={leaf.step}
        // An emptied field means "unset", which is what a null carries through
        // `renderConfig` — the flag is then left to labels.toml.
        onChange={(e) => setValue(e.target.value === '' ? null : Number(e.target.value))}
      />
    </PropertyRow>
  );
};

const stringRow: ControlRenderer = ({ path, pref, value, setValue }) => {
  const leaf = leafOf(pref);
  return (
    <PropertyRow layout="inline" label={leaf.label ?? path} description={leaf.description}>
      <input
        className="row-input"
        type="text"
        value={value === null || value === undefined ? '' : String(value)}
        onChange={(e) => setValue(e.target.value === '' ? null : e.target.value)}
      />
    </PropertyRow>
  );
};

const enumRow: ControlRenderer = ({ path, pref, value, setValue }) => {
  const leaf = leafOf(pref);
  return (
    <PropertyRow layout="inline" label={leaf.label ?? path} description={leaf.description}>
      <select
        className="row-input"
        value={value === null || value === undefined ? '' : String(value)}
        onChange={(e) => setValue(e.target.value)}
      >
        {(leaf.options ?? []).map((option) => (
          <option key={option.value} value={option.value}>
            {option.label ?? option.value}
          </option>
        ))}
      </select>
    </PropertyRow>
  );
};

const booleanRow: ControlRenderer = ({ path, pref, value, setValue }) => {
  const leaf = leafOf(pref);
  return (
    <PropertyRow layout="inline" label={leaf.label ?? path} description={leaf.description}>
      <input
        type="checkbox"
        checked={value === true}
        onChange={(e) => setValue(e.target.checked)}
      />
    </PropertyRow>
  );
};

/** Keyed by leaf kind. `color` is left to labkit, whose colour row is already
 *  inline and carries a picker this would only make worse. */
export const COMPACT_ROWS: Record<string, ControlRenderer> = {
  number: numberRow,
  string: stringRow,
  enum: enumRow,
  boolean: booleanRow,
};
