import fs from 'node:fs';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const bytes = fs.readFileSync(
  new URL('../public/product/aura.glb', import.meta.url),
);
const data = bytes.buffer.slice(
  bytes.byteOffset,
  bytes.byteOffset + bytes.byteLength,
);
const gltf = await new GLTFLoader().parseAsync(data, '');
gltf.scene.rotation.x = Math.PI / 2;
const bbox = new THREE.Box3().setFromObject(gltf.scene);
const size = bbox.getSize(new THREE.Vector3());
assert.ok(size.x > 0.029 && size.x < 0.033, `Width ${size.x}`);
assert.ok(size.y > 0.04 && size.y < 0.049, `Height with loop ${size.y}`);
assert.ok(size.z > 0.009 && size.z < 0.0105, `A02 depth ${size.z}`);
const names = [];
let meshCount = 0;
gltf.scene.traverse((object) => {
  names.push(object.name);
  if (object.isMesh) {
    meshCount++;
    assert.ok(object.position.toArray().every(Number.isFinite));
    assert.ok(object.geometry.attributes.position.count > 0);
  }
});
assert.ok(names.includes('Housing_Front'), 'Front shell is missing');
assert.ok(names.includes('Housing_Back'), 'Back shell is missing');
assert.ok(
  names.some((name) => /Battery/i.test(name)),
  'Battery is missing',
);
assert.ok(
  names.some((name) => /PCB/i.test(name)),
  'PCB is missing',
);
console.log(
  JSON.stringify(
    {
      status: 'passed',
      dimensionsMM: size.toArray().map((v) => +(v * 1000).toFixed(2)),
      meshCount,
      checks: [
        'glTF parses',
        'orientation and physical dimensions',
        'front/rear/battery/PCB present',
        'finite mesh transforms',
      ],
    },
    null,
    2,
  ),
);
