import fs from 'node:fs';
const {parts}=JSON.parse(fs.readFileSync('output/design-manifest.json','utf8'));
const csv=rows=>rows.map(r=>r.map(x=>'"'+String(x??'').replaceAll('"','""')+'"').join(',')).join('\n');
const groups=new Map();
for(const part of parts.filter(p=>!p.mpn.startsWith('AURA-'))){
 const key=part.mpn+'|'+part.fp;
 if(!groups.has(key))groups.set(key,{mpn:part.mpn,fp:part.fp,value:part.value,refs:[],notes:new Set()});
 const group=groups.get(key);group.refs.push(part.ref);if(part.note)group.notes.add(part.note);
}
fs.writeFileSync('output/assembly-bom.csv',csv([
 ['References','Quantity','ManufacturerPartNumber','Description','FootprintKey','Status','ReviewNotes'],
 ...[...groups.values()].map(g=>[g.refs.join(' '),g.refs.length,g.mpn,g.value,g.fp,'ENGINEERING CANDIDATE - NOT APPROVED FOR PURCHASE',[...g.notes].join(' | ')])
]));
fs.writeFileSync('output/cpl-top.csv',csv([
 ['Designator','MidX_mm','MidY_mm','Rotation_deg','Layer','CoordinateConvention'],
 ...parts.filter(p=>!p.mpn.startsWith('AURA-')).map(p=>[p.ref,p.x,p.y,p.r||0,'Top','Board centre origin; positive Y toward necklace loop; counterclockwise degrees; assembler zero-angle verification required'])
]));
fs.writeFileSync('output/external-bom.csv',csv([
 ['Item','Qty','Candidate','Status'],
 ['Protected 150mAh pack',1,'FPBattery/DNK302025-150','Preliminary pack drawing; voltage tolerance, maximum dimensions, swelling and supplier approval unresolved'],
 ['Pack temperature sensor',1,'Semitec103AT-2','Thermal attachment, assembled R/T acceptance and lead routing unqualified'],
 ['LRA motor',1,'Precision MicrodrivesC08-00A','Prototype datasheet; source availability and calibrated drive unqualified'],
 ['Rear contact assembly',1,'Custom 3-contact carrier/tails','Exact contacts/material/retention/current/wear not selected'],
 ['Magnetic dock',1,'Custom keyed 5V100mA dock','Electrical/mechanical design and qualification incomplete']
]));
console.log('Generated engineering assembly BOM, CPL and external-parts candidate list.');
