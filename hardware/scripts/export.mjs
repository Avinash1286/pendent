import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {restoreMicLand} from './restore-mic-land.mjs';
import {normalizeExport} from './normalize-export.mjs';
const cwd=process.cwd();
const bun=path.resolve('node_modules/bun/bin',process.platform==='win32'?'bun.exe':'bun');
const cli=path.resolve('node_modules/@tscircuit/cli/dist/cli/main.js');
const routingReport=fs.existsSync('output/routing-attempt-validation.json')?JSON.parse(fs.readFileSync('output/routing-attempt-validation.json','utf8')):null;
const routed=!!routingReport?.counts?.pcb_trace&&!routingReport?.counts?.pcb_autorouting_error;
const source=path.resolve(`output/aura-${routed?'routing-attempt':'placement'}.circuit.json`);
for(const [format,filename] of [['kicad_pcb',`aura-${routed?'routed':'placement'}.kicad_pcb`],['kicad_sch','aura.kicad_sch'],['specctra-dsn','aura.dsn']]){
 const target=path.resolve('output',filename);
 const result=spawnSync(bun,[cli,'export',source,'-f',format,'-o',target,'--disable-parts-engine'],{cwd,stdio:'inherit'});
 if(result.status!==0)throw Error(`Export ${format} failed with ${result.status}`);
 if(format==='kicad_pcb'){
  // Normalize a verified exporter omission to the authored0.8mm board contract.
  const data=fs.readFileSync(target,'utf8').replace(/\(general\s*\(thickness\s+[\d.]+\)/,'(general\n    (thickness 0.8)');
  fs.writeFileSync(target,normalizeExport(restoreMicLand(data)));
 }
}
console.log('Editable exports written. Review validation reports; these files are not manufacturing approval.');
