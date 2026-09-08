"""Render actual M1 candidate solids as an exploded inspection, not an assembly guide."""
import hashlib,json
from pathlib import Path
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'thin-cell'
source=OUT/'aura-a04-mechanism.blend'
manifest=json.loads((OUT/'parts-manifest.json').read_text())
assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['blendSha256']
bpy.ops.wm.open_mainfile(filepath=str(source))
scene=bpy.context.scene
names={p['object'] for p in manifest['parts']}
for o in list(scene.objects):
    if o.name not in names:o.hide_render=True
offsets={
 '01_FRONT_HOUSING_WITH_BAIL':(0,0,2),
 '02_CAPTIVE_FACE_PADDLE':(0,0,30),
 '03_FACE_RETAINER':(0,0,17),
 '04_FIXED_DIFFUSER_RING':(0,0,38),
 '05_MOVING_STATUS_LIGHTPIPE':(26,0,29),
 '06_PLUNGER_SIZING_INSERT':(-22,-2,24),
 '07_REAR_COVER_AND_SLIDER_KEEPER':(0,0,-32),
 '08_CUS22_PRIVACY_FORK':(13,0,-7),
 '09_ACOUSTIC_DUCT_LEFT':(-11,-2,-22),
 '09_ACOUSTIC_DUCT_RIGHT':(11,-2,-22),
 '10_DOCK_CONTACT_ACCESS_CARRIER':(0,-10,-25),
 '11_RIGHT_LOWER_SENSOR_CARRIER':(13,0,-23),
 '90_UNPOWERED_NOTCHED_BOARD_GAUGE':(-22,0,-8),
 '91_UNPOWERED_MAX_PACK_GAUGE':(0,0,-20),
}
assert set(offsets)==names
for n,offset in offsets.items():bpy.data.objects[n].location+=Vector(offset)

def material(name,color):
    m=bpy.data.materials.new(name);m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Roughness'].default_value=.7
    return m

# Distinct inspection colours override inherited CSG material slots for legibility.
# They describe no selected physical finish and do not change mesh geometry.
for name in names:
    color=(.08,.10,.11)
    if name.startswith('01_'):color=(.32,.26,.17)
    elif name.startswith('02_'):color=(.65,.64,.60)
    elif name.startswith(('04_','05_')):color=(.36,.48,.46)
    elif name.startswith('90_'):color=(.03,.23,.13)
    elif name.startswith('91_'):color=(.40,.21,.065)
    ob=bpy.data.objects[name];ob.data.materials.clear()
    ob.data.materials.append(material('Inspection '+name,color))

floor_mat=material('Inspection background',(.70,.70,.67))
bpy.ops.mesh.primitive_plane_add(size=1000,location=(0,0,-37))
floor=bpy.context.object;floor.name='INSPECTION_FLOOR';floor.data.materials.append(floor_mat)
world=bpy.data.worlds.new('Inspection world');world.use_nodes=True
world.node_tree.nodes['Background'].inputs['Color'].default_value=(.7,.75,.8,1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value=.6
scene.world=world
def area(name,pos,power,size):
    d=bpy.data.lights.new(name,'AREA');d.energy=power;d.shape='DISK';d.size=size
    o=bpy.data.objects.new(name,d);scene.collection.objects.link(o);o.location=pos
    o.rotation_euler=(Vector((0,0,6))-o.location).to_track_quat('-Z','Y').to_euler()
area('Large key',(-65,-70,110),150000,90)
area('Broad fill',(95,-15,75),80000,80)
area('Upper rim',(-10,80,105),120000,70)
cam_data=bpy.data.cameras.new('Inspection camera');cam=bpy.data.objects.new('Inspection camera',cam_data)
scene.collection.objects.link(cam);cam.location=(85,-115,88)
cam.rotation_euler=(Vector((0,0,9))-cam.location).to_track_quat('-Z','Y').to_euler()
cam_data.type='ORTHO';cam_data.ortho_scale=135;cam_data.clip_end=2000
scene.camera=cam

ink=material('Caption ink',(.045,.05,.05))
def caption(name,body,x,y,size):
    data=bpy.data.curves.new(name,'FONT');data.body=body;data.size=size
    data.align_y='TOP';data.space_character=1.08
    ob=bpy.data.objects.new(name,data);scene.collection.objects.link(ob)
    ob.parent=cam;ob.location=(x,y,-50);ob.data.materials.append(ink)
caption('Title','AURA / A04 M1',-61,62,3.7)
caption('Subtitle','UNQUALIFIED MECHANISM STUDY',-61,56,1.8)
caption('Footer','41 mm body / 10.8 mm depth / 1.6 mm PCB',-61,-55,1.8)
caption('Caveat','12 candidate parts + 2 unpowered gauges\nExploded offsets are illustrative. Assembly path remains unresolved.',-61,-59,1.45)
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=24
scene.cycles.use_denoising=False;scene.render.threads_mode='FIXED';scene.render.threads=2
scene.render.resolution_x=1400;scene.render.resolution_y=1400;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
scene.render.image_settings.compression=70
scene.view_settings.view_transform='AgX';scene.render.filepath='//mechanism-exploded.png'
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'mechanism-inspection.blend'),compress=True)
bpy.ops.render.render(write_still=True)
evidence={'status':'EXPERIMENTAL SOLIDS; NOT A PROVEN INSERTION OR ASSEMBLY SEQUENCE','source':'thin-cell/aura-a04-mechanism.blend','sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'rendererSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'image':'thin-cell/mechanism-exploded.png','imageSha256':hashlib.sha256((OUT/'mechanism-exploded.png').read_bytes()).hexdigest(),'displayedPrintedSolids':len(names),'purchasedProxiesHidden':True,'physicalQualification':False,'offsetsMm':offsets}
(ROOT/'inspection-render.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
print('M1_INSPECTION_RENDER_COMPLETE',flush=True)
