import { createRoot } from 'react-dom/client';
import '@weasel-js/labkit/styles.css';
import { createClient } from '@lab/api/client';
import { CorpusWall } from '@lab/corpus/CorpusWall';
import { thumbFontReady } from '@lab/corpus/badges';

// The wall paints once. Mounting before Oswald has arrived draws every cell's
// caption in the fallback face and leaves it there.
thumbFontReady().then(() => {
  createRoot(document.getElementById('root')!).render(
    <CorpusWall client={createClient()} />,
  );
});
