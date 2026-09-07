import fs from 'node:fs';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {nodes} from './restore-mic-land.mjs';

const {parts,boardSpec}=JSON.parse(fs.readFileSync('output/design-manifest.json','utf8'));
const filename='output/aura-placement.kicad_pcb',board=fs.readFileSync(filename,'utf8');
const footprints=nodes(board,'footprint');
let checkedPins=0;
for(const part of parts){
 const fp=footprints.find(f=>f.text.includes(`(property "Reference" "${part.ref}"`));
 assert.ok(fp,`Exported footprint ${part.ref}`);
 const pads=nodes(fp.text,'pad');
 for(const [pin,net] of Object.entries(part.pins)){
  const matches=pads.filter(p=>p.text.startsWith(`(pad "${pin}" `));
  assert.ok(matches.length,`${part.ref}.${pin} pad exists`);
  for(const pad of matches)assert.ok(pad.text.includes(`"${net}")`),`${part.ref}.${pin} retains ${net}`);
  checkedPins++;
 }
 for(const pin of part.nc||[])for(const pad of pads.filter(p=>p.text.startsWith(`(pad "${pin}" `)))
  assert.ok(!/\(net [1-9]\d*/.test(pad.text),`${part.ref}.${pin} remains unconnected by design`);
}
assert.match(board,/\(thickness 0\.8\)/,'Authored board thickness retained');
for(const ref of ['MK1','MK2']){
 const fp=footprints.find(f=>f.text.includes(`(property "Reference" "${ref}"`));
 assert.equal(nodes(fp.text,'pad').filter(p=>p.text.startsWith('(pad "3" ')).length,1,'Native single annular ground land');
 assert.match(fp.text,/gr_circle/,'Microphone ring retains open center');
 assert.match(fp.text,/\(drill 0\.5\)/,'Acoustic hole size');
}
const warnings=[];
for(const ref of ['C3','C4']){
 const fp=footprints.find(f=>f.text.includes(`(property "Reference" "${ref}"`));
 const pads=nodes(fp.text,'pad');
 for(const pad of pads){
  if(!/\(solder_mask_margin -0\.05\)/.test(pad.text))warnings.push(`${ref}: verify native mask-defined opening; expected margin -0.05mm`);
  if(!/\(solder_paste_margin -0\.1\)/.test(pad.text))warnings.push(`${ref}: verify native paste opening; expected margin -0.1mm`);
 }
}
const byRef=Object.fromEntries(parts.map(p=>[p.ref,p]));
const capacitorCenterDistances=Object.fromEntries([['C7','U3'],['C8','U3'],['C9','U3'],['C11','U5'],['C18','U9']].map(([c,u])=>[`${c}-${u}`,Number(Math.hypot(byRef[c].x-byRef[u].x,byRef[c].y-byRef[u].y).toFixed(3))]));
const result={createdAt:new Date().toISOString(),revision:boardSpec.revision,filename,sha256:crypto.createHash('sha256').update(board).digest('hex'),footprints:footprints.length,checkedLogicalPins:checkedPins,sourceToExportNetAssignment:'passed',tracks:nodes(board,'segment').length,vias:nodes(board,'via').length,capacitorCenterDistances_mm:capacitorCenterDistances,warnings,limitations:'Verifies exported pad/net identity and selected geometry only. Zero placement tracks does not establish routed connectivity. Capacitor center distance does not prove a short routed power loop. Does not replace ERC, DRC, stencil review or bench qualification.'};
fs.writeFileSync('output/export-checks.json',JSON.stringify(result,null,2));
console.log(result);
