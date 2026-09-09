"""A04 M2 front-loaded mechanism. Blender 5.2; mm; never writes native PCB."""
import argparse,hashlib,json,math,sys
from pathlib import Path
import bpy,bmesh
from mathutils import Vector
ROOT=Path(__file__).resolve().parent
cfg=json.loads((ROOT/'contract.json').read_text())
p=argparse.ArgumentParser();p.add_argument('--scenario',choices=[s['id'] for s in cfg['scenarios']],default='thin-cell')
a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
case=next(s for s in cfg['scenarios'] if s['id']==a.scenario)
OUT=ROOT/a.scenario;OUT.mkdir(exist_ok=True)
D=case['bodyDepthMm'];CD=case['cellDepthMm'];P=1+.15+CD+.4+.15;PT=P+1.6
FB=D-1.05;STOP=D-3;RB=STOP-1;SZ=P-2.7
parts=[];bounds=[];soft=[]
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.data.orphans_purge(do_local_ids=True,do_linked_ids=True,do_recursive=True)
sc=bpy.context.scene;sc.unit_settings.system='METRIC';sc.unit_settings.length_unit='MILLIMETERS';sc.unit_settings.scale_length=.001
def mat(n,c):
 m=bpy.data.materials.new(n);m.use_nodes=True;m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(*c,1);return m
mats={'part':mat('Trial polymer',(.5,.47,.4)),'gauge':mat('Unpowered gauge',(.05,.2,.15)),'bound':mat('PROPOSED maximum',(.2,.23,.25)),'soft':mat('Measured soft interface',(.25,.1,.05))}
def box(n,d,c):
 bpy.ops.mesh.primitive_cube_add(size=1,location=c);o=bpy.context.object;o.name=n;o.dimensions=d;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);return o
def cyl(n,r,z0,z1,xy=(0,0),vertices=128):
 bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=r,depth=z1-z0,location=(*xy,(z0+z1)/2));o=bpy.context.object;o.name=n;return o
def boolean(o,c,op='UNION'):
 bpy.context.view_layer.objects.active=o;m=o.modifiers.new('Exact construction','BOOLEAN');m.solver='MANIFOLD';m.operation=op;m.object=c;bpy.ops.object.modifier_apply(modifier=m.name);bpy.data.objects.remove(c,do_unlink=True)
def ring(n,ro,ri,z0,z1,xy=(0,0)):
 o=cyl(n,ro,z0,z1,xy);boolean(o,cyl('Through bore',ri,z0-1,z1+1,xy),'DIFFERENCE');return o
def tube(n,r,a,b,verts=64):
 a,b=Vector(a),Vector(b);bpy.ops.mesh.primitive_cylinder_add(vertices=verts,radius=r,depth=(b-a).length,location=(a+b)/2);o=bpy.context.object;o.name=n;o.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler();bpy.ops.object.transform_apply(location=False,rotation=True,scale=True);return o
def polar(r,ang):return (r*math.cos(math.radians(ang)),r*math.sin(math.radians(ang)))
def radial(n,r0,r1,w,z0,z1,ang):
 o=box(n,(r1-r0,w,z1-z0),(*polar((r0+r1)/2,ang),(z0+z1)/2));o.rotation_euler.z=math.radians(ang);bpy.ops.object.transform_apply(location=False,rotation=True,scale=True);return o
def tag(o,n,desc,role='part',group='stationary'):
 o.name=n;o.data.materials.clear();o.data.materials.append(mats[role]);o['role']=role;o['description']=desc;o['group']=group;o['native_placement']=False
 (parts if role in ('part','gauge') else soft if role=='soft' else bounds).append(o);return o
def helix(n,r,t0,t1,zbase,section):
 count=math.ceil((t1-t0)*192);q=16;vs=[];fs=[]
 for i in range(count+1):
  t=t0+(t1-t0)*i/count;ang=2*math.pi*t
  for j in range(q):
   u=2*math.pi*j/q;rr=r+section*math.cos(u);vs.append((rr*math.cos(ang),rr*math.sin(ang),zbase+t+section*math.sin(u)))
 for i in range(count):
  for j in range(q):fs.append((i*q+j,i*q+(j+1)%q,(i+1)*q+(j+1)%q,(i+1)*q+j))
 fs.append(tuple(reversed(range(q))));fs.append(tuple(count*q+j for j in range(q)))
 me=bpy.data.meshes.new(n);me.from_pydata(vs,[],fs);me.update();o=bpy.data.objects.new(n,me);sc.collection.objects.link(o)
 bm=bmesh.new();bm.from_mesh(me);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(me);bm.free();return o

# Fixed cup. Its thread shoulder carries closure torque without using the face.
cup=cyl('Cup',21.5,0,D-.8)
boolean(cup,cyl('Open full front cavity',20,1,D+3),'DIFFERENCE')
boolean(cup,ring('Explicit female thread land',20.05,19.95,D-3.15,D-.8))
boolean(cup,helix('Open female helix run-in and run-out',19.9,-.5,3.2,D-2.75,.4),'DIFFERENCE')
boolean(cup,box('Bail', (5.2,5.0,3.8),(0,22.3,D/2)))
boolean(cup,tube('Bail hole',1.3,(-4,22.3,D/2),(4,22.3,D/2)),'DIFFERENCE')
boolean(cup,cyl('Bail respects cavity',20,1,D-3.2),'DIFFERENCE')
for x,y in cfg['pcbDatums']['centresXYMm']:
 boolean(cup,cyl('Positive lower PCB datum',1.1,.9,P,(x,y)))
for ang in cfg['retainer']['structuralSeatAnglesDeg']:
 boolean(cup,cyl('Independent carrier shoulder',1.2,.9,RB,polar(19,ang)))
# Key exists only near PCB, so it cannot press against the shifted pouch.
boolean(cup,box('Board antirotation key',(3.5,.8,1.8),(-18.35,0,P)))
# Radial slider installation precedes all electronics/pack insertion.
boolean(cup,box('Privacy running slot',(5,6.4,1.3),(21,0,SZ)),'DIFFERENCE')
for y in (-3.55,3.55):boolean(cup,box('Keeper locating rail',(2.6,.6,RB-.9),(19.0,y,(RB+.9)/2)))
# Dock carrier installs through the open front and rests on side-wing shoulders.
boolean(cup,box('Rear contact access well',(9.8,3.5,3),(0,-15.9,.4)),'DIFFERENCE')
boolean(cup,box('Contact flange counterseat',(11,3.5,1.2),(0,-15.9,1.6)),'DIFFERENCE')
# Integrated, actually hollow L ducts avoid an impossible branch insertion.
for x in (-7.2,7.2):
 boolean(cup,cyl('Mic duct riser',1.5,.9,P-.4,(x,-13.5)))
 boolean(cup,tube('Mic duct wall',1.5,(x,-13.5,2.6),(x,-21,2.6)))
 boolean(cup,cyl('Mic vertical bore',.65,2.3,P+1,(x,-13.5)),'DIFFERENCE')
 boolean(cup,tube('Mic exit bore',.65,(x,-13.5,2.6),(x,-23,2.6)),'DIFFERENCE')
boolean(cup,cyl('Duct perimeter clip',21.5,-1,D+1),'INTERSECT')
# Re-add bail after circular clipping; no part of its root intrudes into cavity.
boolean(cup,box('Bail external root',(5.2,4.8,3.8),(0,22.4,D/2)))
boolean(cup,tube('Actual chain hole',1.3,(-4,22.3,D/2),(4,22.3,D/2)),'DIFFERENCE')
boolean(cup,cyl('Bail cavity cleanup',20,1,D-3.2),'DIFFERENCE')
# NTC supports are below the PCB, alongside rather than above the pack.
boolean(cup,box('Sensor floor',(4.8,5.3,.7),(12.3,-7,1.35)))
boolean(cup,box('Sensor outer wall',(.7,5.3,2.8),(14.35,-7,2.8)))
for y in (-9.3,-4.7):boolean(cup,box('Sensor guide wall',(4.8,.7,2.8),(12.3,y,2.8)))
boolean(cup,box('Open sensor lead relief',(2.2,1.4,4),(14.1,-5.2,3.6)),'DIFFERENCE')
tag(cup,'01_FIXED_CUP','Integral rear, three PCB seats, independent carrier shoulders, open front thread, integrated acoustic ducts and sensor pocket')

bezel=ring('Male sleeve',19.85,18.65,D-3,D-.8)
boolean(bezel,helix('Rounded male thread',19.9,0,1.8,D-2.75,.25))
boolean(bezel,ring('Face outward stop',19.85,17.85,D-1.6,D))
boolean(bezel,ring('Stationary torque collar',21.5,17.85,D-.8,D))
boolean(bezel,ring('Fixed diffuser rebate',18.6,17.84,D-.75,D+.1),'DIFFERENCE')
# Two small underside tool sockets; no exposed front screws.
for x in (-20.5,20.5):boolean(bezel,cyl('Service pin socket',.55,D-.6,D+.1,(x,0)),'DIFFERENCE')
tag(bezel,'02_THREADED_BEZEL','Removable rounded-thread bezel; stationary collar stop bypasses moving face/cell','part','bezel')

carrier=ring('Carrier',19.4,17.9,RB,STOP)
for x,y in cfg['pcbDatums']['centresXYMm']:
 ang=math.degrees(math.atan2(y,x));rr=math.hypot(x,y)
 boolean(carrier,radial('Clamp spoke',rr,19.2,2.4,RB,STOP,ang))
 boolean(carrier,cyl('Upper PCB datum foot',.95,PT+.2,STOP,(x,y)))
for ang in cfg['retainer']['guidePinAnglesDeg']:
 xy=polar(15.5,ang)
 boolean(carrier,radial('Guide spoke',15.3,19.2,3,RB,STOP,ang))
 boolean(carrier,cyl('Front-load guide pin',.7,STOP,FB-.8,xy))
for ang in (55,165,285):
 xy=polar(17.3,ang)
 boolean(carrier,cyl('Return pad pocket floor',1.2,RB,STOP,xy))
 boolean(carrier,cyl('Return pad pocket',.85,STOP-.4,STOP+1,xy),'DIFFERENCE')
# Perimeter key fits a notch in cup shoulder and is below the rotating bezel.
boolean(carrier,box('Carrier orientation key',(1.2,1.0,.8),(-19.5,0,RB+.4)))
boolean(cup,box('Carrier key channel',(1.6,1.4,D+2-RB),(-19.5,0,(D+2+RB)/2)),'DIFFERENCE')
# Independent shoe stop: overload flows into carrier/cup, bypassing switch.
SHOE_Z=FB-.74-.3
bridge=box('Capture stop bridge',(math.hypot(6.6,6.4),1.2,.6),(-10.3,-10.4,RB+.3));bridge.rotation_euler.z=math.atan2(6.4,6.6);bpy.ops.object.transform_apply(location=False,rotation=True,scale=True);boolean(carrier,bridge)
boolean(carrier,box('Capture stop crossbar',(6.4,1.2,.6),(-7,-7,RB+.3)))
boolean(carrier,box('Stationary keeper withdrawal stop',(.6,.6,SHOE_Z-.15-RB),(-10.1,-8.3,(SHOE_Z-.15+RB)/2)))
boolean(carrier,box('Keeper stop foot',(.6,2.0,.6),(-10.1,-7.7,RB+.3)))
for xx,startx in ((-9.5,-10.0),(-4.5,-4.0)):
 boolean(carrier,tube('Shoe support side arm',.25,(startx,-7,RB+.3),(xx,-2,RB+.3)))
 boolean(carrier,cyl('Independent calibrated shoe stop',.4,RB,SHOE_Z-cfg['capture']['shoeStopTravelNominalMm'],(xx,-2)))
tag(carrier,'03_PCB_CLAMP_AND_FACE_GUIDE','Three matching clamp feet and rigid frame on independent shoulders; guide pins and 0.6mm face stop')

face=cyl('Pale face',17.6,FB,D-.05)
boolean(face,ring('Edge skirt',17.6,16.9,D-2.4,FB+.05))
boolean(face,ring('Captive continuous flange',18.35,16.9,D-2.4,D-1.6))
for ang in (55,165,285):boolean(face,cyl('Full-area return pad bearing',.9,D-2.4,D-1.6,polar(17.3,ang)))
for ang in cfg['retainer']['guidePinAnglesDeg']:
 xy=polar(15.5,ang)
 boolean(face,cyl('Blind guide sleeve',1.8,D-2.4,FB+.05,xy))
 boolean(face,cyl('Blind guide hole',.95,D-2.6,FB-.05,xy),'DIFFERENCE')
boolean(face,box('Status aperture',(3.2,.7,2),(0,0,D-.5)),'DIFFERENCE')
boolean(face,box('Recessed flush window flange',(4.6,1.7,.4),(0,0,FB+.2)),'DIFFERENCE')
# Captured compliant cartridge; keeper slides laterally before face installation.
sx,sy=cfg['capture']['centreXYMm'];KZ=FB-.74-.3
boolean(face,box('Cartridge sidewalls',(8.8,8.4,1.95),(sx,sy,FB-.575)))
boolean(face,box('Open cartridge pocket',(6.8,6.8,2.3),(sx,sy,FB-1.15)),'DIFFERENCE')
boolean(face,box('Keeper rail slot',(7.7,11,.9),(sx,sy-2,KZ-.15)),'DIFFERENCE')
for side in (-1,1):
 boolean(face,box('Positive cartridge rail ledge',(.8,5,.6),(sx+side*3.6,sy+1,KZ-.9)))
 boolean(face,box('Cartridge rail outer web',(.6,5,1.9),(sx+side*4.1,sy+1,KZ-.25)))
boolean(face,box('Stationary keeper stop entry',(1.4,1.4,3),(sx-3.1,sy-3.8,FB-1.6)),'DIFFERENCE')
boolean(face,box('Local fullpress radio clearance',(11.3,16.3,PT+2.4+.6+.15-(D-4)),(0,8.6,(PT+2.4+.6+.15+D-4)/2)),'DIFFERENCE')
boolean(face,box('Final unobstructed flange rebate',(4.6,1.7,.6),(0,0,FB+.2)),'DIFFERENCE')
tag(face,'04_CAPTIVE_FACE','Front-inserted full face; three blind guide sleeves, flush optical insert, lateral compliant cartridge','part','face')
window=box('Window',(3,.5,D-.05-(FB+.1)),(0,0,(D-.05+FB+.1)/2))
boolean(window,box('Recessed flange',(4.4,1.5,.3),(0,0,FB+.2)))
tag(window,'05_FLUSH_STATUS_WINDOW','No material below face-back plane; inserts from rear before front face installation','part','face')
diff=ring('Diffuser',18.5,17.85,D-.7,D-.05)
tag(diff,'06_FIXED_DIFFUSER','Separate clear ring seated in fixed bezel','part','bezel')
# Captured keeper and removable shoe. Exact shoe height is a measured setting.
keeper=box('Sliding keeper',(7.4,6.4,.6),(sx,sy,KZ-.3))
boolean(keeper,box('Stem passage',(5.0,7.6,2),(sx,sy+2,KZ-.4)),'DIFFERENCE')
for xx in (-9.5,-4.5):boolean(keeper,cyl('Stationary shoe-stop passage',.65,KZ-1,KZ+1,(xx,-2)),'DIFFERENCE')
tag(keeper,'07_CARTRIDGE_KEEPER','Lateral keeper staged in face before front insertion; carrier post blocks withdrawal once face installed','part','face')
shoe=box('Shoe plate',(6.2,6.2,.3),(sx,sy,KZ+.15))
TIP=PT+cfg['capture']['calibratedMountedHeightMm']+cfg['capture']['shoeRestGapNominalMm']
boolean(shoe,box('Replaceable measured stem',(1.8,1.8,KZ-TIP+.05),(sx,sy,(KZ+TIP+.05)/2)))
tag(shoe,'08_MEASURED_PLUNGER_SHOE','Maximum mounted switch height2.25 plus0.05rest gap; re-size from physical measurement, not a qualified fixed actuator','part','shoe')

fork=box('Privacy grip',(1.2,2.8,1.1),(22.3,0,SZ))
boolean(fork,box('Guided stem',(5.2,2.2,.9),(19.7,0,SZ)))
boolean(fork,box('Internal bridge',(.85,6,.9),(17.3,0,SZ)))
for y in (-1.5,1.5):boolean(fork,box('CUS fork finger',(3.4,1,.9),(15.2,y,SZ)))
tag(fork,'09_PRIVACY_FORK','Corrected actuator centre14.85; radial install before battery; nominal OFF=-Y, enabled=+Y','part','privacy')
keep=box('Front-inserted keeper',(1.0,6.4,RB-1.0),(18.55,0,(RB+1.0)/2))
boolean(keep,box('Open-bottom stem channel',(2,4.4,SZ+.65),(18.55,0,(SZ+.65)/2)),'DIFFERENCE')
tag(keep,'10_PRIVACY_KEEPER','Open-bottom U keeper lowers over installed stem; integral measured4.4channel yields2.2travel and independent stops, carrier captures it')
contact=box('Contact access carrier',(9.4,3.1,P-.3),(0,-15.9,(P-.3)/2))
boolean(contact,box('Positive side-wing seat',(10.6,3.1,.5),(0,-15.9,1.25)))
for x in (-3,0,3):boolean(contact,cyl('Contact access',1,-1,P+1,(x,-15.9)),'DIFFERENCE')
tag(contact,'11_CONTACT_ACCESS_CARRIER','Front-installed keyed access with positive side-wing seat; dock nose still separate')
ntccap=box('Sensor cap',(4.4,4.7,P-.1-4.2),(12.1,-7,(P-.1+4.2)/2))
tag(ntccap,'12_SENSOR_RETAINER','Front-inserted cap rests on sensor-pocket walls at4.2;0.1upward travel limited by PCB; thermal contact/force remains unqualified')

board=cyl('Unpowered board gauge',17.6,P,PT)
boolean(board,box('Only proposed board key notch',(1.5,1.2,3),(-17.45,0,P+.8)),'DIFFERENCE')
for y in (-1.5,1.5):boolean(board,cyl('CUS locator NPTH',.45,P-1,PT+1,(13.5,y)),'DIFFERENCE')
for x in (-7.2,7.2):boolean(board,cyl('Proposed acoustic port',.5,P-1,PT+1,(x,-13.5)),'DIFFERENCE')
tag(board,'90_UNPOWERED_BOARD_GAUGE','No old closure notches; only left key and proposed sound holes, not native geometry','gauge','pcb')
pack=box('Max cell gauge',(26,21,CD),(-3.2,0,1.15+CD/2))
tag(pack,'91_UNPOWERED_PACK_GAUGE','Maximum controlled unpowered pack gauge','gauge','pack')
growth=box('Full maximum pouch growth allocation',(26,21,.4),(-3.2,0,1.15+CD+.2))
tag(growth,'BOUND_CELL_GROWTH','Explicit0.4mm occupancy above maximum pack; cannot be used for hardware','bound','pack')

# Purchased body, full terminal/solder fields and connector occupancies. Not native placement.
tag(box('Radio',(10.7,15.7,2.4),(0,8.6,PT+1.2)),'BOUND_RADIO_MAX','Maximum module plus0.15mm seating','bound','pcb')
tag(box('Radio pad/lead field',(10.7,15.7,.15),(0,8.6,PT+.075)),'BOUND_RADIO_TERMINALS','Conservative module mounting field overlaps its body envelope intentionally','bound','pcb')
tag(cyl('ERM',5.05,PT,PT+2.45,(6,-5)),'BOUND_ERM_MAX','Maximum mounted motor','bound','pcb')
tag(box('ERM tab',(1.8,1.8,.7),(12,-5,PT+.5)),'BOUND_ERM_TAB','Conservative tab reaches6.9mm from centre including margin','bound','pcb')
tag(box('CUS body',(4.3,6.9,1.6),(13.5,0,P-.95)),'BOUND_CUS_BODY','Maximum underside CUS body plus separate seating','bound','pcb')
tag(box('CUS lever',(1.8,1.3,1.7),(14.85,0,P-2.6)),'BOUND_CUS_LEVER','Full transverse tolerance13.95..15.75 including0.15locator; calibrated nominal1.3width and maximum rearheight','bound','privacy')
for i,y in enumerate((-1.5,1.5)):tag(cyl('CUS locator occupancy',.4,P-.2,P+.6,(13.5,y)),f'BOUND_CUS_LOCATOR_{i}','Nominal0.9NPTH with conservative0.8pin x0.6protrusion proposal; supplier locator height pending','bound','pcb')
# A maximum rear-terminal field is kept above body actuator volume; actual metal is a subset.
tag(box('CUS full leads',(6.1,8.3,.35),(13.5,0,P-.175)),'BOUND_CUS_FULL_LEADS','Conservative max full lead/solder field; source bound inference clearly separate from body','bound','pcb')
padmap=[]
for pin,x,y in [(1,-2.25,-2.55),(2,.75,-2.55),(3,2.25,-2.55),(4,-2.25,2.55),(5,.75,2.55),(6,2.25,2.55)]:
 cx,cy=13.5+y,-x
 tag(box('CUS pad',(1.5,.7,.05),(cx,cy,P-.025)),f'BOUND_CUS_PAD_{pin}','Exact nominal signal land with corrected backside reflection','bound','pcb')
 padmap.append({'pin':pin,'sourceXY':[x,y],'cadXY':[cx,cy],'cadSizeMm':[1.5,.7]})
for i,(x,y) in enumerate((x,y) for x in (-3.65,3.65) for y in (-1.8,1.8)):
 tag(box('CUS anchor',(.8,1,.05),(13.5+y,-x,P-.025)),f'BOUND_CUS_ANCHOR_{i+1}','Unnumbered anchor copper; grounding unresolved','bound','pcb')
tag(box('KMR stationary body',(4.4,3.0,1.7),(sx,sy,PT+.85)),'BOUND_KMR_BODY','Maximum stationary body with0.15 seating; actuator modeled separately','bound','pcb')
tag(box('KMR actuator',(1,1,.55),(sx,sy,PT+1.975)),'BOUND_KMR_ACTUATOR_MAX','Maximum2.1mm height plus0.15 seating; not the calibrated nominal press state','bound','pcb')
tag(box('KMR terminal field',(5,3.2,.25),(sx,sy,PT+.125)),'BOUND_KMR_TERMINALS','Complete conservative terminal field; exact source footprint still pending','bound','pcb')
tag(box('Semitec',(4,3.7,2.4),(11.9,-7,3.0)),'BOUND_NTC_MAX','Maximum selected sensor body; actual thermal contact still unqualified','bound','sensor')
for x in (-3,0,3):tag(cyl('Dock pad',.85,P-.035,P,(x,-15.9)),f'BOUND_DOCK_PAD_{x}','Proposed underside copper target','bound','pcb')
for x in (-7.2,7.2):
 tag(ring('Compressed acoustic seal',1.5,.6,P-.4,P,(x,-13.5)),f'SOFT_MIC_GASKET_{x}','Working compressed seal; free thickness0.5 and force/sealing require test','soft','stationary')
for i,xy in enumerate(cfg['pcbDatums']['centresXYMm']):tag(cyl('Compressed clamp pad',.9,PT,PT+.2,xy),f'SOFT_PCB_CLAMP_{i}','Measured foam/shim interface at positive datum; nominal0.25free,0.20working','soft','stationary')
tag(box('Cartridge foam',(6.2,6.2,.74),(sx,sy,KZ+.3+.37)),'SOFT_CAPTURE_FOAM','Free0.79 sheet modeled compressed0.74 at rest;0.39 at full press with calibrated0.25shoe stop; force/creep unqualified','soft','face')
for i,ang in enumerate((55,165,285)):
 xy=polar(17.3,ang)
 tag(cyl('Working face return foam',.7,STOP-.4,D-2.4,xy),f'SOFT_FACE_RETURN_{i}','Free1.1mm foam disk,1.0working rest and0.4working fullpress; compression/force/life must be qualified','soft','stationary')
tag(box('Battery backing',(26,21,.15),(-3.2,0,1.075)),'SOFT_BATTERY_BACKING','Unselected0.15backing/fixation layer; supplier adhesive and pouch compatibility pending','soft','pack')
tag(box('Battery dielectric',(26,21,.1),(-3.2,0,P-.1)),'SOFT_BATTERY_DIELECTRIC','0.10dielectric plus0.05free gap after solid growth allocation; material pending','soft','pack')
tag(box('Sensor thermal interface',(.1,3.6,2.4),(9.85,-7,3.0)),'SOFT_NTC_INTERFACE','0.1adhesive/interface at pack edge; conductivity and thermal tracking not qualified','soft','sensor')
# Conservative explicit insulated lead routes; leads terminate at proposed points only.
routes={
 'NTC':[(13.1,-5.2,3),(16.3,-5.2,3),(16.3,-10.2,3.5),(12.8,-11.2,P-.4)],
 'BATTERY':[(-9,-10.5,2.4),(-9,-12,2.4),(-12,-12,3.0),(-12,-11.5,P-.2)],
 'MOTOR':[(12.4,-5,PT+.5),(13.2,-6,PT+.5),(12.5,-8,PT+.5)]}
for name,pts in routes.items():
 for i,(u,v) in enumerate(zip(pts,pts[1:])):tag(tube('Lead route',.35,u,v),f'BOUND_{name}_LEAD_{i}','Conservative insulated lead route; solder termination/strain relief remain proposals','bound','pcb' if name=='MOTOR' else 'sensor' if name=='NTC' else 'pack')

# Unselected fastening and optical/acoustic package bounds, all explicitly provisional.
for x in (-7.2,7.2):
 tag(box('Mic package field',(4.1,3.1,1.2),(x,-13.5,PT+.6)),f'BOUND_MIC_BODY_{x}','Conservative proposed bottom-port microphone body and seating; exact source datum pending','bound','pcb')
 tag(box('Mic terminals',(4.3,3.3,.15),(x,-13.5,PT+.075)),f'BOUND_MIC_TERMINALS_{x}','Complete conservative land field; must be reconciled to actual native footprint','bound','pcb')
tag(box('Status LED',(1.9,1.2,1.15),(0,0,PT+.575)),'BOUND_STATUS_LED','Unselected low LED allocation with complete rectangular lead field; optical coupling not solved','bound','pcb')
# Export fixed data with stable assembly-to-print transforms.
items=[]
for o in parts:
 bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00005);bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.00005);bmesh.ops.triangulate(bm,faces=list(bm.faces));bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(o.data);bm.free()
 pts=[o.matrix_world@Vector(v) for v in o.bound_box];lo=[min(v[i] for v in pts) for i in range(3)];hi=[max(v[i] for v in pts) for i in range(3)]
 old=o.location.copy();o.location.z-=lo[2];bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
 path=OUT/(o.name.lower()+'.stl');bpy.ops.wm.stl_export(filepath=str(path),export_selected_objects=True,global_scale=1,ascii_format=False)
 o.location=old;raw=path.read_bytes();items.append({'object':o.name,'file':path.name,'role':o['role'],'group':o['group'],'description':o['description'],'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'assemblyBoundsMm':[lo,hi],'printTranslationMm':[0,0,-lo[2]]})
bpy.context.view_layer.update();sc['status']=cfg['status'];sc['scenario']=a.scenario;sc['nativePlacementImported']=False;sc.render.filepath='//m2-inspection.png'
bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'aura-a04-m2.blend'),compress=True)
all_objects=[]
for o in parts+bounds+soft:
 pts=[o.matrix_world@Vector(v) for v in o.bound_box];lo=[min(v[i] for v in pts) for i in range(3)];hi=[max(v[i] for v in pts) for i in range(3)]
 geom={'vertices':[[round(float(c),7) for c in o.matrix_world@v.co] for v in o.data.vertices],'faces':[list(p.vertices) for p in o.data.polygons]}
 all_objects.append({'object':o.name,'role':o['role'],'group':o['group'],'description':o['description'],'assemblyBoundsMm':[lo,hi],'worldGeometrySha256':hashlib.sha256(json.dumps(geom,separators=(',',':')).encode()).hexdigest(),'nativePlacement':False})
report={'allAssemblyObjects':all_objects,'revision':cfg['revision'],'status':cfg['status'],'scenario':a.scenario,'bodyDiameterMm':43,'bodyDepthMm':D,'pcbActualThicknessMm':1.6,'pcbBottomZMm':P,'pcbTopZMm':PT,'faceBackZMm':FB,'faceStopZMm':STOP,'carrierBottomZMm':RB,'parts':items,'partCount':len(items),'boundObjects':[o.name for o in bounds],'softObjects':[o.name for o in soft],'cusPadMap':padmap,'contractSha256':hashlib.sha256((ROOT/'contract.json').read_bytes()).hexdigest(),'generatorSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'blendSha256':hashlib.sha256((OUT/'aura-a04-m2.blend').read_bytes()).hexdigest(),'nativePlacementImported':False,'physicalQualification':False}
(OUT/'parts-manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('M2_DRAFT_EXPORTED',a.scenario,len(items),flush=True)
