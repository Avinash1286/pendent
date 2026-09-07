import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { assemblyPose, partForName, travel } from './assembly-model.mjs';
import environmentSize from '../assets/studio-environment.json';

// The A03 website and film use the same part grouping and local Y separation.
// The root's 90° X rotation converts Blender's thickness axis into screen depth.
// Hyperframes may hoist local script assets. Initialize after the composition DOM exists.
window.__auraAssemblyInit=function () {
const canvas=document.getElementById('assembly-canvas');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:true,preserveDrawingBuffer:true});
renderer.setPixelRatio(1);
renderer.setSize(1920,860,false);
renderer.setClearColor(0x101112,0);
renderer.outputColorSpace=THREE.SRGBColorSpace;
renderer.toneMapping=THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure=1.2;
const scene=new THREE.Scene();
const camera=new THREE.PerspectiveCamera(31,1920/860,.01,100);
scene.environmentIntensity=.75;
scene.add(new THREE.HemisphereLight(0xf4f1eb,0x293038,1.2));
const key=new THREE.DirectionalLight(0xffffff,2.8);key.position.set(-3,4,4);scene.add(key);
const rim=new THREE.DirectionalLight(0xf5dac5,1.5);rim.position.set(4,1,-3);scene.add(rim);
const fill=new THREE.DirectionalLight(0xdce5f5,.8);fill.position.set(-4,0,-2);scene.add(fill);
let model,pivot,diameter;
const bases=new Map();
function renderAt(time) {
  if (!model) return;
  // Hidden clips need no repeated draw. A seek into the shot always reconstructs it.
  if ((time<21 || time>29.6) && window.__auraAssemblyProof) return;
  const pose=assemblyPose(time);
  bases.forEach((base,object)=>{
    object.position.copy(base);
    object.position.y=base.y+travel[partForName(object.name)]*diameter*pose.progress;
  });
  pivot.rotation.set(pose.pitch,pose.yaw,pose.roll);
  camera.position.set(.05,.08,pose.distance);camera.lookAt(0,0,0);
  renderer.render(scene,camera);
  window.__auraAssemblyProof={time,...pose,parts:bases.size};
}
window.__auraAssemblyRender=renderAt;
window.addEventListener('hf-seek',event=>renderAt(event.detail.time));
const environmentLoader=new THREE.FileLoader().setResponseType('arraybuffer');
window.__auraAssemblyReady=Promise.all([
  new GLTFLoader().loadAsync('assets/aura-device.glb'),
  environmentLoader.loadAsync('assets/studio-environment.bin')
]).then(([gltf,pixels])=>{
  const environment=new THREE.DataTexture(new Uint16Array(pixels),environmentSize.width,environmentSize.height,THREE.RGBAFormat,THREE.HalfFloatType);
  environment.mapping=THREE.CubeUVReflectionMapping;
  environment.colorSpace=THREE.LinearSRGBColorSpace;
  environment.minFilter=THREE.LinearFilter;environment.magFilter=THREE.LinearFilter;
  environment.needsUpdate=true;scene.environment=environment;
  model=gltf.scene;model.rotation.x=Math.PI/2;
  const box=new THREE.Box3().setFromObject(model);
  const size=box.getSize(new THREE.Vector3());
  const center=box.getCenter(new THREE.Vector3());
  diameter=Math.max(size.x,size.y,size.z);
  const scale=2.15/diameter;
  model.scale.multiplyScalar(scale);model.position.sub(center.multiplyScalar(scale));
  model.children.forEach(object=>bases.set(object,object.position.clone()));
  pivot=new THREE.Group();pivot.add(model);scene.add(pivot);
  renderAt(window.__hfThreeTime||0);
});
};
