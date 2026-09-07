// Run from enclosure: node --import ../hardware/node_modules/tsx/dist/loader.mjs snapshot_component_bodies.mjs
// Snapshot body dimensions only; this does not approve or change component positions.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { parts } from '../hardware/src/design.ts';
const root=path.dirname(fileURLToPath(import.meta.url));
const footprintPath=path.join(root,'../hardware/src/footprints.json');
const footprints=JSON.parse(fs.readFileSync(footprintPath,'utf8'));
const exactCaps={
  C0603C225K8RACTU:'https://search.kemet.com/component-documentation/download/specsheet/C0603C225K8RAC7867',
  C0603C475K8PACTU:'https://search.kemet.com/component-documentation/download/specsheet/C0603C475K8PAC7867',
};
const bodies=Object.fromEntries(parts.map(part=>{
  const fp=footprints[part.fp];
  if(!fp){
    if(part.layer!=='bottom')throw new Error('Missing footprint '+part.fp);
    return [part.ref,{mpn:part.mpn,footprint:part.fp,side:'bottom',nominal_mm:null,dimension_source:'Custom bare PCB contact pads; mechanical mating interface is modeled separately'}];
  }
  const body={mpn:part.mpn,footprint:part.fp,side:part.layer||'top',nominal_mm:[fp.width,fp.height,fp.z],dimension_source:'hardware/src/footprints.json; nominal package body proxy, not vendor STEP'};
  if(exactCaps[part.mpn])Object.assign(body,{maximum_body_mm:[1.75,.95,.9],maximum_source:exactCaps[part.mpn],verified_dimensions:'L1.6±0.15, W0.8±0.15, T0.8±0.10 mm; solder height and placement tolerance excluded'});
  if(['C0402C103K5RACTU','C0402C104K4RACTU'].includes(part.mpn))Object.assign(body,{maximum_body_mm:[1.05,.55,.55],maximum_source:'https://search.kemet.com/download/specsheet/'+part.mpn,verified_dimensions:'L1.0±0.05, W0.5±0.05, T0.5±0.05 mm; solder height and placement tolerance excluded'});
  if(part.mpn==='DMG2302UK-7')Object.assign(body,{body_nominal_mm:[1.3,2.9,1.025],maximum_body_mm:[1.4,3,1.1],maximum_lead_span_mm:[2.5,3,1.1],maximum_source:'https://www.diodes.com/datasheet/download/DMG2302UK.pdf',verified_dimensions:'Page6: B plastic width1.20–1.40, H body length2.80–3.00, C overall lead span2.30–2.50, K1 overall height0.903–1.10 mm. SOT-23 library local X spans leads; long plastic axis is local Y. The nominal source-catalog field is retained for traceability, but is not the plastic body.'});
  return [part.ref,body];
}));
const report={revision:'A03',scope:'Body envelope reference only; component placements are stored separately and remain subject to hardware freeze',source_sha256:crypto.createHash('sha256').update(fs.readFileSync(footprintPath)).digest('hex'),source_design_sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'../hardware/src/design.ts'))).digest('hex'),physical_qualification:false,bodies};
fs.writeFileSync(path.join(root,'component-body-reference.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({parts:parts.length,focused:Object.fromEntries(['C7','C8','C10','R22','R23','D1','U4','SW2'].map(ref=>[ref,bodies[ref]]))},null,2));
