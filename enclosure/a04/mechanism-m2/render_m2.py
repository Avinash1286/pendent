"""Render actual M2 source solids; review must be recorded separately against actual PNG hashes."""
import argparse,hashlib,json,sys
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'documented-pack';source=OUT/'aura-a04-m2.blend';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();m=json.loads((OUT/'parts-manifest.json').read_text());assert sha(source)==m['blendSha256']
p=argparse.ArgumentParser();p.add_argument('--view',choices=['assembled','exploded'],default='exploded');a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []);bpy.ops.wm.open_mainfile(filepath=str(source));sc=bpy.context.scene
names={p['object'] for p in m['parts']}
for o in sc.objects:
 if o.name not in names:o.hide_render=True
colors={}
def mat(n,col):
 m=bpy.data.materials.new(n);m.use_nodes=True;p=m.node_tree.nodes['Principled BSDF'];p.inputs['Base Color'].default_value=(*col,1);p.inputs['Roughness'].default_value=.42;return m
for n in names:
 col=(.14,.16,.16)
 if n.startswith(('01_','02_')):col=(.64,.49,.30)
 if n.startswith('04_'):col=(.87,.85,.78)
 if n.startswith(('05_','06_')):col=(.65,.87,.81)
 if n.startswith('90_'):col=(.025,.25,.15)
 if n.startswith('91_'):col=(.42,.25,.09)
 o=bpy.data.objects[n];o.data.materials.clear();o.data.materials.append(mat('Inspection '+n,col))
 if n.startswith('06_') and a.view=='assembled':
  p=o.data.materials[0].node_tree.nodes['Principled BSDF'];p.inputs['Emission Color'].default_value=(.55,.8,.65,1);p.inputs['Emission Strength'].default_value=.3
if a.view=='exploded':
 offsets={'01_FIXED_CUP':(0,0,0),'02_THREADED_BEZEL':(0,0,40),'03_PCB_CLAMP_AND_FACE_GUIDE':(0,0,24),'04_CAPTIVE_FACE':(0,0,32),'05_FLUSH_STATUS_WINDOW':(28,0,36),'06_FIXED_DIFFUSER':(0,0,46),'07_CARTRIDGE_KEEPER':(-28,-5,28),'08_MEASURED_PLUNGER_SHOE':(-28,-5,35),'09_PRIVACY_FORK':(13,0,2),'10_PRIVACY_KEEPER':(25,0,9),'11_CONTACT_ACCESS_CARRIER':(-25,-10,3),'12_SENSOR_RETAINER':(24,-14,3),'90_UNPOWERED_BOARD_GAUGE':(0,0,15),'91_UNPOWERED_PACK_GAUGE':(0,0,7)}
 assert set(offsets)==names
 for n,v in offsets.items():bpy.data.objects[n].location+=Vector(v)
 target=(0,0,26);scale=130;campos=(90,-145,119);floorz=-3
else:
 offsets={};target=(0,0,5);scale=67;campos=(64,-90,101);floorz=-.2
 for n in names:
  if n.startswith(('90_','91_')):bpy.data.objects[n].hide_render=True
bpy.ops.mesh.primitive_plane_add(size=1000,location=(0,0,floorz));bpy.context.object.data.materials.append(mat('Warm studio',(.68,.68,.64)))
w=bpy.data.worlds.new('M2 studio');w.use_nodes=True;w.node_tree.nodes['Background'].inputs['Color'].default_value=(.7,.75,.8,1);w.node_tree.nodes['Background'].inputs['Strength'].default_value=.6;sc.world=w
for n,pos,power,size in [('Key',(-65,-80,130),180000,100),('Fill',(95,-15,100),90000,90),('Rim',(-10,80,130),150000,90)]:
 d=bpy.data.lights.new(n,'AREA');d.energy=power;d.shape='DISK';d.size=size;o=bpy.data.objects.new(n,d);sc.collection.objects.link(o);o.location=pos;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
d=bpy.data.cameras.new('Inspection camera');cam=bpy.data.objects.new('Inspection camera',d);sc.collection.objects.link(cam);cam.location=campos;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();d.type='ORTHO';d.ortho_scale=scale;d.clip_end=2000;sc.camera=cam
ink=mat('Ink',(.035,.045,.05))
def caption(n,txt,x,y,size):
 d=bpy.data.curves.new(n,'FONT');d.body=txt;d.size=size;d.align_y='TOP';o=bpy.data.objects.new(n,d);sc.collection.objects.link(o);o.parent=cam;o.location=(x,y,-50);o.data.materials.append(ink)
caption('Title','AURA / A04 M2',-scale*.44,scale*.45,scale*.03)
caption('State','DEVELOPMENT CANDIDATE / UNQUALIFIED',-scale*.44,scale*.405,scale*.012)
caption('Dimensions','43 mm body / 12.2 mm depth / 1.6 mm PCB',-scale*.44,-scale*.405,scale*.014)
caption('Limit','4.3 mm pack allocation; supplier pack unapproved.\n'+('12 proposed parts + 2 unpowered gauges. Offsets illustrate parts, not assembly motion.' if a.view=='exploded' else 'Polymer champagne finish and light emission are visual intent; no powered fit release.'),-scale*.44,-scale*.433,scale*.01)
sc.render.engine='CYCLES';sc.cycles.samples=32;sc.cycles.use_denoising=False;sc.render.threads_mode='FIXED';sc.render.threads=2;sc.render.resolution_x=1400;sc.render.resolution_y=1400;sc.render.resolution_percentage=100;sc.render.image_settings.file_format='PNG';sc.render.image_settings.color_mode='RGB';sc.view_settings.view_transform='AgX';sc.render.filepath='//m2-'+a.view+'.png';bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/('m2-'+a.view+'-inspection.blend')),compress=True);bpy.ops.render.render(write_still=True)
r={'view':a.view,'sourceSha256':sha(source),'rendererSha256':sha(Path(__file__)),'image':'documented-pack/m2-'+a.view+'.png','imageSha256':sha(OUT/('m2-'+a.view+'.png')),'inspectionBlendSha256':sha(OUT/('m2-'+a.view+'-inspection.blend')),'bodyDiameterMm':43,'bodyDepthMm':12.2,'physicalQualification':False,'visuallyInspected':False,'visualReviewPolicy':'Only a separate human/model review of this exact PNG may set its hash-bound review record; rendering never self-certifies inspection.','offsetsMm':offsets}
(ROOT/('render-'+a.view+'.json')).write_text(json.dumps(r,indent=2)+'\n');print('M2_RENDERED',a.view,flush=True)
