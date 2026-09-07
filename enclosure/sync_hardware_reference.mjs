// Run only after the hardware owner confirms final native/source coordinates.
// node --import ../hardware/node_modules/tsx/dist/loader.mjs sync_hardware_reference.mjs --confirm-hardware-freeze
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { parts } from '../hardware/src/design.ts';
const root=path.dirname(fileURLToPath(import.meta.url));
assert.ok(process.argv.includes('--confirm-hardware-freeze'),'Await successful native/source placement freeze from the hardware owner.');
const target=path.join(root,'pcb-placement-reference.json');
const before=JSON.parse(fs.readFileSync(target,'utf8'));
const after=Object.fromEntries(parts.map(part=>[part.ref,{x:part.x,y:part.y,r:part.r||0}]));
const changes=Object.fromEntries(Object.keys(after).filter(ref=>JSON.stringify(after[ref])!==JSON.stringify(before[ref])).map(ref=>[ref,{before:before[ref],after:after[ref]}]));
const allowed=new Set(['C7','C8','C10','C18','R22','R23','D1','R7','C17']);
for(const ref of Object.keys(changes))assert.ok(allowed.has(ref),'Unexpected component move: '+ref);
assert.deepEqual(Object.keys(after).sort(),Object.keys(before).sort(),'Component population changed; independently review before synchronizing.');
const sha=data=>crypto.createHash('sha256').update(data).digest('hex');
const source=path.join(root,'../hardware/src/placement-overrides.json');
const report={scope:'A03 internal routing and maximum-body-clearance corrections; fixed exterior interfaces unchanged',hardware_owner_freeze_confirmed_by_caller:true,physical_qualification:false,source:'hardware/src/design.ts resolved parts and placement-overrides.json',source_sha256:sha(fs.readFileSync(source)),before_sha256:sha(fs.readFileSync(target)),changes};
fs.writeFileSync(target,JSON.stringify(after,null,2)+'\n');
report.after_sha256=sha(fs.readFileSync(target));
fs.writeFileSync(path.join(root,'hardware-placement-sync.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
