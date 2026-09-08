/** Shaded orthographic renders of a list of parts, for `scripts/shot-sink.py`.
 *
 * The camera is `ThreePane`'s: direction from `orbitFromAngle`, projection
 * orthographic, and the model keeps the position its part file gives it.
 * LDView cannot render orthographic at all, which is why this exists -- the
 * `ldview` slot beside it stays, so the two can be compared.
 *
 * One WebGL context draws the whole list: a page load per part costs more than
 * the render.
 *
 * The frame is the engine's own: `viewBasis` and `fitAffine` are `hlr`'s, so a
 * part sits in the square canvas under one uniform scale, centred, the way the
 * CLI centres it in a viewBox. Each render POSTs the `.fit.json` that names
 * that map, so a point in the reference and a point in our SVG can be carried
 * to each other through the world. Framing from the part alone -- never from
 * what our engine drew -- is what lets an engine change leave the bake standing.
 */
import * as THREE from 'three';
import { LDrawLoader } from 'three/examples/jsm/loaders/LDrawLoader.js';
import { LDrawConditionalLineMaterial }
  from 'three/examples/jsm/materials/LDrawConditionalLineMaterial.js';
import { orbitFromAngle, parseAngle } from '@lab/panes/orbit';
import { HOME } from '@lab/panes/camera';
import {
  fitAffine, frustum, projectPoint, toThree, viewBasis, type RenderFit,
} from '@lab/panes/viewport';

const SINK = new URLSearchParams(location.search).get('sink') ?? '';
const LIBRARY = `${SINK}/ldraw/`;
const PARTS = `${LIBRARY}parts/`;

declare global {
  interface Window { shotProgress?: string; shotError?: string }
}

/** The projected A/B box of every drawn vertex.
 *
 * The engine fits its canvas to the point cloud, not to a world-axis box: at
 * iso an AABB projects wider than the part inside it, and by a different
 * amount per part, so a box fit is a per-part zoom error nothing downstream
 * can undo. Vertices are read in the pane's turned world and dotted with the
 * turned basis, which is the LDraw projection -- a rotation shared by both
 * sides of a dot product cancels.
 */
function projectedBox(group: THREE.Object3D, basis: RenderFit) {
  const right = toThree(basis.right), up = toThree(basis.up);
  const v = new THREE.Vector3();
  let a0 = Infinity, b0 = Infinity, a1 = -Infinity, b1 = -Infinity;
  group.traverse((o) => {
    const mesh = o as THREE.Mesh;
    const pos = mesh.isMesh ? mesh.geometry?.getAttribute('position') : null;
    if (!pos) return;
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos as THREE.BufferAttribute, i)
        .applyMatrix4(mesh.matrixWorld);
      const [a, b] = projectPoint({ right, up }, v.x, v.y, v.z);
      if (a < a0) a0 = a;
      if (a > a1) a1 = a;
      if (b < b0) b0 = b;
      if (b > b1) b1 = b;
    }
  });
  return Number.isFinite(a0) ? { a0, b0, a1, b1 } : { a0: 0, b0: 0, a1: 1, b1: 1 };
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
  part: string, angleText: string, px: number, margin: number,
): Promise<{ url: string; fit: RenderFit }> {
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
  const basis = viewBasis(angle);
  const fit: RenderFit = {
    ...basis,
    ...fitAffine(projectedBox(group, basis as RenderFit), px, px, margin),
    width: px, height: px,
  };

  // The eye sits on the view axis through the WORLD origin, which is the point
  // the projection is about; the frustum carries the offset to the part.
  const dir = orbitFromAngle(angle, 1);
  const bounds = frustum(fit, { width: px, height: px }, HOME);
  const up = toThree(fit.up);
  const camera = new THREE.OrthographicCamera(
    bounds.left, bounds.right, bounds.top, bounds.bottom, 0.1, back + radius * 4);
  camera.position.set(dir.x * back, dir.y * back, dir.z * back);
  camera.up.set(up[0], up[1], up[2]);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  camera.updateProjectionMatrix();

  renderer.render(scene, camera);
  const url = renderer.domElement.toDataURL('image/png');

  scene.remove(group);
  group.traverse((o) => {
    const m = o as THREE.Mesh;
    m.geometry?.dispose?.();
  });
  return { url, fit };
}

async function main() {
  const work = await (await fetch(`${SINK}/work.json`)).json();
  const { parts, px, angle, margin } = work as
    { parts: string[]; px: number; angle: string; margin: number };

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
      const { url, fit } = await drawOne(renderer, loader, part, angle, px, margin);
      await fetch(`${SINK}/shot/${part}.png`, { method: 'POST', body: url });
      await fetch(`${SINK}/fit/${part}.fit.json`,
                  { method: 'POST', body: JSON.stringify(fit) });
    } catch (e) {
      console.error(`shot ${part}: ${String(e)}`);
    }
  }
  window.shotProgress = 'done';
  await fetch(`${SINK}/done`, { method: 'POST', body: '' });
}

main().catch((e) => { window.shotError = String(e?.stack ?? e); });
