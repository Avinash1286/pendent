// Create a compact handoff manifest after the caller reviews the final encoded frames.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
const project=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const repo=path.resolve(project,'../..');
assert.ok(process.argv.includes('--visual-reviewed'),'Review the final encoded frames before issuing the release manifest.');
const read=relative=>fs.readFileSync(path.join(repo,relative));
const json=relative=>JSON.parse(read(relative).toString());
const media=json('film/aura-launch/qa/media-final.json');
const check=json('film/aura-launch/qa/check-final.json');
const invariance=json('enclosure/print-invariance.json');
assert.equal(check.ok,true);assert.equal(check.strict,true);assert.equal(media.decodeExitCode,0);assert.equal(media.duration,44);assert.equal(invariance.byte_identical,true);
const paths=['enclosure/aura-product.blend','enclosure/aura-device.glb','enclosure/aura-pendant.glb','enclosure/aura-exploded.glb','enclosure/aura-a03-print-kit.zip','enclosure/renders/exploded.png','enclosure/asset-manifest.json','film/aura-launch/assets/aura-device.glb','film/aura-launch/renders/aura-launch.mp4','film/aura-launch/renders/poster.jpg','film/aura-launch/captions.vtt','film/aura-launch/renders/contact-sheet.jpg','film/aura-launch/qa/assembly-encoded.jpg','film/aura-launch/qa/check-final.json'];
const report={edition:'A03 final internal-placement sync',paths_relative_to:'repository root',previous_film_commit:'4d62c6b2f379fb410dc97941b622431bd6104f9b',cli_version:'0.8.31',duration_seconds:44,frames:1320,strict_check_zero_findings:true,full_decode_exit_code:0,encoded_visual_review_confirmed_by_caller:true,actual_print_mesh_changes:[],all_eight_stls_byte_identical:true,physical_qualification:false,artifacts:paths.map(relative=>{const data=read(relative);return {path:relative,bytes:data.length,sha256:crypto.createHash('sha256').update(data).digest('hex').toUpperCase()}})};
fs.writeFileSync(path.join(project,'qa/mechanical-sync-release.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({artifacts:report.artifacts.length,movie_sha256:media.sha256,all_eight_stls_byte_identical:true,physical_qualification:false}));
