import { createRoot } from 'react-dom/client';
import '@weasel-js/labkit/styles.css';
import { createClient } from '@lab/api/client';
import { createPartInspector } from '@lab/instruments/partInspector';
import { createContactSheet } from '@lab/instruments/contactSheet';
import { App } from '@lab/App';

const root = createRoot(document.getElementById('root')!);
const client = createClient();

// The schema is fetched before mount because `defineInstrument` needs it: the
// control panel is the CLI's flag set, not a copy of it.
Promise.all([client.schema(), client.lists()]).then(([fields, lists]) => {
  root.render(
    <App
      instruments={[
        createPartInspector(fields, client),
        createContactSheet(fields, lists, client),
      ]}
      client={client}
    />,
  );
}).catch((error: Error) => {
  root.render(
    <p>
      cannot reach the lab server — start it with
      <code> python -m brick_icons.lab</code> ({error.message})
    </p>,
  );
});
