/** Shaded orthographic renders of a list of parts, for `scripts/shot-sink.py`.
 *
 * The camera is `ThreePane`'s: direction from `orbitFromAngle`, projection
 * orthographic, and the model keeps the position its part file gives it.
 * LDView cannot render orthographic at all, which is why this exists -- the
 * `ldview` slot beside it stays, so the two can be compared.
 *
 * One WebGL context draws the whole list: a page load per part costs more than
 * the render. The frame is the bounding box with a pad, not a tight fit --
 * `bake_part` crops to alpha, the way `-AutoCrop` did.
 */
import * as THREE from 'three';
import { LDrawLoader } from 'three/examples/jsm/loaders/LDrawLoader.js';
import { LDrawConditionalLineMaterial }
  from 'three/examples/jsm/materials/LDrawConditionalLineMaterial.js';
import { orbitFromAngle, parseAngle } from '@lab/panes/orbit';

const SINK = new URLSearchParams(location.search).get('sink') ?? '';
const LIBRARY = `${SINK}/ldraw/`;
const PARTS = `${LIBRARY}parts/`;
const PAD = 1.02;

declare global {
  interface Window { shotProgress?: string; shotError?: string }
}

/** Half-extents in the camera's own basis. A world-axis box clips on the
 *  diagonal at iso. */
function halfExtents(object: THREE.Object3D, camera: THREE.Camera) {
  const box = new THREE.Box3().setFromObject(object);
  const inv = new THREE.Matrix4().copy(camera.matrixWorld).invert();
  const v = new THREE.Vector3();
  let x = 0, y = 0;
  for (const cx of [box.min.x, box.max.x])
    for (const cy of [box.min.y, box.max.y])
      for (const cz of [box.min.z, box.max.z]) {
        v.set(cx, cy, cz).applyMatrix4(inv);
        x = Math.max(x, Math.abs(v.x));
        y = Math.max(y, Math.abs(v.y));
      }
  return { x: x * PAD, y: y * PAD };
}

function makeLoader() {
  const loader = new LDrawLoader();
  loader.setConditionalLineMaterial(LDrawConditionalLineMaterial);
  loader.setPath(PARTS);
  // The subfile search root, and not in the published typings.
  (loader as unknown as { setPartsLibraryPath: (p: string) => void })
    .setPartsLibraryPath(LIBRARY);
  return loader;
}

async function drawOne(
  renderer: THREE.WebGLRenderer, loader: LDrawLoader,
  part: string, angleText: string,
): Promise<string> {
  const group = await loader.loadAsync(`${part}.dat`);
  // LDraw's Y points down; turn the model, not the camera, so the part stays
  // where its file put it.
  group.rotation.x = Math.PI;
  group.updateMatrixWorld(true);
  // Edge lines are the engine's job: this render says what the surfaces
  // look like.
  group.traverse((o) => {
    const l = o as THREE.Line;
    if (l.isLine || (o as THREE.LineSegments).isLineSegments) o.visible = false;
  });

  const scene = new THREE.Scene();
  scene.add(group);
  scene.add(new THREE.AmbientLight(0xffffff, 0.55));
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(-1, 1, 2);
  scene.add(key);

  const radius = Math.max(
    1, new THREE.Box3().setFromObject(group).getSize(new THREE.Vector3()).length() / 2);
  const back = radius * 4 + 1;
  const angle = parseAngle(angleText) ?? { lat: 30, long: 45 };
  const dir = orbitFromAngle(angle, 1);
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, back + radius * 4);
  camera.position.set(dir.x * back, dir.y * back, dir.z * back);
  camera.up.set(0, 1, 0);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);

  const half = halfExtents(group, camera);
  camera.left = -half.x; camera.right = half.x;
  camera.top = half.y; camera.bottom = -half.y;
  camera.updateProjectionMatrix();

  renderer.render(scene, camera);
  const url = renderer.domElement.toDataURL('image/png');

  scene.remove(group);
  group.traverse((o) => {
    const m = o as THREE.Mesh;
    m.geometry?.dispose?.();
  });
  return url;
}

async function main() {
  const work = await (await fetch(`${SINK}/work.json`)).json();
  const { parts, px, angle } = work as { parts: string[]; px: number; angle: string };

  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = px;
  document.body.appendChild(canvas);
  const renderer = new THREE.WebGLRenderer({
    canvas, antialias: true, alpha: true, preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(1);
  renderer.setSize(px, px, false);
  renderer.setClearColor(0x000000, 0);

  const loader = makeLoader();
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i]!;
    window.shotProgress = `${i + 1}/${parts.length} ${part}`;
    try {
      const url = await drawOne(renderer, loader, part, angle);
      await fetch(`${SINK}/shot/${part}.png`, { method: 'POST', body: url });
    } catch (e) {
      console.error(`shot ${part}: ${String(e)}`);
    }
  }
  window.shotProgress = 'done';
  await fetch(`${SINK}/done`, { method: 'POST', body: '' });
}

main().catch((e) => { window.shotError = String(e?.stack ?? e); });
