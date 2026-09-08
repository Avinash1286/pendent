"""Render the A04 allocation model, clearly labelled as a provisional study."""
import hashlib
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
STUDY = ROOT / "study"
bpy.ops.wm.open_mainfile(filepath=str(STUDY / "aura-a04-packaging.blend"))
report = json.loads((STUDY / "packaging-study.json").read_text())
scene = bpy.context.scene
MM = 0.001

for name, amount in {"Study_Rear_Cup_UNENGINEERED": 0.3, "Study_Frame_UNENGINEERED": 0.22,
                     "Study_Front_Lip_UNENGINEERED": 0.06, "Study_Moving_Face_NO_RETENTION": 0.18,
                     "Study_Bail_NO_LOAD_QUALIFICATION": 0.45, "Study_Status_Dash_NO_LIGHTPIPE": 0.03}.items():
    obj = bpy.data.objects[name]
    bevel = obj.modifiers.new("Provisional cosmetic edge rounding", "BEVEL")
    bevel.width = amount * MM
    bevel.segments = 5
    bevel.limit_method = "ANGLE"
    bevel.harden_normals = True

def mat(name, color, metallic=0, roughness=0.4):
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    shader = result.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    return result

chain_material = mat("Styling chain / accessory unqualified", (0.52, 0.43, 0.31), 0.85, 0.22)
for side in (-1, 1):
    for i in range(21):
        bpy.ops.mesh.primitive_torus_add(major_segments=24, minor_segments=8, major_radius=0.60*MM,
                                       minor_radius=0.17*MM, location=(side*(1.8+i*0.58)*MM, (22+i*1.50)*MM, -1.0*MM))
        link = bpy.context.object
        link.name = f"Styling_Chain_{side}_{i}"
        link.scale.y = 1.42
        link.rotation_euler = (0, math.radians(55 if i%2 else -55), -side*math.atan(0.58/1.50))
        link.data.materials.append(chain_material)
        for poly in link.data.polygons:
            poly.use_smooth = True

background = mat("Warm neutral study background", (0.69, 0.66, 0.60), 0, 0.8)
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, (report["planes_mm"]["back"]-0.7)*MM))
bpy.context.object.name = "Study_Background"
bpy.context.object.data.materials.append(background)
world = bpy.data.worlds.new("Study_World")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.72, 0.67, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.25
scene.world = world

def area(name, xyz, power, width, height, target=(0, 0, 0)):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = power
    data.shape = "RECTANGLE"
    data.size = width*MM
    data.size_y = height*MM
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = [v*MM for v in xyz]
    obj.rotation_euler = (Vector([v*MM for v in target])-obj.location).to_track_quat("-Z", "Y").to_euler()

area("Long soft key", (-60, 15, 95), 0.042, 55, 110)
area("Polished rim strip", (65, 30, 35), 0.033, 15, 95)
area("Low front fill", (0, -70, 70), 0.018, 75, 60)
camera = scene.camera
camera.location = (52*MM, -62*MM, 122*MM)
camera.rotation_euler = (Vector((0, 6*MM, 0))-camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.type = "ORTHO"
camera.data.ortho_scale = 70*MM
camera.data.clip_start = 0.001
camera.data.clip_end = 10

label_material = bpy.data.materials.new("Study annotation")
label_material.use_nodes = True
nodes = label_material.node_tree.nodes
nodes.clear()
emission = nodes.new("ShaderNodeEmission")
emission.inputs[0].default_value = (0.09, 0.08, 0.065, 1)
output = nodes.new("ShaderNodeOutputMaterial")
label_material.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])

def label(name, body, x, y, size):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = body
    curve.size = size*MM
    curve.align_x = "CENTER"
    obj = bpy.data.objects.new(name, curve)
    scene.collection.objects.link(obj)
    obj.parent = camera
    obj.location = (x*MM, y*MM, -0.05)
    obj.data.materials.append(label_material)

label("Study title", "A U R A", -20, 24.5, 2.2)
label("Study subtitle", "A04  /  CIRCULAR STUDY", -20, 22.2, 0.9)
label("Study status", "PROVISIONAL GEOMETRY  /  NOT A PRINT RELEASE", 0, -25.0, 1.0)
label("Study thickness", f"40 mm diameter  /  {report['model_depth_mm']:.1f} mm shown with {report['pcb_thickness_mm']:.1f} mm PCB", 0, -27.0, 0.92)
label("Study target", "10.0 mm target requires 0.8 mm PCB  /  pack and fit unqualified", 0, -28.6, 0.80)

scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 40
# The first run exhausted memory in OIDN on the shared workstation. Keep this
# small study render deterministic and self-contained without a denoiser.
scene.cycles.use_denoising = False
scene.render.resolution_x = 1280
scene.render.resolution_y = 1120
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.image_settings.color_depth = "8"
scene.render.film_transparent = False
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = 0.1
path = STUDY / "aura-a04-study.png"
scene.render.filepath = "//aura-a04-study.png"
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(STUDY / "aura-a04-appearance-study.blend"), compress=True)
bpy.ops.render.render(write_still=True)
provenance = {"status": "provisional appearance blockout; not validated CAD", "physical_qualification": False,
              "print_release": False, "native_placement_imported": False, "body_diameter_mm": 40,
              "body_depth_mm": report["model_depth_mm"], "pcb_thickness_mm": report["pcb_thickness_mm"],
              "target_depth_mm": report["target_depth_mm"], "source": "aura-a04-packaging.blend",
              "source_blend_sha256": hashlib.sha256((STUDY / "aura-a04-packaging.blend").read_bytes()).hexdigest(),
              "contract_sha256": report["contract_sha256"],
              "image": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "geometry_note": "Cosmetic bevel modifiers and unqualified styling chain added for this appearance view."}
(STUDY / "appearance-study.json").write_text(json.dumps(provenance, indent=2)+"\n", encoding="utf-8")
print("A04_APPEARANCE_READY", str(path), flush=True)
