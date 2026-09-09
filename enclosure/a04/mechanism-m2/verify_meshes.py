"""Read actual exported binary STLs, independently of Blender/model helpers."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument("--scenario",default="thin-cell");args=p.parse_args()
OUT=ROOT/args.scenario
manifest_path=OUT/'parts-manifest.json'
manifest=json.loads(manifest_path.read_text())
source_checks={name:hashlib.sha256(path.read_bytes()).hexdigest()==manifest[name] for name,path in {
    'contractSha256':ROOT/'contract.json',
    'generatorSha256':ROOT/'build_m2.py',
    'blendSha256':OUT/'aura-a04-m2.blend',
}.items()}


def inspect(path):
    raw=path.read_bytes()
    if len(raw)<84:raise ValueError(path.name)
    count,=struct.unpack_from('<I',raw,80)
    assert len(raw)==84+50*count
    edges={};winding={};parent={};triangles=[];volume=0;degenerate=0
    def find(v):
        parent.setdefault(v,v)
        while parent[v]!=v:parent[v]=parent[parent[v]];v=parent[v]
        return v
    for n in range(count):
        v=struct.unpack_from('<12fH',raw,84+n*50)
        tri=[tuple(v[3+3*i:6+3*i]) for i in range(3)]
        triangles.append(tri)
        a,b,c=tri
        cross=(b[1]*c[2]-b[2]*c[1],b[2]*c[0]-b[0]*c[2],b[0]*c[1]-b[1]*c[0])
        volume+=sum(a[i]*cross[i] for i in range(3))/6
        keys=[tuple(round(x,5) for x in pt) for pt in tri]
        area=math.sqrt(sum(((b[(i+1)%3]-a[(i+1)%3])*(c[(i+2)%3]-a[(i+2)%3])-(b[(i+2)%3]-a[(i+2)%3])*(c[(i+1)%3]-a[(i+1)%3]))**2 for i in range(3)))/2
        if len(set(keys))!=3 or area<1e-9:degenerate+=1
        for u,v in zip(keys,keys[1:]+keys[:1]):
            key=tuple(sorted((u,v)));edges[key]=edges.get(key,0)+1;winding[key]=winding.get(key,0)+(1 if u<v else -1)
            parent[find(v)]=find(u)
    verts=list(parent)
    lo=[min(v[i] for v in verts) for i in range(3)];hi=[max(v[i] for v in verts) for i in range(3)]
    result={'triangles':count,'connectedSolids':len({find(v) for v in verts}),'nonmanifoldEdges':sum(n!=2 for n in edges.values()),'inconsistentWindingEdges':sum(n!=0 for n in winding.values()),'degenerateTriangles':degenerate,'signedVolumeMm3':volume,'boundsMm':[lo,hi],'dimensionsMm':[hi[i]-lo[i] for i in range(3)]}
    result['topologyPass']=result['connectedSolids']==1 and result['nonmanifoldEdges']==result['inconsistentWindingEdges']==result['degenerateTriangles']==0 and volume>0
    return raw,triangles,verts,result


reports=[];failures=[name for name,ok in source_checks.items() if not ok]
for item in manifest['parts']:
    path=OUT/item['file'];raw,tris,verts,result=inspect(path)
    assert len(raw)==item['bytes'] and hashlib.sha256(raw).hexdigest()==item['sha256']
    translation=item['printTranslationMm']
    expected=[[item['assemblyBoundsMm'][end][i]+translation[i] for i in range(3)] for end in range(2)]
    reconstructed=[[result['boundsMm'][end][i]-translation[i] for i in range(3)] for end in range(2)]
    result['expectedPrintBoundsMm']=expected
    result['reconstructedAssemblyBoundsMm']=reconstructed
    result['boundsMatchManifest']=all(abs(result['boundsMm'][end][i]-expected[end][i])<.005 for end in range(2) for i in range(3)) and abs(result['boundsMm'][0][2])<.005
    if not result['topologyPass'] or not result['boundsMatchManifest']:failures.append(item['file'])
    result['file']=item['file'];reports.append(result)
result={'status':'DIGITAL MESH CHECK ONLY; NOT PHYSICAL QUALIFICATION','allPass':not failures,'sourceBindings':source_checks,'failures':failures,'specimenCount':len(reports),'physicalQualification':False,'nativeFitProven':False,'method':'Current contract/generator/BLEND hashes against manifest; binary STL length/hash; vertices welded at0.00001mm; oriented edge incidence, connected solids, signed volume, triangle area and all XYZ bounds translated back to the recorded assembly frame. Does not establish printer accuracy or complete self-intersection freedom.','manifestSha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),'verifierSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'parts':reports}
(OUT/'mesh-audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'scenario':args.scenario,'allPass':not failures,'failures':failures,'parts':len(reports)}))
if failures:raise SystemExit(1)
