"""AURA A03 wearable enclosure and product visualization. Blender 5.2 / Python.

Run: blender --background --python build_aura.py
Coordinates: X width, Y height, Z depth, front=+Z. Design arguments are mm;
Blender geometry is metres, STL exports are millimetres, glTF is metres.
This is a mechanical prototype concept; see MECHANICAL.md before fabrication.
"""
import bpy, math, json, os, sys
from pathlib import Path
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parent
RENDERS = ROOT / 'renders'
RENDERS.mkdir(exist_ok=True)
MM = .001

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for data in list(bpy.data.materials): bpy.data.materials.remove(data)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.length_unit = 'MILLIMETERS'
scene.unit_settings.scale_length = 1.0
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 32
scene.cycles.use_denoising = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.film_transparent = True
scene.render.resolution_percentage = 100
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Medium High Contrast'
scene.view_settings.exposure = -.25
scene.render.image_settings.color_depth = '8'

def mat(name, color, metal=0, rough=.35, emission=None):
    m=bpy.data.materials.new(name); m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Metallic'].default_value=metal
    p.inputs['Roughness'].default_value=rough
    p.inputs['Coat Weight'].default_value=.2
    p.inputs['Coat Roughness'].default_value=.25
    if emission:
        p.inputs['Emission Color'].default_value=(*color,1)
        p.inputs['Emission Strength'].default_value=emission
    return m

shell=mat('Frame / nonconductive satin silver finish',(.50,.52,.54),.68,.29)
backmat=mat('Back / satin silver polymer',(.39,.41,.43),.57,.32)
buttonmat=mat('Face / polished obsidian resin',(.006,.009,.014),.16,.16)
buttonmat.node_tree.nodes.get('Principled BSDF').inputs['Coat Weight'].default_value=.32
buttonmat.node_tree.nodes.get('Principled BSDF').inputs['Coat Roughness'].default_value=.13
buttonmat.node_tree.nodes.get('Principled BSDF').inputs['Specular IOR Level'].default_value=.26
chainmat=mat('Chain / polished stainless reference',(.48,.50,.53),.95,.24)
edgeglaze=mat('Edge • polished nonconductive glaze',(.78,.77,.73),.10,.14)
shell.node_tree.nodes.get('Principled BSDF').inputs['Coat Weight'].default_value=.38
dark=mat('Graphite silicone',(.016,.019,.019),.08,.45)
cordmat=mat('Woven charcoal cord',(.021,.024,.024),0,.68)
gold=mat('Gold plated charging contacts',(.64,.39,.095),.8,.22)
pcbmat=mat('PCB • forest soldermask',(.014,.064,.046),.1,.4)
copper=mat('PCB • immersion gold',(.60,.39,.10),.85,.3)
black=mat('Electronics • ceramic black',(.012,.016,.020),.1,.34)
silver=mat('Electronics • shield',(.40,.44,.46),.78,.32)
batteryfoil=mat('Cell • brushed foil',(.26,.29,.30),.73,.34)
amber=mat('Privacy status • amber',(.98,.35,.045),.15,.32)
ledmat=mat('Recording indicator / ice white',(.64,.81,1.0),.05,.22,2.3)
labelmat=mat('Laser mark • soft warm gray',(.27,.26,.24),.10,.43)
floor_mat=mat('Studio • midnight',(.010,.014,.015),.15,.31)

product=[]
def finish(obj, material, smooth=True, register=True):
    obj.data.materials.clear(); obj.data.materials.append(material)
    if smooth and obj.type=='MESH':
        for p in obj.data.polygons: p.use_smooth=True
    if register: product.append(obj)
    return obj

def rr_points(w,h,r,steps=20):
    out=[]
    for cx,cy,a in [(w/2-r,h/2-r,0),(-w/2+r,h/2-r,90),(-w/2+r,-h/2+r,180),(w/2-r,-h/2+r,270)]:
        for i in range(steps+1):
            ang=math.radians(a+90*i/steps)
            out.append(((cx+r*math.cos(ang))*MM,(cy+r*math.sin(ang))*MM))
    return out

def loft(name, rings, material, register=True):
    verts=[]; faces=[]
    for z,w,h,r in rings: verts.extend([(x,y,z*MM) for x,y in rr_points(w,h,r)])
    n=len(verts)//len(rings)
    faces.append(tuple(reversed(range(n))))
    for j in range(len(rings)-1):
        for i in range(n):
            ni=(i+1)%n
            faces.append((j*n+i,j*n+ni,(j+1)*n+ni,(j+1)*n+i))
    faces.append(tuple(range((len(rings)-1)*n,len(rings)*n)))
    mesh=bpy.data.meshes.new(name); mesh.from_pydata(verts,[],faces); mesh.update()
    ob=bpy.data.objects.new(name,mesh); bpy.context.collection.objects.link(ob)
    return finish(ob,material,register=register)

def radial_loft(name,rings,material,register=True):
    verts=[];faces=[];n=64
    for z,r in rings:
        for i in range(n):
            a=2*math.pi*i/n;verts.append((r*math.cos(a)*MM,r*math.sin(a)*MM,z*MM))
    faces.append(tuple(reversed(range(n))))
    for j in range(len(rings)-1):
        for i in range(n):faces.append((j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i))
    faces.append(tuple(range((len(rings)-1)*n,len(rings)*n)))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    ob=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(ob)
    return finish(ob,material,register=register)

def cube(name, xyz, dims, material, bevel=.1, register=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=[v*MM for v in xyz]); o=bpy.context.object; o.name=name
    o.dimensions=[v*MM for v in dims]
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if bevel:
        mod=o.modifiers.new('Machined radii','BEVEL');mod.width=bevel*MM;mod.segments=5
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return finish(o,material,register=register)

def cyl(name, xyz, radius, depth, material, axis='Z', register=True, vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius*MM,depth=depth*MM,location=[v*MM for v in xyz])
    o=bpy.context.object;o.name=name
    if axis=='X':o.rotation_euler[1]=math.pi/2
    if axis=='Y':o.rotation_euler[0]=math.pi/2
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return finish(o,material,register=register)

def boolean(ob,cut,operation='DIFFERENCE'):
    bpy.context.view_layer.objects.active=ob
    mod=ob.modifiers.new('Functional geometry','BOOLEAN');mod.operation=operation;mod.solver='EXACT';mod.object=cut
    bpy.ops.object.modifier_apply(modifier=mod.name)
    if cut in product:product.remove(cut)
    bpy.data.objects.remove(cut,do_unlink=True)

def bevel(ob, amount=.07):
    bpy.context.view_layer.objects.active=ob
    m=ob.modifiers.new('Edge softening','BEVEL');m.width=amount*MM;m.segments=3
    m.limit_method='ANGLE'
    try:bpy.ops.object.modifier_apply(modifier=m.name)
    except RuntimeError:ob.modifiers.remove(m)

def text(name,body,xyz,size,material,rotation=(0,0,0)):
    curve=bpy.data.curves.new(name,'FONT');curve.body=body;curve.align_x='CENTER';curve.align_y='CENTER';curve.size=size*MM;curve.extrude=.006*MM
    ob=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(ob);ob.location=[v*MM for v in xyz];ob.rotation_euler=rotation
    bpy.context.view_layer.objects.active=ob;ob.select_set(True);bpy.ops.object.convert(target='MESH');ob.select_set(False)
    return finish(ob,material)

def tube(name,points,radius,material,register=True):
    cu=bpy.data.curves.new(name,'CURVE');cu.dimensions='3D';cu.resolution_u=32
    sp=cu.splines.new('BEZIER');sp.bezier_points.add(len(points)-1)
    for p,co in zip(sp.bezier_points,points):
        p.co=[v*MM for v in co];p.handle_left_type='AUTO';p.handle_right_type='AUTO'
    cu.bevel_depth=radius*MM;cu.bevel_resolution=5;cu.resolution_u=24
    ob=bpy.data.objects.new(name,cu);bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active=ob;ob.select_set(True);bpy.ops.object.convert(target='MESH');ob.select_set(False)
    return finish(ob,material,register=register)

# A03 capsule frame, separate rigid face paddle and rear cup.
# Geometry remains in mm arguments / metres in Blender. 48H x28W x10D.
front=loft('Housing_Front',[(.055,28,48,13.98),(3.45,27.95,47.95,13.955),(4.4,27.25,47.25,13.605),(4.88,26.25,46.25,13.105),(5.0,25.5,45.5,12.73)],shell)
boolean(front,loft('Frame cavity',[(-2,25.6,45.6,12.78),(3.50,25.6,45.6,12.78)],dark,False))
boolean(front,loft('Moving face opening',[(3.45,23.6,43.6,11.78),(7,23.6,43.6,11.78)],dark,False))
rear=loft('Housing_Back',[(-5,26.5,46.5,13.23),(-4.8,27.2,47.2,13.58),(-4.2,27.85,47.85,13.905),(-3.2,28,48,13.98),(-.055,28,48,13.98)],backmat)
boolean(rear,loft('Rear cavity',[(-4.0,25.6,45.6,12.78),(1.5,25.6,45.6,12.78)],dark,False))

# Fasteners are beyond PCB ends (+/-21), in the capsule tips.
for y in [-22.5,22.5]:
    boolean(front,cyl('Front retained boss',(0,y,1.755),1.25,3.40,shell,register=False),'UNION')
    boolean(front,cyl('Fastener pilot',(0,y,1.4),.48,4.2,dark,register=False))
    boolean(rear,cyl('Rear retained boss',(0,y,-2.0),1.25,3.89,backmat,register=False),'UNION')
    boolean(rear,cyl('Fastener clearance',(0,y,-2.5),.68,6,dark,register=False))
    boolean(rear,cyl('Fastener head seat',(0,y,-4.78),1.02,.56,dark,register=False))

# Flush 0.9mm paddle, retained from behind by four tabs. The whole black face
# records. Its 0.35mm translation is limited by four wall-connected hard stops.
button=loft('Record_Button',[(4.05,23.2,43.2,11.58),(4.78,23.2,43.2,11.58),(4.95,22.95,42.95,11.455)],buttonmat)
plunger=cyl('Record_Plunger',(0,-6,3.37),.75,1.60,buttonmat)
for side in [-1,1]:
    for y in [-3,3]:
        boolean(button,cube('Paddle tab leg',(side*11.15,y,3.68),(.65,1.6,1.05),buttonmat,.035,False),'UNION')
        boolean(button,cube('Paddle capture flange',(side*11.7,y,3.3),(1.25,1.6,.3),buttonmat,.035,False),'UNION')
    for y in [-7.5,7.5]:
        boolean(front,cube('Paddle travel stop',(side*11.9,y,3.495),(1.4,1.8,.41),shell,.04,False),'UNION')
for x in [-8.5,8.5]:
    boolean(button,cyl('Acoustic aperture',(x,8.5,4.5),.35,3,dark,register=False,vertices=40))
    cyl('AcousticMesh_L' if x<0 else 'AcousticMesh_R',(x,8.5,4.62),.27,.06,dark)
boolean(button,cyl('LED aperture',(0,-1,4.5),.31,3,dark,register=False,vertices=40))
cyl('LED_Lightpipe',(0,-1,4.89),.25,.10,ledmat)
# A moving lightpipe and compressible acoustic boots require physical life testing.
gasket=loft('Paddle_Return_Gasket',[(3.55,23.35,43.35,11.655),(4.02,23.35,43.35,11.655)],dark)
boolean(gasket,loft('Paddle return gasket void',[(3,22.05,42.05,11.005),(5,22.05,42.05,11.005)],dark,False))

# Side privacy slider: longer silhouette, positive mechanical slide gesture.
boolean(front,cube('Privacy actuator clearance',(13.3,-.2,1.4),(3.0,6.5,1.8),dark,.6,False))
cube('Privacy_Slider_Track',(13.78,-.2,1.4),(.42,6.2,1.62),dark,.62)
privacy=cube('Privacy_Slider',(13.94,.4,1.4),(.44,4.6,1.40),shell,.6)
cube('Privacy_Off_Marker',(14.02,-2.65,1.4),(.04,.6,.8),amber,.13)

seam=loft('Seam_Gasket',[(-.04,27.94,47.94,13.95),(.04,27.94,47.94,13.95)],dark)
boolean(seam,loft('Seam void',[(-1,25.55,45.55,12.755),(1,25.55,45.55,12.755)],dark,False))

# Rear contacts moved below cell to Y-19 on longer A03 PCB.
boolean(rear,cube('Contact carrier opening',(0,-19,-4.55),(10.0,3.1,2),dark,1.1,False))
carrier=cube('Charging_Contact_Bed',(0,-19,-4.57),(9.8,2.9,.70),dark,.80)
for x in [-3,0,3]:boolean(carrier,cyl('Contact tail hole',(x,-19,-4.55),.35,2,dark,register=False))
for i,x in enumerate([-3,0,3]):cyl(f'Charging_Contact_{i+1}',(x,-19,-4.96),.85,.08,gold)

# Jewelry-like integrated bail, one solid part of rear cup. Hole axis is X.
bail=cube('Integrated bail',(0,26.4,-2.4),(5.5,7.2,4.6),backmat,1.05,False)
boolean(bail,cyl('Bail opening',(0,27.2,-2.4),1.7,9,dark,axis='X',register=False))
boolean(rear,bail,'UNION')

# Board rails retain 24x42 R10 outline; shelves support Z=-0.15 underside.
for side in [-1,1]:
    for y in [-6,5]:
        for name,x,z,dims in [('PCB rail root',12.7,-1.2,(1.4,3.5,1.5)),('PCB shelf',12.10,-.5,(1.1,3.5,.7)),('PCB stem',12.55,-.1,(.5,1.6,1.9)),('PCB lip',12.15,.95,(.9,1.6,.30))]:
            boolean(rear,cube(name,(side*x,y,z),dims,backmat,.025,False),'UNION')

# Maximum target cell allowance includes tentative PCM length and assembly room.
board=loft('PCB_Reference',[(-.15,24,42,10),(.65,24,42,10)],pcbmat)
battery=cube('Battery_Envelope',(0,-3,-2.10),(20.5,28,3.3),batteryfoil,.45)
cube('Battery_Insulator',(0,-3,-.425),(20.5,28,.05),dark,.35)
text('Battery_Label','AURA / 150 mAh TARGET\nPROTECTED CELL ENVELOPE',(0,-5,-.386),1.25,labelmat)
for x in [-10.7,10.7]:cube('Battery_Locator',(x,-3,-2.4),(.6,21,1.8),dark,.15)

# Proxy bodies use hardware placement snapshot, not manufacturing STEP data.
placements=json.loads((ROOT/'pcb-placement-reference.json').read_text())
def package(name,ref,dims,material=black):
    pos=placements[ref]
    ob=cube(name,(pos['x'],pos['y'],.65+dims[2]/2),dims,material,.08)
    ob.rotation_euler.z=math.radians(pos.get('r',0));ob['hardware_reference']=ref
    ob['geometry_status']='package envelope proxy, not vendor STEP';return ob
module=package('RF_Module_Envelope','U1',(10.5,15.5,2.05),silver)
cube('Antenna_Window',(0,13.85,2.735),(10.45,3.7,.07),black,.06)
text('Module_Mark','RAYTAC\nnRF52840',(0,6.5,2.708),1.05,labelmat)
for ref in ['MK1','MK2']:package('MEMS_Microphone',ref,(2.65,3.5,1.0),silver)
package('Flash_Envelope','U2',(8,6,.8))
for ref,dims in [('U3',(2.5,2.5,.9)),('U4',(3,3,1)),('U5',(2,2,.9)),('U6',(3,3,.9)),('U7',(1.5,1.5,.6)),('U8',(2,2,.8)),('U9',(1.6,1.6,1.1)),('Q1',(3,3,1.1))]:
    if ref in placements:package('Power_Envelope_'+ref,ref,dims)
package('Privacy_DPDT_Switch','SW1',(9.1,3.6,1.4),silver)
package('Record_Tact_Switch','SW2',(4.8,4.8,1.5),silver)
cyl('Record_Switch_Actuator',(0,-6,2.35),1.5,.4,black)
cyl('Haptic_Reference',(6,-12,2.075),4.05,2.75,silver)
cyl('Haptic_Insulator',(6,-12,.675),4.15,.05,dark)
for ref,pos in placements.items():
    if ref.startswith(('R','C')):package('Passive_Reference_'+ref,ref,(2,1.25,1.4) if ref=='C9' else (1,.5,.5),dark)
for x in [-8.5,8.5]:
    tube('Acoustic_Gasket_Channel',[(x,8.5,-.35),(12.45 if x>0 else -12.45,8.5,-.45),(12.45 if x>0 else -12.45,8.5,3.1),(x,8.5,3.55),(x,8.5,4.5)],.28,dark)
text('Rear_Wordmark','A U R A',(0,1,-5.022),1.6,labelmat,(math.pi,0,0))
text('Rear_Prototype_Mark','DESIGN PROTOTYPE\nMODEL A03',(0,-3,-5.022),.7,labelmat,(math.pi,0,0))

# Top retainer polymer, bottom micro-screw. Both sit beyond PCB in capsule tips.
for y in [-22.5,22.5]:
    if y>0:
        head=radial_loft('Top_Polymer_Retainer',[(-4.77,.86),(-4.55,.86),(-4.51,.625),(-.85,.625),(-.75,.49),(2.0,.5),(2.35,.41)],backmat);head.location.y=y*MM;top_retainer=head
    else:head=cyl('Case_Screw',(0,y,-4.66),.86,.22,silver)
    boolean(head,cube('Fastener slot',(0,y,-4.79),(1.25,.19,.14),dark,.02,False))

# Fine linked-chain visual; practical wearable hardware needs a tested breakaway.
cords=[]
for side,name in [(-1,'Chain_Left'),(1,'Chain_Right')]:
    links=[]
    for i in range(23):
        y=27.2+i*1.94;x=side*(2.7+i*1.01)
        bpy.ops.mesh.primitive_torus_add(major_radius=.78*MM,minor_radius=.23*MM,major_segments=32,minor_segments=10,location=(x*MM,y*MM,-2.4*MM))
        link=bpy.context.object;link.scale.y=1.55
        link.rotation_euler=(0,math.radians(52 if i%2 else -52),-side*math.atan(1.01/1.94))
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);links.append(link)
    bpy.ops.object.select_all(action='DESELECT')
    for link in links:link.select_set(True)
    bpy.context.view_layer.objects.active=links[0];bpy.ops.object.join();chain=bpy.context.object;chain.name=name
    finish(chain,chainmat);cords.append(chain)

for ob in product:
    if ob.type=='MESH' and ob not in cords:
        for poly in ob.data.polygons:
            if abs(poly.normal.z)>.995:poly.use_smooth=False

# Product metadata helps downstream Three.js interaction.
sys.path.insert(0,str(ROOT))
from surface_normals import refine_capsule_normals
refine_capsule_normals(front,rear)
for o in product:
    o['part']=o.name
    o['design_status']='prototype concept; physical validation required'
    o['design_revision']='A03 / 10.0mm / 150mAh target'
    if o.name.startswith(('Housing_','Record_Button','Privacy_Slider')):o['color_customizable']=True

# Only actual shells export as separate, closed STL meshes (millimetres).
def select_only(objects):
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objects:ob.hide_set(False);ob.select_set(True)
    if objects:bpy.context.view_layer.objects.active=objects[0]

def export_glb(filename):
    target=ROOT/filename
    pending=ROOT/('.'+target.stem+'.writing.glb')
    bpy.ops.export_scene.gltf(filepath=str(pending),export_format='GLB',use_selection=True,export_extras=True,export_apply=True)
    os.replace(pending,target)

def exploded_layout():
    poses={ob.name:(ob.location.copy(),ob.hide_render) for ob in product}
    front_parts=('Housing_Front','Paddle_Return','AcousticMesh','LED_Lightpipe','Button_Seal','Record_Button','Record_Plunger','Button_Tactile_Mark','Front_Wordmark','Privacy_')
    rear_parts=('Housing_Back','Charging_','Rear_','Case_Screw','Top_Polymer_Retainer','Battery_Locator')
    for ob in product:
        if ob.name.startswith(front_parts):ob.location.z+=20*MM
        elif ob.name.startswith(rear_parts):ob.location.z-=22*MM
        elif ob.name.startswith(('Battery_Envelope','Battery_Insulator','Battery_Label')):ob.location.z-=12*MM
        elif ob in cords or ob.name.startswith('Acoustic_Gasket'):ob.hide_render=True
    return poses

def restore_layout(poses):
    for ob in product:ob.location,ob.hide_render=poses[ob.name]

# Real fabrication meshes live in a hidden collection, separate from beauty parts.
fab_collection=bpy.data.collections.new('FABRICATION / printable parts')
scene.collection.children.link(fab_collection)
def fabrication_copy(source,name):
    ob=source.copy();ob.data=source.data.copy();ob.name=name;bpy.context.collection.objects.link(ob)
    return ob
def register_fabrication(ob):
    for coll in list(ob.users_collection):coll.objects.unlink(ob)
    fab_collection.objects.link(ob);ob.hide_render=True
    return ob

print_button=fabrication_copy(button,'Fabrication_Button')
boolean(print_button,fabrication_copy(plunger,'Integral plunger cutter'),'UNION')
print_button.data.transform(print_button.matrix_world);print_button.matrix_world=Matrix.Identity(4)
for v in print_button.data.vertices:v.co=(v.co.x,-v.co.y,4.95*MM-v.co.z)
register_fabrication(print_button)

print_retainer=fabrication_copy(top_retainer,'Fabrication_Top_Retainer')
print_retainer.data.transform(print_retainer.matrix_world);print_retainer.matrix_world=Matrix.Identity(4)
for v in print_retainer.data.vertices:v.co.y-=22.5*MM;v.co.z+=4.77*MM
register_fabrication(print_retainer)

print_carrier=fabrication_copy(carrier,'Fabrication_Contact_Carrier')
print_carrier.data.transform(print_carrier.matrix_world);print_carrier.matrix_world=Matrix.Identity(4)
for v in print_carrier.data.vertices:v.co.y+=19*MM;v.co.z+=4.92*MM
register_fabrication(print_carrier)

print_privacy=fabrication_copy(privacy,'Fabrication_Privacy_Slider')
print_privacy.data.transform(print_privacy.matrix_world);print_privacy.matrix_world=Matrix.Identity(4)
for v in print_privacy.data.vertices:v.co=(v.co.y-.4*MM,v.co.z-1.4*MM,v.co.x-13.72*MM)
register_fabrication(print_privacy)

coupon=cube('Fabrication_Fit_Coupon',(0,0,1),(40,24,2),backmat,.25,False)
for x,d in zip([-15,-7.5,0,7.5,15],[.90,.96,1.02,1.36,2.04]):boolean(coupon,cyl('Fastener fit bore',(x,7,1),d/2,4,dark,register=False))
for x,d in zip([-11,0,11],[1.4,1.6,1.8]):boolean(coupon,cube('Slider fit slot',(x,-5,1),(7,d,4),dark,.2,False))
boolean(coupon,cube('Coupon orientation notch',(-20,-12,1),(3,3,4),dark,0,False))
register_fabrication(coupon)

dock=loft('Fabrication_Dock_Alignment_Jig',[(0,38,58,17.98),(5.5,38,58,17.98)],backmat,False)
boolean(dock,loft('Dock device pocket',[(2.2,28.5,48.5,14.23),(8,28.5,48.5,14.23)],dark,False))
for x in [-3,0,3]:boolean(dock,cyl('Dock contact guide',(x,-19,2),.70,8,dark,register=False))
boolean(dock,cube('Dock cable channel',(0,-24,.6),(4.2,12,1.2),dark,.20,False))
boolean(dock,cube('Dock bail relief',(0,26.2,4),(8,8.5,4),dark,.8,False))
register_fabrication(dock)

print_parts=[(front,'aura-front-shell.stl'),(rear,'aura-rear-shell.stl'),(print_button,'aura-record-face.stl'),(print_retainer,'aura-top-retainer.stl'),(print_carrier,'aura-contact-carrier.stl'),(print_privacy,'aura-privacy-slider.stl'),(coupon,'aura-fit-coupon.stl'),(dock,'aura-dock-alignment-jig.stl')]
for ob,filename in print_parts:
    previous_render_visibility=ob.hide_render
    ob.hide_render=False
    select_only([ob])
    bpy.context.view_layer.update()
    pending=ROOT/('.'+Path(filename).stem+'.writing.stl')
    bpy.ops.wm.stl_export(filepath=str(pending),export_selected_objects=True,global_scale=1000,apply_modifiers=True)
    os.replace(pending,ROOT/filename)
    with (ROOT/filename).open('rb') as stream:
        stream.seek(80);triangle_count=int.from_bytes(stream.read(4),'little')
    assert triangle_count>0,f'Empty STL export: {filename}'
    ob.hide_render=previous_render_visibility
    if ob not in product:ob.hide_set(True)

select_only(product)
export_glb('aura-pendant.glb')
select_only([o for o in product if o not in cords])
export_glb('aura-device.glb')
# Always refresh all3GLBs, even when only a rear render or CAD export is requested.
poses=exploded_layout()
select_only([ob for ob in product if ob not in cords and not ob.name.startswith('Acoustic_Gasket')])
export_glb('aura-exploded.glb')
restore_layout(poses)

# Manifold audit is geometric only, not a manufacturing approval.
import bmesh
audit={}
for ob in [front,rear,button,print_button,print_retainer,print_carrier,print_privacy,coupon,dock]:
    bm=bmesh.new();bm.from_mesh(ob.data)
    audit[ob.name]={'vertices':len(bm.verts),'faces':len(bm.faces),'non_manifold_edges':sum(not e.is_manifold for e in bm.edges),'signed_volume_mm3':round(bm.calc_volume()*1e9,2),'dimensions_mm':[round(v*1000,3) for v in ob.dimensions]}
    bm.free()
(ROOT/'mesh-audit.json').write_text(json.dumps(audit,indent=2))
print('MESH_AUDIT',json.dumps(audit),flush=True)
(ROOT/'design-contract.json').write_text(json.dumps({
    'revision':'A03','status':'prototype CAD; no physical qualification',
    'body_mm':{'width':28,'height':48,'depth':10},'overall_case_height_mm':54,
    'pcb_mm':{'width':24,'height':42,'corner_radius':10,'thickness':.8,'top_z':.65,'underside_z':-.15},
    'cell_target':{'capacity_mah':150,'envelope_width_mm':20.5,'envelope_height_mm':28,'envelope_depth_mm':3.3,'center_y_mm':-3,'top_z_mm':-.45,'bottom_z_mm':-3.75,'qualified':False},
    'face_paddle':{'width_mm':23.2,'height_mm':43.2,'skin_mm':.9,'travel_mm':.35,'underside_z_rest_mm':4.05,'underside_z_pressed_mm':3.70,'radial_gap_mm':.2,'plunger_rest_gap_mm':.02,'switch':'KMR211NGULCLFS'},
    'rear_inner_floor_z_mm':-4,'seam_gap_mm':.11,'bail_hole_diameter_mm':3.4,
    'charging_contacts_xy_mm':[[-3,-19],[0,-19],[3,-19]],'charging_contact_diameter_mm':1.7,
    'antenna_exclusion_y_min_mm':11.95,'top_retainer_material':'nonconductive polymer',
    'haptic_max_envelope_mm':[8.1,8.1,2.75],'haptic_insulator_mm':.05,
},indent=2))

# Studio with broad strip lights; high dynamic range physically lit materials.
world=bpy.data.worlds.new('AURA studio');scene.world=world;world.use_nodes=True
world.node_tree.nodes.get('Background').inputs['Color'].default_value=(.18,.22,.24,1)
world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.40

def area(name,xyz,power,size,color,target=(0,0,0),shape='DISK',size_y=None):
    data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape=shape;data.size=size*MM;data.color=color
    if size_y and shape=='RECTANGLE':data.size_y=size_y*MM
    ob=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(ob);ob.location=[v*MM for v in xyz]
    direction=Vector([v*MM for v in target])-ob.location;ob.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
    return ob
area('Key / softbox',(-72,8,90),.033,32,(1.0,.93,.84),shape='RECTANGLE',size_y=110)
area('Rim / cold strip',(70,35,25),.043,18,(.64,.79,1.0),shape='RECTANGLE',size_y=95)
area('Fill / front',(10,-65,80),.020,65,(.83,.95,1.0))
area('Crown / edge',(-5,65,-10),.026,55,(1.0,.75,.47),target=(0,10,0),shape='RECTANGLE',size_y=18)
rear_fill=area('Rear / inspection softbox',(-35,20,-95),.085,80,(1.0,.92,.80))
rear_fill.hide_render=True

camdata=bpy.data.cameras.new('Product_Camera');cam=bpy.data.objects.new('Product_Camera',camdata);bpy.context.collection.objects.link(cam);scene.camera=cam
camdata.type='ORTHO';camdata.lens=70;camdata.clip_start=.001;camdata.clip_end=10
def camera(xyz,target,scale):
    cam.location=[v*MM for v in xyz]; direction=Vector([v*MM for v in target])-cam.location
    cam.rotation_euler=direction.to_track_quat('-Z','Y').to_euler();camdata.ortho_scale=scale*MM

def render(name,xyz,target,scale,width=2000,height=2000,transparent=True):
    camera(xyz,target,scale);scene.render.resolution_x=width;scene.render.resolution_y=height;scene.render.film_transparent=transparent
    scene.render.filepath=str(RENDERS/name);bpy.ops.render.render(write_still=True)
    print('RENDER_READY',scene.render.filepath,flush=True)

# Save editable assembled scene with camera before long-running rendering.
camera((52,-24,130),(0,12,0),86)
select_only([front]);bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'aura-product.blend'),compress=True)

if '--no-render' not in sys.argv:
    if '--rear-only' in sys.argv:
        scene.cycles.samples=32
        rear_fill.hide_render=False
        render('rear.png',(-58,28,-115),(0,5,-1),72,2000,2000,True)
        sys.exit(0)
    if '--preview' in sys.argv:
        scene.cycles.samples=20
        render('preview.png',(52,-24,130),(0,12,0),86,1000,1000)
        sys.exit(0)
    if '--remaining' not in sys.argv:
        if '--finish-renders' not in sys.argv:
            render('hero-transparent.png',(52,-24,130),(0,12,0),86)
            render('detail.png',(105,-15,70),(3,0,1.2),42,2000,1600,True)
            for ob in cords:ob.hide_render=True
            render('profile.png',(120,-20,24),(0,0,0),68,2200,1800,True)
            for ob in cords:ob.hide_render=False
        floor=cube('Studio_Backdrop',(0,0,-6.7),(600,600,.5),floor_mat,0,False)
        render('hero.png',(52,-24,130),(0,12,0),99,2400,1800,False)
        floor.hide_render=True
    else:
        scene.cycles.samples=32
        floor=cube('Studio_Backdrop',(0,0,-6.7),(600,600,.5),floor_mat,0,False)
        floor.hide_render=True
    rear_fill.hide_render=False
    render('rear.png',(-58,28,-115),(0,5,-1),72,2000,2000,True)
    rear_fill.hide_render=True
    # Explode front up and battery/back down along the physical assembly axis.
    poses=exploded_layout()
    render('exploded.png',(80,-58,115),(0,0,0),103,2200,1800,True)
    restore_layout(poses)
    floor.hide_render=True
    camera((52,-24,130),(0,12,0),86)
    scene.render.resolution_x=2000;scene.render.resolution_y=2000;scene.render.film_transparent=True
    select_only([front]);bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'aura-product.blend'),compress=True)

print('AURA_ASSETS_COMPLETE',flush=True)
