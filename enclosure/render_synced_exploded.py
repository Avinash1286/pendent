"""Refresh only the internal exploded plate from the saved assembled A03 scene.
blender --background aura-product.blend --threads 4 --python render_synced_exploded.py
Does not alter or save source geometry. Camera and separation match build_aura.py.
"""
import bpy,json,hashlib
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parent
scene=bpy.context.scene
assert bpy.data.filepath and Path(bpy.data.filepath).name=='aura-product.blend'
front_parts=('Housing_Front','Paddle_Return','AcousticMesh','LED_Lightpipe','Button_Seal','Record_Button','Record_Plunger','Button_Tactile_Mark','Front_Wordmark','Privacy_')
rear_parts=('Housing_Back','Charging_','Rear_','Case_Screw','Top_Polymer_Retainer','Battery_Locator')
for ob in bpy.data.objects:
    if ob.name.startswith('Fabrication_'):continue
    if ob.name.startswith(front_parts):ob.location.z+=.020
    elif ob.name.startswith(rear_parts):ob.location.z-=.022
    elif ob.name.startswith(('Battery_Envelope','Battery_Insulator','Battery_Label')):ob.location.z-=.012
    elif ob.name.startswith(('Chain_','Acoustic_Gasket')):ob.hide_render=True
for name in ['Rear / inspection softbox','Studio_Backdrop']:
    if bpy.data.objects.get(name):bpy.data.objects[name].hide_render=True
camera=scene.camera
xyz=(80,-58,115);target=(0,0,0)
camera.location=[v*.001 for v in xyz]
camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO';camera.data.ortho_scale=.103
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=32;scene.cycles.use_denoising=True
scene.render.threads_mode='FIXED';scene.render.threads=4
scene.render.resolution_x=2200;scene.render.resolution_y=1800;scene.render.resolution_percentage=100;scene.render.film_transparent=True
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.color_depth='8'
target_path=ROOT/'renders'/'exploded.png';scene.render.filepath=str(target_path)
bpy.ops.render.render(write_still=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report={'revision':'A03','scope':'Internal package position/dimension sync; no source geometry changed by this renderer','scene_sha256':sha(Path(bpy.data.filepath)),'output':'renders/exploded.png','output_sha256':sha(target_path),'camera_mm':xyz,'ortho_scale_mm':103,'size':[2200,1800],'samples':32,'physical_qualification':False}
(ROOT/'exploded-render-provenance.json').write_text(json.dumps(report,indent=2)+'\n')
print('SYNCED_EXPLODED_READY',str(target_path),flush=True)
