"""Bind M2 digital evidence; --verify checks without modifying any artifact."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[2];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text(encoding='utf-8'))
p=argparse.ArgumentParser();p.add_argument('--verify',action='store_true');a=p.parse_args();rp=ROOT/'readiness.json'
def section_hash():
 t=(REPO/'docs/a04/industrial-design.md').read_bytes().decode('utf-8');i=t.index('## M2 development checkpoint');j=t.index('## M1 mechanism checkpoint',i);return hashlib.sha256(t[i:j].encode('utf-8')).hexdigest()
if a.verify:
 r=read(rp);fail=[]
 for it in r['files']:
  f=ROOT/it['file']
  if not f.exists() or sha(f)!=it['sha256']:fail.append(it['file'])
 if section_hash()!=r['industrialDesignM2SectionSha256']:fail.append('industrial-design M2 section')
 au=REPO/r['externalCusVerification']['file']
 if sha(au)!=r['externalCusVerification']['sha256']:fail.append('authoritative CUS verification')
 print(json.dumps({'allBindingsMatch':not fail,'digitalScopePass':r['digitalScopePass'],'printRelease':False,'physicalQualification':False,'failures':fail}))
 if fail:raise SystemExit(1)
 raise SystemExit(0)
errors=[];scenarios=[]
for s in ('documented-pack','thin-cell'):
 d=ROOT/s;m=read(d/'parts-manifest.json');mesh=read(d/'mesh-audit.json');motion=read(d/'motion-audit.json')
 bindings={'contract':sha(ROOT/'contract.json')==m['contractSha256'],'generator':sha(ROOT/'build_m2.py')==m['generatorSha256'],'blend':sha(d/'aura-a04-m2.blend')==m['blendSha256'],'meshManifest':sha(d/'parts-manifest.json')==mesh['manifestSha256'],'motionManifest':sha(d/'parts-manifest.json')==motion['manifestSha256'],'motionBlend':sha(d/'aura-a04-m2.blend')==motion['blendSha256'],'checker':sha(ROOT/'check_m2.py')==motion['checkerSha256'],'meshVerifier':sha(ROOT/'verify_meshes.py')==mesh['verifierSha256']}
 for it in m['parts']:
  if sha(d/it['file'])!=it['sha256']:errors.append(s+'/'+it['file'])
 if not all(bindings.values()) or not mesh['allPass'] or not all(motion[k] for k in ['allStaticRigidPass','allSampledOperatingPass','allSampledAssemblyPass']):errors.append(s+' digital evidence')
 scenarios.append({'scenario':s,'bodyDiameterMm':43,'bodyDepthMm':m['bodyDepthMm'],'sourceBindings':bindings,'stlSpecimens':len(m['parts']),'meshPass':mesh['allPass'],'rigidSolids':motion['rigidSolidCount'],'softSolids':motion['softSolidCount'],'staticPass':motion['allStaticRigidPass'],'operatingPass':motion['allSampledOperatingPass'],'assemblyPass':motion['allSampledAssemblyPass'],'assemblyPaths':len(motion['assemblyPaths']),'assemblyPoseSamples':sum(p['samples'] for p in motion['assemblyPaths']),'capturePoseSamples':25,'privacyPoseSamples':162,'softWorkingStates':3,'continuousProof':False,'sourceBlendSha256':m['blendSha256'],'manifestSha256':sha(d/'parts-manifest.json')})
e=read(ROOT/'engineering-audit.json')
if not e['allPass'] or e['contractSha256']!=sha(ROOT/'contract.json') or e['scriptSha256']!=sha(ROOT/'engineering_audit.py'):errors.append('engineering audit')
ss=read(ROOT/'structural-screen.json')
if ss['sourceBindings']!={'contractSha256':sha(ROOT/'contract.json'),'generatorSha256':sha(ROOT/'build_m2.py'),'scriptSha256':sha(ROOT/'structural_screen.py')} or not ss['screeningSupportsNextUnpoweredJointTest']:errors.append('structural screening bindings')
vr=read(ROOT/'visual-review.json');renders=[]
for v in ('assembled','exploded'):
 r=read(ROOT/('render-'+v+'.json'));review=next(x for x in vr['reviews'] if x['view']==v);im=ROOT/r['image'];checked=r['imageSha256']==sha(im)==review['imageSha256'] and review['visuallyInspected'] and r['sourceSha256']==sha(ROOT/'documented-pack/aura-a04-m2.blend') and r['rendererSha256']==sha(ROOT/'render_m2.py') and r['inspectionBlendSha256']==sha(ROOT/'documented-pack'/('m2-'+v+'-inspection.blend'))
 if not checked:errors.append(v+' render/review binding')
 renders.append({'view':v,'image':r['image'],'imageSha256':sha(im),'sourceAndReviewBindingPass':checked,'rootActuallyReviewed':review['visuallyInspected'],'physicalOrNativeApproval':False})
files=[]
for f in sorted(ROOT.rglob('*')):
 if f.is_file() and f!=rp and f.suffix not in ('.log','.pyc') and '__pycache__' not in f.parts:files.append({'file':f.relative_to(ROOT).as_posix(),'bytes':f.stat().st_size,'sha256':sha(f)})
result={'revision':'A04 M2 S1 hybrid structural candidate','status':'SCOPED DIGITAL CHECKS ONLY; NOT A PRINT, POWERED, WEARABLE OR NATIVE PCB RELEASE','digitalScopePass':not errors,'sourceAndArtifactBindingsPass':not errors,'errors':errors,'scenarios':scenarios,'renders':renders,'externalCusVerification':{'file':e['authoritativeCusReview'],'sha256':e['authoritativeCusReviewSha256']},'industrialDesignM2SectionSha256':section_hash(),'files':files,'printRelease':False,'physicalQualification':False,'nativePlacementImported':False,'nativeBoardPlacedComponentsAtCheckpoint':0,'all72NativeFeaturesPending':True,'purchasedPcbReferencesPending':68,'safeSwitchEndpointQualified':False,'forceAndStructuralStrengthQualified':False,'structuralScreening':{'report':'structural-screen.json','candidate':'ASTM A666 Type 301 half-hard; explicitly lot-certified yield at least 110 ksi / 758 MPa','supplierLotOrFinishedPartQualified':False,'rejectedAnnealed304OneArm5NScreenPass':False,'candidate301CalculatedMetalScreenPass':ss['candidate301ScreenPass'],'candidateOneArm5NFactoredStressMPa':max(x['factoredMaximumEquivalentMPa'] for x in ss['unequalOneArmScreens']),'oneArm5NMaxSupportDeflectionSurrogateMm':max(x['serialDeflectionSurrogateMm'] for x in ss['unequalOneArmScreens']),'jointAndEndpointQualified':False,'nominalCaptureSectionIsToleranceProof':False},'supplierPackQualified':False,'rfAccepted':False,'bail':{'modeled':True,'rearDirection':'+Y','holeDiameterMm':2.6,'visibleInReviewedImages':False,'loadComfortBreakawayQualified':False},'requiredGates':['Source/footprint acceptance and placement of all72native PCB features; storage and other unmodeled packages, RF/courtyard/pad/lead integration.','Supplier-controlled pack/PCM/tab/lead/growth, dielectric, adhesive and thermal-sensor approval.','Actual switch mounted height, first operation, allowed endpoints, asymmetric privacy stops and safe overtravel calibration.','Foam rest preload, working force, alignment, creep, temperature and life; CAD soft allocation is not a material simulation.','Hybrid stock certificate/thickness and dielectric qualification; measured root seating, clamp preload, bearing, liner/cover creep and force-displacement; printed strips/ledges/thread and off-axis/cycle tests before print release.','Off-axis presses, repeated assembly/closure, torque, sealing, bail/chain strength, comfort and breakaway behavior.','Actual dock hardware, acoustic seals/response, thermal behavior, RF/finish/chain/body interaction and powered/worn testing.'],'visualReviewDoesNotApproveRelease':True}
rp.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({'digitalScopePass':not errors,'errors':errors,'filesBound':len(files),'readinessSha256':sha(rp)}))
if errors:raise SystemExit(1)
