"""Isolated A04 packaging study. Not printable CAD or an actual populated PCB.

Run Blender --background --python this_file.py -- [--pcb-thickness 1.6]
No A03 inputs or outputs are modified. No print meshes or product renders export.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "design-contract.json"
cfg = json.loads(CONTRACT.read_text(encoding="utf-8"))
parser = argparse.ArgumentParser()
parser.add_argument("--pcb-thickness", type=float, default=cfg["pcb"]["thickness_actual_reported_mm"])
parser.add_argument("--pcb-diameter", type=float, default=cfg["pcb"]["diameter_target_mm"])
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
if not 0.4 <= args.pcb_thickness <= 2.0:
    raise ValueError("Study thickness must be between0.4 and2.0 mm")
if not 30 <= args.pcb_diameter < cfg["body"]["cavity_diameter_mm"]:
    raise ValueError("Board study diameter must fit within the nominal cavity")

MM = 0.001
stack = cfg["stack"]
depth = sum(stack.values()) + args.pcb_thickness
target_depth = sum(stack.values()) + cfg["pcb"]["thickness_target_mm"]
assert math.isclose(target_depth, cfg["body"]["target_depth_mm"], abs_tol=1e-8)
back = -depth / 2
floor = back + stack["rear_skin_mm"]
cell_bottom = floor + stack["cell_backing_mm"]
cell_top = cell_bottom + stack["cell_supplier_max_mm"]
growth_top = cell_top + stack["cell_growth_reserve_mm"]
pcb_bottom = growth_top + stack["dielectric_and_clearance_mm"]
pcb_top = pcb_bottom + args.pcb_thickness
component_top = pcb_top + stack["component_plus_mount_max_mm"]
pressed_face = component_top + stack["pressed_face_clearance_mm"]
face_bottom = pressed_face + stack["face_travel_mm"]
face_top = face_bottom + stack["face_skin_mm"]
front = depth / 2
assert math.isclose(face_top + stack["cosmetic_setback_mm"], front, abs_tol=1e-8)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.length_unit = "MILLIMETERS"


def material(name, color, metallic=0.0, roughness=0.4, emission=0.0):
    value = bpy.data.materials.new(name)
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    if emission:
        shader.inputs["Emission Color"].default_value = (*color, 1)
        shader.inputs["Emission Strength"].default_value = emission
    return value


ivory = material("A04 pale satin face / material unqualified", (0.66, 0.63, 0.56), 0.0, 0.40)
champagne = material("A04 champagne appearance / nonconductive finish required", (0.63, 0.51, 0.34), 0.72, 0.20)
back_material = material("A04 rear polymer", (0.40, 0.38, 0.34), 0.0, 0.38)
diffuser = material("A04 lightguide optical concept only", (0.98, 0.89, 0.70), 0.0, 0.35, 0.8)
board_material = material("PLACEHOLDER board allocation", (0.02, 0.13, 0.10))
cell_material = material("PLACEHOLDER pack allocation", (0.48, 0.24, 0.06))
radio_material = material("PLACEHOLDER nominal radio envelope", (0.32, 0.35, 0.38), 0.60)
reserve_material = material("RESERVED volume", (0.65, 0.08, 0.05))


def finish(obj, mat):
    obj.data.materials.append(mat)
    obj["revision"] = "A04 proposed packaging study"
    obj["physical_qualification"] = False
    obj["print_release"] = False
    for polygon in obj.data.polygons:
        polygon.use_smooth = abs(polygon.normal.z) < 0.99
    return obj


def cylinder(name, radius, low, high, mat, xy=(0, 0), axis="Z"):
    bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=radius * MM, depth=(high-low) * MM,
                                       location=(xy[0]*MM, xy[1]*MM, (low+high)*MM/2))
    obj = bpy.context.object
    obj.name = name
    if axis == "X":
        obj.rotation_euler.y = math.pi/2
    return finish(obj, mat)


def box(name, dims, centre, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=[v*MM for v in centre])
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = [v*MM for v in dims]
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, mat)


def subtract(obj, cutter):
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new("Study cavity", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def ring(name, outside, inside, low, high, mat):
    obj = cylinder(name, outside, low, high, mat)
    subtract(obj, cylinder("Temporary ring cutter", inside, low-1, high+1, mat))
    return obj


rear = cylinder("Study_Rear_Cup_UNENGINEERED", 20, back, 0, back_material)
subtract(rear, cylinder("Temporary rear cavity", 18.8, floor, 1, back_material))
ring("Study_Frame_UNENGINEERED", 20, 18.8, 0.10, front, champagne)
ring("Study_Front_Lip_UNENGINEERED", 18.8, cfg["face"]["aperture_diameter_mm"]/2,
     face_top-0.35, front, champagne)
cylinder("Study_Moving_Face_NO_RETENTION", cfg["face"]["diameter_mm"]/2, face_bottom, face_top, ivory)
ring("Study_Fixed_Light_Ring_OPTICAL_PLACEHOLDER", cfg["diffuser"]["outer_radius_mm"],
     cfg["diffuser"]["inner_radius_mm"], face_top, front+0.005, diffuser)
box("Study_Status_Dash_NO_LIGHTPIPE", (3, 0.5, 0.05), (0, 0, face_top+0.025), diffuser)

bail_cfg = cfg["bail"]
bail = box("Study_Bail_NO_LOAD_QUALIFICATION", (bail_cfg["width_mm"], 5.2, bail_cfg["depth_mm"]),
           (0, 21.4, -1.0), champagne)
hole = cylinder("Temporary bail passage", bail_cfg["passage_diameter_mm"]/2, -5, 5, back_material, axis="X")
hole.location = (0, 22.0*MM, -1.0*MM)
subtract(bail, hole)

board = cylinder("ALLOCATION_PCB_NO_NATIVE_PLACEMENT", args.pcb_diameter/2, pcb_bottom, pcb_top, board_material)
board["actual_native_import"] = False
board["notches_applied"] = False
cell = cfg["cell"]
box("ALLOCATION_CELL_SUPPLIER_UNSELECTED", (cell["max_width_mm"], cell["max_height_mm"], cell["max_depth_mm"]),
    (*cell["center_xy_mm"], (cell_bottom+cell_top)/2), cell_material)
growth = box("RESERVE_CELL_GROWTH_NOT_SUPPLIER_QUALIFIED", (cell["max_width_mm"], cell["max_height_mm"], stack["cell_growth_reserve_mm"]),
             (*cell["center_xy_mm"], (cell_top+growth_top)/2), reserve_material)
growth.display_type = "WIRE"
growth.hide_render = True
sensor = cfg["temperature_sensor"]
sensor_reserve = box("RESERVE_NTC_EDGE_POCKET_THERMALLY_UNQUALIFIED", sensor["pocket_proposed_mm"],
                     (*sensor["pocket_center_xy_mm"], (cell_bottom+cell_top)/2), reserve_material)
sensor_reserve.display_type = "WIRE"
sensor_reserve.hide_render = True
radio_dims = cfg["radio"]["maximum_body_mm"]
radio = box("ENVELOPE_RADIO_MAXIMUM_NO_NATIVE_PLACEMENT", radio_dims,
            (0, 5.7, pcb_top+cfg["radio"]["solder_seating_reserve_mm"]+radio_dims[2]/2), radio_material)
radio["dimension_source"] = cfg["radio"]["source"]
radio["installed_height_qualified"] = False
haptic = cfg["haptic"]
cylinder("CANDIDATE_ERM_NO_NATIVE_PLACEMENT", haptic["maximum_body_diameter_mm"]/2,
         pcb_top+haptic["supplied_tape_nominal_mm"],
         pcb_top+haptic["supplied_tape_nominal_mm"]+haptic["maximum_body_height_mm"], radio_material, (7, -8))
motor_lead_reserve = box("RESERVE_ERM_TAB_AND_LEAD_EXIT", (2.5, 2.0, 1.0), (7, -13.8, pcb_top+0.5), reserve_material)
motor_lead_reserve.display_type = "WIRE"
motor_lead_reserve.hide_render = True

for index, xy in enumerate(cfg["closure"]["boss_centers_xy_mm"], 1):
    reserve = cylinder(f"RESERVE_BOSS_{index}_BOARD_NOTCH_REQUIRED", 2.1, pcb_bottom-0.2, pcb_top+0.2, reserve_material, xy)
    reserve.display_type = "WIRE"
    reserve.hide_render = True
for index, xy in enumerate(cfg["dock"]["contact_centers_xy_mm"], 1):
    cylinder(f"Study_Dock_Contact_{index}_UNSELECTED", 0.85, back-0.01, back+0.05, champagne, xy)

# A useful editable study camera; no product render is emitted by this scaffold.
bpy.ops.object.camera_add(location=(65*MM, -75*MM, 78*MM))
camera = bpy.context.object
camera.name = "Study_Camera"
camera.rotation_euler = (Vector((0, 1*MM, 0))-camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.type = "ORTHO"
camera.data.ortho_scale = 65*MM
scene.camera = camera
scene["study_status"] = "Unfrozen allocation model; no print/collision/physical qualification"
scene["target_depth_mm"] = cfg["body"]["target_depth_mm"]
scene["model_depth_mm"] = depth
scene["pcb_thickness_mm"] = args.pcb_thickness

output = ROOT / "study"
output.mkdir(exist_ok=True)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(output / "aura-a04-packaging.blend"))
report = {
    "revision": "A04", "status": "proposed allocation study; not a fit audit", "physical_qualification": False,
    "print_release": False, "native_placement_imported": False, "collision_checks_complete": False,
    "contract_sha256": hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),
    "pcb_diameter_mm": args.pcb_diameter, "pcb_thickness_mm": args.pcb_thickness,
    "target_depth_mm": cfg["body"]["target_depth_mm"], "model_depth_mm": round(depth, 6),
    "target_depth_met": depth <= cfg["body"]["target_depth_mm"]+1e-8,
    "board_radial_cavity_clearance_mm": (cfg["body"]["cavity_diameter_mm"]-args.pcb_diameter)/2,
    "planes_mm": {"back": back, "rear_inner_floor": floor, "cell_bottom": cell_bottom, "cell_top": cell_top,
                  "growth_top": growth_top, "pcb_bottom": pcb_bottom, "pcb_top": pcb_top,
                  "max_component_top": component_top, "pressed_face_underside": pressed_face,
                  "face_rest_underside": face_bottom, "face_front": face_top, "front_datum": front},
    "not_modelled": ["actual populated board", "PCB notches", "face retention/plunger/stops", "privacy linkage",
                     "real acoustic ducts", "optical lightguide", "selected cell/haptic/contacts", "closure hardware",
                     "qualified thermal sensor contact and carrier"],
}
(output / "packaging-study.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
print("A04_STUDY_COMPLETE", json.dumps({"depth_mm": depth, "target_met": report["target_depth_met"]}))
