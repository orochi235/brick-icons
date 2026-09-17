import { createRoot } from 'react-dom/client';
import '@weasel-js/labkit/styles.css';
import { createClient } from '@lab/api/client';
import { ReviewPage } from '@lab/review/ReviewPage';

createRoot(document.getElementById('root')!).render(
  <ReviewPage client={createClient()} />,
);
