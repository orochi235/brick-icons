import { createRoot } from 'react-dom/client';
import '@weasel-js/labkit/styles.css';
import { createClient } from '@lab/api/client';
import { thumbFontReady } from '@lab/corpus/badges';
import { BrickWall } from '@lab/wall/BrickWall';

// The wall paints once; captions painted before Oswald arrives keep the fallback face.
thumbFontReady().then(() => {
  createRoot(document.getElementById('root')!).render(<BrickWall client={createClient()} />);
});
