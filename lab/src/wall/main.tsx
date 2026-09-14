import { createRoot } from 'react-dom/client';
import { Persistence } from '@weasel-js/labkit';
import '@weasel-js/labkit/styles.css';
import { createClient } from '@lab/api/client';
import { thumbFontReady } from '@lab/corpus/badges';
import { BrickWall } from '@lab/wall/BrickWall';

// The wall paints once; captions painted before Oswald arrives keep the fallback face.
thumbFontReady().then(() => {
  // No Lab above the wall, so pezlie's legend has nothing else to remember its
  // position in.
  createRoot(document.getElementById('root')!).render(
    <Persistence storageKey="brick-icons-wall">
      <BrickWall client={createClient()} />
    </Persistence>,
  );
});
