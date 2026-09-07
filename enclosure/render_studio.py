"""Refresh the A03 studio hero from the editable scene, without changing CAD."""
from pathlib import Path
import bpy
from mathutils import Vector
root = Path(__file__).resolve().parent
bpy.ops.wm.open_mainfile(filepath=str(root / 'aura-product.blend'))
scene = bpy.context.scene
scene.cycles.samples = 32
cam = scene.camera
cam.location = Vector((.052, -.024, .130))
cam.rotation_euler = (Vector((0, .012, 0)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.ortho_scale = .099
scene.render.resolution_x = 2400
scene.render.resolution_y = 1800
scene.render.resolution_percentage = 100
scene.render.film_transparent = False
bpy.data.objects['Studio_Backdrop'].hide_render = False
bpy.data.objects['Rear / inspection softbox'].hide_render = True
scene.render.filepath = str(root / 'renders' / 'hero.png')
bpy.ops.render.render(write_still=True)
print('A03_STUDIO_READY', flush=True)
