import fs from 'node:fs';
const archive='output/attempts/freerouting-frozen-a03';
fs.mkdirSync(archive,{recursive:true});
for(const file of ['design-manifest.json','logical-netlist.json','aura-a03-routing-inputs.json','aura-placement.kicad_pcb','aura-placement.kicad_pro','aura-placement.circuit.json','placement-validation.json']){
  const target=`${archive}/${file}`;if(!fs.existsSync(target))fs.copyFileSync(`output/${file}`,target);
}
const changes={C7:{x:-1.3,y:-9.85},C8:{x:-8,y:-9.05},R22:{x:-8.5,y:-13.4},R23:{x:-8.5,y:-11.5},D1:{x:.8,y:-9.05},C10:{x:.9,y:-10.55},C18:{x:-2.05,y:-13.3},R7:{x:-3.55,y:-1.4},C17:{x:-5.55,y:-1.8}};
const path='src/placement-overrides.json';const placement=JSON.parse(fs.readFileSync(path));
for(const [ref,xy] of Object.entries(changes))Object.assign(placement[ref],xy);
fs.writeFileSync(path,JSON.stringify(placement,null,2)+'\n');
fs.writeFileSync('output/aura-a03-final-placement-changes.json',JSON.stringify(changes,null,2)+'\n');
console.log('Synced nine physically and electrically reviewed passive placements into authored tscircuit source.');
