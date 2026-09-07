import fs from 'node:fs';
import path from 'node:path';
const sampleRate = 48000, duration = 36, frames = sampleRate * duration;
const left = new Float64Array(frames), right = new Float64Array(frames);
const TAU = Math.PI * 2;
const midi = n => 440 * 2 ** ((n - 69) / 12);
function tone(start, length, note, gain, pan=0, bell=false) {
  const hz=midi(note), first=Math.floor(start*sampleRate), count=Math.min(Math.floor(length*sampleRate), frames-first);
  for(let i=0;i<count;i++) {
    const t=i/sampleRate, f=i/count;
    const attack = Math.min(1,t/(bell?.015:1.5));
    const release = Math.min(1,(length-t)/(bell?.8:1.7));
    const env = attack * release * (bell?Math.exp(-t/1.3):Math.sin(Math.PI*f)**.65);
    const fundamental = Math.sin(TAU*hz*t + (bell?.22:.05)*Math.sin(TAU*hz*2*t)*Math.exp(-t*2));
    const v=gain*env*(fundamental+.14*Math.sin(TAU*hz*2*t)+.04*Math.sin(TAU*hz*3*t));
    left[first+i]+=v*Math.sqrt((1-pan)/2); right[first+i]+=v*Math.sqrt((1+pan)/2);
  }
}
const chords=[[50,57,64,66],[47,54,61,66],[43,50,57,62],[45,52,59,64],[50,57,62,66]];
const starts=[0,7,14,21,28];
chords.forEach((chord,j)=>chord.forEach((note,i)=>tone(starts[j],8,note,.021,(i-1.5)*.2)));
const bells=[[.8,74],[2.4,81],[4,78],[6.8,76],[9.7,74],[11.6,78],[14,81],[17.1,79],[19.3,78],[22,76],[24.1,74],[26.4,73],[29,74],[31.1,81],[32.7,78]];
bells.forEach(([start,note],i)=>tone(start,3.2,note,.043,Math.sin(i*2.4)*.42,true));
// Two gentle, source-original transition swells, deterministic harmonic synthesis.
for(const start of [9.5,21.3,28.4]) tone(start,1.3,86,.009,0,false);
for(let i=0;i<frames;i++) {
  const t=i/sampleRate, fade=Math.min(1,t/1.2,(duration-t)/2.4);
  // Bounded feedback-free echo widens the bells; all audio is rendered offline.
  const echo=Math.floor(.271*sampleRate);
  const l=left[i]+(i>echo?right[i-echo]*.17:0),r=right[i]+(i>echo?left[i-echo]*.17:0);
  left[i]=Math.tanh(l*2.1)*1.84*fade; right[i]=Math.tanh(r*2.1)*1.84*fade;
}
const data=Buffer.alloc(frames*4+44);
data.write('RIFF',0);data.writeUInt32LE(data.length-8,4);data.write('WAVE',8);data.write('fmt ',12);data.writeUInt32LE(16,16);data.writeUInt16LE(1,20);data.writeUInt16LE(2,22);data.writeUInt32LE(sampleRate,24);data.writeUInt32LE(sampleRate*4,28);data.writeUInt16LE(4,32);data.writeUInt16LE(16,34);data.write('data',36);data.writeUInt32LE(frames*4,40);
for(let i=0;i<frames;i++){data.writeInt16LE(Math.round(Math.max(-1,Math.min(1,left[i]))*32767),44+i*4);data.writeInt16LE(Math.round(Math.max(-1,Math.min(1,right[i]))*32767),46+i*4);}
fs.mkdirSync('assets',{recursive:true});fs.writeFileSync(path.resolve('assets/aura-score.wav'),data);
console.log(`Original score: ${duration}s, ${sampleRate}Hz stereo, ${data.length} bytes`);
