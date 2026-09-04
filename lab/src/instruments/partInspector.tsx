import { createRef, lazy, Suspense, useEffect, useRef, useState,
  type RefObject } from 'react';
import { defineInstrument, f, useAnnotations,
  type Annotation, type CaptureSource } from '@weasel-js/labkit';
import type { LabClient, RenderResult, SchemaField } from '@lab/api/client';
import { buildSchema, defaultsFor, renderConfig } from '@lab/config/nodes';
import { takePendingPart } from '@lab/config/pending';
import { CommandLine } from '@lab/chrome/CommandLine';
import { GoldenStatus } from '@lab/chrome/GoldenStatus';
import { SourcePane, type LoupeView, type PaneState } from '@lab/panes/SourcePane';
import { readView } from '@lab/panes/camera';
import { enabledSources, SOURCES, type Source, type SourceId } from '@lab/panes/sources';
import { renderSignature, runRenders, type SourceRender } from '@lab/instruments/renderJob';
import { paneSpec, type PaneDeps } from '@lab/panes/paneSpec';
import { useArtifactSvg } from '@lab/panes/useArtifactSvg';
import { PartTitle, PoseBar } from '@lab/chrome/PoseBar';
import { diffCaption, diffWarning, useDiff } from '@lab/panes/useDiff';
import { FileDefectDialog } from '@lab/defects/FileDefectDialog';
import { DefectCard } from '@lab/defects/DefectCard';
import { buildDefect, STATUSES, useDefects } from '@lab/defects/useDefects';
import { defectToMarks, markToDefectFields, targetId,
  type MarkMeta } from '@lab/defects/projection';
import { createTargetRegistry, type TargetRegistry } from '@lab/defects/targets';
import { useReference } from '@lab/panes/useReference';
import { useRenderFit } from '@lab/panes/useRenderFit';
import { threeStyle } from '@lab/panes/viewport';
import { decalCaption, useDecal } from '@lab/panes/useDecal';
import { showsLoupe } from '@lab/panes/loupe';
import { useLoupe } from '@lab/panes/useLoupe';

/** three.js and its loaders are around a megabyte, and the 3D pane is off by
 *  default, so the code for it is fetched the first time a pane asks to draw
 *  one rather than at startup. */
const ThreePane = lazy(() => import('@lab/panes/ThreePane')
  .then((module) => ({ default: module.ThreePane })));

export interface InspectorState {
  renders: Partial<Record<SourceId, RenderResult>>;
  errors: Partial<Record<SourceId, string>>;
  /** Which run each pane's render came from, so a pane can tell its own
   *  drawing from the one before it. */
  stamps: Partial<Record<SourceId, string>>;
  /** This trial's key into the annotation target registry. `targets` is given
   *  the instrument's state and nothing else, so a trial has no other way to
   *  say which one it is, and two open trials would read each other's panes. */
  trialKey: string;
}

/** What a capture composites the marks over. A pane already holds exactly the
 *  two shapes `CaptureSource` takes. */
function baseOf(deps: PaneDeps, source: Source): CaptureSource {
  const state = paneSpec(source, deps).state;
  if (state.kind === 'svg') return { kind: 'svg', markup: state.markup };
  if (state.kind === 'image') return { kind: 'image', src: state.src };
  return { kind: 'svg', markup: '<svg xmlns="http://www.w3.org/2000/svg"/>' };
}

function Panes({ ctx, client, registry }:
    { ctx: any; client: LabClient; registry: TargetRegistry }) {
  const config = ctx.config as Record<string, unknown>;
  const camera = readView(ctx.trial.view);
  const paneRefs = useRef<Record<string, RefObject<HTMLDivElement | null>>>({});
  const refFor = (id: SourceId) => {
    paneRefs.current[id] ??= createRef<HTMLDivElement>();
    return paneRefs.current[id]!;
  };
  const sources = enabledSources((config.sources as SourceId[]) ?? []);
  const renders = (ctx.state as InspectorState).renders;
  const markup = useArtifactSvg(client, renders);
  const diff = useDiff(client, renders);
  const layout = String(config.layout ?? 'grid');

  const part = String(config.part ?? '');
  const { defects, file, setStatus } = useDefects(client, part);
  const [boxes, setBoxes] = useState<Record<string, { width: number; height: number }>>({});
  const [selected, setSelected] = useState<string | null>(null);

  const marks = useAnnotations();
  const [pending, setPending] = useState<Annotation | null>(null);

  useEffect(() => marks.subscribe(() => {
    // No delta comes with the callback, so the unfiled mark is found by the
    // absence of the id the projection stamps on every mark it makes.
    const loose = marks.query().find((a) => !(a.meta as MarkMeta | undefined)?.defectId);
    setPending(loose ?? null);
    // Selection arrives on this same channel: weasel keeps a canvas's selection
    // on the scene, so setSelection notifies the store's listeners. Probed
    // rather than called, because `selection()` lands in labkit after
    // 1.4.0-pre.0 -- drop the probe when the pin moves.
    const withSelection = marks as typeof marks & { selection?: () => readonly string[] };
    const picked = withSelection.selection?.()[0];
    const mark = picked ? marks.get(picked) : undefined;
    setSelected((mark?.meta as MarkMeta | undefined)?.defectId ?? null);
  }), [marks]);

  const angle = String(config.angle ?? 'iso');
  const shows = (kind: string) => sources.some((s) => s.kind === kind);
  const referencePane = useReference(client, part, angle,
                                     config.part_color as string | undefined,
                                     shows('reference'));
  const decal = useDecal(client, part, shows('decal'));
  const fit = useRenderFit(client, renders);
  const loupe = useLoupe(config, (key, value) => ctx.setConfig(key, value));
  const [threeSnapshot, setThreeSnapshot] = useState<string | null>(null);
  const over = loupe.over ? SOURCES[loupe.over] : null;

  const engineIds = sources.filter((s) => s.kind === 'engine').map((s) => s.id);
  // What every engine pane compares its own render against: the run on screen.
  const run = { signature: renderSignature(part, renderConfig(config)),
                running: ctx.job?.status === 'running' };
  const shown = defects.find((d) => d.id === selected);

  const loupeFor = (source: Source): LoupeView | null => {
    if (!loupe.at || !showsLoupe(source, over, loupe.allPanes)) return null;
    if (source.kind !== '3d') return { at: loupe.at, factor: loupe.factor };
    return threeSnapshot
      ? { at: loupe.at, factor: loupe.factor, image: threeSnapshot }
      : null;
  };

  const deps: PaneDeps = {
    engines: ctx.state as InspectorState,
    markup,
    run,
    reference: referencePane,
    // The decal is flat, not a view of the part, so the shared camera still
    // pans and zooms it but no angle applies.
    decal: { pane: decal.pane, note: decalCaption(decal.urls) },
    diff: { pane: diff.pane, note: diffWarning(config) ?? diffCaption(diff.result) },
    three: {
      // Until a render lands there is no fit to frame by. Say so: an
      // unregistered pane looks exactly like a mis-registered one.
      note: fit ? undefined : 'unregistered',
      node: (
        <Suspense fallback={<div className="pane-note">loading 3D…</div>}>
          <ThreePane part={part} angle={angle} fit={fit} style={threeStyle(config)}
            box={boxes['3d'] ?? { width: 0, height: 0 }} view={camera}
            onSnapshot={loupe.live ? setThreeSnapshot : undefined}
            onSettle={(next) => ctx.setConfig('angle', next)} />
        </Suspense>
      ),
    },
  };

  const markable = sources.filter((s) => paneSpec(s, deps).marks);
  registry.publish((ctx.state as InspectorState).trialKey, {
    camera,
    panes: markable.map((s) => ({
      id: s.id,
      ref: refFor(s.id),
      // The measured body, not `render_px`: a stored fraction has always been
      // a fraction of the box the layout gave the pane. Passing the render
      // size instead moves every defect filed before today.
      content: (() => {
        const box = boxes[s.id] ?? { width: 1, height: 1 };
        return { w: box.width, h: box.height };
      })(),
      base: () => baseOf(deps, s),
    })),
  });

  const shownTargets = markable.map((s) => targetId(s.id));
  useEffect(() => {
    for (const a of marks.query()) {
      if ((a.meta as MarkMeta | undefined)?.defectId) marks.remove(a.id);
    }
    for (const d of defects) {
      for (const init of defectToMarks(d, shownTargets)) marks.add(init, config);
    }
  }, [defects, shownTargets.join(','), marks, config]);

  return (
    <div className={`panes panes-${layout}`}>
      {sources.map((source) => {
        const spec = paneSpec(source, deps);
        return (
          <SourcePane
            key={source.id}
            source={source}
            note={spec.note}
            state={spec.state}
            busy={spec.busy}
            camera={camera}
            loupe={loupeFor(source)}
            onHover={loupe.live ? (at) => loupe.onHover(source.id, at) : undefined}
            onFactor={loupe.bumpFactor}
            onCamera={spec.followsCamera ? (next) => ctx.trial.setView(next) : () => {}}
            onBox={(box) => setBoxes((prev) => ({ ...prev, [source.id]: box }))}
            bodyRef={spec.marks ? refFor(source.id) : undefined}
            overlay={spec.overlay}
          />
        );
      })}
      {pending ? (
        <FileDefectDialog
          part={part}
          mark={pending.frac}
          engines={engineIds}
          onCancel={() => { marks.remove(pending.id); setPending(null); }}
          onFile={async (fields) => {
            const geometry = markToDefectFields({
              id: pending.id, target: pending.target,
              kind: pending.kind, frac: pending.frac, points: pending.points,
            });
            await file(buildDefect({
              part, engines: fields.engines, title: fields.title, notes: fields.notes,
              mark: geometry.mark, kind: geometry.kind, points: geometry.points,
              config,
              existing: defects.map((d) => d.id),
              today: new Date().toISOString().slice(0, 10),
            }));
            // The server owns it now; the projection remakes it on reload.
            marks.remove(pending.id);
            setPending(null);
          }}
        />
      ) : null}
      {shown ? (
        <DefectCard defect={shown} onStatus={setStatus} onClose={() => setSelected(null)} />
      ) : null}
    </div>
  );
}

function DefectCount({ client, part }: { client: LabClient; part: string }) {
  const { defects } = useDefects(client, part);
  const open = defects.filter((d) => d.status === 'open').length;
  if (defects.length === 0) return <span>no defects</span>;
  return <span>{open} open / {defects.length} filed</span>;
}

export function createPartInspector(fields: SchemaField[], client: LabClient) {
  const nodes = buildSchema(fields);
  const defaults = defaultsFor(fields);
  // One registry per instrument, keyed by trial: `targets` runs per trial
  // but the capability is declared once, so a single holder lets two open
  // trials overwrite each other's pane refs.
  const registry = createTargetRegistry();

  return defineInstrument<InspectorState, Record<string, unknown>, SourceRender>({
    name: 'part-inspector',

    config: f.schema({ part: f.string(''), ...nodes } as never) as never,

    // Both `config` and `defaultConfig` are supplied. `defineInstrument`
    // synthesizes the latter only when it is absent, and `addTrial` calls it,
    // which is how the pending part reaches the new trial. Task 15's
    // walkthrough is what confirms this at runtime.
    defaultConfig: () => ({ ...defaults, part: takePendingPart() }),

    initialState: () => ({
      renders: {}, errors: {}, stamps: {},
      // Random rather than a counter: state is persisted, so a counter
      // restarting at zero on reload would collide with a stored trial.
      trialKey: `t${Math.random().toString(36).slice(2, 10)}`,
    }),

    chrome: [
      {
        id: 'part-title',
        region: 'titlebar',
        render: (ctx) => (
          <PartTitle
            client={client}
            part={String((ctx.config as Record<string, unknown>).part ?? '')}
          />
        ),
      },
      {
        id: 'pose-bar',
        region: 'toolbar',
        group: 'pose',
        render: (ctx) => {
          const config = ctx.config as Record<string, unknown>;
          return (
            <PoseBar
              angle={String(config.angle ?? '')}
              config={config}
              fields={fields}
              setConfig={(key, value) => ctx.setConfig(key, value)}
            />
          );
        },
      },
      {
        id: 'defect-count',
        region: 'status',
        render: (ctx) => (
          <DefectCount
            client={client}
            part={String((ctx.config as Record<string, unknown>).part ?? '')}
          />
        ),
      },
      {
        id: 'golden-status',
        region: 'status',
        render: (ctx) => (
          <GoldenStatus
            client={client}
            part={String((ctx.config as Record<string, unknown>).part ?? '')}
          />
        ),
      },
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
        renderSignature(String(config.part ?? ''), renderConfig(config)),
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
        ...state,
        renders: { ...state.renders, [item.source]: item.result },
        errors: {
          ...state.errors,
          [item.source]: item.result.ok ? undefined : (item.result.error ?? 'render failed'),
        },
        stamps: { ...state.stamps, [item.source]: item.signature },
      }),
    },

    annotations: {
      targets: (state) => registry.targets((state as InspectorState).trialKey),
      meaning: {
        statuses: STATUSES.map((id) => ({ id, label: id })),
      },
    },

    render: (ctx) => <Panes ctx={ctx} client={client} registry={registry} />,
  });
}
