import { defineInstrument, f, useLabContext } from '@weasel-js/labkit';
import type { LabClient, SchemaField } from '@lab/api/client';
import { buildSchema, defaultsFor, renderConfig } from '@lab/config/nodes';
import { setPendingPart } from '@lab/config/pending';
import { runSheet, type SheetCell } from '@lab/instruments/sheetJob';
import '@lab/instruments/contactSheet.css';

export interface CorpusList {
  name: string;
  source: string;
  parts: string[];
}

export interface SheetState {
  cells: SheetCell[];
}

/** Run lives here, not in the trial toolbar: labkit puts `job` on the render
 *  context and not on `TrialChromeContext`, and it draws no start control of
 *  its own -- so `auto: false` without this leaves no way to run the sheet. */
function RunBar({ ctx, list }: { ctx: any; list?: CorpusList }) {
  const job = ctx.job;
  const running = job?.status === 'running';
  return (
    <div className="sheet-bar">
      <button type="button" className="pose"
        onClick={() => (running ? job.cancel() : job.start())}>
        {running ? 'Cancel' : 'Run'}
      </button>
      <span>
        {list ? `${list.parts.length} parts in ${list.name}` : 'no list'}
        {running ? ` — ${job.done}/${job.total ?? '?'}` : ''}
      </span>
    </div>
  );
}

function Sheet({ ctx, client, lists }:
               { ctx: any; client: LabClient; lists: CorpusList[] }) {
  const { addTrial } = useLabContext();
  const cells = (ctx.state as SheetState).cells;
  const list = lists.find((l) => l.name === ctx.config.list);
  const open = (part: string) => { setPendingPart(part); addTrial('part-inspector'); };

  return (
    <div className="sheet-wrap">
      <RunBar ctx={ctx} list={list} />
      {cells.length === 0 ? (
        <p className="sheet-empty">press Run to render the sheet.</p>
      ) : (
    <div className="sheet">
      {cells.map((cell) => (
        <figure
          key={cell.part}
          className={`sheet-cell${cell.error ? ' sheet-cell-failed' : ''}`}
          role="button"
          tabIndex={0}
          onClick={() => open(cell.part)}
          onKeyDown={(e) => { if (e.key === 'Enter') open(cell.part); }}
        >
          {cell.svg
            ? <img src={client.artifactUrl(cell.key, cell.svg)} alt={cell.part} />
            : <span>{cell.error ?? 'no output'}</span>}
          <figcaption>{cell.part}</figcaption>
        </figure>
      ))}
    </div>
      )}
    </div>
  );
}

export function createContactSheet(fields: SchemaField[], lists: CorpusList[],
                                   client: LabClient) {
  const nodes = buildSchema(fields);
  const defaults = defaultsFor(fields);
  const names = lists.map((l) => l.name);

  return defineInstrument<SheetState, Record<string, unknown>, SheetCell>({
    name: 'contact-sheet',

    config: f.schema({
      list: f.enum(names[0] ?? 'specimens', names.length > 0 ? names : ['specimens']),
      ...nodes,
    } as never) as never,

    defaultConfig: () => ({ ...defaults, list: names[0] ?? 'specimens' }),

    initialState: () => ({ cells: [] }),

    job: {
      // A list is dozens of renders. Nothing starts it but the Run control.
      auto: false,
      key: (config) => [config.list, JSON.stringify(renderConfig(config))],
      run: ({ config, signal }) => runSheet({
        client,
        parts: lists.find((l) => l.name === config.list)?.parts ?? [],
        config: renderConfig(config),
        signal,
      }),
      onItem: (item, state) => ({ cells: [...state.cells, item] }),
    },

    // A sheet half from the old parameters and half from the new is worse than
    // an empty one: nothing on screen says which cell is which.
    onConfigChange: () => ({ cells: [] }),

    render: (ctx) => <Sheet ctx={ctx} client={client} lists={lists} />,
  });
}
