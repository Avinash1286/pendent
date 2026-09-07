import fs from 'node:fs';
const {parts,boardSpec}=JSON.parse(fs.readFileSync('output/design-manifest.json','utf8'));
const footprints=JSON.parse(fs.readFileSync('src/footprints.json','utf8'));
const esc=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;');
const colors={radio:'#b7cebd',audio:'#d9b86f',storage:'#8ea6b4',power:'#b7a194',privacy:'#dccaab',ux:'#c8b8ce'};
const s=14,cx=310,cy=438,X=x=>cx+x*s,Y=y=>cy-y*s;
let svg=`<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="900" viewBox="0 0 1200 900"><rect width="1200" height="900" fill="#111713"/><style>text{font-family:Arial,sans-serif;fill:#ecf1ea}.muted{fill:#9daf9f}.small{font-size:13px}.body{font-size:16px}.label{font-size:10px;fill:#111713;font-weight:bold}</style><text x="70" y="75" font-size="34" letter-spacing="5">AURA / A03</text><text x="70" y="110" class="body muted">Engineering placement and mechanical interfaces</text><rect x="${X(-boardSpec.width/2)}" y="${Y(boardSpec.height/2)}" width="${boardSpec.width*s}" height="${boardSpec.height*s}" rx="${boardSpec.radius*s}" fill="#24362a" stroke="#77917a" stroke-width="2"/><path d="M${X(-11)},${Y(11.95)} H${X(11)}" stroke="#d7b972" stroke-dasharray="5 4"/><text x="310" y="192" text-anchor="middle" class="small">RF WINDOW / NO METAL</text>`;
for(const p of parts.filter(p=>p.layer!=='bottom')){
 const f=footprints[p.fp];let w=f?.width||2,h=f?.height||1;
 if(p.ref==='SW1'){w=9.1;h=3.6;}
 svg+=`<g transform="translate(${X(p.x)} ${Y(p.y)}) rotate(${-(p.r||0)})"><rect x="${-w*s/2}" y="${-h*s/2}" width="${w*s}" height="${h*s}" rx="2" fill="${colors[p.block]}" opacity="${p.ref==='SW3'?'.35':'.9'}"/><text class="label" text-anchor="middle" dominant-baseline="central">${esc(p.ref)}</text></g>`;
}
svg+=`<circle cx="${X(6)}" cy="${Y(-12)}" r="${4.25*s}" fill="#111713" fill-opacity=".5" stroke="#c8b8ce" stroke-dasharray="6 5"/><text x="${X(6)}" y="${Y(-12)}" text-anchor="middle" class="small">8mm LRA</text><text x="310" y="768" text-anchor="middle" class="body">24 × 42 × 0.8mm · 4 layers · R10 corners</text><text x="310" y="796" text-anchor="middle" class="small muted">Placement view; this graphic does not show copper routing.</text>`;
for(const x of [-3,0,3])svg+=`<circle cx="${X(x)}" cy="${Y(-19)}" r="${.85*s}" fill="none" stroke="#d7b972" stroke-dasharray="3 2"/>`;
const rows=[['01','CAPTURE','Two PDM microphones · 17mm acoustic spacing','Physical microphone power disconnect'],['02','COMPUTE','nRF52840 module · Bluetooth LE','Phone / optional cloud performs AI processing'],['03','REMEMBER','128MiB NAND · PCM note journal','~66min ideal storage; hardware not bench-tested'],['04','FEEL','Flush face paddle · hard amber recording light','1.2N low-current tactile · C08-00A LRA candidate'],['05','POWER','150mAh target · 53mA charge · pack NTC','Independent hot cutoff · pack still unqualified']];
rows.forEach((r,i)=>{const y=185+i*106;svg+=`<text x="635" y="${y}" class="small muted">${r[0]}</text><text x="680" y="${y}" font-size="18" letter-spacing="2">${r[1]}</text><text x="680" y="${y+29}" class="body">${r[2]}</text><text x="680" y="${y+52}" class="small muted">${r[3]}</text>`;});
svg+=`<rect x="625" y="730" width="515" height="90" rx="12" fill="#392f24"/><text x="650" y="761" class="body">ROUTING DRAFT / NOT FOR FABRICATION</text><text x="650" y="787" class="small">Read hardware.md and exact KiCad DRC/connectivity reports.</text><text x="70" y="861" class="small muted">Positive Y → necklace loop · PCB top Z0.65mm in A03 case · antenna boundary Y11.95mm</text></svg>`;
fs.writeFileSync('output/assembly-plan.svg',svg);
console.log('Assembly reference written from current manifest.');
