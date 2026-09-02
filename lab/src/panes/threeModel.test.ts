import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { fattenLines, paint } from '@lab/panes/threeModel';

function segments(color = 0x123456): THREE.LineSegments {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(
    [0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 1, 0], 3));
  return new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color }));
}

/** What LDrawLoader builds for a type-5 line: a LineSegments that draws only
 *  where the edge is a silhouette, flagged so nothing else touches it. */
function conditional(): THREE.LineSegments {
  const line = segments() as THREE.LineSegments & { isConditionalLine: boolean };
  line.isConditionalLine = true;
  return line;
}

function mesh(): THREE.Mesh {
  return new THREE.Mesh(new THREE.BoxGeometry(),
                        new THREE.MeshStandardMaterial({ color: 0xff0000 }));
}

describe('fattenLines', () => {
  it('replaces a hairline with one the width can reach', () => {
    const group = new THREE.Group();
    group.add(segments());
    const made = fattenLines(group);

    expect(made).toHaveLength(1);
    const kinds = group.children.map((c) => c.type);
    expect(kinds).toContain('LineSegments2');
    expect(kinds).not.toContain('LineSegments');
  });

  it("draws in the engines' stroke colour, not the one LDraw gave the edge", () => {
    const group = new THREE.Group();
    group.add(segments(0x00ff00));
    expect(fattenLines(group)[0]!.color.getHex()).toBe(0x000000);
    expect(fattenLines((() => { const g = new THREE.Group();
      g.add(segments()); return g; })(), 0x123456)[0]!.color.getHex()).toBe(0x123456);
  });

  it('leaves conditional lines alone: they have no fat equivalent', () => {
    const group = new THREE.Group();
    group.add(conditional());
    expect(fattenLines(group)).toHaveLength(0);
    expect(group.children[0]!.type).toBe('LineSegments');
  });

  it('reaches lines nested under subfile groups', () => {
    const group = new THREE.Group();
    const sub = new THREE.Group();
    sub.add(segments());
    group.add(sub);
    expect(fattenLines(group)).toHaveLength(1);
    expect(sub.children[0]!.type).toBe('LineSegments2');
  });

  it('keeps the line where it was', () => {
    const group = new THREE.Group();
    const line = segments();
    line.position.set(5, -3, 2);
    line.updateMatrix();
    group.add(line);
    fattenLines(group);
    expect(group.children[0]!.position.toArray()).toEqual([5, -3, 2]);
  });
});

describe('paint', () => {
  it('imposes the render colour on the faces', () => {
    const group = new THREE.Group();
    group.add(mesh());
    paint(group, 0x9d9d9d, 1);
    expect(((group.children[0] as THREE.Mesh).material as THREE.MeshStandardMaterial)
      .color.getHex()).toBe(0x9d9d9d);
  });

  it('leaves the LDraw colours alone when the render imposed none', () => {
    const group = new THREE.Group();
    group.add(mesh());
    paint(group, null, 1);
    expect(((group.children[0] as THREE.Mesh).material as THREE.MeshStandardMaterial)
      .color.getHex()).toBe(0xff0000);
  });

  it('only turns on transparency for an opacity that needs it', () => {
    const group = new THREE.Group();
    group.add(mesh());
    paint(group, null, 1);
    expect((group.children[0] as THREE.Mesh).material).toHaveProperty('transparent', false);
    paint(group, null, 0.4);
    expect((group.children[0] as THREE.Mesh).material)
      .toMatchObject({ transparent: true, opacity: 0.4 });
  });

  it('does not paint the edges, which are not faces', () => {
    const group = new THREE.Group();
    group.add(segments(0x000000));
    paint(group, 0x9d9d9d, 1);
    expect(((group.children[0] as THREE.LineSegments).material as THREE.LineBasicMaterial)
      .color.getHex()).toBe(0x000000);
  });
});
