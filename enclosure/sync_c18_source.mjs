// Final native C18 orientation correction; never edits a native KiCad file.
// Run --apply, then `npm run build` in ../hardware, then --verify.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const hardware=path.resolve(root,'../hardware');
const override=path.join(hardware,'src/placement-overrides.json');
const manifest=path.join(hardware,'output/design-manifest.json');
const reportPath=path.join(root,'c18-source-sync.json');
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const signature=parts=>sha(JSON.stringify(parts.map(p=>({ref:p.ref,x:p.x,y:p.y,r:p.ref==='C18'?null:p.r||0,mpn:p.mpn,fp:p.fp,side:p.layer||'top',pins:p.pins,nc:p.nc||[]})).sort((a,b)=>a.ref.localeCompare(b.ref))));
if(process.argv.includes('--apply')){
  assert.ok(!fs.existsSync(reportPath),'Do not overwrite the orientation correction checkpoint.');
  const raw=fs.readFileSync(override,'utf8'),before=JSON.parse(raw);
  assert.deepEqual(before.C18,{x:-2.05,y:-13.3,r:90});
  const afterRaw=raw.replace(/("C18"\s*:\s*\{[^}]*"r"\s*:\s*)90\b/,(_,prefix)=>prefix+'270');
  const after=JSON.parse(afterRaw);
  assert.deepEqual(after.C18,{x:-2.05,y:-13.3,r:270});
  assert.deepEqual({...after,C18:{...after.C18,r:90}},before,'Unexpected source mutation');
  const previous=JSON.parse(fs.readFileSync(manifest,'utf8'));
  assert.equal(previous.parts.length,61);
  const report={scope:'C18 nonpolar capacitor native/source pin-orientation correction only',native_files_edited_by_this_script:[],source_before_sha256:sha(raw),source_after_sha256:sha(afterRaw),before:before.C18,after:after.C18,placement_and_pinmap_signature_before:signature(previous.parts),logical_netlist_sha256_before:sha(fs.readFileSync(path.join(hardware,'output/logical-netlist.json'))),verified:false};
  fs.writeFileSync(override,afterRaw);
  fs.writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');
  console.log('Applied only C18 r90→270; now run the authored placement build.');
}else if(process.argv.includes('--verify')){
  const report=JSON.parse(fs.readFileSync(reportPath,'utf8'));
  const current=JSON.parse(fs.readFileSync(manifest,'utf8'));
  const c18=current.parts.find(p=>p.ref==='C18');
  assert.equal(current.parts.length,61);
  assert.deepEqual({x:c18.x,y:c18.y,r:c18.r},report.after);
  assert.equal(signature(current.parts),report.placement_and_pinmap_signature_before,'Another placement, MPN, footprint or logical pin map changed');
  assert.equal(sha(fs.readFileSync(path.join(hardware,'output/logical-netlist.json'))),report.logical_netlist_sha256_before,'Logical netlist changed');
  assert.equal(sha(fs.readFileSync(override)),report.source_after_sha256,'Source changed during build');
  Object.assign(report,{verified:true,components:61,other_package_placements_unchanged:true,all_logical_pinmaps_unchanged:true,logical_netlist_unchanged:true,manifest_sha256:sha(fs.readFileSync(manifest))});
  fs.writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
}else throw new Error('Choose --apply or --verify');
