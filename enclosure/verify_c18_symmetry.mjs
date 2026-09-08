// Prove the existing exported C18 body is invariant under a local half-turn.
// This applies to one unmarked, nonpolar body proxy only; never to PCB pin mapping.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const sha=data=>crypto.createHash('sha256').update(data).digest('hex');
const json=name=>JSON.parse(fs.readFileSync(path.join(root,name),'utf8'));
const mpn='C0402C104K4RACTU';
assert.equal(json('component-body-reference.json').bodies.C18.mpn,mpn);
const tolerance=2e-10,normalTolerance=1e-5;
const turn=p=>[-p[0],p[1],-p[2]]; // glTF local Y is CAD local Z.
const key=p=>p.map(v=>Math.round(v/tolerance)||0).join(',');
const sub=(a,b)=>a.map((v,i)=>v-b[i]);
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const norm=a=>Math.sqrt(dot(a,a));
const expected={
  'aura-device.glb':'a0d3b7e04b07141e8dd1b356f22eae08e609571b16788506ccfb431f409ac72a',
  'aura-pendant.glb':'634a9facee379874444c120e4978ec42811c330679d971c849f478a806180e80',
  'aura-exploded.glb':'4b2fe53470fabf70384097e84d25a2c54ffd7a70d793f47bbdf67d85522d21c7',
  'aura-product.blend':'25780cc538bb25db6df25e3af51778f81035e04bca98b08444ad4ae4418f9733',
  '../film/aura-launch/renders/aura-launch.mp4':'1f208827348028c6aba7508524e1d1da0ffa45779663bf3bf75e97fb6cdfaee0',
};
const preserved=Object.entries(expected).map(([name,hash])=>{
  const data=fs.readFileSync(path.join(root,name));assert.equal(sha(data),hash,'Unexpected binary change: '+name);
  return {path:name,sha256:hash,bytes:data.length,unchanged:true};
});
const meshes=[];
for(const name of Object.keys(expected).filter(n=>n.endsWith('.glb'))){
  const data=fs.readFileSync(path.join(root,name)),length=data.readUInt32LE(12);
  const gltf=JSON.parse(data.subarray(20,20+length).toString()),bin=data.subarray(28+length);
  const nodes=gltf.nodes.filter(n=>n.extras?.hardware_reference==='C18');assert.equal(nodes.length,1);
  const node=nodes[0];assert.equal(node.extras.manufacturer_part_number,mpn);
  assert.ok(!node.children?.length,'C18 must have no child pad or marking geometry');
  assert.deepEqual(node.scale||[1,1,1],[1,1,1]);
  const q=node.rotation;assert.ok(Math.abs(q[0])+Math.abs(q[2])<1e-6&&Math.abs(q[1]-Math.SQRT1_2)<1e-6&&Math.abs(q[3]-Math.SQRT1_2)<1e-6,'Expected canonical 90 degree display rotation');
  const primitives=gltf.meshes[node.mesh].primitives;assert.equal(primitives.length,1);
  const primitive=primitives[0];assert.equal(primitive.mode??4,4);assert.ok(!primitive.targets);
  const material=gltf.materials[primitive.material];
  assert.ok(!/texture|anisotrop/i.test(JSON.stringify(material)),'No direction-dependent material allowed');
  assert.ok(!Object.keys(primitive.attributes).some(k=>k.startsWith('COLOR')));
  const accessor=index=>{
    const a=gltf.accessors[index],view=gltf.bufferViews[a.bufferView];assert.ok(!a.sparse&&!a.normalized);assert.equal(view.buffer,0);
    const counts={SCALAR:1,VEC2:2,VEC3:3},types={5126:[4,'readFloatLE'],5123:[2,'readUInt16LE'],5125:[4,'readUInt32LE']};
    const count=counts[a.type],[bytes,read]=types[a.componentType];assert.ok(count);
    const offset=(view.byteOffset||0)+(a.byteOffset||0),stride=view.byteStride||bytes*count;
    return Array.from({length:a.count},(_,i)=>Array.from({length:count},(_,j)=>bin[read](offset+i*stride+j*bytes)));
  };
  const positions=accessor(primitive.attributes.POSITION),normals=accessor(primitive.attributes.NORMAL),indices=accessor(primitive.indices).flat();
  assert.equal(positions.length,normals.length);assert.equal(indices.length%3,0);
  const unique=new Map(positions.map(p=>[key(p),p])),points=[...unique.values()];
  const maxVertexError=Math.max(...points.map(p=>Math.min(...points.map(other=>norm(sub(turn(p),other))))));
  assert.ok(maxVertexError<tolerance,'Actual exported vertex set is not half-turn invariant');
  let maxNormalError=0;
  positions.forEach((p,i)=>{
    const candidates=positions.map((other,j)=>norm(sub(turn(p),other))<tolerance?j:-1).filter(j=>j>=0);
    const error=Math.min(...candidates.map(j=>norm(sub(turn(normals[i]),normals[j]))));
    maxNormalError=Math.max(maxNormalError,error);assert.ok(error<normalTolerance,'Shading normal is not half-turn invariant');
  });
  const edges=new Map(),adjacency=new Map(points.map(p=>[key(p),new Set()])),triangles=[];let signedVolume=0;
  for(let i=0;i<indices.length;i+=3){
    const triangle=indices.slice(i,i+3).map(j=>positions[j]),keys=triangle.map(key);assert.equal(new Set(keys).size,3);
    triangles.push(keys.sort().join('|'));
    const [a,b,c]=triangle,normal=cross(sub(b,a),sub(c,a)),size=norm(normal);assert.ok(size>1e-18);
    signedVolume+=dot(a,cross(b,c))/6;
    for(let j=0;j<3;j++){
      const u=key(triangle[j]),v=key(triangle[(j+1)%3]),edge=[u,v].sort().join('|');
      edges.set(edge,(edges.get(edge)||0)+1);adjacency.get(u).add(v);adjacency.get(v).add(u);
    }
  }
  assert.ok([...edges.values()].every(count=>count===2),'Mesh is not closed manifold');
  const visited=new Set(),queue=[key(points[0])];while(queue.length){const k=queue.pop();if(visited.has(k))continue;visited.add(k);queue.push(...adjacency.get(k));}
  assert.equal(visited.size,points.length,'Mesh must be connected');
  assert.equal(points.length-edges.size+triangles.length,2);assert.ok(Math.abs(signedVolume)>1e-14);
  const rotated=[];for(let i=0;i<indices.length;i+=3)rotated.push(indices.slice(i,i+3).map(j=>key(turn(positions[j]))).sort().join('|'));
  const exactTriangleSet=JSON.stringify(triangles.sort())===JSON.stringify(rotated.sort());
  assert.ok(exactTriangleSet,'Actual triangulated surface is not half-turn invariant');
  const normalKey=n=>n.map(v=>Math.round(v/normalTolerance)||0).join(',');
  const shadedSignature=rotation=>{
    const rows=[];for(let i=0;i<indices.length;i+=3)rows.push(indices.slice(i,i+3).map(j=>key(rotation(positions[j]))+'@'+normalKey(rotation(normals[j]))).sort().join('|'));
    return sha(JSON.stringify(rows.sort()));
  };
  assert.equal(shadedSignature(p=>p),shadedSignature(turn),'Triangle-associated shading normals differ');
  meshes.push({path:name,glb_sha256:sha(data),node:node.name,mpn,visual_rotation_degrees:90,unique_position_count:points.length,triangle_count:triangles.length,connected_closed_manifold:true,euler_characteristic:2,volume_mm3:Math.abs(signedVolume)*1e9,maximum_half_turn_vertex_error_metres:maxVertexError,maximum_half_turn_normal_error:maxNormalError,vertex_set_half_turn_invariant:true,normal_field_half_turn_invariant:true,triangle_connectivity_half_turn_invariant:exactTriangleSet,shaded_triangle_signature:shadedSignature(turn),triangle_associated_normals_half_turn_invariant:true,uniform_untextured_material:true,unused_uvs_present:'TEXCOORD_0' in primitive.attributes,physical_body_solid_half_turn_invariant:true});
}
const report={scope:'C18 exact-MPN visual body symmetry only; PCB pin orientation is not exempted',ok:true,reference:'C18',mpn,source_rotation_degrees:270,canonical_visual_rotation_degrees:90,symmetry_degrees:180,position_tolerance_metres:tolerance,normal_tolerance:normalTolerance,proof:'Each actual exported body is a connected closed manifold with an invariant complete triangle set, including the normals associated with each triangle vertex, under a half-turn. This proves the same triangulated surface and interpolated shading, without relying on a bounding box or convexity assumption. The material is uniform and untextured; UVs are unused. No pads or pin labels are represented.',manufacturer_marking:'No',manufacturer_specification:'https://search.kemet.com/download/specsheet/C0402C104K4RACTU',physical_qualification:false,meshes,preserved_artifacts:preserved};
fs.writeFileSync(path.join(root,'c18-symmetry-audit.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({ok:report.ok,meshes:meshes.length,preserved_artifacts:preserved.length,maximum_vertex_error:Math.max(...meshes.map(m=>m.maximum_half_turn_vertex_error_metres)),maximum_normal_error:Math.max(...meshes.map(m=>m.maximum_half_turn_normal_error)),triangle_invariance:meshes.map(m=>m.triangle_connectivity_half_turn_invariant)}));
