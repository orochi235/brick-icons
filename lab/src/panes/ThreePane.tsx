import { Suspense, useEffect, useMemo, useState } from 'react';
import { Canvas, useLoader, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { LDrawLoader } from 'three/examples/jsm/loaders/LDrawLoader.js';
import { LDrawConditionalLineMaterial }
  from 'three/examples/jsm/materials/LDrawConditionalLineMaterial.js';
import * as THREE from 'three';
import { angleFromOrbit, formatAngle, orbitFromAngle, parseAngle } from '@lab/panes/orbit';

// A fixed camera distance frames one part size and misframes every other, so
// the distance comes from the model's own bounding sphere.
const FILL = 2.6;
const RADIUS = 240;
const LIBRARY = '/ldraw/';
const PARTS = `${LIBRARY}parts/`;

function Part({ part, onRadius }: { part: string; onRadius: (r: number) => void }) {
  // A BARE filename against `path`, never a path against the library root: a
  // subfile reference is resolved relative to its parent's name, so any
  // directory in the name is folded into the child's and then doubled by the
  // loader's own `parts/` search (`/ldraw/parts/parts/s/3001s01.dat`).
  const model = useLoader(LDrawLoader, `${part}.dat`, (loader) => {
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
    // LDraw's Y axis points down: studs are at negative Y. Without this flip
    // the part hangs upside down and every angle reads inverted.
    group.rotation.x = Math.PI;
    const box = new THREE.Box3().setFromObject(group);
    const centre = box.getCenter(new THREE.Vector3());
    group.position.sub(centre);
    return { group, radius: box.getSize(new THREE.Vector3()).length() / 2 };
  }, [model]);

  useEffect(() => { onRadius(object.radius); }, [object, onRadius]);

  return <primitive object={object.group} />;
}

function Camera({ angle, radius, onSettle }:
                { angle: string; radius: number; onSettle: (a: string) => void }) {
  const { camera } = useThree();

  useEffect(() => {
    const parsed = parseAngle(angle);
    if (!parsed) return;
    const p = orbitFromAngle(parsed, radius);
    camera.position.set(p.x, p.y, p.z);
    camera.lookAt(0, 0, 0);
  }, [angle, radius, camera]);

  return (
    <OrbitControls
      enablePan={false}
      // `end` fires when the drag stops, which is when LDView is worth firing.
      onEnd={() => onSettle(formatAngle(angleFromOrbit(camera.position)))}
    />
  );
}

export interface ThreePaneProps {
  part: string;
  angle: string;
  onSettle: (angle: string) => void;
}

export function ThreePane({ part, angle, onSettle }: ThreePaneProps) {
  const [radius, setRadius] = useState(RADIUS);
  if (!part.trim()) return <p className="three-empty">no part chosen</p>;
  return (
    <Canvas camera={{ fov: 35, near: 1, far: 20000 }}>
      <ambientLight intensity={0.7} />
      <directionalLight position={[-1, 1, 2]} intensity={1.2} />
      <Suspense fallback={null}>
        <Part part={part} onRadius={(r) => setRadius(Math.max(1, r) * FILL)} />
      </Suspense>
      <Camera angle={angle} radius={radius} onSettle={onSettle} />
    </Canvas>
  );
}
