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
const glbHash=crypto.createHash('sha256').update(data).digest('hex');
const proof=JSON.parse(read('c18-symmetry-audit.json'));
assert.equal(proof.ok,true);assert.equal(proof.reference,'C18');assert.equal(proof.mpn,'C0402C104K4RACTU');
assert.ok(proof.meshes.some(m=>m.path==='aura-device.glb'&&m.glb_sha256===glbHash&&m.triangle_connectivity_half_turn_invariant&&m.triangle_associated_normals_half_turn_invariant));
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
  const exact=Math.abs(dot-1)<.00001&&Math.abs(q[0])+Math.abs(q[2])<.00001;
  if(!exact){
    assert.equal(ref,'C18','Unexpected exported rotation deviation: '+ref);
    assert.equal(bodies[ref].mpn,proof.mpn);assert.equal(node.extras.manufacturer_part_number,proof.mpn);
    assert.equal(pos.r,270);assert.equal(proof.canonical_visual_rotation_degrees,90);
    const displayAngle=Math.PI/4;
    assert.ok(Math.abs(Math.abs(q[1]*Math.sin(displayAngle)+q[3]*Math.cos(displayAngle))-1)<.00001&&Math.abs(q[0])+Math.abs(q[2])<.00001,'C18 is not at the proven canonical body orientation');
  }
  const entry={ref,node:node.name,xy_mm:[x,y],rotation_match_kind:exact?'exact':'symmetry-equivalent',source_rotation_degrees:pos.r,model_rotation_degrees:Math.round(2*Math.atan2(q[1],q[3])*180/Math.PI*1e6)/1e6};
  if(!exact)Object.assign(entry,{symmetry_evidence:'c18-symmetry-audit.json',pcb_pin_rotation_exempted:false});
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
const exactCount=checks.filter(c=>c.rotation_match_kind==='exact').length,symmetryCount=checks.filter(c=>c.rotation_match_kind==='symmetry-equivalent').length;
assert.equal(exactCount,55);assert.equal(symmetryCount,1);
const report={revision:'A03',ok:true,glb_sha256:glbHash,placement_reference_sha256:crypto.createHash('sha256').update(read('pcb-placement-reference.json')).digest('hex'),symmetry_audit_sha256:crypto.createHash('sha256').update(read('c18-symmetry-audit.json')).digest('hex'),package_transform_count:checks.length,exact_rotation_count:exactCount,symmetry_equivalent_rotation_count:symmetryCount,unintended_deviation_count:0,dimension_check_count:checks.filter(c=>c.dimensions_match).length,coordinate_convention:'glTF X=CAD X; glTF Y=CAD Z; glTF Z=−CAD Y. Units converted to millimetres for checking.',physical_qualification:false,checks};
fs.writeFileSync(path.join(root,'model-sync-audit.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({ok:report.ok,package_transform_count:report.package_transform_count,exact_rotation_count:exactCount,symmetry_equivalent_rotation_count:symmetryCount,unintended_deviation_count:0,dimension_check_count:report.dimension_check_count,glb_sha256:report.glb_sha256}));
