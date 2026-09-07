import fs from 'node:fs';
import {nodes} from './restore-mic-land.mjs';

/** Narrow, repeatable corrections to tscircuit's placement export.
 * This does not import routing, create tracks or modify a routing session.
 * KiCad's pad angle is absolute; rotated pad width/height must not be swapped again.
 */
export function normalizeExport(board){
 const {parts}=JSON.parse(fs.readFileSync('output/design-manifest.json','utf8'));
 const netCodes=new Map();
 for(const item of nodes(board,'net')){const m=item.text.match(/^\(net\s+(\d+)\s+"([^"]+)"/);if(m)netCodes.set(m[2],Number(m[1]));}
 for(const fp of nodes(board,'footprint').reverse()){
  const ref=fp.text.match(/\(property "Reference" "([^"]+)"/)?.[1];
  const part=parts.find(p=>p.ref===ref);if(!part)continue;
  let changed=fp.text;
  for(const pad of nodes(changed,'pad').reverse()){
   const number=pad.text.match(/^\(pad "([^"]*)"/)?.[1];let text=pad.text;
   // KMR has two physical lands for each internally-common terminal.
   // Both must retain the same authored net in the exported KiCad board.
   if(ref==='SW2'&&part.pins[number]&&!/\(net\s/.test(text)){
    const net=part.pins[number],code=netCodes.get(net);if(code===undefined)throw Error(`Missing net code ${net}`);
    text=text.slice(0,-1)+`(net ${code} "${net}")\n)`;
   }
   // The converter carries the mask margin but drops the paste margin.
   if(['C3','C4'].includes(ref)&&!text.includes('(solder_paste_margin'))text=text.slice(0,-1)+'(solder_paste_margin -0.1)\n)';
   changed=changed.slice(0,pad.start)+text+changed.slice(pad.end);
  }
  board=board.slice(0,fp.start)+changed+board.slice(fp.end);
 }
 return board;
}
