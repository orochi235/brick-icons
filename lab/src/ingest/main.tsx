import { createRoot } from 'react-dom/client';
import '@weasel-js/labkit/styles.css';
import { createClient } from '@lab/api/client';
import { IngestPage } from '@lab/ingest/IngestPage';

createRoot(document.getElementById('root')!).render(
  <IngestPage client={createClient()} />,
);
