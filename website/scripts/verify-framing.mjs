import fs from 'node:fs';
import assert from 'node:assert/strict';
import ts from 'typescript';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const source = fs.readFileSync(
  new URL('../components/assembly-model.ts', import.meta.url),
  'utf8',
);
const js = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const { partForName, separation, assemblyCameraDistance } = await import(
  `data:text/javascript;base64,${Buffer.from(js).toString('base64')}`
);
const bytes = fs.readFileSync(
  new URL('../public/product/aura.glb', import.meta.url),
);
const gltf = await new GLTFLoader().parseAsync(
  bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
  '',
);
const model = gltf.scene;
model.rotation.x = Math.PI / 2;
const box = new THREE.Box3().setFromObject(model);
const dimensions = box.getSize(new THREE.Vector3());
const size = Math.max(...dimensions.toArray());
const scale = 2.15 / size;
model.scale.multiplyScalar(scale);
model.position.sub(box.getCenter(new THREE.Vector3()).multiplyScalar(scale));
const pivot = new THREE.Group();
pivot.add(model);
const bases = new Map(
  model.children.map((object) => [object, object.position.clone()]),
);
const categories = new Set(
  model.children.map((object) => partForName(object.name)),
);
for (const id of ['shell', 'controls', 'board', 'battery', 'back'])
  assert.ok(categories.has(id), `Missing selectable layer ${id}`);
let cases = 0;
let maximumFrameFraction = 0;
for (const [width, height] of [
  [1100, 620],
  [768, 540],
  [390, 470],
  [320, 470],
]) {
  const aspect = width / height;
  for (const p of [0, 0.25, 0.5, 0.75, 1]) {
    for (const preset of ['perspective', 'front', 'profile']) {
      bases.forEach((base, object) => {
        object.position.y =
          base.y + separation(partForName(object.name), p, size);
      });
      pivot.rotation.set(
        -0.07,
        preset === 'front'
          ? 0
          : preset === 'profile'
            ? -Math.PI / 2
            : -0.27 - p * 0.7,
        0.04,
      );
      pivot.updateMatrixWorld(true);
      const camera = new THREE.PerspectiveCamera(32, aspect, 0.01, 100);
      camera.position
        .set(0.15, 0.12, 4.2)
        .setLength(assemblyCameraDistance(aspect, p));
      camera.lookAt(0, 0, 0);
      camera.updateMatrixWorld(true);
      let maximum = 0;
      const point = new THREE.Vector3();
      model.traverse((object) => {
        if (!object.isMesh) return;
        const positions = object.geometry.attributes.position;
        for (let i = 0; i < positions.count; i++) {
          point
            .fromBufferAttribute(positions, i)
            .applyMatrix4(object.matrixWorld)
            .project(camera);
          assert.ok(point.z > -1 && point.z < 1, 'Geometry behind camera');
          maximum = Math.max(maximum, Math.abs(point.x), Math.abs(point.y));
        }
      });
      assert.ok(
        maximum < 0.98,
        `Clipped product: ${width}×${height}, ${preset}, ${p}: ${maximum}`,
      );
      maximumFrameFraction = Math.max(maximumFrameFraction, maximum);
      cases++;
    }
  }
}
console.log(
  JSON.stringify(
    {
      status: 'passed',
      cameraCases: cases,
      maximumFrameFraction: +maximumFrameFraction.toFixed(3),
      selectableLayers: [...categories],
      scope: 'Model geometry and camera framing; not browser interaction QA',
    },
    null,
    2,
  ),
);
