// Precompute the fixed studio once; no environment convolution runs during video seeks.
import fs from 'node:fs';
import http from 'node:http';
import crypto from 'node:crypto';
import { build } from 'esbuild';
import puppeteer from 'puppeteer-core';
const code=`
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
const renderer=new THREE.WebGLRenderer({antialias:false});
renderer.setSize(16,16);document.body.appendChild(renderer.domElement);
const pmrem=new THREE.PMREMGenerator(renderer);
const room=new RoomEnvironment();
const target=pmrem.fromScene(room,.03);
const data=new Uint16Array(target.width*target.height*4);
renderer.readRenderTargetPixels(target,0,0,target.width,target.height,data);
window.__baked={width:target.width,height:target.height,halfFloat:true,data:Array.from(data)};
`;
const built=await build({stdin:{contents:code,resolveDir:process.cwd()},bundle:true,write:false,format:'iife',minify:true});
const html='<!doctype html><body><script>'+built.outputFiles[0].text.replaceAll('</script','<\\/script')+'</script></body>';
const server=http.createServer((req,res)=>{res.writeHead(200,{'Content-Type':'text/html'});res.end(html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const executablePath=process.env.CHROME_PATH||'C:/Users/avina/.cache/hyperframes/chrome/chrome-headless-shell/win64-152.0.7977.30/chrome-headless-shell-win64/chrome-headless-shell.exe';
let browser;
try {
  browser=await puppeteer.launch({executablePath,headless:true,args:['--use-angle=d3d11','--ignore-gpu-blocklist','--enable-webgl']});
  const page=await browser.newPage();
  const warnings=[];page.on('console',msg=>{if(msg.type()==='warn')warnings.push(msg.text());});
  await page.goto('http://127.0.0.1:'+server.address().port,{waitUntil:'load'});
  await page.waitForFunction(()=>Boolean(window.__baked),{timeout:60000});
  const {data,...meta}=await page.evaluate(()=>window.__baked);
  const bytes=Buffer.from(new Uint16Array(data).buffer);
  if(!data.some(n=>n!==0))throw new Error('Environment readback is empty');
  fs.writeFileSync('assets/studio-environment.bin',bytes);
  fs.writeFileSync('assets/studio-environment.json',JSON.stringify(meta,null,2)+'\n');
  const report={...meta,bytes:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex').toUpperCase(),three:'0.182.0',source:'RoomEnvironment, PMREM sigma 0.03',bakeWarnings:warnings};
  fs.writeFileSync('qa/environment-bake.json',JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({...report,bakeWarnings:warnings.length}));
} finally { if(browser)await browser.close();await new Promise(resolve=>server.close(resolve)); }
