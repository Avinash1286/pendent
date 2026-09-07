import fs from 'node:fs';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';

// Read-only SES inspection: this never changes or imports a KiCad project.
const sessionPath=process.argv[2]||'output/aura-a03-route-refine.ses';
const drcPath=process.argv[3]||'output/aura-a03-refine-freerouting-drc.json';
const source=fs.readFileSync(sessionPath,'utf8');
const tokens=source.match(/"(?:\\.|[^"\\])*"|[^\s()]+|[()]/g);
let cursor=0;
function read(){const t=tokens[cursor++];if(t==='('){const a=[];while(tokens[cursor]!==')')a.push(read());cursor++;return a;}return t.startsWith('"')?JSON.parse(t):t;}
const tree=read(),child=(n,k)=>n.find(x=>Array.isArray(x)&&x[0]===k),children=(n,k)=>n.filter(x=>Array.isArray(x)&&x[0]===k);
const routes=child(tree,'routes'),resolution=child(routes,'resolution');
assert.equal(resolution[1],'um','SES resolution unit');
const perMm=Number(resolution[2])*1000;
const networks=child(routes,'network_out'),wirePaths=[],vias=[];
for(const net of children(networks,'net')){
 for(const wire of children(net,'wire')){
  const p=child(wire,'path');if(!p)continue;
  const coords=p.slice(3).map(Number);assert.equal(coords.length%2,0);
  const points=[];for(let i=0;i<coords.length;i+=2)points.push([coords[i]/perMm-100,coords[i+1]/perMm+100]);
  wirePaths.push({net:net[1],layer:p[1],widthMm:Number(p[2])/perMm,points});
 }
 for(const v of children(net,'via'))vias.push({net:net[1],padstack:v[1],x:Number(v[2])/perMm-100,y:Number(v[3])/perMm+100});
}
const drc=fs.existsSync(drcPath)?JSON.parse(fs.readFileSync(drcPath,'utf8')):null;
const {parts,boardSpec}=JSON.parse(fs.readFileSync('output/design-manifest.json','utf8'));
const inputRecord=JSON.parse(fs.readFileSync('output/aura-a03-routing-inputs.json','utf8'));
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const inputMatches=inputRecord.inputs.map(i=>({...i,unchanged:sha(i.path)===i.sha256}));
assert.ok(inputMatches.every(x=>x.unchanged),'All routing input files retain their recorded SHA-256');
const unconnected=drc?(drc.unconnectedItems||drc.unconnected_items||[]):[];
const routerLog=sessionPath.endsWith('route-refine.ses')?'output/aura-a03-refine.log':'output/aura-a03-freerouting.log';
const scoreMatches=fs.existsSync(routerLog)?[...fs.readFileSync(routerLog,'utf8').matchAll(/final score:[^\r\n]*?\((\d+) unrouted and (\d+) violations\)/g)]:[];
const score=scoreMatches.at(-1);
const report={revision:boardSpec.revision,generatedAt:new Date().toISOString(),sessionPath,sessionSha256:sha(sessionPath),wirePaths:wirePaths.length,vias:vias.length,layerWirePaths:Object.fromEntries(['F.Cu','In1.Cu','In2.Cu','B.Cu'].map(l=>[l,wirePaths.filter(w=>w.layer===l).length])),standaloneDrc:drc?{path:drcPath,violations:drc.violations?.length,violationTypes:drc.violations?.map(v=>v.type),disconnectedNetGroups:unconnected.length,disconnectedNets:unconnected.map(v=>v.description.match(/\[([^\]]+)\]/)?.[1]),countingNote:'Freerouting DRC groups all members of each disconnected net; this length is not the router airwire count.'}:null,inputMatches,importedIntoKiCad:false,fabricationReady:false,limitation:'Standalone session inspection only. Connector import was previously cancelled without reason. No imported-board DRC, return planes, manufacturing release or hardware qualification is established.'};
report.inMemoryRouterFinal=score?{path:routerLog,unroutedConnections:Number(score[1]),violations:Number(score[2]),reconciliation:'Serialized-session reload has different counts. Preserve both; no independent imported-KiCad check has been performed.'}:null;
fs.writeFileSync('output/aura-a03-routing-status.json',JSON.stringify(report,null,2)+'\n');
fs.writeFileSync('output/aura-a03-route-geometry.json',JSON.stringify({source:sessionPath,coordinateSystem:'mm, board centre (0,0), positive Y toward necklace loop',wirePaths,vias},null,2)+'\n');
const esc=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;');
const s=12,cy=439;
const layers=[['F.Cu','#e5bc6c'],['In1.Cu','#79b99e'],['In2.Cu','#83b1da'],['B.Cu','#c995bb']];
let svg='<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900"><rect width="1600" height="900" fill="#101613"/><style>text{font-family:Arial,sans-serif;fill:#e8efea}.muted{fill:#9fb0a5}</style><text x="66" y="67" font-size="33" letter-spacing="4">AURA / A03 ROUTING STUDY</text><text x="66" y="103" font-size="17" class="muted">Actual standalone Freerouting session geometry · 24 × 42 × 0.8mm · no imported KiCad copper</text>';
layers.forEach(([layer,color],index)=>{
 const cx=214+index*391,X=x=>cx+x*s,Y=y=>cy-y*s;
 svg+=`<text x="${cx}" y="152" text-anchor="middle" font-size="20">${layer}</text><rect x="${X(-12)}" y="${Y(21)}" width="288" height="504" rx="120" fill="#1b2820" stroke="#506457"/><line x1="${X(-11.7)}" y1="${Y(11.95)}" x2="${X(11.7)}" y2="${Y(11.95)}" stroke="#b6c2b9" stroke-dasharray="4 4"/><text x="${cx}" y="234" text-anchor="middle" font-size="12" class="muted">RF EXCLUSION</text>`;
 for(const w of wirePaths.filter(w=>w.layer===layer))svg+=`<polyline points="${w.points.map(([x,y])=>`${X(x).toFixed(2)},${Y(y).toFixed(2)}`).join(' ')}" fill="none" stroke="${color}" stroke-width="${w.widthMm*s}" stroke-linejoin="round" stroke-linecap="round" opacity=".92"><title>${esc(w.net)}</title></polyline>`;
 for(const v of vias)svg+=`<circle cx="${X(v.x)}" cy="${Y(v.y)}" r="${.225*s}" fill="none" stroke="${color}" stroke-width="1"/><circle cx="${X(v.x)}" cy="${Y(v.y)}" r="${.1*s}" fill="#101613"/>`;
 if(layer==='F.Cu')for(const p of parts.filter(p=>p.layer!=='bottom'))svg+=`<text x="${X(p.x)}" y="${Y(p.y)}" text-anchor="middle" font-size="8" fill-opacity=".8">${esc(p.ref)}</text>`;
 svg+=`<text x="${cx}" y="734" text-anchor="middle" font-size="15" class="muted">${wirePaths.filter(w=>w.layer===layer).length} wire paths</text>`;
});
const d=report.standaloneDrc;
svg+=`<rect x="66" y="776" width="1468" height="74" rx="12" fill="#3c2b20"/><text x="91" y="806" font-size="19">UNFINISHED / NOT FOR FABRICATION</text><text x="91" y="834" font-size="15">${wirePaths.length} wire paths · ${vias.length} vias · ${d?`${d.disconnectedNetGroups} disconnected net groups · ${d.violations} DRC findings`:'Standalone DRC pending'} · No filled reference planes or independent imported-board DRC.</text></svg>`;
fs.writeFileSync('output/aura-a03-route-study.svg',svg);
console.log(JSON.stringify(report,null,2));
