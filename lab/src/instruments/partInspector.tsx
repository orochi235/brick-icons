import { defineInstrument, f } from '@weasel-js/labkit';
import type { LabClient, RenderResult, SchemaField } from '@lab/api/client';
import { buildSchema, defaultsFor, renderConfig, type SourceId } from '@lab/config/nodes';
import { takePendingPart } from '@lab/config/pending';
import { CommandLine } from '@lab/chrome/CommandLine';
import { SourcePane, type PaneState } from '@lab/panes/SourcePane';
import { readView } from '@lab/panes/camera';
import { SOURCES, enabledSources } from '@lab/panes/sources';
import { runRenders, type SourceRender } from '@lab/instruments/renderJob';

export interface InspectorState {
  renders: Partial<Record<SourceId, RenderResult>>;
  errors: Partial<Record<SourceId, string>>;
}

function paneState(source: SourceId, state: InspectorState,
                   svg: Partial<Record<SourceId, string>>): PaneState {
  if (state.errors[source]) return { kind: 'error', message: state.errors[source]! };
  const markup = svg[source];
  if (markup) return { kind: 'svg', markup };
  if (state.renders[source]) return { kind: 'running' };
  return { kind: 'idle' };
}

export function createPartInspector(fields: SchemaField[], client: LabClient) {
  const nodes = buildSchema(fields);
  const defaults = defaultsFor(fields);

  return defineInstrument<InspectorState, Record<string, unknown>, SourceRender>({
    name: 'part-inspector',

    config: f.schema({ part: f.string(''), ...nodes } as never) as never,

    // Both `config` and `defaultConfig` are supplied. `defineInstrument`
    // synthesizes the latter only when it is absent, and `addTrial` calls it,
    // which is how the pending part reaches the new trial. Task 15's
    // walkthrough is what confirms this at runtime.
    defaultConfig: () => ({ ...defaults, part: takePendingPart() }),

    initialState: () => ({ renders: {}, errors: {} }),

    layers: { ids: Object.values(SOURCES).map((s) => s.id) },

    chrome: [
      {
        id: 'command-line',
        region: 'status',
        render: (ctx) => (
          <CommandLine
            client={client}
            part={String((ctx.config as Record<string, unknown>).part ?? '')}
            config={renderConfig(ctx.config as Record<string, unknown>)}
          />
        ),
      },
    ],

    job: {
      auto: true,
      // Only what changes a render: the layout toggle rearranges panes that
      // are already drawn, and re-running on it would throw them away.
      key: (config) => [
        config.part,
        JSON.stringify(renderConfig(config)),
        (config.sources as SourceId[]).join(','),
      ],
      run: ({ config, signal }) => runRenders({
        client,
        part: String(config.part ?? ''),
        config: renderConfig(config),
        sources: (config.sources as SourceId[]) ?? [],
        signal,
      }),
      onItem: (item, state) => ({
        renders: { ...state.renders, [item.source]: item.result },
        errors: {
          ...state.errors,
          [item.source]: item.result.ok ? undefined : (item.result.error ?? 'render failed'),
        },
      }),
    },

    render: (ctx) => {
      const config = ctx.config as Record<string, unknown>;
      const camera = readView(ctx.trial.view);
      const sources = enabledSources((config.sources as SourceId[]) ?? []);
      const stack = config.layout === 'stack';

      return (
        <div className={stack ? 'panes panes-stack' : 'panes panes-split'}>
          {sources.map((source) => (
            <SourcePane
              key={source.id}
              source={source}
              state={paneState(source.id, ctx.state, {})}
              camera={camera}
              onCamera={(next) => ctx.trial.setView(next)}
            />
          ))}
        </div>
      );
    },
  });
}
