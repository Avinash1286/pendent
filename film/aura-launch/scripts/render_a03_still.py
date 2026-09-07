"""Render a film plate from the saved A03 Blender scene without rebuilding geometry.

Usage:
  blender --background ../../enclosure/aura-product.blend --python scripts/render_a03_still.py -- detail
  blender --background ../../enclosure/aura-product.blend --python scripts/render_a03_still.py -- profile

Run each view in its own process. Camera poses match enclosure/build_aura.py.
"""
import bpy
import hashlib
import json
import sys
from pathlib import Path
from mathutils import Vector

project = Path(__file__).resolve().parents[1]
args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
view = args[0] if args else ''
poses = {
    'detail': ((105, -15, 70), (3, 0, 1.2), 42, 2000, 1600),
    'profile': ((120, -20, 24), (0, 0, 0), 68, 2200, 1800),
}
if view not in poses:
    raise SystemExit('Choose detail or profile.')

scene = bpy.context.scene
camera = scene.camera
if camera is None or camera.name != 'Product_Camera':
    raise RuntimeError('Expected the saved A03 Product_Camera.')
scene_path = Path(bpy.data.filepath)
source_hash = hashlib.sha256(scene_path.read_bytes()).hexdigest()
xyz, target, scale, width, height = poses[view]
camera.location = [v * .001 for v in xyz]
direction = Vector([v * .001 for v in target]) - camera.location
camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
camera.data.type = 'ORTHO'
camera.data.ortho_scale = scale * .001

# The chains are omitted from the profile exactly as in the enclosure renderer.
for name in ('Chain_Left', 'Chain_Right'):
    chain = bpy.data.objects.get(name)
    if chain is None:
        raise RuntimeError(f'Missing A03 chain object: {name}')
    chain.hide_render = view == 'profile'
rear_light = bpy.data.objects.get('Rear / inspection softbox')
if rear_light is not None:
    rear_light.hide_render = True
backdrop = bpy.data.objects.get('Studio_Backdrop')
if backdrop is not None:
    backdrop.hide_render = True

scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 32
scene.cycles.use_denoising = True
scene.render.threads_mode = 'FIXED'
scene.render.threads = 6
scene.render.resolution_x = width
scene.render.resolution_y = height
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.image_settings.color_depth = '8'
output = project / 'assets' / f'{view}.png'
scene.render.filepath = str(output)
print(f'FILM_PLATE_BEGIN {view} {source_hash}', flush=True)
bpy.ops.render.render(write_still=True)
record = {
    'edition': 'A03', 'view': view, 'renderer': bpy.app.version_string,
    'source_scene': str(scene_path), 'source_scene_sha256': source_hash,
    'camera_mm': xyz, 'target_mm': target, 'ortho_scale_mm': scale,
    'size': [width, height], 'samples': 32, 'geometry_rebuilt': False,
    'output': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
}
(project / 'qa' / f'plate-{view}.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(f'FILM_PLATE_READY {output}', flush=True)
