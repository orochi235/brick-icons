import { useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { CellsBody } from '@lab/corpus/types';
import '@lab/corpus/corpus.css';

/** The whole app, minus its mount. Exported so a labkit instrument can host it
 *  without the standalone page. */
export function CorpusWall({ client }: { client: LabClient }) {
  const [body, setBody] = useState<CellsBody | null>(null);

  useEffect(() => {
    void client.cells('census-naive').then(setBody);
  }, [client]);

  if (!body) return <p className="corpus-loading">loading the corpus…</p>;
  return <p className="corpus-loading">{body.count} parts</p>;
}
