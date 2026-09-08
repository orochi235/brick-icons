/** Turning a loaded LDraw model into what the pane draws.
 *
 * Split out of `ThreePane` because the pane needs a WebGL context and this
 * does not: geometry and materials are built on the CPU, so the swap below is
 * testable and the JSX around it stays thin.
 */
import * as THREE from 'three';
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';

function materialsOf(object: THREE.Mesh | THREE.LineSegments): THREE.Material[] {
  return Array.isArray(object.material) ? object.material : [object.material];
}

/** Swap three's hairlines for lines that can take a width.
 *
 * WebGL ignores `LineBasicMaterial.linewidth` -- every edge draws one pixel
 * wide whatever it is set to -- so matching `--line-width` needs the
 * screen-space line shader instead. Conditional lines keep their own material,
 * which is what draws them only where the edge is a silhouette; there is no
 * fat equivalent, so those stay hairlines.
 *
 * The color is the engines' stroke, not the one LDraw gave the edge: the pane
 * is here to be compared against a line drawing, and an edge tinted to match
 * the part reads as a shading artefact next to one that is not.
 *
 * Returns the materials it made, for the caller to size: a `LineMaterial`
 * works in clip space and draws nothing until it is told the pixel resolution.
 */
export function fattenLines(group: THREE.Object3D,
                            color = 0x000000): LineMaterial[] {
  const swaps: THREE.LineSegments[] = [];
  group.traverse((child) => {
    const line = child as THREE.LineSegments & { isConditionalLine?: boolean };
    if (line.isLineSegments && !line.isConditionalLine && line.parent) swaps.push(line);
  });
  return swaps.map((line) => {
    const material = new LineMaterial({ color, linewidth: 1 });
    const fat = new LineSegments2(
      new LineSegmentsGeometry().fromLineSegments(line), material);
    fat.applyMatrix4(line.matrix);
    line.parent!.add(fat);
    line.parent!.remove(line);
    return material;
  });
}

/** The render's part color and face opacity, on the model's meshes. A null
 *  color leaves the part in the colors its LDraw file gave it. */
export function paint(group: THREE.Object3D, color: number | null,
                      opacity: number): void {
  group.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (!mesh.isMesh) return;
    for (const m of materialsOf(mesh)) {
      if (color !== null) (m as THREE.MeshStandardMaterial).color?.setHex(color);
      m.transparent = opacity < 1;
      m.opacity = opacity;
    }
  });
}
