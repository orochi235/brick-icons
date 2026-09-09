import { Select, ToggleBar } from '@weasel-js/ui';
import { FAMILY_LABEL, facetOf, familiesIn, familyOf, slotIn,
         type Family } from '@lab/corpus/slotFamily';
import '@lab/corpus/FilterBar.css';

export function FilterBar({ sources, source, onSource }: {
  sources: { source: string; n: number }[];
  source: string;
  onSource: (next: string) => void;
}) {
  // The family is read off the shown slot rather than held beside it: two
  // pieces of state for one choice go out of step the moment a slot arrives
  // from the hash or from the sources poll.
  const family = familyOf(source);
  const families = familiesIn(sources);
  const inFamily = sources.filter((s) => familyOf(s.source) === family);

  const pickFamily = (next: Family | null) => {
    if (!next) return;
    const slot = slotIn(sources, next, facetOf(source));
    if (slot) onSource(slot);
  };

  return (
    <div className="corpus-bar">
      <ToggleBar size="sm" variant="minimal" ariaLabel="Engine"
                 className="corpus-bar__engine"
                 items={families.map((f) => ({ value: f, label: FAMILY_LABEL[f] }))}
                 value={family} onChange={pickFamily} />
      {/* One slot in the family is no choice -- decal is the whole family --
          so the dropdown is not offered. No visible caption: the facet names
          say what they are; `aria-label` carries the name for anyone who
          cannot see them. The label is a node rather than a string so the rows
          can be typed without reaching the popover's CSS, which is portaled
          out of this subtree and skinned in modules -- `textValue` is then
          what type-to-select reads. */}
      {inFamily.length > 1 && (
        <Select aria-label="Slot" className="corpus-bar__slot"
                selectedKey={source} onSelectionChange={onSource}
                options={inFamily.map((s) => ({
                  value: s.source,
                  textValue: `${facetOf(s.source)} (${s.n})`,
                  label: (
                    <span className="corpus-pick">
                      {facetOf(s.source)}&nbsp;<span className="corpus-pick__n">({s.n})</span>
                    </span>
                  ),
                }))} />
      )}
    </div>
  );
}
