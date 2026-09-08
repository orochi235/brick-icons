import { PropertyRow } from '@weasel-js/labkit';
import type { ControlRenderer } from '@weasel-js/labkit';
import type { LabClient } from '@lab/api/client';
import { ColorField } from '@lab/config/ColorRow';

/**
 * Compact rows for the settings panel.
 *
 * `@weasel-js/ui`'s rows take a `layout`, but `ControlPanel` never threads one,
 * so every leaf draws at the default `layout="block"` — label stacked above
 * control. With 38 CLI flags that is a very long panel, so these re-declare one
 * row per leaf kind with the label beside the control instead.
 *
 * They are keyed by kind rather than by config path, so a flag the CLI grows
 * picks up the compact row without being named here.
 *
 * A density option on `ControlPanel` would retire most of this but NOT the
 * boolean row: `PropertyRow` applies its inline class only for
 * `variant === 'default'`, and ui's `CheckboxRow` and `ColorRow` render other
 * variants and accept no `layout` at all. Ours goes inline precisely because it
 * builds a plain `PropertyRow` around a raw checkbox instead of using
 * `CheckboxRow`.
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

/** Keyed by leaf kind. `color` is left to labkit, whose color row is already
 *  inline and carries a picker this would only make worse. */
export const COMPACT_ROWS: Record<string, ControlRenderer> = {
  number: numberRow,
  string: stringRow,
  enum: enumRow,
  boolean: booleanRow,
};

/** The compact rows plus the ones that need the server. `--part-color` takes
 *  hex, an LDraw code or a name, and the palette that resolves the last two
 *  lives behind the API — so this row is keyed by config path, over the
 *  `string` row its leaf would otherwise get. */
export function rowsFor(client: LabClient): Record<string, ControlRenderer> {
  // No label: the swatch and the palette names say what the field is, and the
  // value is what needs the width.
  const partColor: ControlRenderer = ({ pref, value, setValue }) => {
    const leaf = leafOf(pref);
    return (
      <ColorField
        client={client}
        label=""
        description={leaf.description}
        value={value === null || value === undefined ? '' : String(value)}
        onChange={setValue}
      />
    );
  };
  return { ...COMPACT_ROWS, part_color: partColor };
}
