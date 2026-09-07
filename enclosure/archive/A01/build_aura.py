"""AURA wearable enclosure and product visualization. Blender 5.2 / Python.

Run: blender --background --python build_aura.py
Coordinates: X width, Y height, Z depth, front=+Z. Design arguments are mm;
Blender geometry is metres, STL exports are millimetres, glTF is metres.
This is a mechanical prototype concept; see MECHANICAL.md before fabrication.
"""
import bpy, math, json, os, sys
from pathlib import Path
from mathutils import Vector

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
scene.cycles.samples = 48
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

shell=mat('Shell • Moonstone ceramic-effect polymer',(.72,.70,.65),.26,.29)
backmat=mat('Back • warm RF-transparent polymer',(.48,.46,.42),.1,.38)
buttonmat=mat('Button • brushed pale titanium',(.61,.60,.55),.67,.24)
dark=mat('Graphite silicone',(.016,.019,.019),.08,.45)
cordmat=mat('Woven charcoal cord',(.021,.024,.024),0,.68)
gold=mat('Gold plated charging contacts',(.64,.39,.095),.8,.22)
pcbmat=mat('PCB • forest soldermask',(.014,.064,.046),.1,.4)
copper=mat('PCB • immersion gold',(.60,.39,.10),.85,.3)
black=mat('Electronics • ceramic black',(.012,.016,.020),.1,.34)
silver=mat('Electronics • shield',(.40,.44,.46),.78,.32)
batteryfoil=mat('Cell • brushed foil',(.26,.29,.30),.73,.34)
amber=mat('Privacy status • amber',(.98,.35,.045),.15,.32)
ledmat=mat('Recording indicator • warm white',(.80,1.0,.77),.12,.25,2)
labelmat=mat('Laser mark • deep warm gray',(.15,.145,.13),.3,.43)
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

# Two closed, hollow shells. Rearward opening on front, forward opening on back.
front=loft('Housing_Front',[(.18,30,40,8),(3.6,29.9,39.9,8.2),(5.05,29,39,8),(5.8,27.6,37.6,7.7),(6,26.4,36.4,7.3)],shell)
cut=loft('Front cavity cutter',[(-2,27.6,37.6,6.8),(3.7,27.4,37.4,6.9),(4.7,26.4,36.4,6.9)],dark,False)
boolean(front,cut)
rear=loft('Housing_Back',[(-6,28.6,38.6,7.7),(-5.7,29.4,39.4,8),(-4.8,29.85,39.85,8.1),(-3.6,29.9,39.9,8.2),(-.18,30,40,8)],backmat)
cut=loft('Rear cavity cutter',[(-4.8,26.4,36.4,6.9),(-3.7,27.4,37.4,6.9),(2,27.6,37.6,6.8)],dark,False)
boolean(rear,cut)

# Integrated two-post case fasteners, outside PCB envelope. Self-tapping M1.2
# prototype screws into pilot holes; size must be validated for process/material.
for y in [-18.4,18.4]:
    boss=cyl('Front screw boss',(0,y,2.25),1.25,4.14,shell,register=False)
    boolean(front,boss,'UNION')
    pilot=cyl('M1.2 pilot',(0,y,1.6),.48,4.6,dark,register=False)
    boolean(front,pilot)
    boss=cyl('Rear screw boss',(0,y,-2.3),1.25,4.24,backmat,register=False)
    boolean(rear,boss,'UNION')
    bore=cyl('Screw clearance',(0,y,-3.0),.68,7,dark,register=False)
    boolean(rear,bore)
    recess=cyl('Rear screw counterbore',(0,y,-5.65),1.02,1.3,dark,register=False)
    boolean(rear,recess)

# Front record recess, actual acoustic ports, indicator aperture.
boolean(front,cyl('Button aperture',(0,-6,5.9),4.30,4,dark,register=False))
for x in [-8.5,8.5]:
    boolean(front,cyl('Acoustic aperture',(x,8.5,5.7),.46,4,dark,register=False,vertices=40))
    cyl('AcousticMesh_L' if x<0 else 'AcousticMesh_R',(x,8.5,5.63),.38,.07,dark)
boolean(front,cyl('LED aperture',(0,-1,5.9),.42,4,dark,register=False,vertices=40))
# Dedicated coin-LRA recess. Leaves0.9mm local skin, with0.10mm nominal
# clearance over an8x3mm motor on0.05mm insulation; physical validation required.
boolean(front,cyl('LRA ceiling pocket',(6,-12,4.5),4.25,1.2,dark,register=False))
cyl('LED_Lightpipe',(0,-1,5.88),.34,.25,ledmat)
button_gasket=cyl('Button_Seal',(0,-6,5.52),4.23,.45,dark)
button=cyl('Record_Button',(0,-6,5.67),3.96,.59,buttonmat)
bevel(button,.16)
# Button plunger extends from cap rear to switch actuation level.
cyl('Record_Plunger',(0,-6,4.705),.8,1.35,dark)
cyl('Button_Tactile_Mark',(0,-6,5.977),.43,.018,labelmat)

# Accessible physical privacy slider; the amber patch is visible when off.
slider_cut=cube('Privacy actuator clearance',(14.1,0,1.65),(4.2,5.5,2.1),dark,.5,False)
boolean(front,slider_cut)
cube('Privacy_Slider_Track',(14.72,0,1.65),(.50,5.0,1.9),dark,.45)
cube('Privacy_Off_Marker',(15.00,-1.65,1.65),(.05,.8,1.1),amber,.1)
privacy=cube('Privacy_Slider',(15.02,.75,1.65),(.8,2.55,1.55),buttonmat,.42)
for y in [.18,.73,1.28]:cube('Privacy_Grip',(15.437,y,1.65),(.06,.13,.83),dark,.03)

# Black gasket separates shells. Non-certified dust barrier, not a waterproof claim.
gasket=loft('Seam_Gasket',[(-.16,29.88,39.88,8),(.16,29.88,39.88,8)],dark)
boolean(gasket,loft('Gasket void',[(-1,27.2,37.2,6.7),(1,27.2,37.2,6.7)],dark,False))

# Three rear flush contacts align in XY with J1. A thin passive lead/flex
# interposer must route around the battery; no through-cell pogo connection.
pogo_cut=cube('Charging bed opening',(0,-15,-5.65),(10.0,3.1,3),dark,1.2,False)
boolean(rear,pogo_cut)
cube('Charging_Contact_Bed',(0,-15,-5.70),(9.8,2.9,.50),dark,1.15)
for i,x in enumerate([-3,0,3]):cyl(f'Charging_Contact_{i+1}',(x,-15,-5.983),.85,.10,gold)

# Integrated polymer lanyard eyelet connected to the rear shell.
loop=loft('Integrated lanyard eyelet',[(-2.8,8.4,8.8,3),(.10,8.4,8.8,3)],backmat,False)
loop.location.y=21.1*MM
inner=loft('Lanyard pass-through',[(-4,4.4,4.8,1.55),(2,4.4,4.8,1.55)],dark,False);inner.location.y=21.6*MM
boolean(loop,inner)
boolean(rear,loop,'UNION')
bevel(front,.075)

# PCB snap/support rails on rear housing, with 0.25mm underside clearance.
for side in [-1,1]:
    for y in [-6,5]:
        # Wall-connected base remains behind seam; shelf and flexible stem stay
        # fully within the front cavity, so mating shells do not intersect.
        for name,x,z,dims in [
            ('PCB rail root',13.2,-.90,(3.0,4.5,1.45)),
            ('PCB support shelf',12.2,.475,(1.0,4.5,1.35)),
            ('PCB clip stem',12.75,1.10,(.9,1.8,2.4)),
            ('PCB clip lip',12.55,2.25,(1.4,1.8,.30)),
        ]:
            support=cube(name,(side*x,y,z),dims,backmat,.035,False)
            boolean(rear,support,'UNION')

# Optional silicone battery locator strips; they leave the RF region clear.
for x in [-10.55,10.55]:cube('Battery_Locator',(x,-4,-2.6),(.7,20,3.6),dark,.25)

# Internal reference envelopes are documented visualizations, not a PCB export.
board=loft('PCB_Reference',[(-.4,24,34,4),(.4,24,34,4)],pcbmat)
board.location.z=.95*MM
battery=cube('Battery_Envelope',(0,-4,-2.2),(20,25,5),batteryfoil,.55)
cube('Battery_Insulator',(0,-4,.325),(20,25,.05),dark,.35)
text('Battery_Label','AURA   /   Li-Po\n3.7 V • 250 mAh',(0,-5,.367),1.8,labelmat)
module=cube('RF_Module_Envelope',(0,8,2.4),(10.5,15.5,2.05),silver,.17)
cube('Antenna_Window',(0,13.9,3.452),(10.45,3.55,.09),black,.10)
text('Module_Mark','RAYTAC\nnRF52840',(0,6.6,3.457),1.12,labelmat)
for x in [-5.48,5.48]:
    for y in [2,3.5,5,6.5,8,9.5,11.0]:cube('RF_Castellation',(x,y,1.70),(.28,.6,.38),gold,.04)
for x in [-8.5,8.5]:
    cube('MEMS_Microphone',(x,8.5,2.0),(2.75,1.85,1.3),silver,.10)
    # Wrap-around gasket reference routes through the PCB-edge clearance.
    tube('Acoustic_Gasket_Channel',[(x,8.5,.9),(13.0 if x>0 else -13.0,8.5,.75),(13.0 if x>0 else -13.0,8.5,4.1),(x,8.5,4.25),(x,8.5,5.25)],.42,dark)
cube('Record_Tact_Switch',(0,-6,2.1),(4.8,4.8,1.5),silver,.2)
cyl('Record_Switch_Actuator',(0,-6,3.05),1.5,.4,black)
cube('Flash_Envelope',(-6.5,-5,2.1),(4,5,1.5),black,.18)
cube('Power_Envelope',(7,-4,1.8),(3.1,3.1,.9),black,.14)
cyl('Haptic_Reference',(6,-12,2.90),4.0,3.0,silver)
cyl('Haptic_Insulator',(6,-12,1.375),4.1,.05,dark)
for x,y in [(-7,-11),(-4,-12),(-8,-8),(7,-3),(6,-1),(8,3),(-8,1),(4,-3)]:
    cube('Passive_Reference',(x,y,1.7),(1.3,.75,.55),dark,.08)
    for dx in [-.53,.53]:cube('Passive_Termination',(x+dx,y,1.705),(.24,.75,.57),silver,.04)

# Refined logo. Every graphic is real mesh and exports with glTF.
text('Front_Wordmark','a u r a',(0,3.2,6.035),2.30,labelmat)
text('Rear_Wordmark','A U R A',(0,2,-6.026),2.1,labelmat,(math.pi,0,0))
text('Rear_Prototype_Mark','DESIGN PROTOTYPE\nMODEL A01',(0,-2.8,-6.028),.92,labelmat,(math.pi,0,0))
for y in [-18.4,18.4]:
    # Antenna-adjacent top retention must be nonconductive; geometry is a
    # prototype fastener envelope, not a qualified polymer fastener selection.
    head=cyl('Case_Screw',(0,y,-5.53),.88,.26,backmat if y>0 else buttonmat)
    head['required_material']='nonconductive polymer' if y>0 else 'metal allowed outside antenna region'
    boolean(head,cube('Screw slot',(0,y,-5.69),(1.3,.22,.17),dark,.02,False))

# Refined stack allocates clearance to cell swelling/insulation: PCB underside
# 1.15, PCB top1.95, tallest component4.05, cell−4.4..+.6, front ceiling4.70.
pcb_parts=('PCB_Reference','RF_Module_Envelope','Antenna_Window','Module_Mark','RF_Castellation','MEMS_Microphone','Record_Tact_Switch','Record_Switch_Actuator','Flash_Envelope','Power_Envelope','Haptic_','Passive_')
for ob in product:
    if ob.name.startswith(pcb_parts):ob.location.z+=.60*MM
    elif ob.name.startswith(('Battery_Envelope','Battery_Insulator','Battery_Label','Battery_Locator')):ob.location.z+=.30*MM

# Two physically modelled continuous strands. Cord is separated in the model.
cords=[]
cords.append(tube('Cord_Woven_Left',[(-1.1,21.5,-1.1),(-3.4,25,-1.9),(-9,34,-2.4),(-18,46,-2),( -21,65,-1)],.79,cordmat))
cords.append(tube('Cord_Woven_Right',[(1.1,21.5,-1.1),(3.0,25,-2.0),(9,34,-1.4),(18,49,-.5),(24,65,-1)],.79,cordmat))
# A restrained satin weave shader avoids visually noisy strands at product scale.
cord_nodes=cordmat.node_tree.nodes
noise=cord_nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=9500
bump=cord_nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.22;bump.inputs['Distance'].default_value=.00004
cordmat.node_tree.links.new(noise.outputs['Fac'],bump.inputs['Height'])
cordmat.node_tree.links.new(bump.outputs['Normal'],cord_nodes.get('Principled BSDF').inputs['Normal'])

# Keep planar caps planar: smooth shading on boolean cap tessellation introduces
# fake folds. Side quads retain their soft interpolated pebble highlight.
for ob in product:
    if ob.type=='MESH' and ob not in cords:
        for poly in ob.data.polygons:
            if abs(poly.normal.z)>.995 or len(poly.vertices)>6:poly.use_smooth=False

# Product metadata helps downstream Three.js interaction.
for o in product:
    o['part']=o.name
    o['design_status']='prototype concept; physical validation required'
    if o.name.startswith(('Housing_','Record_Button','Privacy_Slider')):o['color_customizable']=True

# Only actual shells export as separate, closed STL meshes (millimetres).
def select_only(objects):
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objects:ob.hide_set(False);ob.select_set(True)
    if objects:bpy.context.view_layer.objects.active=objects[0]

def exploded_layout():
    poses={ob.name:(ob.location.copy(),ob.hide_render) for ob in product}
    front_parts=('Housing_Front','AcousticMesh','LED_Lightpipe','Button_Seal','Record_Button','Record_Plunger','Button_Tactile_Mark','Front_Wordmark','Privacy_')
    rear_parts=('Housing_Back','Charging_','Rear_','Case_Screw','Battery_Locator')
    for ob in product:
        if ob.name.startswith(front_parts):ob.location.z+=20*MM
        elif ob.name.startswith(rear_parts):ob.location.z-=22*MM
        elif ob.name.startswith(('Battery_Envelope','Battery_Insulator','Battery_Label')):ob.location.z-=12*MM
        elif ob in cords or ob.name.startswith('Acoustic_Gasket'):ob.hide_render=True
    return poses

def restore_layout(poses):
    for ob in product:ob.location,ob.hide_render=poses[ob.name]

select_only([front]);bpy.ops.wm.stl_export(filepath=str(ROOT/'aura-front-shell.stl'),export_selected_objects=True,global_scale=1000,apply_modifiers=True)
select_only([rear]);bpy.ops.wm.stl_export(filepath=str(ROOT/'aura-rear-shell.stl'),export_selected_objects=True,global_scale=1000,apply_modifiers=True)
select_only([button]);bpy.ops.wm.stl_export(filepath=str(ROOT/'aura-record-button.stl'),export_selected_objects=True,global_scale=1000,apply_modifiers=True)

select_only(product)
bpy.ops.export_scene.gltf(filepath=str(ROOT/'aura-pendant.glb'),export_format='GLB',use_selection=True,export_extras=True,export_apply=True)
select_only([o for o in product if o not in cords])
bpy.ops.export_scene.gltf(filepath=str(ROOT/'aura-device.glb'),export_format='GLB',use_selection=True,export_extras=True,export_apply=True)
# Always refresh all3GLBs, even when only a rear render or CAD export is requested.
poses=exploded_layout()
select_only([ob for ob in product if ob not in cords and not ob.name.startswith('Acoustic_Gasket')])
bpy.ops.export_scene.gltf(filepath=str(ROOT/'aura-exploded.glb'),export_format='GLB',use_selection=True,export_extras=True,export_apply=True)
restore_layout(poses)

# Manifold audit is geometric only, not a manufacturing approval.
import bmesh
audit={}
for ob in [front,rear,button]:
    bm=bmesh.new();bm.from_mesh(ob.data)
    audit[ob.name]={'vertices':len(bm.verts),'faces':len(bm.faces),'non_manifold_edges':sum(not e.is_manifold for e in bm.edges),'signed_volume_mm3':round(bm.calc_volume()*1e9,2),'dimensions_mm':[round(v*1000,3) for v in ob.dimensions]}
    bm.free()
(ROOT/'mesh-audit.json').write_text(json.dumps(audit,indent=2))
print('MESH_AUDIT',json.dumps(audit),flush=True)

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
area('Key / softbox',(-60,45,90),.055,80,(1.0,.89,.74),shape='RECTANGLE',size_y=110)
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
camera((62,-45,112),(0,10,0),77)
select_only([front]);bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'aura-product.blend'),compress=True)

if '--no-render' not in sys.argv:
    if '--rear-only' in sys.argv:
        scene.cycles.samples=32
        rear_fill.hide_render=False
        render('rear.png',(-58,28,-115),(0,4,-1),62,2000,2000,True)
        sys.exit(0)
    if '--preview' in sys.argv:
        scene.cycles.samples=20
        render('preview.png',(62,-45,112),(0,10,0),77,1000,1000)
        sys.exit(0)
    if '--remaining' not in sys.argv:
        render('hero-transparent.png',(62,-45,112),(0,10,0),77)
        # Low studio plane catches the device silhouette and restrained reflections.
        floor=cube('Studio_Backdrop',(0,0,-8.4),(600,600,.5),floor_mat,0,False)
        render('hero.png',(62,-45,112),(0,10,0),89,2400,1600,False)
        floor.hide_render=True
        render('detail.png',(95,-28,64),(4,-.5,1.5),39,2000,1600,True)
    else:
        scene.cycles.samples=32
        floor=cube('Studio_Backdrop',(0,0,-8.4),(600,600,.5),floor_mat,0,False)
        floor.hide_render=True
    rear_fill.hide_render=False
    render('rear.png',(-58,28,-115),(0,4,-1),62,2000,2000,True)
    rear_fill.hide_render=True
    # Explode front up and battery/back down along the physical assembly axis.
    poses=exploded_layout()
    render('exploded.png',(80,-58,115),(0,0,0),93,2200,1800,True)
    restore_layout(poses)
    floor.hide_render=True
    camera((62,-45,112),(0,10,0),77)
    scene.render.resolution_x=2000;scene.render.resolution_y=2000;scene.render.film_transparent=True
    select_only([front]);bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'aura-product.blend'),compress=True)

print('AURA_ASSETS_COMPLETE',flush=True)
