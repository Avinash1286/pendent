import React from 'react';
import footprints from './footprints.json';
import {parts,boardSpec, type Part} from './design';
import {createKiCadRoutingToolsAutorouter} from '@tscircuit/krt-wasm';

function Footprint({fp}:{fp:string}) {
  const f=(footprints as any)[fp];
  if(!f){
    const count=fp==='debug'?6:fp==='motor'?2:3;
    const pitch=fp==='debug'?1.5:fp==='dock'?3:1.5;
    const diameter=fp==='dock'?1.7:fp==='debug'?0.9:1;
    return <footprint>{Array.from({length:count},(_,i)=><smtpad key={i} shape="circle" radius={diameter/2} pcbX={(i-(count-1)/2)*pitch} pcbY={0} portHints={[String(i+1)]} />)}</footprint>;
  }
  return <footprint>
    {f.pads.map((pad:any,i:number)=>{
      const x=pad.at[0],y=-pad.at[1],rot=pad.at[2]||0;
      if(pad.pad_type==='np_thru_hole')return <hole key={i} pcbX={x} pcbY={y} diameter={pad.drill.width||pad.size[0]} />;
      // Preserve microphone annulus instead of the converter's solid copper disk.
      if(fp==='mic' && pad.name==='3'){
        // Single-contour wedges avoid a KiCad custom-pad anchor in the acoustic hole.
        return <React.Fragment key={i}>{Array.from({length:32},(_,j)=>{
          const a=j*2*Math.PI/32,b=(j+1)*2*Math.PI/32;
          const pt=(r:number,t:number)=>({x:r*Math.cos(t),y:-0.77+r*Math.sin(t)});
          return <smtpad key={j} shape="polygon" points={[pt(.8125,a),pt(.8125,b),pt(.5125,b),pt(.5125,a)]} portHints={['3']} solderPasteMargin={-1}/>;
        })}</React.Fragment>;
      }
      const w=pad.size[0],h=pad.size[1];
      if(pad.pad_shape==='circle')return <smtpad key={i} shape="circle" radius={w/2} pcbX={x} pcbY={y} portHints={[pad.name]} />;
      return <smtpad key={i} shape="rect" width={rot%180===90?h:w} height={rot%180===90?w:h} pcbX={x} pcbY={y} portHints={[pad.name]} />;
    })}
    {f.lines.map((l:any,i:number)=><silkscreenpath key={`s${i}`} route={[{x:l.start[0],y:-l.start[1]},{x:l.end[0],y:-l.end[1]}]} strokeWidth={0.1} />)}
  </footprint>
}
const blocks=['radio','audio','storage','power','privacy','ux'];
function DevicePart({part,index}:{part:Part,index:number}){
  const sameBlock=parts.filter(p=>p.block===part.block);
  const n=sameBlock.indexOf(part), bi=blocks.indexOf(part.block);
  const pinNumbers=Object.keys(part.pins);
  const allPins=Array.from(new Set([...pinNumbers,...(part.nc||[])]));
  const labels=Object.fromEntries(allPins.map(n=>[`pin${n}`,part.labels?.[n]||`P${n}`]));
  return <chip name={part.ref} manufacturerPartNumber={part.mpn}
    footprint={<Footprint fp={part.fp}/>}
    pcbX={part.x} pcbY={part.y} pcbRotation={part.r||0} layer={part.layer||'top'}
    schX={bi*35+(n%3)*10} schY={-Math.floor(n/3)*14}
    schWidth={part.ref==='U1'?7:5}
    pinLabels={labels} noConnect={(part.nc||[]).map(n=>`pin${n}`)}
    connections={Object.fromEntries(Object.entries(part.pins).map(([p,net])=>[`pin${p}`,`net.${net}`]))}
  />;
}
export default function AuraPendant({route=false}:{route?:boolean}){
  return <board width={boardSpec.width} height={boardSpec.height} borderRadius={boardSpec.radius} thickness={0.8} layers={4}
    title="AURA EVT-A · private capture pendant" solderMaskColor="black" silkscreenColor="white"
    routingDisabled={!route} autorouter={{algorithmFn:createKiCadRoutingToolsAutorouter({gridStep:0.12,clearance:0.12,maxIterations:120000,viaCost:6})}}
    schTraceAutoLabelEnabled schMaxTraceDistance={0.5} bomDisabled
    minTraceWidth={0.12} nominalTraceWidth={0.15} minTraceToPadEdgeClearance={0.12}
    minPadEdgeToPadEdgeClearance={0.12} minBoardEdgeClearance={0.3}
    minViaHoleDiameter={0.2} minViaPadDiameter={0.45}>
    {Array.from(new Set(parts.flatMap(p=>Object.values(p.pins)))).map(n=><net key={n} name={n} />)}
    {parts.map((p,i)=><DevicePart key={p.ref} part={p} index={i}/>)}
    <keepout pcbX={0} pcbY={14.475} width={24} height={5.05} shape="rect" layers={['top','inner1','inner2','bottom']} />
    <silkscreentext text="AURA · EVT A" pcbX={0} pcbY={-16.1} fontSize={0.7}/>
    <silkscreentext text="ANTENNA / NO METAL" pcbX={0} pcbY={15} fontSize={0.6}/>
  </board>
}
