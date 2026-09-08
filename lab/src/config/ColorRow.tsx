import { useEffect, useId, useRef, useState, type CSSProperties } from 'react';
import { PropertyRow } from '@weasel-js/labkit';
import type { LabClient } from '@lab/api/client';
import type { LdrawColor } from '@lab/api/types';
import { familyLabel, matchColors, swatchFor } from '@lab/config/colorMatch';
import '@lab/config/ColorRow.css';

/** The palette, fetched once per client rather than once per row: four color
 *  fields in the panel, two trials open, and it never changes. */
const loading = new WeakMap<LabClient, Promise<LdrawColor[]>>();

export function loadColors(client: LabClient): Promise<LdrawColor[]> {
  let p = loading.get(client);
  if (!p) {
    p = client.colors().catch(() => []);
    loading.set(client, p);
  }
  return p;
}

export interface ColorFieldProps {
  client: LabClient;
  /** Empty for a field whose swatch already says what it is: the row then
   *  gives the whole width to the value instead of a label column. */
  label: string;
  description?: string;
  value: string;
  onChange: (next: string | null) => void;
}

/** A `--part-color` field: type hex, a code or a name, and see the palette
 *  entries that still match, each with its own swatch. */
export function ColorField({ client, label, description, value, onChange }: ColorFieldProps) {
  const [palette, setPalette] = useState<LdrawColor[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    let live = true;
    void loadColors(client).then((rows) => { if (live) setPalette(rows); });
    return () => { live = false; };
  }, [client]);

  const hits = open ? matchColors(palette, value, expanded) : [];

  const pick = (color: LdrawColor) => {
    onChange(color.name);
    setOpen(false);
    setActive(0);
  };

  const field = (
    <div className="color-field" ref={box}>
        <span className="color-field-swatch"
              style={swatchStyle(currentSwatch(palette, value))} aria-hidden="true" />
        <input
          className="row-input"
          type="text"
          role="combobox"
          aria-expanded={hits.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          value={value}
          onChange={(e) => {
            onChange(e.target.value === '' ? null : e.target.value);
            setOpen(true);
            setActive(0);
          }}
          onFocus={() => setOpen(true)}
          // A blur that lands on a suggestion must not close the list before
          // the click reaches it; the pointerdown handler below picks first.
          onBlur={() => window.setTimeout(() => setOpen(false), 0)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') { setOpen(false); return; }
            if (!hits.length) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => (i + 1) % hits.length); }
            if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => (i - 1 + hits.length) % hits.length); }
            if (e.key === 'Enter') { e.preventDefault(); pick(hits[active] ?? hits[0]!); }
          }}
        />
        <label className="color-field-all"
               title="Also offer the LDraw-only entries: derived materials, Modulex, and the retired list">
          <input type="checkbox" checked={expanded}
                 onChange={(e) => setExpanded(e.target.checked)} />
          all
        </label>
        {hits.length > 0 ? (
          <div className="color-field-list" id={listId} role="listbox">
            {hits.map((color, i) => (
              <div
                key={color.code}
                role="option"
                aria-selected={i === active}
                className={i === active ? 'color-option is-active' : 'color-option'}
                onPointerDown={(e) => { e.preventDefault(); pick(color); }}
                onPointerEnter={() => setActive(i)}
              >
                <span className="color-field-swatch"
                      style={swatchStyle(swatchFor(color))} aria-hidden="true" />
                <span className="color-option-name">{color.name}</span>
                {familyLabel(color.category)
                  ? <span className="color-option-family">{familyLabel(color.category)}</span>
                  : null}
                <span className="color-option-code">{color.code}</span>
              </div>
            ))}
          </div>
        ) : null}
    </div>
  );

  if (!label) return <div className="color-field-row">{field}</div>;
  return (
    <PropertyRow layout="inline" label={label} description={description}>
      {field}
    </PropertyRow>
  );
}

/** The one thing about a swatch a class cannot carry: which color it is. It
 *  goes in as a custom property, so the CSS still owns how it paints. */
function swatchStyle(color: string): CSSProperties {
  return { '--swatch': color } as CSSProperties;
}

/** What the field's own swatch shows: the entry the typed value names, or the
 *  hex it already is. Nothing recognizable leaves the swatch empty. */
function currentSwatch(palette: readonly LdrawColor[], value: string): string {
  const v = value.trim();
  if (!v) return 'transparent';
  if (/^#[0-9a-f]{3,8}$/i.test(v)) return v;
  if (/^[0-9a-f]{6}$/i.test(v)) return `#${v}`;
  const exact = matchColors(palette, v)[0];
  return exact ? swatchFor(exact) : 'transparent';
}
