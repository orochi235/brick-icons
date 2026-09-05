import { createRoot } from 'react-dom/client';
import { createClient } from '@lab/api/client';
import { CorpusWall } from '@lab/corpus/CorpusWall';

createRoot(document.getElementById('root')!).render(
  <CorpusWall client={createClient()} />,
);
