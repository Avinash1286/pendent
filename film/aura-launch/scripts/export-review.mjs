// Decode and inspect the actual Hyperframes output, then generate review assets.
import fs from 'node:fs';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
const movie='renders/aura-launch.mp4';
function run(command,args,log) {
  const result=spawnSync(command,args,{encoding:'utf8',maxBuffer:10*1024*1024,windowsHide:true});
  if(log)fs.writeFileSync(log,result.stderr||'');
  if(result.error)throw result.error;
  if(result.status!==0)throw new Error(command+' failed: '+result.stderr?.slice(-1500));
  return result.stdout;
}
const probe=JSON.parse(run('ffprobe',['-v','error','-show_entries','format=duration,size:stream=codec_name,codec_type,width,height,r_frame_rate,nb_frames,sample_rate,channels','-of','json',movie]));
fs.writeFileSync('qa/ffprobe-final.json',JSON.stringify(probe,null,2)+'\n');
const video=probe.streams.find(s=>s.codec_type==='video');
const audio=probe.streams.find(s=>s.codec_type==='audio');
assert.equal(Number(probe.format.duration),44);assert.equal(video.width,1920);assert.equal(video.height,1080);assert.equal(video.r_frame_rate,'30/1');assert.equal(Number(video.nb_frames),1320);assert.equal(video.codec_name,'h264');assert.equal(audio.codec_name,'aac');assert.equal(Number(audio.sample_rate),48000);assert.equal(audio.channels,2);assert.ok(Number(probe.format.size)<100*1024*1024);
run('ffmpeg',['-hide_banner','-threads','2','-i',movie,'-af','volumedetect','-f','null','NUL'],'qa/decode-audio.log');
const levels=fs.readFileSync('qa/decode-audio.log','utf8');
const peak=Number(levels.match(/max_volume:\s*([-\d.]+) dB/)[1]);
const mean=Number(levels.match(/mean_volume:\s*([-\d.]+) dB/)[1]);
assert.ok(peak<0&&mean>-50);
const ffbase=['-hide_banner','-y','-threads','2','-i',movie];
const still=(filter,path,log)=>run('ffmpeg',[...ffbase,'-vf',filter,'-frames:v','1','-q:v','2','-update','1',path],log);
still('select=eq(n\\,1254)','renders/poster.jpg','qa/poster.log');
const grid=(frames,scale,tile,path,log)=>still('select='+frames.map(n=>'eq(n\\,'+n+')').join('+')+',scale='+scale+',tile='+tile,path,log);
grid([84,264,435,585,651,744,852,1014,1254],'640:360','3x3','renders/contact-sheet.jpg','qa/contact-sheet.log');
grid([651,678,726,768,822,852],'640:360','3x2','qa/assembly-encoded.jpg','qa/assembly-encoded.log');
grid([630,642,870,882,1044,1056],'640:360','3x2','qa/transitions-final.jpg','qa/transitions-final.log');
still('select=eq(n\\,1319)','qa/final-frame.png','qa/final-frame.log');
const report={edition:'A03-context-assembly',movie,duration:44,bytes:fs.statSync(movie).size,sha256:crypto.createHash('sha256').update(fs.readFileSync(movie)).digest('hex').toUpperCase(),video,audio,decodeExitCode:0,audioMeanDbfs:mean,audioPeakDbfs:peak,posterSeconds:41.8,contactSeconds:[2.8,8.8,14.5,19.5,21.7,24.8,28.4,33.8,41.8],assemblySeconds:[21.7,22.6,24.2,25.6,27.4,28.4],finalFrame:1319};
fs.writeFileSync('qa/media-final.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
