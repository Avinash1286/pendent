"""DXF/profile/PDF checks and an immutable-file binding verifier."""
import argparse,hashlib,json,math,sys,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parent;SOURCE=ROOT.parent/'mechanism-m2';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text(encoding='utf-8'))
a=argparse.ArgumentParser();a.add_argument('--verify',action='store_true');args=a.parse_args();report=ROOT/'manufacturing-verification.json'
if args.verify:
 r=read(report);bad=[x['file'] for x in r['files'] if not (ROOT/x['file']).exists() or sha(ROOT/x['file'])!=x['sha256']]
 for x in r['sourceFiles']:
  if not (SOURCE/x['file']).exists() or sha(SOURCE/x['file'])!=x['sha256']:bad.append('source/'+x['file'])
 print(json.dumps({'allBindingsMatch':not bad,'profileAndDxfChecksPass':r['profileAndDxfChecksPass'],'pdfReviewed':r['pdfReviewed'],'fabricationRelease':False,'physicalQualification':False,'failures':bad}))
 raise SystemExit(bool(bad))
sys.path.insert(0,str(ROOT/'tmp/dxf-deps'))
import ezdxf
from pypdf import PdfReader
p=read(ROOT/'profiles.json');assert sha(ROOT/'extract_profiles.py')==p['extractorSha256'];assert sha(SOURCE/'readiness.json')==p['sourceReadinessSha256'];assert sha(SOURCE/'build_m2.py')==p['sourceGeneratorSha256'];assert sha(SOURCE/'contract.json')==p['contractSha256']

def orient(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def between(a,b,c):return min(a[0],b[0])-1e-9<=c[0]<=max(a[0],b[0])+1e-9 and min(a[1],b[1])-1e-9<=c[1]<=max(a[1],b[1])+1e-9
def crossing(a,b,c,d):
 o=[orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)]
 if o[0]*o[1]<0 and o[2]*o[3]<0:return True
 return any(abs(v)<1e-10 and between(x,y,z) for v,x,y,z in [(o[0],a,b,c),(o[1],a,b,d),(o[2],c,d,a),(o[3],c,d,b)])
checks=[]
for item in p['scenarios'][0]['parts']:
 path=ROOT/item['profileFile'];doc=ezdxf.readfile(path);audit=doc.audit();entities=list(doc.modelspace());assert not audit.errors and not audit.fixes;assert len(entities)==1;ent=entities[0];assert ent.dxftype()=='LWPOLYLINE' and ent.closed and doc.units==4;points=[tuple(v) for v in ent.get_points('xy')];want=item['profileLocalXYMm'];assert len(points)==len(want);err=max(math.dist(a,b) for a,b in zip(points,want));assert err<=1e-6
 assert not ent.has_arc and all(math.dist(a,b)>1e-8 for a,b in zip(points,points[1:]+points[:1]))
 n=len(points)
 for i in range(n):
  for j in range(i+1,n):
   if j==i+1 or (i==0 and j==n-1):continue
   assert not crossing(points[i],points[(i+1)%n],points[j],points[(j+1)%n]),('Self intersection',i,j)
 area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))/2;assert area>0 and abs(area-item['profileAreaMm2'])<1e-4
 svg=ET.parse(path.with_suffix('.svg')).getroot();assert svg.attrib['width'].endswith('mm') and svg.attrib['height'].endswith('mm');paths=svg.findall('{http://www.w3.org/2000/svg}path');assert len(paths)==1 and paths[0].attrib['d'].endswith(' Z')
 checks.append({'file':path.name,'reader':'ezdxf '+ezdxf.__version__,'readWithoutRecovery':True,'auditErrors':0,'auditFixes':0,'units':4,'unitMeaning':'millimetres','closedLwPolylineCount':1,'vertices':len(points),'selfIntersections':0,'fittedArcs':False,'kerfCompensationApplied':False,'maxRoundTripVertexErrorMm':err,'profileAreaMm2':area,'pass':True})
pdf=ROOT/'m2-s1-steel-development-drawings.pdf';reader=PdfReader(str(pdf));assert len(reader.pages)==2
for i,page in enumerate(reader.pages):
 txt=page.extract_text();assert all(s in txt for s in ['DEVELOPMENT','A666','758','INSUNITS','NO HOLES','MESH REF','QUOTE / UNPOWERED FIXTURE ONLY']);assert abs(float(page.mediabox.width)-297*72/25.4)<.01 and abs(float(page.mediabox.height)-210*72/25.4)<.01
review=read(ROOT/'drawing-review.json');assert review['pdfSha256']==sha(pdf) and review['visuallyInspected'] and review['pagesReviewed']==[1,2]
files=[{'file':f.relative_to(ROOT).as_posix(),'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(ROOT.rglob('*')) if f.is_file() and f!=report and 'tmp' not in f.relative_to(ROOT).parts and '__pycache__' not in f.relative_to(ROOT).parts]
sources=['readiness.json','contract.json','build_m2.py','structural-screen.json']
for s in p['scenarios']:
 sources.extend([s['scenario']+'/aura-a04-m2.blend',s['scenario']+'/parts-manifest.json'])
 sources.extend(x['stlFile'] for x in s['parts'])
r={'status':'DEVELOPMENT QUOTE AND UNPOWERED FIXTURE ARTIFACTS ONLY','scratchDirectoryExcluded':'tmp/','profileAndDxfChecksPass':True,'pdfReviewed':True,'pdfPages':2,'drawingPdfSha256':sha(pdf),'profileChecks':checks,'prismaticSourceAndTwoVariantConcordance':True,'extractionDetails':'profiles.json','numericalComparisonIsManufacturingTolerance':False,'sourceFiles':[{'file':f,'sha256':sha(SOURCE/f)} for f in sorted(set(sources))],'files':files,'materialCandidate':'ASTM A666 Type 301 half-hard; explicitly lot-certified 0.2% yield >=110 ksi /758 MPa','definedActualMetalThicknessAcceptanceMm':{'shoe':[.28,.32],'lowerSupport':[.95,1.00]},'xyToleranceApproved':False,'flatnessLimitApproved':False,'edgeProcessQualified':False,'insulationQualified':False,'supplierOrLotApproved':False,'nativeBoardFitQualified':False,'physicalStrengthQualified':False,'fabricationRelease':False,'noOrdersOrSupplierMessagesSent':True}
report.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps({'allPass':True,'filesBound':len(files),'sourceFilesBound':len(set(sources)),'dxfProfiles':2,'pdfPages':2,'verificationSha256':sha(report)}))
