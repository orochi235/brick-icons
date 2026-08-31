import { Lab, useLabContext } from '@weasel-js/labkit';
import type { Instrument, TrialContribution } from '@weasel-js/labkit';
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

function CameraIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
      <path fill="currentColor"
        d="M6 2h4l1 2h3v9H2V4h3zm2 3.5A3.5 3.5 0 1 0 8 12a3.5 3.5 0 0 0 0-7zm0 1.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4z" />
    </svg>
  );
}

// labkit's own `snapshot` sits in the `history` group at the left; `clone` and
// `reset` already declare `end`. Re-declaring it with `end` puts all three
// together on the right. Delete this once labkit moves them itself.
const TRIAL_CHROME: TrialContribution[] = [
  {
    id: 'snapshot-right',
    region: 'toolbar',
    group: 'trial',
    end: true,
    // `render`, not `item`: an item's `onActivate` is a bare callback with no
    // access to the trial, and saving a snapshot needs `ctx.saveSnapshot`.
    render: (ctx) => (
      <button
        type="button"
        className="toolbar-icon"
        title="Save snapshot"
        aria-label="Save snapshot"
        onClick={() => ctx.saveSnapshot()}
      >
        <CameraIcon />
      </button>
    ),
  },
];

export function App({ instrument, client }:
                    { instrument: Instrument<any, any, any>; client: LabClient }) {
  return (
    <Lab
      instruments={[instrument]}
      defaultInstrument="part-inspector"
      storageKey="brick-icons-lab"
      title="brick-icons lab"
      chrome={TRIAL_CHROME}
      suppress={['snapshot']}
    >
      <TitleBar client={client} />
    </Lab>
  );
}
