"""Blender boolean-volume audit of exported assembly and sampled mechanisms.

This checks authored trial solids. It cannot validate unplaced native packages,
part tolerances, soft materials, switch contact timing or physical performance.
"""
import argparse,hashlib,itertools,json,math,sys
from pathlib import Path
import bpy,bmesh
from mathutils import Vector

ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--scenario',default='thin-cell')
args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
OUT=ROOT/args.scenario
cfg=json.loads((ROOT/'mechanism-contract.json').read_text())
manifest=json.loads((OUT/'parts-manifest.json').read_text())
source_checks={name:hashlib.sha256(path.read_bytes()).hexdigest()==manifest[name] for name,path in {
    'contractSha256':ROOT/'mechanism-contract.json',
    'generatorSha256':ROOT/'build_mechanism.py',
    'blendSha256':OUT/'aura-a04-mechanism.blend',
}.items()}
if not all(source_checks.values()):raise RuntimeError('Stale mechanism source/assembly binding: '+str(source_checks))
bpy.ops.wm.open_mainfile(filepath=str(OUT/'aura-a04-mechanism.blend'))
MM=1.0


def bounds(o):
    pts=[o.matrix_world@Vector(v) for v in o.bound_box]
    return [[min(v[i] for v in pts),max(v[i] for v in pts)] for i in range(3)]


def overlap(a,b):
    aa,bb=bounds(a),bounds(b)
    if any(min(aa[i][1],bb[i][1])-max(aa[i][0],bb[i][0])<1e-8 for i in range(3)):return 0.0
    c=a.copy();c.data=a.data.copy();bpy.context.scene.collection.objects.link(c)
    bpy.context.view_layer.objects.active=c
    mod=c.modifiers.new('Audit intersection','BOOLEAN');mod.solver='EXACT';mod.operation='INTERSECT';mod.object=b
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bm=bmesh.new();bm.from_mesh(c.data);v=abs(bm.calc_volume(signed=True))/(MM**3);bm.free()
    mesh=c.data;bpy.data.objects.remove(c,do_unlink=True);bpy.data.meshes.remove(mesh)
    return v


parts={item['object']:bpy.data.objects[item['object']] for item in manifest['parts']}
threshold=.001
static=[]
for (an,a),(bn,b) in itertools.combinations(parts.items(),2):
    v=overlap(a,b)
    if v>threshold:static.append({'a':an,'b':bn,'intersectionMm3':v})
face_parts=[parts[n] for n in ('02_CAPTIVE_FACE_PADDLE','05_MOVING_STATUS_LIGHTPIPE','06_PLUNGER_SIZING_INSERT')]
proxy_names=['PROPOSED_CUS22_MAX_BODY','PROPOSED_CUS22_MAX_LEVER','PROPOSED_SEMITEC_MAX_BODY','PROPOSED_RADIO_MAX_WITH_SEATING','PROPOSED_ERM_MAX_MOUNTED','PROPOSED_KMR2_ENVELOPE']
rigid_proxies=[bpy.data.objects[n] for n in proxy_names]
face_targets=[o for o in parts.values() if o not in face_parts]+rigid_proxies
face_results=[]
for stroke in (0,.1,.2,.3,.4):
    for o in face_parts:o.location.z-=stroke*MM
    bpy.context.view_layer.update()
    hits=[]
    for a,b in itertools.product(face_parts,face_targets):
        v=overlap(a,b)
        if v>threshold:hits.append({'a':a.name,'b':b.name,'intersectionMm3':v})
    face_results.append({'inwardStrokeMm':stroke,'rigidIntersectionFindings':hits})
    for o in face_parts:o.location.z+=stroke*MM
    bpy.context.view_layer.update()
slider=parts['08_CUS22_PRIVACY_FORK'];lever=bpy.data.objects['PROPOSED_CUS22_MAX_LEVER']
slider_targets=[o for o in parts.values() if o!=slider]+[o for o in rigid_proxies if o!=lever]
slider_results=[]
for y in (-.75,-.375,0,.375,.75):
    slider.location.y+=y*MM;lever.location.y+=y*MM;bpy.context.view_layer.update()
    hits=[]
    for b in slider_targets+[lever]:
        v=overlap(slider,b)
        if v>threshold:hits.append({'a':slider.name,'b':b.name,'intersectionMm3':v})
    lever_hits=[]
    for b in slider_targets:
        v=overlap(lever,b)
        if v>threshold:lever_hits.append({'a':lever.name,'b':b.name,'intersectionMm3':v})
    slider_results.append({'translationYMm':y,'rigidIntersectionFindings':hits,'leverSurroundingFindings':lever_hits})
    slider.location.y-=y*MM;lever.location.y-=y*MM;bpy.context.view_layer.update()
proxy_hits=[]
for name in proxy_names:
    a=bpy.data.objects[name]
    for b in parts.values():
        v=overlap(a,b)
        if v>threshold:proxy_hits.append({'a':name,'b':b.name,'intersectionMm3':v})
proxy_pairs=[]
for a,b in itertools.combinations(rigid_proxies,2):
    v=overlap(a,b)
    if v>threshold:proxy_pairs.append({'a':a.name,'b':b.name,'intersectionMm3':v})
all_hits=static+proxy_hits+proxy_pairs+[h for s in face_results+slider_results for h in s['rigidIntersectionFindings']]+[h for s in slider_results for h in s['leverSurroundingFindings']]
capture=[h for h in all_hits if set([h['a'],h['b']])=={'06_PLUNGER_SIZING_INSERT','PROPOSED_KMR2_ENVELOPE'}]
result={'status':'MECHANISM TRIAL; NOT NATIVE OR PHYSICAL FIT VALIDATION','scenario':args.scenario,'thresholdMm3':threshold,'staticPrintedPartFindings':static,'faceSweep':face_results,'privacySweep':slider_results,'maximumAllocationFindings':proxy_hits,'maximumProxyPairFindings':proxy_pairs,'allRigidTrialChecksPass':not all_hits,'nonActuatingRigidClearancesPass':not [h for h in all_hits if h not in capture],'captureActuationContactFindings':capture,'captureActuationValidated':False,'captureInterfaceNote':'Rigid sizing insert contact with nominal KMR2 envelope is reported, not waived. At full0.4mm face stroke nominal demanded switch depression is0.35mm; published0.1-0.3mm electrical travel does not establish safe overtravel. Measure/trim insert or qualify compliance before powered actuation.','physicalQualification':False,'nativePlacementImported':False,'switchTimingProven':False,'continuousSweepProven':False,'method':'Exact CSG intersection volume on saved assembly meshes; authored contact surfaces below0.001mm3 threshold. Five sampled face positions versus every other printed solid and six rigid component bounds. Five nominal slider/lever positions versus stationary solids and bounds. All rigid proxy pairs checked at rest. No tolerance, insertion-path or force simulation.','blendSha256':hashlib.sha256((OUT/'aura-a04-mechanism.blend').read_bytes()).hexdigest(),'checkerSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
result['sourceBindings']=source_checks
result['manifestSha256']=hashlib.sha256((OUT/'parts-manifest.json').read_bytes()).hexdigest()
result['exclusions']=['Full CUS pads, leads and solder anchors are not CSG solids; separate nominal pad-corner calculation only.', 'Slider and lever share five nominal translations; fork take-up and unshimmed2.4mm shell stroke are not validated.', 'The0.4mm cell-growth reservation is not included in the rigid pack gauge.', 'No complete insertion sequence or positive axial PCB support is proven.', 'Motor tab, wire paths, adhesive, tolerances, foam force and actual native component placement are not verified.']
(OUT/'motion-audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print('A04_MECHANISM_AUDIT',json.dumps(result),flush=True)
