import { createRoot } from 'react-dom/client';
import '@weasel-js/labkit/styles.css';
import { createClient } from '@lab/api/client';
import { StatsPage } from '@lab/stats/StatsPage';

createRoot(document.getElementById('root')!).render(
  <StatsPage client={createClient()} />,
);
