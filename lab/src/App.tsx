import { useEffect, useMemo, useState } from 'react';
import { FloatingPanel, Lab } from '@weasel-js/labkit';
import type { Instrument, TrialContribution } from '@weasel-js/labkit';
import type { LabClient } from '@lab/api/client';
import { PartSearch } from '@lab/chrome/PartSearch';
import { rowsFor } from '@lab/config/rows';
import { DefectList } from '@lab/defects/DefectList';
import type { Defect, DefectStatus } from '@lab/defects/useDefects';
import { useOpenPart } from '@lab/config/pending';
import '@lab/app.css';

// `FloatingPanel` is a positioned box and nothing else -- it carries neither a
// title nor a dismissal, so both are written here as its first child.
function AllDefects({ client }: { client: LabClient }) {
  const openPart = useOpenPart();
  const [defects, setDefects] = useState<Defect[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (open) void client.defects().then((rows) => setDefects(rows as Defect[]));
  }, [open, client]);

  if (!open) {
    return (
      <button type="button" className="defects-open" onClick={() => setOpen(true)}>
        Defects
      </button>
    );
  }

  return (
    <FloatingPanel anchor="bottom-right" storageKey="brick-icons-lab.defects"
      className="defects-panel">
      <div className="defects-panel-head">
        <strong>Defects</strong>
        <button type="button" aria-label="Close defects" onClick={() => setOpen(false)}>
          x
        </button>
      </div>
      <DefectList
        defects={defects}
        onOpen={(part) => openPart(part)}
        onStatus={async (id: string, status: DefectStatus) => {
          await client.patchDefect(id, { status });
          setDefects((await client.defects()) as Defect[]);
        }}
      />
    </FloatingPanel>
  );
}

// `<Lab>` renders the shell, the workspace and a `<Trial>` per record itself,
// and puts its children in the shell's header beside the built-in controls.
// Nesting a `<LabShell>` here would lay the whole app out as one header item.
function TitleBar({ client }: { client: LabClient }) {
  const openPart = useOpenPart();
  return (
    <>
      <PartSearch client={client} onOpen={(part) => openPart(part)} />
      <AllDefects client={client} />
    </>
  );
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

export function App({ instruments, client }:
                    { instruments: Instrument<any, any, any>[]; client: LabClient }) {
  const controls = useMemo(() => rowsFor(client), [client]);
  return (
    <Lab
      instruments={instruments}
      defaultInstrument="part-inspector"
      storageKey="brick-icons-lab"
      title="brick-icons lab"
      chrome={TRIAL_CHROME}
      controls={controls}
      suppress={['snapshot']}
    >
      <TitleBar client={client} />
    </Lab>
  );
}
