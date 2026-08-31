import { Suspense, useEffect, useMemo, useRef } from 'react';
import { Canvas, useLoader, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { LDrawLoader } from 'three/examples/jsm/loaders/LDrawLoader.js';
import * as THREE from 'three';
import { angleFromOrbit, formatAngle, orbitFromAngle, parseAngle } from '@lab/panes/orbit';

const RADIUS = 240;

function Part({ part }: { part: string }) {
  const model = useLoader(LDrawLoader, `/ldraw/parts/${part}.dat`, (loader) => {
    // LDrawLoader resolves subfile references against this root. Not in its
    // published typings, so the cast is the only way to reach it.
    (loader as unknown as { setPartsLibraryPath: (p: string) => void })
      .setPartsLibraryPath('/ldraw/');
  });

  const object = useMemo(() => {
    const group = model.clone();
    // LDraw's Y axis points down: studs are at negative Y. Without this flip
    // the part hangs upside down and every angle reads inverted.
    group.rotation.x = Math.PI;
    const box = new THREE.Box3().setFromObject(group);
    const centre = box.getCenter(new THREE.Vector3());
    group.position.sub(centre);
    return group;
  }, [model]);

  return <primitive object={object} />;
}

function Camera({ angle, onSettle }: { angle: string; onSettle: (a: string) => void }) {
  const { camera } = useThree();

  useEffect(() => {
    const parsed = parseAngle(angle);
    if (!parsed) return;
    const p = orbitFromAngle(parsed, RADIUS);
    camera.position.set(p.x, p.y, p.z);
    camera.lookAt(0, 0, 0);
  }, [angle, camera]);

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
  if (!part.trim()) return <p className="three-empty">no part chosen</p>;
  return (
    <Canvas camera={{ fov: 35, near: 1, far: 4000 }}>
      <ambientLight intensity={0.7} />
      <directionalLight position={[-1, 1, 2]} intensity={1.2} />
      <Suspense fallback={null}>
        <Part part={part} />
      </Suspense>
      <Camera angle={angle} onSettle={onSettle} />
    </Canvas>
  );
}
