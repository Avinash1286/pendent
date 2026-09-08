"""Overview from the exact exported A04 coupon STLs, not rebuilt approximations."""
import hashlib
import json
import math
from pathlib import Path
import struct

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
manifest = json.loads((ROOT/"coupon-manifest.json").read_text())
MM = 0.001
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene


def mat(name, color, metallic=0, roughness=0.4):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    return material


polymer = mat("Unqualified process-test polymer", (0.32, 0.43, 0.46), 0.05, 0.43)
floor_mat = mat("Warm neutral table", (0.70, 0.68, 0.63), 0, 0.85)
layout = [(-23, 52), (23, 52), (-23, 4), (23, 4), (-23, -48), (30, -43), (12, -70), (26, -70), (40, -70)]
for part, (x, y) in zip(manifest["parts"], layout):
    raw = (ROOT/part["file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == part["sha256"]
    count, = struct.unpack_from("<I", raw, 80)
    vertices = []
    faces = []
    for index in range(count):
        values = struct.unpack_from("<12fH", raw, 84+50*index)
        for j in range(3):
            vertices.append(tuple(v*MM for v in values[3+j*3:6+j*3]))
        faces.append((index*3, index*3+1, index*3+2))
    mesh = bpy.data.meshes.new(part["file"])
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(part["file"], mesh)
    scene.collection.objects.link(obj)
    obj.location = (x*MM, y*MM, 0)
    obj.data.materials.append(polymer)
    obj["source_stl_sha256"] = part["sha256"]
    obj["physical_qualification"] = False

bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, -0.4*MM))
bpy.context.object.data.materials.append(floor_mat)
world = bpy.data.worlds.new("Coupon world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.73, 0.69, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.25
scene.world = world

for name, xyz, power, size in [("Key", (-100, 40, 230), 0.32, 150), ("Fill", (130, -70, 150), 0.18, 110)]:
    light = bpy.data.lights.new(name, "AREA")
    light.energy = power
    light.size = size*MM
    obj = bpy.data.objects.new(name, light)
    scene.collection.objects.link(obj)
    obj.location = [v*MM for v in xyz]
    obj.rotation_euler = (-obj.location).to_track_quat("-Z", "Y").to_euler()
bpy.ops.object.camera_add(location=(6*MM, -90*MM, 320*MM))
camera = bpy.context.object
camera.rotation_euler = (Vector((6*MM, -2*MM, 0))-camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.type = "ORTHO"
camera.data.ortho_scale = 180*MM
camera.data.clip_start = 0.001
camera.data.clip_end = 10
scene.camera = camera

ink = bpy.data.materials.new("Coupon captions")
ink.use_nodes = True
nodes = ink.node_tree.nodes
nodes.clear()
emission = nodes.new("ShaderNodeEmission")
emission.inputs[0].default_value = (0.06, 0.065, 0.065, 1)
out = nodes.new("ShaderNodeOutputMaterial")
ink.node_tree.links.new(emission.outputs[0], out.inputs["Surface"])
for name, value, y, size in [("Title", "AURA / A04", 81, 3.3),
                              ("Subtitle", "FULL-SIZE FACE + PROCESS COUPON", 76.5, 1.7),
                              ("Footer", "9 EXACT STL SPECIMENS / MILLIMETRES", -73, 1.7),
                              ("Status", "UNPOWERED FIT TRIAL / NOT QUALIFIED DEVICE PARTS", -77, 1.4)]:
    text = bpy.data.curves.new(name, "FONT")
    text.body = value
    text.align_x = "CENTER"
    text.size = size*MM
    obj = bpy.data.objects.new(name, text)
    scene.collection.objects.link(obj)
    obj.parent = camera
    obj.location = (0, y*MM, -0.06)
    obj.data.materials.append(ink)

scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 32
scene.cycles.use_denoising = False
scene.render.resolution_x = 960
scene.render.resolution_y = 1280
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.render.filepath = str(ROOT/"coupon-overview.png")
bpy.ops.render.render(write_still=True)
print("A04_COUPON_OVERVIEW_READY", scene.render.filepath, flush=True)
