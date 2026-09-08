"""Build two unqualified A04 mechanism trials; never writes the native PCB.

Blender 5.2: --background --python build_mechanism.py -- --scenario thin-cell
All STL specimens are separate, in millimetres, with their lowest point at z=0.
The .blend keeps assembly coordinates. No supplier parts are exported as device parts.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
import bmesh
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "mechanism-contract.json"
cfg = json.loads(CONTRACT.read_text())
parser = argparse.ArgumentParser()
parser.add_argument("--scenario", choices=[s["id"] for s in cfg["cellScenarios"]], default="thin-cell")
args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
scenario = next(s for s in cfg["cellScenarios"] if s["id"] == args.scenario)
OUT = ROOT / args.scenario
OUT.mkdir(exist_ok=True)
MM, N = 1.0, 192
D = scenario["bodyDepthMm"]
R = cfg["bodyDiameterMm"]/2
CR = cfg["cavityDiameterMm"]/2
CELL_X,CELL_Y = cfg["cellCentreXYMm"]
ANGLES = cfg["retainerColumns"]["anglesDeg"]
COL_R = cfg["retainerColumns"]["radiusFromOriginMm"]
cell_depth = scenario["maximumAllocationMm"][2]
P = 1 + .15 + cell_depth + .4 + .15  # true PCB underside, not target thickness
PT = P + 1.6
FACE_BACK = D-1.05
STOP = D-2.8
RET_BOTTOM = STOP-1.1
SLIDE_Z = P-2.7
bosses = cfg["closure"]["screwCentresXYMm"]
columns = [(COL_R*math.cos(math.radians(a)), COL_R*math.sin(math.radians(a))) for a in ANGLES]
parts, proxies = [], []

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.data.orphans_purge(do_local_ids=True,do_linked_ids=True,do_recursive=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.length_unit = "MILLIMETERS"
scene.unit_settings.scale_length = .001


def material(name, color, metal=0, rough=.38):
    m=bpy.data.materials.new(name);m.use_nodes=True
    p=m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value=(*color,1)
    p.inputs["Metallic"].default_value=metal;p.inputs["Roughness"].default_value=rough
    return m


ivory=material("Unqualified satin polymer",(.73,.70,.62))
rim=material("Nonconductive champagne finish target",(.40,.31,.18),.35,.27)
dark=material("Unqualified graphite polymer",(.045,.06,.062))
clear=material("Clear polymer optical trial",(.72,.81,.79),0,.22)
pcbmat=material("PROPOSED NOTCHED DUMMY BOARD",(.035,.20,.13))
amber=material("UNQUALIFIED MAXIMUM PACK ALLOCATION",(.40,.19,.055))
metal=material("Purchased metal envelopes",(.32,.34,.35),.7,.32)
foam=material("Unqualified silicone foam",(.16,.17,.15))


def box(name,dims,center):
    bpy.ops.mesh.primitive_cube_add(size=1, location=[v*MM for v in center])
    o=bpy.context.object;o.name=name;o.dimensions=[v*MM for v in dims]
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return o


def cyl(name,r,low,high,xy=(0,0),n=N):
    bpy.ops.mesh.primitive_cylinder_add(vertices=n,radius=r*MM,depth=(high-low)*MM,
        location=(xy[0]*MM,xy[1]*MM,(low+high)*MM/2))
    o=bpy.context.object;o.name=name
    return o


def tube_axis(name,r,a,b):
    a,b=Vector(a)*MM,Vector(b)*MM
    bpy.ops.mesh.primitive_cylinder_add(vertices=96,radius=r*MM,depth=(b-a).length,location=(a+b)/2)
    o=bpy.context.object;o.name=name;o.rotation_euler=(b-a).to_track_quat("Z","Y").to_euler()
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    return o


def boolean(o,c,op="UNION"):
    bpy.context.view_layer.objects.active=o
    mod=o.modifiers.new("Functional solid", "BOOLEAN");mod.operation=op;mod.solver="MANIFOLD";mod.object=c
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(c,do_unlink=True)


def ring(name,ro,ri,z0,z1):
    o=cyl(name,ro,z0,z1)
    boolean(o,cyl("Open through bore",ri,z0-1,z1+1),"DIFFERENCE")
    return o


def radial_box(name,radial,tangent,z0,z1,r,angle):
    a=math.radians(angle)
    o=box(name,(radial,tangent,z1-z0),(r*math.cos(a),r*math.sin(a),(z0+z1)/2))
    o.rotation_euler.z=a
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    return o


def mark(o,name,mat,desc,role="part"):
    o.name=name;o.data.materials.append(mat)
    o["revision"]=cfg["revision"];o["status"]="UNQUALIFIED MECHANISM TRIAL"
    o["description"]=desc;o["native_placement_imported"]=False;o["physical_qualification"]=False
    (parts if role=="part" else proxies).append(o)
    return o


def subtract_boss_clearance(o,r=3.05,z0=-1,z1=20):
    for xy in bosses:boolean(o,cyl("Closure relief",r,z0,z1,xy),"DIFFERENCE")


# One structural front housing; the bail is an actual bored, connected load path.
housing=ring("Front housing",R,CR,1,D)
boolean(housing,ring("Stationary outward face stop",R,17.85,D-1.6,D))
boolean(housing,ring("Diffuser seat recess",18.65,17.84,D-.8,D+.2),"DIFFERENCE")
boolean(housing,box("Bail root",(5.2,5.3,3.8),(0,21.35,D/2)))
boolean(housing,tube_axis("Actual transverse bail passage",1.3,(-4,21.5,D/2),(4,21.5,D/2)),"DIFFERENCE")
boolean(housing,cyl("Bail root must respect internal cavity",CR,1,D-1.6),"DIFFERENCE")
for a in ANGLES:
    boolean(housing,radial_box("Radial guide bearing",1.8,3.0,D-2.7,D-1.5,19.25,a))
    boolean(housing,radial_box("Face antirotation running channel",1.2,1.6,D-2.95,D-1.55,18.3,a),"DIFFERENCE")
for xy in bosses:
    boolean(housing,cyl("Closure load boss",2.7,1,D-1.8,xy))
    nut=cyl("Rear-loaded captive hex nut pocket",3.45/math.sqrt(3),.5,6.8,xy,6)
    boolean(housing,nut,"DIFFERENCE")
    boolean(housing,cyl("Screw tip clearance",.95,6.7,D-1.7,xy),"DIFFERENCE")
    boolean(housing,cyl("Rear screw seat insertion clearance",2.75,.8,2.25,xy),"DIFFERENCE")
# Keeper is integral with rear cover and fills this removable side panel.
boolean(housing,box("Privacy keeper installation opening",(4.0,6.9,P-1.3),(19.4,0,(1+P-.3)/2)),"DIFFERENCE")
for x in (-6.5,6.5):
    boolean(housing,tube_axis("Acoustic insert access",1.65,(x,-13.8,2.6),(x,-22,2.6)),"DIFFERENCE")
mark(housing,"01_FRONT_HOUSING_WITH_BAIL",rim,"Hollow housing, fixed outward stops, captive nut seats, real bail passage, removable privacy side panel and acoustic access")

# Captive face. Its thick edge occupies a negotiated radial keepout, not a global height band.
face=cyl("Face skin",17.6,FACE_BACK,D-.05)
boolean(face,ring("Edge skirt",17.6,16.9,D-2.4,FACE_BACK+.1))
boolean(face,ring("Capturing flange",18.35,16.9,D-2.4,D-1.6))
for a in ANGLES:boolean(face,radial_box("Antirotation key",.6,1.2,D-2.4,D-1.6,18.35,a))
subtract_boss_clearance(face,z0=-1,z1=FACE_BACK-.05)
boolean(face,box("Maximum radio motion relief",(11.3,16.3,5),(0,8.6,FACE_BACK-2.55)),"DIFFERENCE")
boolean(face,box("Real status aperture",(3.0,.5,3),(0,0,D-.6)),"DIFFERENCE")
# Rear keyed plunger socket accepts a sizing insert; no printed miniature threads.
sx,sy=cfg["controlsProposal"]["faceSwitchXYMm"]
boolean(face,box("Plunger socket walls",(4.0,3.6,.9),(sx,sy,FACE_BACK-.35)))
boolean(face,box("Plunger insert pocket",(2.2,1.8,1.25),(sx,sy,FACE_BACK-.425)),"DIFFERENCE")
mark(face,"02_CAPTIVE_FACE_PADDLE",ivory,"35.2 mm face, true retaining flange, three guides, status through-slot and replaceable sizing-plunger socket")

retainer=ring("Stationary overload retainer",18.75,16.3,RET_BOTTOM,STOP)
for xy in bosses:
    bridge=ring("Closure notch bridge",4.4,3.05,RET_BOTTOM,STOP)
    bridge.location.x+=xy[0];bridge.location.y+=xy[1]
    boolean(bridge,cyl("Clip bridge to carrier perimeter",18.75,RET_BOTTOM-1,STOP+1),"INTERSECT")
    boolean(retainer,bridge)
subtract_boss_clearance(retainer)
boolean(retainer,box("Maximum radio carrier relief",(11.3,16.3,5),(0,8.6,STOP-1)),"DIFFERENCE")
for (x,y),a in zip(columns,ANGLES):
    boolean(retainer,radial_box("Return foam through pocket",1.2,1.7,RET_BOTTOM-.2,STOP+.2,17.5,a),"DIFFERENCE")
mark(retainer,"03_FACE_RETAINER",dark,"Clamped by three rear columns; rigid overload stop at 0.40 mm stroke, openings for separate silicone returns")

diffuser=ring("Fixed optical ring",18.5,17.85,D-.75,D-.05)
mark(diffuser,"04_FIXED_DIFFUSER_RING",clear,"Separate clear optical trial; fixed seat, no uniformity or efficiency qualification")
dash=box("Status lightpipe stem",(3,.5,2.3),(0,0,D-1.2))
boolean(dash,box("Status pipe rear retention flange",(4.4,1.6,.4),(0,0,FACE_BACK-.25)))
mark(dash,"05_MOVING_STATUS_LIGHTPIPE",clear,"Separate clear pipe retained behind real face slot; moves with face; optical gap remains unqualified")

plunger=box("Sizing plunger insert",(1.9,1.5,1.3),(sx,sy,FACE_BACK-.55))
mark(plunger,"06_PLUNGER_SIZING_INSERT",dark,"Sizing blank with 1.20 mm protrusion; do not rigidly actuate powered KMR2 until measured/trimmed/compliant-tip qualification")

rear=cyl("Rear cover floor",R,0,1)
# Three separate location keys leave the maximum rectangular cell corners unobstructed.
for a in (45,135,270):boolean(rear,radial_box("Rear cover location key",.85,2.8,.9,2.0,18.625,a))
for x,y in columns:boolean(rear,cyl("Retainer support column",1.3,.9,RET_BOTTOM,(x,y)))
for xy in bosses:
    boolean(rear,cyl("Rear screw load seat",2.65,.9,2.2,xy))
    boolean(rear,cyl("Screw clearance",.95,-1,3,xy),"DIFFERENCE")
    boolean(rear,cyl("Recessed pan-head seat",1.75,-1,1.1,xy),"DIFFERENCE")
# A separate sliding fork is retained by this actual structural keeper/side panel.
boolean(rear,box("Privacy keeper panel",(2.7,6.5,P-1.4),(19.05,0,(.9+P-.5)/2)))
boolean(rear,box("Slider stem running slot and adjustable hard-stop allowance",(5,4.6,1.3),(18.9,0,SLIDE_Z)),"DIFFERENCE")
# Open access well; actual contact pads are a PCB proposal, not invented metal pins.
boolean(rear,box("Keyed contact carrier rear access",(9.9,3.6,4),(0,-15.5,1)),"DIFFERENCE")
boolean(rear,box("Contact carrier key clearance",(1.4,1.1,2),(-3.9,-13.9,.7)),"DIFFERENCE")
# Separate open wire cleats cannot pinch the pouch; no selected lead route is implied.
for x in (-3,3):
    cleat=box("Lead restraint cleat",(2.5,1.5,2.1),(x,-12.9,1.95))
    boolean(cleat,box("Insulated lead/tie passage",(1.3,3,1.1),(x,-12.9,1.85)),"DIFFERENCE")
    boolean(rear,cleat)
boolean(rear,cyl("Rear perimeter trim",R,-1,D),"INTERSECT")
mark(rear,"07_REAR_COVER_AND_SLIDER_KEEPER",ivory,"Removable rear, three retainer supports, recessed screw seats, privacy keeper, contact well and open lead cleats")

slider=box("External low-profile privacy grip",(1.1,4.8,1.8),(21.25,0,SLIDE_Z))
boolean(slider,box("Guided stem",(4.1,2.2,.9),(18.85,0,SLIDE_Z)))
boolean(slider,box("Captive internal bridge",(.85,6.0,.9),(16.98,0,SLIDE_Z)))
for y in (-1.4,1.4):
    boolean(slider,box("Open fork finger",(3.35,1.0,.9),(14.925,y,SLIDE_Z)))
mark(slider,"08_CUS22_PRIVACY_FORK",dark,"Real captive translating fork; 1.8 mm lever opening, nominal 1.5 mm motion and 2.4 mm unshimmed shell allowance; endpoint shims/actual switch timing must be measured; proposed CUS22 only")

# Separate actually hollow L ducts. Each may be drilled/inspected from both ends.
for x,side in [(-6.5,"LEFT"),(6.5,"RIGHT")]:
    duct=cyl("PCB port carrier",1.5,1.1,P-.4,(x,-13.8))
    boolean(duct,tube_axis("Hollow side duct exterior",1.5,(x,-13.8,2.6),(x,-20,2.6)))
    boolean(duct,cyl("Trim to outer case",R-.02,-2,D+1),"INTERSECT")
    boolean(duct,cyl("Vertical sound bore",.65,2.3,P+1,(x,-13.8)),"DIFFERENCE")
    boolean(duct,tube_axis("Side sound bore",.65,(x,-13.8,2.6),(x,-22,2.6)),"DIFFERENCE")
    mark(duct,f"09_ACOUSTIC_DUCT_{side}",dark,"Separate open 1.30 mm L bore; 0.40 mm working gasket gap to proposed PCB port; actual acoustic seal and response unqualified")

contact=box("Contact access chimney",(9.4,3.1,P-.3),(0,-15.5,(P-.3)/2))
for x in (-3,0,3):boolean(contact,cyl("Pogo access bore",1.0,-1,P+1,(x,-15.5)),"DIFFERENCE")
# An asymmetric upper tab provides a real carrier orientation datum.
boolean(contact,box("Carrier key",(1.0,.7,.8),(-3.9,-13.9,.5)))
mark(contact,"10_DOCK_CONTACT_ACCESS_CARRIER",dark,"Insulating access to proposed B.Cu pads; requires raised keyed dock nose, not raw 4.5 mm pins reaching a 5-6 mm recess")

sensor=box("Sensor carrier floor",(4.9,5.3,.8),(13.65,-7,1.4))
boolean(sensor,box("Outer sensor wall",(.8,5.3,2.6),(15.7,-7,2.7)))
for y in (-9.3,-4.7):boolean(sensor,box("Sensor retaining side",(4.9,.7,2.6),(13.65,y,2.7)))
boolean(sensor,box("Open-top sensor lead release",(1.4,1.2,3.0),(14.5,-4.7,3.6)),"DIFFERENCE")
mark(sensor,"11_RIGHT_LOWER_SENSOR_CARRIER",dark,"Open cell-side thermal pocket below privacy switch; contact adhesive, lead relief and thermal lag still unqualified")

# Fit gauges are clearly distinct from final device parts and from native PCB geometry.
dummy=cyl("Unpowered notched board gauge",17.6,P,PT)
for xy in bosses:boolean(dummy,cyl("Proposed screw boss notch",3.05,P-1,PT+1,xy),"DIFFERENCE")
for xy in columns:boolean(dummy,cyl("Proposed column notch",1.6,P-1,PT+1,xy),"DIFFERENCE")
for x in (-6.5,6.5):boolean(dummy,cyl("Proposed PCB acoustic port",.5,P-1,PT+1,(x,-13.8)),"DIFFERENCE")
mark(dummy,"90_UNPOWERED_NOTCHED_BOARD_GAUGE",pcbmat,"Physical fit gauge ONLY; differs from unnotched native board and includes unaccepted port proposals")
dummy["device_part"]=False
pack=box("Controlled maximum pack gauge",(26,21,cell_depth),(CELL_X,CELL_Y,1.15+cell_depth/2))
mark(pack,"91_UNPOWERED_MAX_PACK_GAUGE",amber,"Solid unpowered gauge, not a battery; dimensions are controlled allocation, not a qualified supplied assembly")
pack["device_part"]=False

# Purchased parts / bounds, all named as proposals and excluded from STL print kit.
radio=box("PROPOSED_RADIO_MAX_WITH_SEATING",(10.7,15.7,2.4),(0,8.6,PT+1.2))
mark(radio,radio.name,metal,"Illustrative allocation for maximum body plus 0.15 mm seating; not native position", "proxy")
motor=cyl("PROPOSED_ERM_MAX_MOUNTED",5.05,PT,PT+2.45,(6,-5))
mark(motor,motor.name,metal,"Maximum mounted motor allocation; wire/tab needs its own keepout", "proxy")
switch=box("PROPOSED_CUS22_MAX_BODY",(4.3,6.9,1.6),(13.5,0,P-.15-.8))
mark(switch,switch.name,metal,"Underside alternative, not native JS202", "proxy")
lever=box("PROPOSED_CUS22_MAX_LEVER",(.9,1.4,1.7),(14.45,0,P-.15-1.6-.85))
mark(lever,lever.name,dark,"Conservative actuator height/width envelope; separate translation sweep", "proxy")
ntc=box("PROPOSED_SEMITEC_MAX_BODY",(4,3.7,2.4),(13.2,-7,3.0))
mark(ntc,ntc.name,amber,"Cell-edge body allocation; measured thermal contact missing", "proxy")
tactile=box("PROPOSED_KMR2_ENVELOPE",(4.4,3.2,1.9),(sx,sy,PT+.95))
mark(tactile,tactile.name,metal,"Nominal-height switch position for plunger sizing only", "proxy")
for i,(xy,a) in enumerate(zip(columns,ANGLES)):
    pad=radial_box("RETURN_FOAM_ALLOCATION",1,1.5,RET_BOTTOM,RET_BOTTOM+1.6,17.5,a)
    mark(pad,f"RETURN_FOAM_ALLOCATION_{i+1}",foam,"Uncompressed allocation; compresses in actual assembly; not printable rigid geometry", "proxy")
for i,(x,y) in enumerate(bosses):
    screw=cyl("Purchased screw envelope",.8,1.1,7.1,(x,y))
    boolean(screw,cyl("Pan head nominal envelope",1.6,.1,1.1,(x,y)))
    mark(screw,f"M1_6x6_SCREW_{i+1}",metal,"Nominal purchased fastener; no threads modelled, torque/tolerance unqualified", "proxy")

# Orient faces outward consistently after exact CSG, before export.
def volume(o):
    bm=bmesh.new();bm.from_mesh(o.data);v=bm.calc_volume(signed=True);bm.free();return v/(MM**3)


manifest=[]
for o in parts:
    bm=bmesh.new();bm.from_mesh(o.data)
    # Remove sub-0.00005 mm CSG slivers before the STL float32 conversion.
    # This is orders of magnitude below the 0.005 mm export-dimension check.
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00005)
    bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.00005)
    bmesh.ops.triangulate(bm,faces=list(bm.faces))
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(o.data);bm.free()
    if volume(o)<0:
        bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.reverse_faces(bm,faces=list(bm.faces));bm.to_mesh(o.data);bm.free()
    points=[o.matrix_world@Vector(c) for c in o.bound_box]
    low=[min(p[i] for p in points)/MM for i in range(3)]
    high=[max(p[i] for p in points)/MM for i in range(3)]
    filename=o.name.lower()+".stl"
    old=o.location.copy();o.location.z-=low[2]*MM
    bpy.ops.object.select_all(action="DESELECT");o.select_set(True);bpy.context.view_layer.objects.active=o
    bpy.ops.wm.stl_export(filepath=str(OUT/filename),export_selected_objects=True,global_scale=1,apply_modifiers=True,ascii_format=False)
    o.location=old
    raw=(OUT/filename).read_bytes()
    manifest.append({"object":o.name,"file":filename,"description":o["description"],"devicePartCandidate":o.get("device_part",True),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"assemblyBoundsMm":[low,high],"printTranslationMm":[0,0,-low[2]]})

scene["status"]=cfg["status"];scene["body_depth_mm"]=D;scene["pcb_thickness_mm"]=1.6
scene["native_placement_imported"]=False
scene.render.filepath="//mechanism-exploded.png"
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"aura-a04-mechanism.blend"),compress=True)
report={"revision":cfg["revision"],"status":cfg["status"],"scenario":args.scenario,"physicalQualification":False,"printRelease":False,"nativePlacementImported":False,"nativePcbChanged":False,"bodyDiameterMm":2*R,"bodyDepthMm":D,"pcbThicknessMm":1.6,"cellMaximumAllocationMm":[26,21,cell_depth],"pcbBottomZMm":P,"pcbTopZMm":PT,"componentTopZMm":PT+2.45,"retainerBottomZMm":RET_BOTTOM,"retainerStopZMm":STOP,"contractSha256":hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),"generatorSha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"blendSha256":hashlib.sha256((OUT/'aura-a04-mechanism.blend').read_bytes()).hexdigest(),"parts":manifest,"partCount":len(manifest),"devicePartCandidates":sum(p['devicePartCandidate'] for p in manifest),"unpoweredGauges":sum(not p['devicePartCandidate'] for p in manifest),"requiredPcbChanges":["Two screw-boss notches radius3.05","Three support notches radius1.6","Maximum top parts excluded from retainer annulus","Underside CUS22 footprint/body/actuator and solder anchors","Two actual bottom-mic acoustic ports and gasket keepouts","Underside dock pads accessible in chimney","NTC pocket moved right/lower","Actual module/flash/motor/72-part placement and routing still absent"]}
(OUT/"parts-manifest.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print("A04_MECHANISM_CANDIDATE_EXPORTED",args.scenario,len(manifest),flush=True)
