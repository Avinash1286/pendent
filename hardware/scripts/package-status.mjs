import fs from 'node:fs';
import crypto from 'node:crypto';

const routing=JSON.parse(fs.readFileSync('output/aura-a03-routing-status.json','utf8'));
const erc=JSON.parse(fs.readFileSync('output/kicad-a03-schematic-erc.json','utf8')).sheets.flatMap(s=>s.violations||[]);
const files=[
 'src/design.ts','src/AuraPendant.tsx','src/footprints.json','src/placement-overrides.json',
 'output/design-manifest.json','output/logical-netlist.json','output/logical-checks.json',
 'output/aura-placement.circuit.json','output/aura-placement.kicad_pcb','output/aura.kicad_sch',
 'output/aura-placement.kicad_pro','output/aura-placement.pcb.svg','output/aura-placement.schematic.svg',
 'output/aura-a03.dsn','output/aura-a03-routing-inputs.json','output/aura-a03-refinement-inputs.json','output/aura-a03-route-attempt.ses',
 'output/aura-a03-route-refine.ses','output/aura-a03-route-freerouting-drc.json',
 'output/aura-a03-refine-freerouting-drc.json','output/aura-a03-routing-status.json',
 'output/kicad-a03-final-placement-drc.json','output/kicad-a03-schematic-erc.json',
 'output/export-checks.json','output/placement-validation.json',
 'output/assembly-bom.csv','output/cpl-top.csv','output/external-bom.csv',
 'output/fabrication-review-notes.md','output/assembly-plan.svg','output/assembly-plan.png',
 'output/aura-a03-route-study.svg','output/aura-a03-route-study.png',
 'output/aura-a03-freerouting.log','output/aura-a03-refine.log',
 'output/aura-a03-route-drc.log','output/aura-a03-refine-drc.log',
];
const manifest={revision:'EVT-A03',createdAt:new Date().toISOString(),status:'ENGINEERING_REVIEW_ONLY',fabricationReady:false,board:{widthMm:24,heightMm:42,radiusMm:10,thicknessMm:.8,copperLayers:4},logical:{references:61,nets:43,connectedPinsVerifiedInPlacement:208},assembly:{candidateSmtReferences:57,customPcbFeatures:4},routing,schematicErc:{findings:erc.length,types:erc.reduce((o,v)=>(o[v.type]=(o[v.type]||0)+1,o),{})},manufacturingOutputsReleased:false,files:files.map(path=>{const bytes=fs.readFileSync(path);return{path,bytes:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex')};})};
fs.writeFileSync('output/engineering-package-manifest.json',JSON.stringify(manifest,null,2)+'\n');
console.log(`Engineering manifest written: ${files.length} hashed files. Fabrication ready: false.`);
