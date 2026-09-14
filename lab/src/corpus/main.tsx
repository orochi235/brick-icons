import { createRoot } from 'react-dom/client';
import { Persistence } from '@weasel-js/labkit';
import '@weasel-js/labkit/styles.css';
import { createClient } from '@lab/api/client';
import { CorpusWall } from '@lab/corpus/CorpusWall';
import { thumbFontReady } from '@lab/corpus/badges';

// The wall paints once. Mounting before Oswald has arrived draws every cell's
// caption in the fallback face and leaves it there.
thumbFontReady().then(() => {
  createRoot(document.getElementById('root')!).render(
    // The wall is a LabShell, not a Lab, so nothing else would keep the
    // legend's position across a reload.
    <Persistence storageKey="brick-icons-corpus">
      <CorpusWall client={createClient()} />
    </Persistence>,
  );
});
