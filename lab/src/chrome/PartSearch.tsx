import { useEffect, useState } from 'react';
import type { LabClient, PartHit } from '@lab/api/client';
import { setPendingPart } from '@lab/config/pending';

export interface PartSearchProps {
  client: LabClient;
  /** Called with the part id after the pending slot is set. */
  onOpen: (part: string) => void;
}

export function PartSearch({ client, onOpen }: PartSearchProps) {
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<PartHit[]>([]);

  useEffect(() => {
    if (!query.trim()) {
      setHits([]);
      return;
    }
    let live = true;
    const timer = setTimeout(() => {
      client.searchParts(query).then((found) => { if (live) setHits(found); })
        .catch(() => { if (live) setHits([]); });
    }, 120);
    return () => { live = false; clearTimeout(timer); };
  }, [query]);

  function open(part: string) {
    if (!part.trim()) return;
    setPendingPart(part);
    onOpen(part.trim());
    setQuery('');
    setHits([]);
  }

  return (
    <div className="part-search">
      <input
        type="search"
        placeholder="part id or description"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') open(query); }}
      />
      {hits.length > 0 ? (
        <ul className="part-search-hits">
          {hits.map((hit) => (
            <li key={hit.id}>
              <span
                role="button"
                tabIndex={0}
                onClick={() => open(hit.id)}
                onKeyDown={(e) => { if (e.key === 'Enter') open(hit.id); }}
              >
                <strong>{hit.id}</strong> {hit.description}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
