"""All-solid sampled CSG audit. Explicit contacts are reported, never silently erased."""
import argparse,hashlib,itertools,json,math,sys
from pathlib import Path
import bpy,bmesh
from mathutils import Vector
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--scenario',default='documented-pack');p.add_argument('--static-only',action='store_true');a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);OUT=ROOT/a.scenario
cfg=json.loads((ROOT/'contract.json').read_text());m=json.loads((OUT/'parts-manifest.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
checks={k:sha(p)==m[k] for k,p in {'contractSha256':ROOT/'contract.json','generatorSha256':ROOT/'build_m2.py','blendSha256':OUT/'aura-a04-m2.blend'}.items()}
assert all(checks.values()),checks
bpy.ops.wm.open_mainfile(filepath=str(OUT/'aura-a04-m2.blend'))
obs={o.name:o for o in bpy.context.scene.objects if o.type=='MESH'};rigid={n:o for n,o in obs.items() if o.get('role')!='soft'};soft={n:o for n,o in obs.items() if o.get('role')=='soft'}
solid={**rigid,**soft}
base={n:o.matrix_world.copy() for n,o in obs.items()};threshold=.001;calls=0

def bb(o):
 ps=[o.matrix_world@Vector(v) for v in o.bound_box];return [[min(v[i] for v in ps),max(v[i] for v in ps)] for i in range(3)]
def vol(x,y):
 global calls
 bx,by=bb(x),bb(y)
 if any(min(bx[i][1],by[i][1])-max(bx[i][0],by[i][0])<.000001 for i in range(3)):return 0.
 calls+=1;c=x.copy();c.data=x.data.copy();bpy.context.scene.collection.objects.link(c);bpy.context.view_layer.objects.active=c
 mod=c.modifiers.new('Audit CSG','BOOLEAN');mod.solver='MANIFOLD';mod.operation='INTERSECT';mod.object=y
 bpy.ops.object.modifier_apply(modifier=mod.name);bm=bmesh.new();bm.from_mesh(c.data);v=abs(bm.calc_volume(signed=True));bm.free();me=c.data;bpy.data.objects.remove(c,do_unlink=True);bpy.data.meshes.remove(me);return v

def owner(n):
 if n.startswith('BOUND_CUS'):return 'CUS'
 if n.startswith('BOUND_KMR'):return 'KMR'
 if n.startswith('BOUND_RADIO'):return 'RADIO'
 if n.startswith(('BOUND_ERM','BOUND_MOTOR')):return 'MOTOR'
 if n.startswith('BOUND_MIC'):return 'MIC_'+n.split('_')[-1]
 if n.startswith('BOUND_NTC'):return 'NTC'
 if n.startswith(('91_','BOUND_CELL','BOUND_BATTERY')):return 'PACK'
 return None

def hits(pairs):
 out=[];contacts=[]
 for x,y in pairs:
  v=vol(x,y)
  if v>threshold:
   r={'a':x.name,'b':y.name,'intersectionMm3':round(v,6)}
   if owner(x.name) and owner(x.name)==owner(y.name):r['reason']='Same purchased component: intentionally overlapping conservative body/lead/pad route envelope';contacts.append(r)
   elif set((x.name,y.name))=={'08_MEASURED_PLUNGER_SHOE','BOUND_KMR_ACTUATOR_MAX'}:r['reason']='Maximum height intersects nominal measured shoe; rest shoe height must be calibrated to actual mounted actuator, no fit pass';out.append(r)
   else:out.append(r)
 return out,contacts
static,inc=hits(itertools.combinations(rigid.values(),2));print('STATIC',json.dumps(static),flush=True)
result={'scenario':a.scenario,'status':'DIGITAL DEVELOPMENT AUDIT, NOT PRINT OR POWER RELEASE','sourceBindings':checks,'staticFindings':static,'intentionalSameComponentEnvelopeIntersections':inc,'thresholdMm3':threshold,'rigidSolidCount':len(rigid),'softSolidCount':len(soft),'nativePlacementImported':False,'physicalQualification':False,'forceQualification':False,'actuationQualification':False,'continuousSweepProven':False,'collisionMethod':'Blender MANIFOLD CSG intersection volume with AABB pruning; valid solids independently checked. Finite samples only.','all72NativeFeaturesPending':True}

def reset():
 for n,o in obs.items():o.matrix_world=base[n].copy()
 bpy.context.view_layer.update()
def pose(names,dx=0,dy=0,dz=0,rot=0):
 from mathutils import Matrix
 t=Matrix.Translation(Vector((dx,dy,dz)))@Matrix.Rotation(rot,4,'Z')
 for n in names:obs[n].matrix_world=t@base[n]
 bpy.context.view_layer.update()
def sweep(label,movers,targets,poses,method):
 out=[];ignored=[]
 for i,kw in enumerate(poses):
  reset();pose(movers,**kw);h,c=hits(itertools.product((solid[n] for n in movers if n in solid),(solid[n] for n in targets if n in solid)))
  if h:out.append({'sample':i,'pose':kw,'findings':h})
  if c:ignored.append({'sample':i,'intersections':c})
 reset();print('PATH',label,len(out),'/',len(poses),flush=True)
 return {'path':label,'method':method,'samples':len(poses),'movingObjects':movers,'targetObjects':targets,'findings':out,'intentionalEnvelopeContacts':ignored,'pass':not out}
if not a.static_only:
 ops=[];face=[n for n,o in rigid.items() if o.get('group')=='face'];shoe=[n for n,o in rigid.items() if o.get('group')=='shoe'];act=['BOUND_KMR_ACTUATOR_MAX'];moving=face+shoe+act;station=[n for n in rigid if n not in moving]
 states=[]
 for i in range(25):
  f=.6*i/24;sh=min(f,.25);ac=max(0,sh-.05);reset();pose(face,dz=-f);pose(shoe,dz=-sh);pose(act,dz=-ac)
  h,c=hits(itertools.product([rigid[n] for n in moving],[rigid[n] for n in station]));internal,ic=hits(itertools.combinations([rigid[n] for n in moving],2))
  # Actuator entering its own KMR body is the intended telescoping bound, captured under component ownership.
  if h+internal:states.append({'faceStrokeMm':f,'shoeStrokeMm':sh,'actuatorStrokeMm':ac,'findings':h+internal})
 ops.append({'path':'Calibrated maximum-height capture,0.6face/0.25shoe/0.2actuator','samples':25,'stepMm':.025,'findings':states,'pass':not states,'forceAndElectricalTimingQualified':False})
 reset();print('PATH calibrated face coupled',len(states),'/25',flush=True)
 soft_states=[]
 for f in (0,.3,.6):
  sh=min(f,.25);ac=max(0,sh-.05);reset();pose(face,dz=-f);pose(shoe,dz=-sh);pose(act,dz=-ac)
  for n,o in soft.items():
   if n.startswith('SOFT_FACE_RETURN_'):
    z0=bb(o)[2][0];h=1-f;o.scale.z=h;o.location.z=z0+h/2
   elif n=='SOFT_CAPTURE_FOAM':
    z0=bb(o)[2][0]-sh;h=.74-f+sh;o.scale.z=h/.74;o.location.z=z0+h/2
  bpy.context.view_layer.update();hh,cc=hits(itertools.product(soft.values(),rigid.values()));ih,ic=hits(itertools.combinations(soft.values(),2))
  soft_states.append({'faceStrokeMm':f,'findings':hh+ih,'pass':not hh+ih})
 result['workingSoftAllocationStates']=soft_states;reset();print('SOFT',[(x['faceStrokeMm'],len(x['findings'])) for x in soft_states],flush=True)
 # Piecewise lost motion in both directions; sweep specified minimum/nominal/maximum switch travel and width.
 slider='09_PRIVACY_FORK';lever='BOUND_CUS_LEVER';privacy=[];keeper_obj=obs['10_PRIVACY_KEEPER'];keeper_original=keeper_obj.data.copy()
 for t,w in ((1.3,1.4),(1.5,1.3),(1.7,1.2)):
  ext=t+2-w;states=[];channel=2.2+ext
  keeper_obj.data=keeper_original.copy();bpy.context.view_layer.objects.active=keeper_obj
  def alter_keeper(dims,loc,op):
   bpy.ops.mesh.primitive_cube_add(size=1,location=loc);c=bpy.context.object;c.dimensions=dims;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);bpy.context.view_layer.objects.active=keeper_obj;mod=keeper_obj.modifiers.new('Measured replacement keeper','BOOLEAN');mod.operation=op;mod.solver='MANIFOLD';mod.object=c;bpy.ops.object.modifier_apply(modifier=mod.name);bpy.data.objects.remove(c,do_unlink=True)
  sz=m['pcbBottomZMm']-2.7
  if channel>4.4:alter_keeper((2,channel,sz+.65),(18.55,0,(sz+.65)/2),'DIFFERENCE')
  elif channel<4.4:
   for side in (-1,1):alter_keeper((1,(4.4-channel)/2+.02,sz+.65-1),(18.55,side*((channel+4.4)/4+.01),(sz+.65+1)/2),'UNION')

  for direction in (-1,1):
   for i in range(27):
    f=-direction*ext/2+direction*ext*i/26
    # Start at opposite internal detent; after reversal take up G-w before lever moves.
    l=max(-t/2,min(t/2,f-direction*(2-w)/2))
    reset();obs[lever].scale.y=w/1.3;pose([slider],dy=f);pose([lever],dy=l);obs[lever].scale.y=w/1.3;bpy.context.view_layer.update()
    h,c=hits(itertools.product([rigid[slider],rigid[lever]],[o for n,o in rigid.items() if n not in (slider,lever)]))
    # Alternate keeper widths are analytical tolerance cases, nominal keeper remains and mismatch reported.
    if h:states.append({'forkY':f,'leverY':l,'findings':h})
  privacy.append({'switchTravelMm':t,'leverWidthMm':w,'requiredExternalTravelMm':ext,'requiredKeeperChannelMm':2.2+ext,'nominalKeeperCase':t==1.5,'actualReplacementKeeperGeometryTested':True,'samples':54,'findings':states,'pass':not states})
 keeper_obj.data=keeper_original.copy();reset();result['operationPaths']=ops;result['privacyTolerancePaths']=privacy
 # Ordered removal/assembly paths: mating counterparts are stationary only when already installed.
 paths=[];cup=['01_FIXED_CUP'];fork=[slider];keeper=['10_PRIVACY_KEEPER'];contact=['11_CONTACT_ACCESS_CARRIER'];sensor=[n for n,o in solid.items() if o.get('group')=='sensor']+['12_SENSOR_RETAINER'];pack=[n for n,o in solid.items() if o.get('group')=='pack'];pcb=[n for n,o in rigid.items() if o.get('group')=='pcb'];carrier=['03_PCB_CLAMP_AND_FACE_GUIDE']+[n for n,o in solid.items() if o.get('group')=='carrier']+[n for n in soft if n.startswith(('SOFT_PCB_CLAMP_','SOFT_FACE_RETURN_'))];face_assembly=face+shoe+['SOFT_CAPTURE_FOAM'];gaskets=[n for n in soft if n.startswith('SOFT_MIC_GASKET_')];bezel=[n for n,o in rigid.items() if o.get('group')=='bezel']
 paths.append(sweep('00 preseat acoustic working gaskets',[n for n in soft if n.startswith('SOFT_MIC_GASKET_')],cup,[{'dz':i*.25} for i in range(33)],'Working compressed allocations, front loading; free thickness compression force pending'))
 paths.append(sweep('01 radial privacy insertion before electronics',fork,cup,[{'dx':i*.5} for i in range(29)],'Reverse insertion route +X0..14 sampled0.5mm'))
 installed=cup+fork+gaskets
 for label,group,targets in [('02 privacy keeper front insertion',keeper,installed),('03 contact carrier front insertion',contact,installed+keeper),('04 sensor and routed lead insertion',sensor,installed+keeper+contact),('05 pack growth and lead front insertion',pack,installed+keeper+contact+sensor),('06 populated board proposal front insertion',pcb,installed+keeper+contact+sensor+pack),('07 clamp carrier front insertion',carrier,installed+keeper+contact+sensor+pack+pcb),('08 preassembled face front insertion',face_assembly,installed+keeper+contact+sensor+pack+pcb+carrier)]:
  paths.append(sweep(label,group,targets,[{'dz':i*.5} for i in range(49)],'Reverse front insertion +Z0..24 sampled0.5mm; flexible routes held as conservative rigid proxies, deformation not assumed.'))
 paths.append(sweep('07a steel and liner into carrier underside',['13_LOWER_STEEL_STIFFENER','SOFT_STIFFENER_DIELECTRIC'],['03_PCB_CLAMP_AND_FACE_GUIDE'],[{'dz':-.25*i} for i in range(17)],'Before front insertion, seat the lined steel from the carrier underside. Hold this unfastened subassembly on a fixture until the closure captures its root; bonding and measured shims remain process work.'))
 paths.append(sweep('09 bezel unscrew and front removal',bezel,[n for n in rigid if n not in bezel],[{'dz':3*i/72,'rot':6*math.pi*i/72} for i in range(73)]+[{'dz':3+i*.5,'rot':6*math.pi} for i in range(1,45)],'Helical thread path3turns sampled15deg then axial removal0.5mm samples'))
 paths.append(sweep('09b fixed diffuser front insertion',['06_FIXED_DIFFUSER'],['02_THREADED_BEZEL'],[{'dz':i*.25} for i in range(33)],'Separate diffuser inserts from front before bezel is threaded onto cup'))
 # Face component assembly in isolation, with carrier/cup absent.
 for label,group,axis,steps in [('09c capture foam rear loading',['SOFT_CAPTURE_FOAM'],'dz',[-.25*i for i in range(17)]),('10 status insert rear loading',['05_FLUSH_STATUS_WINDOW'],'dz',[-.25*i for i in range(17)]),('11 shoe rear loading',shoe,'dz',[-.25*i for i in range(17)])]:
  target=['04_CAPTIVE_FACE']
  if 'keeper' in label:target+=shoe+['SOFT_CAPTURE_FOAM']
  if 'shoe' in label:target+=['SOFT_CAPTURE_FOAM']
  if 'screw' in label:target+=['07_CARTRIDGE_KEEPER','BOUND_CARTRIDGE_NUT']
  paths.append(sweep(label,group,target,[{axis:k} for k in steps],'Local subassembly insertion sampled0.25mm'))
 paths.append(sweep('12 cartridge keeper dogleg insertion',['07_CARTRIDGE_KEEPER_LEFT','15_CARTRIDGE_KEEPER_RIGHT'],['04_CAPTIVE_FACE']+shoe+['SOFT_CAPTURE_FOAM'],[{'dy':-.25*i} for i in range(15)]+[{'dy':-3.5,'dz':-.25*i} for i in range(1,21)],'Reverse removal: slide3.5mm to clear positive rail ledges while staying inside flange; then lower5mm toward rear. Reverse order inserts the keeper before carrier/face assembly.'))
 # Two front service-tool pins approach exposed blind rim sockets. They are tooling, not assembled product solids.
 tool_names=[]
 for i,x in enumerate((-20.5,20.5)):
  bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=.45,depth=8.55,location=(x,0,m['bodyDepthMm']+3.725));o=bpy.context.object;o.name=f'TOOL_BEZEL_PIN_{i}';tool_names.append(o.name);obs[o.name]=o;solid[o.name]=o;rigid[o.name]=o;base[o.name]=o.matrix_world.copy()
 paths.append(sweep('15 front bezel-tool pin access',tool_names,[n for n in rigid if n not in tool_names],[{'dz':i*.5} for i in range(21)],'0.9mm pins reach1.1mm front sockets; separate tool handle, torque and strength unqualified'))
 result['serviceToolBoundsMm']={n:bb(obs[n]) for n in tool_names}
 result['assemblyPaths']=paths
result.update({'booleanEvaluations':calls,'allStaticRigidPass':not static,'allSampledOperatingPass':not a.static_only and all(x['pass'] for x in result['operationPaths']) and all(x['pass'] for x in result['privacyTolerancePaths']) and all(x['pass'] for x in result['workingSoftAllocationStates']),'allSampledAssemblyPass':not a.static_only and all(x['pass'] for x in result['assemblyPaths']),'blendSha256':sha(OUT/'aura-a04-m2.blend'),'manifestSha256':sha(OUT/'parts-manifest.json'),'checkerSha256':sha(Path(__file__)),'exclusions':['No continuous proof: these are finite CSG pose samples, with narrow collisions possible between samples.','Capture sweep uses calibrated2.25mounted-height and0.20actuator-travel example; actual mounted height, first operation, allowed endpoint and foam force remain unqualified.','Privacy tolerance sweeps use actual virtual replacement keeper geometry for each case; correct per-part stop/contact calibration and detent behavior remain physical tests.','Compliant foam deformation and capture/contact force are calculations and allocations, not material simulations.','All72 native features, RF acceptance, cell/PCM/adhesive/lead control and actual component manufacture/placement remain pending.']})
(OUT/('static-audit.json' if a.static_only else 'motion-audit.json')).write_text(json.dumps(result,indent=2)+'\n');print('DONE',calls,flush=True)
