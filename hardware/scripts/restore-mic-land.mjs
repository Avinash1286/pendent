import fs from 'node:fs';
// KiCad supports a native annular custom pad. Restore that original library land
// and its four paste arcs after tscircuit's portable polygon approximation.
function nodes(text,type){
 const result=[];let pos=0;
 while((pos=text.indexOf(`(${type}`,pos))>=0){
  if(!/\s/.test(text[pos+type.length+1]||'')){pos++;continue;}
  let depth=0,quoted=false,escape=false,end=pos;
  for(;end<text.length;end++){const c=text[end];if(quoted){if(escape)escape=false;else if(c==='\\')escape=true;else if(c==='"')quoted=false;}else if(c==='"')quoted=true;else if(c==='(')depth++;else if(c===')'&&--depth===0){end++;break;}}
  result.push({start:pos,end,text:text.slice(pos,end)});pos=end;
 }return result;
}
export function restoreMicLand(board){
 const original=fs.readFileSync('library/Knowles_LGA-5_3.5x2.65mm.kicad_mod','utf8');
 const ring=nodes(original,'pad').find(n=>/^\(pad "3"/.test(n.text)).text.replace(/\(uuid "[^"]+"\)/,'(net 1 "GND")');
 const paste=nodes(original,'fp_arc').filter(n=>n.text.includes('"F.Paste"')).map(n=>n.text.replace(/\s*\(uuid "[^"]+"\)/,'')).join('\n');
 for(const fp of nodes(board,'footprint').reverse()){
  if(!/\(property "Reference" "MK[12]"/.test(fp.text))continue;
  let changed=fp.text;
  for(const pad of nodes(changed,'pad').filter(n=>/^\(pad "3"/.test(n.text)).reverse())changed=changed.slice(0,pad.start)+changed.slice(pad.end);
  changed=changed.slice(0,-1)+ring+'\n'+paste+'\n)';
  board=board.slice(0,fp.start)+changed+board.slice(fp.end);
 }
 return board;
}
