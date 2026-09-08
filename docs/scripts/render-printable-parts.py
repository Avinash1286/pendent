"""Render the eight actual final A03 STL meshes for the repository overview.

blender --background --threads 4 --python docs/scripts/render-printable-parts.py
Only docs/assets/printable-parts.png is written. Uniform display scales differ
between tiles; source STL vertices, triangles and files are never modified.
"""
from pathlib import Path
import hashlib
import json
import math
import struct
import bpy
from mathutils import Euler, Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/assets/printable-parts.png'
PARTS = [
    ('aura-front-shell.stl', 'Front frame', 'Cosmetic rim + face opening', (25, -17, -12)),
    ('aura-rear-shell.stl', 'Rear cup', 'Internal clips + necklace bail', (25, -16, -12)),
    ('aura-record-face.stl', 'Record face', 'Inner face + stem + retaining tabs', (27, -19, -12)),
    ('aura-privacy-slider.stl', 'Privacy slider', 'External control surface', (37, -18, -12)),
    ('aura-top-retainer.stl', 'Top retainer', 'Polymer retaining pin', (69, -9, -24)),
    ('aura-contact-carrier.stl', 'Contact carrier', 'Insulating contact guide', (30, -16, -12)),
    ('aura-fit-coupon.stl', 'Fit coupon', 'Measure bores + slots after cure', (27, -17, -10)),
    ('aura-dock-alignment-jig.stl', 'Passive dock jig', 'Alignment pocket + contact guides', (27, -16, -12)),
]
reference = json.loads((ROOT/'enclosure/print-invariance.json').read_text())['current']
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 48
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 5
scene.render.resolution_x = 1920
scene.render.resolution_y = 1200
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.render.image_settings.color_depth = '8'
scene.render.image_settings.compression = 100
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Medium High Contrast'
scene.world = bpy.data.worlds.new('Soft studio')
scene.world.use_nodes = True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (.82, .85, .9, 1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = .38


def material(name, color, roughness=.4, metallic=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Roughness'].default_value = roughness
    shader.inputs['Metallic'].default_value = metallic
    return mat


resin = material('Warm grey prototype resin', (.22, .245, .255), .31, .12)
paper = material('Warm white background', (.86, .85, .82), .9)


def ink(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (*color, 1)
    emission.inputs['Strength'].default_value = 1
    mat.node_tree.links.new(emission.outputs[0], output.inputs['Surface'])
    return mat


dark = ink('Graphite typography', (.033, .039, .041))
muted = ink('Secondary typography', (.055, .065, .07))
accent = ink('Quiet apricot numbering', (.21, .095, .04))
regular_path = Path('C:/Windows/Fonts/segoeui.ttf')
bold_path = Path('C:/Windows/Fonts/segoeuib.ttf')
regular = bpy.data.fonts.load(str(regular_path)) if regular_path.exists() else None
bold = bpy.data.fonts.load(str(bold_path)) if bold_path.exists() else regular


def text(body, x, y, size, mat=dark, strong=False):
    curve = bpy.data.curves.new(body, 'FONT')
    curve.body = body
    curve.size = size
    curve.space_character = 1.05
    font = bold if strong else regular
    if font:
        curve.font = font
    ob = bpy.data.objects.new(body, curve)
    scene.collection.objects.link(ob)
    ob.location = (x, y, 5)
    ob.data.materials.append(mat)


def load_exact_stl(filename):
    raw = (ROOT/'enclosure'/filename).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == reference[filename]['sha256']
    count = struct.unpack_from('<I', raw, 80)[0]
    assert len(raw) == 84 + count * 50
    vertices, faces, lookup = [], [], {}
    for i in range(count):
        values = struct.unpack_from('<9f', raw, 84 + i*50 + 12)
        face = []
        for j in range(3):
            position = tuple(values[j*3:j*3+3])
            if position not in lookup:
                lookup[position] = len(vertices)
                vertices.append(position)
            face.append(lookup[position])
        faces.append(face)
    mesh = bpy.data.meshes.new(filename)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    assert len(mesh.polygons) == count
    # Smooth only shading normals on shallow-angle edges; no geometry modifiers.
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    mesh.set_sharp_from_angle(angle=math.radians(28))
    ob = bpy.data.objects.new(filename, mesh)
    scene.collection.objects.link(ob)
    ob.data.materials.append(resin)
    return ob, vertices, count


counts = {}
for index, (filename, label, detail, angles) in enumerate(PARTS):
    ob, vertices, count = load_exact_stl(filename)
    counts[filename] = count
    centre = Vector([(min(v[i] for v in vertices)+max(v[i] for v in vertices))/2 for i in range(3)])
    rotation = Euler(tuple(math.radians(a) for a in angles), 'XYZ').to_matrix().to_4x4()
    rotated = [rotation.to_3x3() @ (Vector(v)-centre) for v in vertices]
    low = Vector([min(v[i] for v in rotated) for i in range(3)])
    high = Vector([max(v[i] for v in rotated) for i in range(3)])
    scale = min(4.65/(high.x-low.x), 3.9/(high.y-low.y))
    x = -9 + (index % 4)*6
    y = 3.05 if index < 4 else -2.7
    offset = Vector((x-(low.x+high.x)*scale/2, y-(low.y+high.y)*scale/2, .10-low.z*scale))
    ob.matrix_world = Matrix.Translation(offset) @ rotation @ Matrix.Scale(scale, 4) @ Matrix.Translation(-centre)
    label_y = .52 if index < 4 else -5.13
    text(f'{index+1:02}', x-2.55, label_y, .23, accent, True)
    text(label, x-2.02, label_y-.025, .36, dark, True)
    text(detail, x-2.55, label_y-.47, .24, muted)

text('AURA / PRINTABLE PARTS', -11.55, 6.40, .54, dark, True)
text('Eight actual STL meshes. Ready for a measured fit prototype.', -11.53, 5.84, .27, muted)
text('A03', 10.65, 6.46, .30, accent, True)
text('NOT TO SCALE  /  Views enlarged individually for clarity', -11.53, -6.65, .245, muted)
text('Geometry audited. Physical fit and material qualification remain open.', -11.53, -7.00, .245, muted)
bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -.02))
bpy.context.object.name = 'Seamless studio background'
bpy.context.object.data.materials.append(paper)


def light(name, xyz, power, size):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = power
    data.shape = 'DISK'
    data.size = size
    ob = bpy.data.objects.new(name, data)
    scene.collection.objects.link(ob)
    ob.location = xyz
    ob.rotation_euler = (Vector((0, 0, 0))-ob.location).to_track_quat('-Z', 'Y').to_euler()


light('Large soft key', (-7, 8, 15), 3000, 11)
light('Right fill', (10, 1, 12), 1600, 9)
light('Soft lower fill', (-3, -8, 11), 800, 8)
camera_data = bpy.data.cameras.new('Overview orthographic camera')
camera = bpy.data.objects.new('Overview orthographic camera', camera_data)
scene.collection.objects.link(camera)
camera.location = (0, 0, 40)
camera.rotation_euler = (0, 0, 0)
camera_data.type = 'ORTHO'
camera_data.ortho_scale = 24
scene.camera = camera
OUT.parent.mkdir(parents=True, exist_ok=True)
scene.render.filepath = str(OUT)
bpy.ops.render.render(write_still=True)
for filename in counts:
    assert hashlib.sha256((ROOT/'enclosure'/filename).read_bytes()).hexdigest() == reference[filename]['sha256']
print(json.dumps({'output': 'docs/assets/printable-parts.png', 'parts': 8, 'source_triangles': counts,
                  'source_files_unchanged': True, 'display_scale': 'Not to scale; uniform per-part framing'}, indent=2), flush=True)
