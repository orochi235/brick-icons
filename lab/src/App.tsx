import { useEffect, useState } from 'react';
import { FloatingPanel, Lab, useLabContext } from '@weasel-js/labkit';
import type { Instrument, TrialContribution } from '@weasel-js/labkit';
import type { LabClient } from '@lab/api/client';
import { PartSearch } from '@lab/chrome/PartSearch';
import { COMPACT_ROWS } from '@lab/config/rows';
import { DefectList } from '@lab/defects/DefectList';
import type { Defect, DefectStatus } from '@lab/defects/useDefects';
import { setPendingPart } from '@lab/config/pending';
import '@lab/app.css';

// `FloatingPanel` captures the pointer to drag itself, exempting only
// `input, button, a, select, textarea, [data-no-drag]` by element name. A
// `div`/`span` with `role="button"` is NOT on that list, so it is captured,
// mouseup retargets to the panel, and no `click` is ever synthesized on the
// row -- it is simply dead to a real mouse while a programmatic `.click()`
// still works. The list's rows are spans, hence this.
const stopDrag = (e: { stopPropagation: () => void }) => e.stopPropagation();

// `FloatingPanel` is a positioned box and nothing else -- it carries neither a
// title nor a dismissal, so both are written here as its first child.
function AllDefects({ client }: { client: LabClient }) {
  const { addTrial } = useLabContext();
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
      <div onPointerDown={stopDrag}>
        <DefectList
          defects={defects}
          onOpen={(part) => { setPendingPart(part); addTrial('part-inspector'); }}
          onStatus={async (id: string, status: DefectStatus) => {
            await client.patchDefect(id, { status });
            setDefects((await client.defects()) as Defect[]);
          }}
        />
      </div>
    </FloatingPanel>
  );
}

// `<Lab>` renders the shell, the workspace and a `<Trial>` per record itself,
// and puts its children in the shell's header beside the built-in controls.
// Nesting a `<LabShell>` here would lay the whole app out as one header item.
function TitleBar({ client }: { client: LabClient }) {
  const { addTrial } = useLabContext();
  // `addTrial` reads the pending part through the instrument's defaultConfig;
  // see src/config/pending.ts.
  return (
    <>
      <PartSearch client={client} onOpen={() => addTrial('part-inspector')} />
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
  return (
    <Lab
      instruments={instruments}
      defaultInstrument="part-inspector"
      storageKey="brick-icons-lab"
      title="brick-icons lab"
      chrome={TRIAL_CHROME}
      controls={COMPACT_ROWS}
      suppress={['snapshot']}
    >
      <TitleBar client={client} />
    </Lab>
  );
}
