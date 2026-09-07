import fs from 'node:fs';
const {parts}=JSON.parse(fs.readFileSync('output/design-manifest.json','utf8'));
const f=JSON.parse(fs.readFileSync('src/footprints.json','utf8'));
const fixed=new Set(['U1','MK1','MK2','SW1','SW2','SW3','LED1']);
Object.assign(parts.find(p=>p.ref==='LED1'),{x:0,y:-1,r:90});
const placed=[],result={};
function dims(p,r){
 const fp=f[p.fp]; if(!fp)return [p.fp==='debug'?8.4:p.fp==='dock'?7.7:p.fp==='motor'?2.5:4, p.fp==='dock'?1.7:1];
 let w=fp.width,h=fp.height;
 for(const pad of fp.pads){let pw=pad.size[0],ph=pad.size[1];if((pad.at[2]||0)%180===90)[pw,ph]=[ph,pw];w=Math.max(w,2*Math.abs(pad.at[0])+pw);h=Math.max(h,2*Math.abs(pad.at[1])+ph);}
 if(p.fp==='privacy')w=9.1;
 return r%180===90?[h,w]:[w,h];
}
function inboard(x,y,w,h){
 for(const sx of [-1,1])for(const sy of [-1,1]){const px=x+sx*w/2,py=y+sy*h/2;if(Math.abs(px)>11.7||Math.abs(py)>16.7)return false;const dx=Math.max(Math.abs(px)-8,0),dy=Math.max(Math.abs(py)-13,0);if(dx*dx+dy*dy>3.7*3.7)return false;}
 return y+h/2<11.7;
}
function free(x,y,w,h,side,gap=.16){return !placed.some(q=>q.side===side && Math.abs(x-q.x)<(w+q.w)/2+gap && Math.abs(y-q.y)<(h+q.h)/2+gap);}
function put(p,x,y,r){const[w,h]=dims(p,r);placed.push({ref:p.ref,x,y,r,w,h,side:p.layer||'top',pins:p.pins});result[p.ref]={x,y,r};}
for(const p of parts.filter(p=>fixed.has(p.ref)))put(p,p.x,p.y,p.r||0);
// Front-side8mm LRA envelope, with0.25mm radial assembly allowance.
placed.push({ref:'LRA_CASE_KEEP_OUT',x:6,y:-12,w:8.5,h:8.5,r:0,side:'top',pins:{}});
const clusterOrder=['U2','C5','C6','U3','C7','C8','C9','U4','C10','U5','C11','U6','C12','C13','U7','C14','C15','U8','C16','C1','C2','C3','C4'];
const capParent={C1:'U1',C2:'U1',C3:'MK1',C4:'MK2',C5:'U2',C6:'U2',C7:'U3',C8:'U3',C9:'U3',C10:'U4',C11:'U5',C12:'U6',C13:'U6',C14:'U7',C15:'U7',C16:'U8'};
const movable=parts.filter(p=>!fixed.has(p.ref)).sort((a,b)=>{
 const ai=clusterOrder.indexOf(a.ref),bi=clusterOrder.indexOf(b.ref);
 if(ai>=0||bi>=0)return (ai<0?100:ai)-(bi<0?100:bi);
 const[aw,ah]=dims(a,0),[bw,bh]=dims(b,0);return bw*bh-aw*ah;
});
for(const p of movable){
 if(p.layer==='bottom'){put(p,p.x,p.y,p.r||0);continue;}
 let best=null,target={x:p.x,y:p.y};
 if(capParent[p.ref]){
  const parent=parts.find(q=>q.ref===capParent[p.ref]),position=result[parent.ref];
  const pin=Object.entries(parent.pins).find(([_,n])=>n===p.pins['1'])?.[0];
  const pad=f[parent.fp].pads.find(q=>q.name===pin);
  if(position&&pad){const a=position.r*Math.PI/180,px=pad.at[0],py=-pad.at[1];target={x:position.x+px*Math.cos(a)-py*Math.sin(a),y:position.y+px*Math.sin(a)+py*Math.cos(a)};}
 }
 for(const r of [p.r||0,(p.r||0)+90]){
  const[w,h]=dims(p,r);
  for(let y=-15.8;y<=11.8;y+=.25)for(let x=-10.8;x<=10.8;x+=.25){
   if(!inboard(x,y,w,h)||!free(x,y,w,h,'top'))continue;
   let cost=((x-target.x)**2+(y-target.y)**2)*(capParent[p.ref]?4:1);
   for(const q of placed){const shared=Object.values(p.pins).filter(n=>!['GND','V3','VSYS','VBAT','MIC_VDD'].includes(n)&&Object.values(q.pins).includes(n));if(shared.length)cost+=.25*((x-q.x)**2+(y-q.y)**2);}
   if(r!==p.r&&r!==0)cost+=.5;
   if(!best||cost<best.cost)best={x:+x.toFixed(3),y:+y.toFixed(3),r,cost};
  }
 }
 if(!best){console.error('No space for',p.ref);process.exit(1);}put(p,best.x,best.y,best.r);
}
fs.writeFileSync('src/placement-overrides.json',JSON.stringify(result,null,2));
fs.writeFileSync('output/placement-rectangles.json',JSON.stringify(placed,null,2));
console.log(`Placed ${placed.length} bodies with0.16mm separation; fixed mechanical controls preserved.`);
