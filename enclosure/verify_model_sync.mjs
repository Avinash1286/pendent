// Independently check the exported GLB's package transforms against the source snapshot.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const read=name=>fs.readFileSync(path.join(root,name));
const placements=JSON.parse(read('pcb-placement-reference.json'));
const bodies=JSON.parse(read('component-body-reference.json')).bodies;
const data=read('aura-device.glb');
const gltf=JSON.parse(data.subarray(20,20+data.readUInt32LE(12)).toString());
const checks=[];
for(const node of gltf.nodes){
  const ref=node.extras?.hardware_reference;
  if(!ref)continue;
  const pos=placements[ref];assert.ok(pos,'Unmapped GLB reference: '+ref);
  const t=node.translation||[0,0,0],q=node.rotation||[0,0,0,1];
  const x=t[0]*1000,y=-t[2]*1000;
  assert.ok(Math.abs(x-pos.x)<.0001&&Math.abs(y-pos.y)<.0001,'Wrong exported XY: '+ref);
  const angle=pos.r*Math.PI/360,dot=Math.abs(q[1]*Math.sin(angle)+q[3]*Math.cos(angle));
  assert.ok(Math.abs(dot-1)<.00001&&Math.abs(q[0])+Math.abs(q[2])<.00001,'Wrong exported package rotation: '+ref);
  const entry={ref,node:node.name,xy_mm:[x,y],rotation_matches:true};
  if(node.name.startsWith('Power_Envelope_')||node.name.startsWith('Passive_Reference_')||node.name.startsWith('Diode_Reference_')){
    const spec=bodies[ref],dims=spec.body_nominal_mm||spec.nominal_mm;
    const ranges=gltf.meshes[node.mesh].primitives.map(p=>gltf.accessors[p.attributes.POSITION]);
    const actual=[0,2,1].map(axis=>(Math.max(...ranges.map(a=>a.max[axis]))-Math.min(...ranges.map(a=>a.min[axis])))*1000);
    actual.forEach((v,i)=>assert.ok(Math.abs(v-dims[i])<.0001,'Wrong exported package dimension: '+ref));
    assert.ok(Math.abs(t[1]*1000-(.65+dims[2]/2))<.0001,'Wrong exported package height: '+ref);
    Object.assign(entry,{nominal_body_mm:actual,dimensions_match:true});
  }
  checks.push(entry);
}
for(const ref of ['C7','C8','C10','C18','R22','R23','D1','Q1','R7','C17'])assert.equal(checks.filter(c=>c.ref===ref).length,1,'Missing or duplicate focused GLB package: '+ref);
const report={revision:'A03',ok:true,glb_sha256:crypto.createHash('sha256').update(data).digest('hex'),package_transform_count:checks.length,dimension_check_count:checks.filter(c=>c.dimensions_match).length,coordinate_convention:'glTF X=CAD X; glTF Y=CAD Z; glTF Z=−CAD Y. Units converted to millimetres for checking.',physical_qualification:false,checks};
fs.writeFileSync(path.join(root,'model-sync-audit.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({ok:report.ok,package_transform_count:report.package_transform_count,dimension_check_count:report.dimension_check_count,glb_sha256:report.glb_sha256}));
