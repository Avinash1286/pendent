"""Blender A04 full-size face/rim process coupon; not device enclosure parts.

Exports nine separate millimetre STLs plus a laid-out inspection BLEND.
"""
import hashlib
import json
import math
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent
ROOT.mkdir(exist_ok=True)
MM = 0.001
N = 256
parts = []
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.length_unit = "MILLIMETERS"


def cylinder(name, radius, low, high, xy=(0, 0), axis="Z"):
    bpy.ops.mesh.primitive_cylinder_add(vertices=N, radius=radius*MM, depth=(high-low)*MM,
                                       location=(xy[0]*MM, xy[1]*MM, (low+high)*MM/2))
    obj = bpy.context.object
    obj.name = name
    if axis == "X":
        obj.rotation_euler.y = math.pi/2
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def box(name, dims, center):
    bpy.ops.mesh.primitive_cube_add(size=1, location=[v*MM for v in center])
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = [v*MM for v in dims]
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def boolean(obj, cutter, operation="UNION"):
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new("Coupon functional solid", "BOOLEAN")
    modifier.operation = operation
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def emboss(obj, text, x, y, z, size=3):
    curve = bpy.data.curves.new("Coupon label", "FONT")
    curve.body = text
    curve.align_x = "CENTER"
    curve.size = size*MM
    curve.extrude = 0.20*MM
    label = bpy.data.objects.new("Coupon label", curve)
    scene.collection.objects.link(label)
    label.location = (x*MM, y*MM, (z-0.05)*MM)
    bpy.ops.object.select_all(action="DESELECT")
    label.select_set(True)
    bpy.context.view_layer.objects.active = label
    bpy.ops.object.convert(target="MESH")
    boolean(obj, bpy.context.object)


def register(obj, filename, description):
    obj["purpose"] = "Unpowered manufacturing-process coupon; not a device part"
    obj["physical_qualification"] = False
    obj["dimensions"] = "millimetres in exported STL"
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.stl_export(filepath=str(ROOT/filename), export_selected_objects=True, global_scale=1000,
                          apply_modifiers=True, ascii_format=False)
    parts.append((obj, filename, description))


# Each ring tests the full intended face diameter, so gross warp and coating
# buildup are exposed. The tab keeps the label away from the working bore.
for gap in (0.15, 0.20, 0.25, 0.30):
    code = round(gap*100)
    ring = cylinder(f"R{code}_FACE_RING", 20, 0, 1.2)
    boolean(ring, box("Label tab", (16, 6.0, 1.2), (0, -21.0, 0.6)))
    boolean(ring, cylinder("Face aperture", 17.6+gap, -1, 3), "DIFFERENCE")
    emboss(ring, f"R{code}", 0, -22.8, 1.2)
    register(ring, f"a04-face-ring-r{code}.stl", f"Full-size35.2 mm face gauge; {gap:.2f} mm nominal radial gap")

# Shared face gauge prints face-down. The wider flange prevents it dropping
# through a ring; hold the rear grip when testing from the back of each ring.
face = cylinder("F352_SHARED_FACE_GAUGE", 17.6, 0, 1.0)
boolean(face, cylinder("Retaining flange", 18.6, 0.95, 1.6))
boolean(face, cylinder("Rear grip", 3.0, 1.55, 4.6))
emboss(face, "F352", 0, -7.0, 1.6, 3.0)
register(face, "a04-face-gauge-35p2.stl", "35.2 mm working face,1.0 mm skin;37.2 mm retaining flange and rear grip")

# Separate card: tall wall specimens can be gauged above the base without
# confusing base thickness with wall thickness. The actual transverse bail
# opening tests the horizontal-hole process, not only easy vertical bores.
card = box("WALL_AND_BAIL_PROCESS_CARD", (60, 30, 1.5), (0, 0, 0.75))
for x, thickness, label in [(-20, 1.0, "10"), (-8, 1.2, "12"), (4, 1.5, "15")]:
    boolean(card, box("Wall specimen", (thickness, 12, 8.05), (x, 5, (1.45+9.5)/2)))
    emboss(card, label, x, -7.0, 1.5, 3.0)
bail = box("Bail cross-section", (5.2, 5.2, 3.8), (21, 5, 3.35))
hole = cylinder("Bail transverse aperture", 1.3, -4, 4, axis="X")
hole.location = (21*MM, 5*MM, 3.35*MM)
boolean(bail, hole, "DIFFERENCE")
boolean(card, bail)
emboss(card, "B26", 21, -7.0, 1.5, 3.0)
emboss(card, "COUPON / mm", 0, -13.0, 1.5, 2.7)
register(card, "a04-wall-bail-card.stl", "1.0/1.2/1.5 mm walls,8 mm exposed height;2.6 mm transverse bail hole")

# Three removable relative-fit gauges. They are not certified pin gauges:
# measure shaft diameter before interpreting a hole/pin fit as clearance.
for diameter in (2.4, 2.5, 2.6):
    code = round(diameter*10)
    pin = box(f"P{code}_RELATIVE_PIN", (10, 7, 1.5), (0, 0, 0.75))
    boolean(pin, cylinder("Gauge shaft", diameter/2, 1.45, 7.0, (0, 1.0)))
    bpy.ops.mesh.primitive_cone_add(vertices=N, radius1=diameter/2*MM, radius2=0.75*MM,
                                   depth=0.6*MM, location=(0, 1.0*MM, 7.25*MM))
    boolean(pin, bpy.context.object)
    emboss(pin, f"P{code}", 0, -2.8, 1.5, 2.1)
    register(pin, f"a04-relative-pin-{code}.stl", f"{diameter:.1f} mm nominal pin for2.6 mm bail hole; measure actual diameter")

layout = [(-23, 52), (23, 52), (-23, 4), (23, 4), (-23, -48), (30, -43), (12, -70), (26, -70), (40, -70)]
for (obj, _, _), (x, y) in zip(parts, layout):
    obj.location.x += x*MM
    obj.location.y += y*MM

material = bpy.data.materials.new("Unqualified process-test polymer")
material.diffuse_color = (0.55, 0.64, 0.66, 1)
for obj, _, _ in parts:
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "a04-coupon-layout.blend"), compress=True)
manifest = {
    "revision": "A04 coupon v1", "units": "millimetres", "purpose": "Unpowered same-process face/rim/bail fit trials",
    "complete_device_parts": False, "physical_qualification": False, "specimen_count": len(parts),
    "target_face_diameter_mm": 35.2, "radial_gap_series_mm": [0.15, 0.20, 0.25, 0.30],
    "wall_series_mm": [1.0, 1.2, 1.5], "bail_bore_diameter_mm": 2.6, "relative_pin_diameters_mm": [2.4, 2.5, 2.6],
    "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "parts": [{"file": file, "description": description, "bytes": (ROOT/file).stat().st_size,
               "sha256": hashlib.sha256((ROOT/file).read_bytes()).hexdigest()} for _, file, description in parts],
}
(ROOT / "coupon-manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
print("A04_COUPON_EXPORTED", len(parts), flush=True)
