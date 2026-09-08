"""Bind the experimental M1 checkpoint without concealing failed design checks."""
import hashlib,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
scenarios=[]
for name in ('thin-cell','documented-pack'):
    folder=ROOT/name;m=read(folder/'parts-manifest.json')
    assert m['partCount']==14 and m['devicePartCandidates']==12 and m['unpoweredGauges']==2
    for key,path in [('contractSha256',ROOT/'mechanism-contract.json'),('generatorSha256',ROOT/'build_mechanism.py'),('blendSha256',folder/'aura-a04-mechanism.blend')]:assert m[key]==sha(path),(name,key)
    assert {p.name for p in folder.glob('*.stl')}=={p['file'] for p in m['parts']}
    for p in m['parts']:
        path=folder/p['file'];assert path.stat().st_size==p['bytes'] and sha(path)==p['sha256']
    mesh=read(folder/'mesh-audit.json');motion=read(folder/'motion-audit.json')
    assert mesh['allPass'] and all(mesh['sourceBindings'].values())
    assert mesh['manifestSha256']==motion['manifestSha256']==sha(folder/'parts-manifest.json')
    assert mesh['verifierSha256']==sha(ROOT/'verify_meshes.py')
    assert motion['checkerSha256']==sha(ROOT/'check_motion.py') and all(motion['sourceBindings'].values())
    scenarios.append({'id':name,'stlSpecimens':14,'meshExportChecksPass':True,'allRigidTrialChecksPass':motion['allRigidTrialChecksPass'],'nonActuatingRigidClearancesPass':motion['nonActuatingRigidClearancesPass'],'captureActuationValidated':False,'faceSweepSamples':len(motion['faceSweep']),'privacySweepSamples':len(motion['privacySweep']),'bodyDiameterMm':m['bodyDiameterMm'],'bodyDepthMm':m['bodyDepthMm'],'pcbActualThicknessMm':m['pcbThicknessMm']})
allocation=read(ROOT/'allocation-audit.json')
assert allocation['calculatorSha256']==sha(ROOT/'audit_allocation.py') and allocation['contractSha256']==sha(ROOT/'mechanism-contract.json')
render=read(ROOT/'inspection-render.json')
assert render['sourceSha256']==sha(ROOT/render['source']) and render['rendererSha256']==sha(ROOT/'render_mechanism.py')
raw=(ROOT/render['image']).read_bytes()
assert sha(ROOT/render['image'])==render['imageSha256']
assert raw[:8]==b'\x89PNG\r\n\x1a\n' and raw[-12:]==b'\x00\x00\x00\x00IEND\xaeB`\x82'
assert struct.unpack('>II',raw[16:24])==(1400,1400)
review_path=ROOT/'visual-review.json'
review=read(review_path) if review_path.exists() else {}
visually_inspected=(review.get('image')==render['image'] and review.get('imageSha256')==render['imageSha256'] and review.get('visuallyInspected') is True)
files=[]
for path in sorted(ROOT.rglob('*')):
    if not path.is_file() or path.name=='mechanism-readiness.json' or '__pycache__' in path.parts:continue
    assert not path.is_symlink()
    files.append({'path':path.relative_to(ROOT).as_posix(),'bytes':path.stat().st_size,'sha256':sha(path)})
result={
 'revision':'A04 M1','status':'EXPERIMENTAL CHECKPOINT; ASSEMBLY AND MOTION FAILURES REMAIN',
 'blenderVersionUsed':'5.2.1 LTS','nativePcbModified':False,'nativePlacementImported':False,
 'physicalQualification':False,'completeBodyAssemblyReady':False,'printRelease':False,'wearableReady':False,
 'exportedStlSpecimens':28,'devicePartCandidatesPerScenario':12,'unpoweredGaugesPerScenario':2,
 'sourceAndExportBindingsPass':True,'scenarios':scenarios,
 'blockingFindings':[
  'Fixed closure bosses obstruct straight rear insertion of the full face skin; no alternate insertion construction/path is proven.',
  'PCB axial support/retention is absent; its assembly Z remains a placement assumption.',
  'Moving status lightpipe intersects maximum radio envelope by about0.022mm3 at0.4mm inward travel in both scenarios.',
  'Sizing plunger demands0.35mm depression; safe switch overtravel is not established by0.1-0.3mm electrical travel.',
  'Native JS202011JCQN conflicts with thin generic top stack; CUS22 is a proposed unaccepted substitution.',
 ],
 'unqualifiedInterfaces':['Small pack/boss/body gaps and0.4mm reserved growth space','CUS terminal/anchor grounding, footprint, take-up, shell stops and full stroke','All native package locations/maximum leads/antenna keepout','Fastener insertion, torque, foam return force/creep and assembly accessibility','Actual battery/PCM/NTC adhesion, strain relief and thermal response','Acoustic datum/sealing, optical behaviour and raised keyed charging dock'],
 'inspectionImage':{'path':render['image'],'width':1400,'height':1400,'pngContainerChecksPass':True,'visuallyInspected':visually_inspected,'visualReviewRecord':'visual-review.json' if visually_inspected else None,'label':'UNQUALIFIED MECHANISM STUDY; 12 candidate parts + 2 unpowered gauges; assembly path unresolved'},
 'files':files,'fileCount':len(files),
 'manifestScope':'Paths relative to this mechanism directory. This manifest does not hash itself. Original40mm study, verified coupon, A03 release and native PCB are outside this new checkpoint.',
}
(ROOT/'mechanism-readiness.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'files':len(files),'stls':28,'bindingsPass':True,'completeBodyAssemblyReady':False,'manifestSha256':sha(ROOT/'mechanism-readiness.json')}))
