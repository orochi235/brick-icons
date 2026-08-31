import { Lab, useLabContext } from '@weasel-js/labkit';
import type { Instrument } from '@weasel-js/labkit';
import type { LabClient } from '@lab/api/client';
import { PartSearch } from '@lab/chrome/PartSearch';
import '@lab/app.css';

// `<Lab>` renders the shell, the workspace and a `<Trial>` per record itself,
// and puts its children in the shell's header beside the built-in controls.
// Nesting a `<LabShell>` here would lay the whole app out as one header item.
function TitleBar({ client }: { client: LabClient }) {
  const { addTrial } = useLabContext();
  // `addTrial` reads the pending part through the instrument's defaultConfig;
  // see src/config/pending.ts.
  return <PartSearch client={client} onOpen={() => addTrial('part-inspector')} />;
}

export function App({ instrument, client }:
                    { instrument: Instrument<any, any, any>; client: LabClient }) {
  return (
    <Lab
      instruments={[instrument]}
      defaultInstrument="part-inspector"
      storageKey="brick-icons-lab"
      title="brick-icons lab"
    >
      <TitleBar client={client} />
    </Lab>
  );
}
