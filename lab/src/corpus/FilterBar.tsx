import { Select } from '@weasel-js/ui';
import '@lab/corpus/FilterBar.css';

export function FilterBar({ sources, source, onSource }: {
  sources: { source: string; n: number }[];
  source: string;
  onSource: (next: string) => void;
}) {
  return (
    <div className="corpus-bar">
      {/* No visible caption -- the slot names say what they are; `aria-label`
          carries the name for anyone who cannot see them. The label is a node
          rather than a string so the rows can be typed without reaching the
          popover's CSS, which is portaled out of this subtree and skinned in
          modules -- `textValue` is then what type-to-select reads. */}
      <Select aria-label="Slot" selectedKey={source} onSelectionChange={onSource}
              options={sources.map((s) => ({
                value: s.source,
                textValue: `${s.source} (${s.n})`,
                label: (
                  <span className="corpus-pick">
                    {s.source}&nbsp;<span className="corpus-pick__n">({s.n})</span>
                  </span>
                ),
              }))} />
    </div>
  );
}
