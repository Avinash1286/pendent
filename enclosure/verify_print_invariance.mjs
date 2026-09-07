// Run once with --baseline before an internal-only rebuild; then without it.
// Binary SHA and canonical triangle geometry are compared independently.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const file=path.join(root,'print-invariance.json');
const sha=data=>crypto.createHash('sha256').update(data).digest('hex');
const parts=fs.readdirSync(root).filter(name=>name.endsWith('.stl')).sort();
assert.equal(parts.length,8);
const snapshot=Object.fromEntries(parts.map(name=>{
  const data=fs.readFileSync(path.join(root,name)),count=data.readUInt32LE(80);
  assert.equal(data.length,84+50*count);
  const triangles=[];
  for(let i=0;i<count;i++){
    const vertices=[];
    for(let v=0;v<3;v++)vertices.push([0,1,2].map(axis=>data.readFloatLE(84+i*50+12+v*12+axis*4).toFixed(5)).join(','));
    triangles.push(vertices.sort().join('|'));
  }
  return [name,{bytes:data.length,triangles:count,sha256:sha(data),canonical_geometry_sha256:sha(triangles.sort().join('\n'))}];
}));
if(process.argv.includes('--baseline')){
  assert.ok(!fs.existsSync(file),'Do not overwrite the original checkpoint.');
  fs.writeFileSync(file,JSON.stringify({scope:'A03 internal component sync; no print geometry changes authorized or intended',canonical_method:'Sort triangles and vertices; XYZ rounded to 0.00001mm; normals/order/header ignored',baseline:snapshot,physical_qualification:false},null,2)+'\n');
  console.log('Recorded eight baseline STL signatures.');
}else{
  const report=JSON.parse(fs.readFileSync(file,'utf8'));
  report.current=snapshot;
  report.byte_identical=parts.every(name=>snapshot[name].sha256===report.baseline[name].sha256);
  report.geometry_identical=parts.every(name=>snapshot[name].canonical_geometry_sha256===report.baseline[name].canonical_geometry_sha256);
  report.actual_print_mesh_changes=parts.filter(name=>snapshot[name].canonical_geometry_sha256!==report.baseline[name].canonical_geometry_sha256);
  fs.writeFileSync(file,JSON.stringify(report,null,2)+'\n');
  assert.ok(report.geometry_identical,'An actual print mesh changed; investigate before release.');
  console.log(JSON.stringify({byte_identical:report.byte_identical,geometry_identical:report.geometry_identical,actual_print_mesh_changes:report.actual_print_mesh_changes}));
}
