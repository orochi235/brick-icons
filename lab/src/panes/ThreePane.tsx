import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useLoader, useThree } from '@react-three/fiber';
import { OrbitControls, OrthographicCamera } from '@react-three/drei';
import { LDrawLoader } from 'three/examples/jsm/loaders/LDrawLoader.js';
import { LDrawConditionalLineMaterial }
  from 'three/examples/jsm/materials/LDrawConditionalLineMaterial.js';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import * as THREE from 'three';
import type { Camera } from '@lab/panes/camera';
import { angleFromOrbit, formatAngle, orbitFromAngle, parseAngle } from '@lab/panes/orbit';
import { fattenLines, paint } from '@lab/panes/threeModel';
import {
  frustum, lightPosition, partColorHex, strokePx, toThree,
  type Box, type RenderFit, type ThreeStyle, type Vec3Tuple,
} from '@lab/panes/viewport';

// The engines project orthographically, so this pane does too -- there is no
// perspective mode, because there is nothing for one to be compared against.
// FILL frames the unregistered fallback; a fit frames everything else.
const FILL = 1.3;
const RADIUS = 240;
const LIBRARY = '/ldraw/';
const PARTS = `${LIBRARY}parts/`;
// Relative to PARTS, which is what the loader hands its own file loader.
const COLORS = '../LDConfig.ldr';

/** The stock loader, with the library's color table actually in place.
 *
 *  `preloadMaterials` exists for this and does not survive: `load()` opens
 *  every part with `setMaterials([])`, which throws the table away again. So
 *  the colors are read per part and the text is parsed rather than loaded.
 *  Without them the loader knows two: code 16 as #FF8080 and edges as
 *  #A0A0A0, which is why a decorated part turned up flat pink. */
class ColoredLDrawLoader extends LDrawLoader {
  override load(url: string, onLoad: (group: THREE.Group) => void,
                onProgress?: (e: ProgressEvent) => void,
                onError?: (e: unknown) => void): void {
    const file = new THREE.FileLoader(this.manager);
    file.setPath(this.path);
    file.load(url, (text) => {
      // Three arguments, whatever the published typings say the second is.
      const parse = (this as unknown as {
        parse(text: string, onLoad: (group: THREE.Group) => void,
              onError?: (e: unknown) => void): void }).parse.bind(this);
      void this.preloadMaterials(COLORS)
        .then(() => parse(text as string, onLoad, onError))
        .catch(onError);
    }, onProgress, onError);
  }
}
// Enough backing store for the loupe to magnify. `frameloop="demand"` is what
// pays for the dpr, and the readback only happens while the loupe is up.
const SUPERSAMPLE = 3;

interface Framing {
  radius: number;
  center: Vec3Tuple;
}

function Part({ part, color, opacity, onFraming, onLines }: {
  part: string;
  color: number | null;
  opacity: number;
  onFraming: (f: Framing) => void;
  onLines: (materials: LineMaterial[]) => void;
}) {
  // A BARE filename against `path`, never a path against the library root: a
  // subfile reference is resolved relative to its parent's name, so any
  // directory in the name is folded into the child's and then doubled by the
  // loader's own `parts/` search (`/ldraw/parts/parts/s/3001s01.dat`).
  const model = useLoader(ColoredLDrawLoader, `${part}.dat`, (loader) => {
    // Required since three 0.170: without it the loader throws on the first
    // !COLOUR directive it meets.
    loader.setConditionalLineMaterial(LDrawConditionalLineMaterial);
    loader.setPath(PARTS);
    // The subfile search root, and not in the published typings.
    (loader as unknown as { setPartsLibraryPath: (p: string) => void })
      .setPartsLibraryPath(LIBRARY);
  });

  const object = useMemo(() => {
    const group = model.clone();
    // LDraw's Y axis points down: studs are at negative Y. `viewport.toThree`
    // undoes this turn for anything the fit hands over, so the part must stay
    // where the part file put it -- recentring it here would slide it out of
    // the frame the render fit describes.
    group.rotation.x = Math.PI;
    group.updateMatrixWorld(true);
    const lines = fattenLines(group);
    const box = new THREE.Box3().setFromObject(group);
    const center = box.getCenter(new THREE.Vector3());
    return {
      group,
      lines,
      framing: {
        radius: box.getSize(new THREE.Vector3()).length() / 2,
        center: [center.x, center.y, center.z] as Vec3Tuple,
      },
    };
  }, [model]);

  useEffect(() => { paint(object.group, color, opacity); }, [object, color, opacity]);
  useEffect(() => { onFraming(object.framing); onLines(object.lines); }, [object]);

  return <primitive object={object.group} />;
}

interface RigProps {
  angle: string;
  fit: RenderFit | null;
  box: Box;
  view: Camera;
  style: ThreeStyle;
  framing: Framing;
  lines: LineMaterial[];
  orbit: Orbit;
  onSettle: (angle: string) => void;
}

/** Who owns the left drag. In the trial the pane shares a camera with every
 *  other pane, so the left drag pans that one and orbiting is the middle and
 *  right buttons; a pane standing on its own has no shared camera to protect
 *  and the plain drag should turn the part. */
export type Orbit = 'shared' | 'own';

/** Points the camera at the pose `--angle` names and frames it the way the
 *  render did.
 *
 *  Direction comes from the angle rather than from the fit: after a drag the
 *  angle is current and the fit is a render behind, and taking the direction
 *  from the stale one would snap the part back to the previous pose. The
 *  framing lags by that one render, which is all registration promises. */
function Rig({ angle, fit, box, view, style, framing, lines, orbit,
               onSettle }: RigProps) {
  const { camera, invalidate } = useThree();
  const controls = useRef<{ target: THREE.Vector3; update: () => void } | null>(null);

  useEffect(() => {
    const ortho = camera as THREE.OrthographicCamera;
    const parsed = parseAngle(angle);
    const dir = orbitFromAngle(parsed ?? { lat: 30, long: 45 }, 1);
    const radius = Math.max(1, framing.radius);
    // Registered, the eye sits on the view axis through the WORLD origin,
    // which is the point the engine projects about; the bounds carry the pan
    // and the zoom, so aiming it at the framed middle would apply that offset
    // twice. Unregistered there are no such bounds -- they are symmetric about
    // the axis -- so the axis has to run through the part instead. An LDraw
    // part's origin is where it meets the brick below it, not its middle, so
    // aiming at the origin hung a 2x4 half out of the bottom of the frame.
    const target: Vec3Tuple = fit ? [0, 0, 0] : framing.center;
    const back = radius * 4 + 1;
    ortho.position.set(target[0] + dir.x * back, target[1] + dir.y * back,
                       target[2] + dir.z * back);
    ortho.near = 0.1;
    ortho.far = back + radius * 4;

    if (fit) {
      const bounds = frustum(fit, box, view);
      const up = toThree(fit.up);
      ortho.up.set(up[0], up[1], up[2]);
      ortho.left = bounds.left;
      ortho.right = bounds.right;
      ortho.top = bounds.top;
      ortho.bottom = bounds.bottom;
    } else {
      // No render to register against: frame the part by its own size, about
      // its own middle. That is what the pane's `unregistered` note is warning
      // about -- this framing is the part's, not any slot's picture of it.
      const aspect = box.height >= 1 ? box.width / box.height : 1;
      const half = radius * FILL;
      ortho.up.set(0, 1, 0);
      ortho.left = -half * aspect;
      ortho.right = half * aspect;
      ortho.top = half;
      ortho.bottom = -half;
    }

    ortho.lookAt(target[0], target[1], target[2]);
    ortho.updateProjectionMatrix();
    controls.current?.target.set(target[0], target[1], target[2]);
    controls.current?.update();
    // `frameloop="demand"` draws only when asked, and moving a camera object
    // in an effect is not an ask. Without this the pane holds whatever was on
    // the buffer until some other event drew a frame -- which for a pane that
    // is revealed rather than laid out means an empty canvas until the first
    // drag.
    invalidate();
  }, [angle, fit, box.width, box.height, view, framing, camera, invalidate]);

  useEffect(() => {
    const width = strokePx(fit, box, view, style.lineWidth);
    for (const material of lines) {
      material.linewidth = width;
      // The line shader works in clip space, so it has to be told the pixels.
      material.resolution.set(Math.max(1, box.width), Math.max(1, box.height));
    }
    invalidate();
  }, [lines, fit, box.width, box.height, view, style.lineWidth, invalidate]);

  return (
    <OrbitControls
      // Everything but rotation is the shared camera's: a dolly or a pan of
      // this camera alone would put the pane back out of register.
      ref={controls as never}
      enablePan={false}
      enableZoom={false}
      // An undefined button is one OrbitControls does nothing with, which is
      // how the left drag is left to the shared camera.
      mouseButtons={orbit === 'own'
        ? { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.ROTATE,
            RIGHT: THREE.MOUSE.ROTATE }
        : { LEFT: undefined, MIDDLE: THREE.MOUSE.ROTATE,
            RIGHT: THREE.MOUSE.ROTATE }}
      // Touch has no middle or right button to put the orbit on, and in the
      // trial the defaults (one finger rotates, two dolly-pan) would take
      // both of the pane's own gestures. A pane on its own has no gestures to
      // lose, so one finger turns it.
      touches={orbit === 'own'
        ? { ONE: THREE.TOUCH.ROTATE, TWO: undefined }
        : { ONE: undefined, TWO: undefined }}
      // `end` fires when the drag stops, which is when a re-render is worth it.
      // The angle is the direction FROM what the camera turns about, which is
      // the part's own middle when there is no render to register against --
      // read off the position alone it would carry that offset into the pose.
      onEnd={() => onSettle(formatAngle(angleFromOrbit(
        camera.position.clone().sub(
          controls.current?.target ?? new THREE.Vector3()))))}
    />
  );
}

/** Reads the canvas back for the loupe when the scene has changed, and not on
 *  the pointer moves in between. */
function Snapshot({ token, onSnapshot }:
                  { token: string; onSnapshot: (url: string | null) => void }) {
  const { gl, scene, camera } = useThree();
  const invalidate = useThree((state) => state.invalidate);
  const pending = useRef(false);

  useEffect(() => {
    pending.current = true;
    invalidate();
  }, [token, invalidate]);

  useFrame(() => {
    if (!pending.current) return;
    pending.current = false;
    gl.render(scene, camera);
    try {
      onSnapshot(gl.domElement.toDataURL('image/png'));
    } catch {
      onSnapshot(null);
    }
  });

  return null;
}

export interface ThreePaneProps {
  part: string;
  angle: string;
  /** The render's world -> viewBox map, or null while none has landed. */
  fit: RenderFit | null;
  /** The pane body, in pixels: what the frustum has to cover. */
  box: Box;
  view: Camera;
  style: ThreeStyle;
  /** The pane's drawing as an image, for the loupe to magnify. */
  onSnapshot?: (url: string | null) => void;
  /** Who owns the left drag; 'shared' (the default) leaves it to the trial's
   *  shared camera. */
  orbit?: Orbit;
  onSettle: (angle: string) => void;
}

export function ThreePane({ part, angle, fit, box, view, style, onSnapshot,
                            orbit = 'shared', onSettle }: ThreePaneProps) {
  const [framing, setFraming] = useState<Framing>({ radius: RADIUS, center: [0, 0, 0] });
  const [lines, setLines] = useState<LineMaterial[]>([]);
  if (!part.trim()) return <p className="three-empty">no part chosen</p>;
  // A frustum needs a measured pane; before the first ResizeObserver callback
  // there is nothing to fit into and the fit would divide by zero.
  const registered = fit && box.width >= 1 && box.height >= 1 ? fit : null;
  const sun = lightPosition(registered, Math.max(1, framing.radius) * 8);
  return (
    // `demand` is what pays for the supersampled buffer across the trial's
    // several panes, and it needs every draw to be asked for. A pane on its
    // own is one small canvas that is revealed rather than laid out, where the
    // model arrives through Suspense after the asking is over -- so it runs
    // the plain loop and always has something on the buffer.
    <Canvas dpr={SUPERSAMPLE} frameloop={orbit === 'own' ? 'always' : 'demand'}
      gl={{ preserveDrawingBuffer: true }}>
      {style.background ? <color attach="background" args={[style.background]} /> : null}
      <OrthographicCamera makeDefault near={0.1} far={20000} />
      <ambientLight intensity={0.7} />
      <directionalLight position={sun ?? [-1, 1, 2]} intensity={1.2} />
      <Suspense fallback={null}>
        <Part part={part} color={partColorHex(registered)} opacity={style.opacity}
          onFraming={setFraming} onLines={setLines} />
      </Suspense>
      <Rig angle={angle} fit={registered} box={box} view={view} style={style}
        framing={framing} lines={lines} orbit={orbit} onSettle={onSettle} />
      {onSnapshot ? (
        <Snapshot onSnapshot={onSnapshot}
          // `framing` is the term that says the model has ARRIVED: the part
          // loads through Suspense long after its name settles, so a token
          // without it snapshots the empty scene and caches that.
          token={[part, angle, box.width, box.height, view.zoom,
                  view.pan.x, view.pan.y, style.lineWidth, style.opacity,
                  style.background,
                  JSON.stringify(registered), JSON.stringify(framing)].join('|')} />
      ) : null}
    </Canvas>
  );
}
