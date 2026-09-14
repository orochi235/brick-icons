import { ComboBox, useAsyncOptions, type ComboBoxCommit } from '@weasel-js/ui';
import type { LabClient } from '@lab/api/client';
import '@lab/shared/PartSearch.css';

export interface PartSearchProps {
  client: LabClient;
  /** Called with the part id after the pending slot is set. */
  onOpen: (part: string) => void;
}

export function PartSearch({ client, onOpen }: PartSearchProps) {
  const search = useAsyncOptions<string>({
    load: async (query, signal) => {
      if (!query.trim()) return [];
      const hits = await client.searchParts(query, 25, signal);
      return hits.map((hit) => ({
        value: hit.id,
        textValue: `${hit.id} ${hit.description}`,
        label: (
          <span className="part-search-hit">
            <strong>{hit.id}</strong> {hit.description}
          </span>
        ),
      }));
    },
    debounceMs: 120,
    minLength: 1,
  });

  const commit = (picked: ComboBoxCommit<string>) => {
    const part = (picked.source === 'option' ? picked.key : picked.text).trim();
    if (!part) return;
    onOpen(part);
    search.onInputChange('');
  };

  // A typed id opens even when no hit names it, so the text commits too.
  return (
    <ComboBox<string>
      aria-label="Search parts"
      placeholder="part id or description"
      className="part-search"
      filter="none"
      allowsCustomValue
      selectedKey={null}
      emptyLabel="no parts match"
      errorLabel="search failed"
      {...search}
      onCommit={commit}
    />
  );
}
