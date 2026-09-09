"""Extract constant-thickness profiles from frozen S1 meshes. Never edit their source."""
import collections,hashlib,json,math,struct
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parent;SOURCE=ROOT.parent/'mechanism-m2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
NAMES=['08_MEASURED_PLUNGER_SHOE','13_LOWER_STEEL_STIFFENER']
EXPECTED_READINESS='5c14fb6971a0d69e322c3e61b7ffa980de14be209d35e379c558c3df31dad157'
assert sha(SOURCE/'readiness.json')==EXPECTED_READINESS,'Frozen source checkpoint differs'
TOL=1e-5

def area(p):return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(p,p[1:]+p[:1]))/2

def boundary(tri,z):
 edges=collections.Counter();xy={}
 for t in tri:
  if all(abs(v[2]-z)<TOL for v in t):
   keys=[(round(v[0],7),round(v[1],7)) for v in t]
   for k,v in zip(keys,t):xy[k]=v[:2]
   for a,b in zip(keys,keys[1:]+keys[:1]):edges[tuple(sorted((a,b)))]+=1
 assert edges and all(n in (1,2) for n in edges.values())
 graph=collections.defaultdict(list)
 for (a,b),n in edges.items():
  if n==1:graph[a].append(b);graph[b].append(a)
 assert all(len(v)==2 for v in graph.values()),'Open/branching cap boundary'
 unseen=set(graph);loops=[]
 while unseen:
  start=min(unseen);chain=[start];prev=None;cur=start
  while True:
   nxt=next(x for x in sorted(graph[cur]) if x!=prev)
   if nxt==start:break
   assert nxt not in chain,'Non-simple chain'
   chain.append(nxt);prev,cur=cur,nxt
  unseen.difference_update(chain);pts=[xy[k] for k in chain]
  if area(pts)<0:pts.reverse()
  j=min(range(len(pts)),key=lambda i:(pts[i][0],pts[i][1]));pts=pts[j:]+pts[:j];loops.append(pts)
 return loops

def dxf(path,pts):
 # R2000 DXF, one closed LWPOLYLINE, millimetre unit header, zero bulges.
 rows=[(0,'SECTION'),(2,'HEADER'),(9,'$ACADVER'),(1,'AC1015'),(9,'$INSUNITS'),(70,4),(9,'$MEASUREMENT'),(70,1),(0,'ENDSEC'),(0,'SECTION'),(2,'ENTITIES'),(0,'LWPOLYLINE'),(100,'AcDbEntity'),(8,'CUT_PROFILE'),(100,'AcDbPolyline'),(90,len(pts)),(70,1)]
 for x,y in pts:rows.extend([(10,f'{x:.6f}'),(20,f'{y:.6f}')])
 rows.extend([(0,'ENDSEC'),(0,'EOF')]);path.write_text(''.join(f'{a}\n{b}\n' for a,b in rows),encoding='ascii')

cases=[]
for scenario in ('documented-pack','thin-cell'):
 out=SOURCE/scenario;m=json.loads((out/'parts-manifest.json').read_text(encoding='utf-8'));assert sha(out/'aura-a04-m2.blend')==m['blendSha256'];assert sha(SOURCE/'contract.json')==m['contractSha256'];assert sha(SOURCE/'build_m2.py')==m['generatorSha256']
 bpy.ops.wm.open_mainfile(filepath=str(out/'aura-a04-m2.blend'));items=[]
 for n in NAMES:
  o=bpy.data.objects[n];mi=next(x for x in m['parts'] if x['object']==n);ao=next(x for x in m['allAssemblyObjects'] if x['object']==n)
  geom={'vertices':[[round(float(c),7) for c in o.matrix_world@v.co] for v in o.data.vertices],'faces':[list(p.vertices) for p in o.data.polygons]}
  worldsha=hashlib.sha256(json.dumps(geom,separators=(',',':')).encode()).hexdigest();assert worldsha==ao['worldGeometrySha256']
  vv=[list(o.matrix_world@v.co) for v in o.data.vertices];assert all(len(p.vertices)==3 for p in o.data.polygons);tri=[[vv[i] for i in p.vertices] for p in o.data.polygons]
  zmin=min(v[2] for v in vv);zmax=max(v[2] for v in vv);assert all(min(abs(v[2]-zmin),abs(v[2]-zmax))<TOL for v in vv),'Not a two-plane prism'
  top=boundary(tri,zmax);bottom=boundary(tri,zmin);assert len(top)==len(bottom)==1,'Profile requires holes or separate islands';top=top[0];bottom=bottom[0]
  assert len(top)==len(bottom) and max(math.dist(a,b) for a,b in zip(top,bottom))<TOL
  lo=[min(v[i] for v in vv) for i in range(3)];hi=[max(v[i] for v in vv) for i in range(3)];pts=[[x-lo[0],y-lo[1]] for x,y in top]
  # Independent exported STL cap comparison, applying its recorded print translation.
  sp=out/mi['file'];assert sha(sp)==mi['sha256'];raw=sp.read_bytes();count=struct.unpack_from('<I',raw,80)[0];assert len(raw)==84+50*count;st=[]
  for i in range(count):
   q=struct.unpack_from('<12fH',raw,84+50*i);st.append([[q[3+3*j+k]-mi['printTranslationMm'][k] for k in range(3)] for j in range(3)])
  sttop=boundary(st,hi[2]);assert len(sttop)==1 and len(sttop[0])==len(top);sterr=max(math.dist(a,b) for a,b in zip(sttop[0],top));assert sterr<TOL
  vol=abs(sum(a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]) for a,b,c in tri)/6);av=area(pts)*(hi[2]-lo[2]);assert abs(vol-av)<max(1e-4,av*1e-5)
  items.append({'object':n,'profileLocalXYMm':pts,'cadOriginXYMm':lo[:2],'cadBoundsMm':[lo,hi],'worldGeometrySha256':worldsha,'stlFile':str(sp.relative_to(SOURCE)).replace('\\','/'),'stlSha256':sha(sp),'stlToSourceCapMaxVertexErrorMm':sterr,'profileAreaMm2':area(pts),'sourceVolumeMm3':vol,'areaTimesThicknessMm3':av,'allVerticesOnTwoParallelPlanes':True,'closedExteriorLoops':1,'holes':0,'nominalMeshThicknessMm':hi[2]-lo[2]})
 cases.append({'scenario':scenario,'manifestSha256':sha(out/'parts-manifest.json'),'blendSha256':sha(out/'aura-a04-m2.blend'),'parts':items})
# The two depth variants translate these flat forms only in Z.
for a,b in zip(cases[0]['parts'],cases[1]['parts']):
 assert len(a['profileLocalXYMm'])==len(b['profileLocalXYMm']) and max(math.dist(x,y) for x,y in zip(a['profileLocalXYMm'],b['profileLocalXYMm']))<TOL
 assert math.dist(a['cadOriginXYMm'],b['cadOriginXYMm'])<TOL and abs(a['nominalMeshThicknessMm']-b['nominalMeshThicknessMm'])<TOL
for p in cases[0]['parts']:
 name='shoe' if p['object'].startswith('08_') else 'lower-support';pts=p['profileLocalXYMm'];w=max(x for x,y in pts);h=max(y for x,y in pts);p['profileFile']=f'm2-s1-{name}-profile.dxf';dxf(ROOT/p['profileFile'],pts)
 svg='M '+' L '.join(f'{x:.6f},{h-y:.6f}' for x,y in pts)+' Z';(ROOT/f'm2-s1-{name}-profile.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.6f}mm" height="{h:.6f}mm" viewBox="0 0 {w:.6f} {h:.6f}"><title>M2 S1 {name}: development profile, no fabrication release</title><desc>Millimetres; exact faceted source boundary. No kerf compensation or fitted arcs. SVG Y is reflected for display; DXF uses CAD +Y up.</desc><path d="{svg}" fill="none" stroke="black" stroke-width="0.02"/></svg>',encoding='utf-8')
r={'status':'DEVELOPMENT QUOTE / UNPOWERED FIXTURE GEOMETRY; NOT FABRICATION OR FIT RELEASE','sourceReadinessSha256':EXPECTED_READINESS,'contractSha256':sha(SOURCE/'contract.json'),'sourceGeneratorSha256':sha(SOURCE/'build_m2.py'),'extractorSha256':sha(Path(__file__)),'method':'Top cap boundary of actual frozen BLEND triangles; direct world-geometry hash match and independent STL cap comparison. Exact faceted polyline; no silhouette smoothing, arc fitting, offset or redesign.','coordinateConvention':'DXF local origin is the lower-left XY envelope intersection, not a physical datum. CAD XY = profile XY + reported origin. CAD +Y is up; viewing from +Z.','numericalComparisonToleranceMm':TOL,'numericalToleranceIsManufacturingTolerance':False,'bothVariantsShareProfiles':True,'scenarios':cases,'nativeBoardFitQualified':False,'manufacturingTolerancesApproved':False,'physicalStrengthQualified':False,'fabricationRelease':False}
(ROOT/'profiles.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps({'profiles':[(p['object'],len(p['profileLocalXYMm']),p['profileAreaMm2']) for p in cases[0]['parts']],'bothVariantsConcordant':True}))
