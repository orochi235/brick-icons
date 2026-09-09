import { createRoot } from 'react-dom/client';
import '@weasel-js/labkit/styles.css';
import { Bench } from '@lab/bench/Bench';

createRoot(document.getElementById('root')!).render(<Bench />);
