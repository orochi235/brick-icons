import { Lab, LabShell, Trial, Workspace, useLabContext } from '@weasel-js/labkit';
import type { Instrument } from '@weasel-js/labkit';
import type { LabClient } from '@lab/api/client';
import { PartSearch } from '@lab/chrome/PartSearch';
import '@lab/app.css';

function TitleBar({ client }: { client: LabClient }) {
  const { addTrial } = useLabContext();
  // `addTrial` reads the pending part through the instrument's defaultConfig;
  // see src/config/pending.ts.
  return <PartSearch client={client} onOpen={() => addTrial('part-inspector')} />;
}

function Trials() {
  const { trials } = useLabContext();
  return (
    <Workspace ids={trials.map((trial) => trial.id)}>
      {trials.map((trial) => <Trial key={trial.id} id={trial.id} />)}
    </Workspace>
  );
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
      <LabShell title="brick-icons lab" header={<TitleBar client={client} />}>
        <Trials />
      </LabShell>
    </Lab>
  );
}
