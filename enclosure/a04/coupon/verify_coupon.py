"""Independently inspect actual binary STL topology and functional dimensions.

Python stdlib only; no Blender data/model helpers are used by this verifier.
"""
import hashlib
import json
import math
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent
TOL = 0.005


def load_stl(path):
    raw = path.read_bytes()
    count, = struct.unpack_from("<I", raw, 80)
    if len(raw) != 84+50*count:
        raise ValueError(f"Invalid binary STL length: {path.name}")
    triangles = []
    for index in range(count):
        values = struct.unpack_from("<12fH", raw, 84+index*50)
        triangles.append(tuple(tuple(values[3+3*j:6+3*j]) for j in range(3)))
    return raw, triangles


def audit_mesh(triangles):
    edges = {}
    signed = {}
    parent = {}
    volume = 0
    degenerate = 0

    def key(v):
        return tuple(round(n, 5) for n in v)

    def find(v):
        parent.setdefault(v, v)
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    for triangle in triangles:
        a, b, c = triangle
        cross = (b[1]*c[2]-b[2]*c[1], b[2]*c[0]-b[0]*c[2], b[0]*c[1]-b[1]*c[0])
        volume += sum(a[i]*cross[i] for i in range(3))/6
        keys = [key(v) for v in triangle]
        if len(set(keys)) != 3:
            degenerate += 1
        for u, v in zip(keys, keys[1:]+keys[:1]):
            edge = tuple(sorted((u, v)))
            edges[edge] = edges.get(edge, 0)+1
            signed[edge] = signed.get(edge, 0)+(1 if u < v else -1)
            parent[find(v)] = find(u)
    vertices = list(parent)
    components = len({find(v) for v in vertices})
    nonmanifold = sum(value != 2 for value in edges.values())
    reversed_edges = sum(value != 0 for value in signed.values())
    low = [min(v[i] for v in vertices) for i in range(3)]
    high = [max(v[i] for v in vertices) for i in range(3)]
    return vertices, {"triangles": len(triangles), "connected_solids": components,
                      "nonmanifold_edges": nonmanifold, "inconsistent_winding_edges": reversed_edges,
                      "degenerate_triangles": degenerate, "signed_volume_mm3": volume,
                      "bounds_mm": [low, high], "dimensions_mm": [high[i]-low[i] for i in range(3)]}


def close(value, expected, label):
    if abs(value-expected) > TOL:
        raise AssertionError(f"{label}: measured{value:.6f}, expected{expected:.6f} mm")


def section_at_z(triangles, z):
    """Intersect exported triangles at the working shaft, excluding its lead-in."""
    points = []
    for triangle in triangles:
        for a, b in zip(triangle, triangle[1:]+triangle[:1]):
            if (a[2] < z < b[2]) or (b[2] < z < a[2]):
                amount = (z-a[2])/(b[2]-a[2])
                points.append(tuple(a[i]+amount*(b[i]-a[i]) for i in range(3)))
            elif abs(a[2]-z) < 1e-8:
                points.append(a)
    return points


manifest = json.loads((ROOT / "coupon-manifest.json").read_text())
reports = []
for item in manifest["parts"]:
    path = ROOT / item["file"]
    raw, triangles = load_stl(path)
    assert hashlib.sha256(raw).hexdigest() == item["sha256"]
    assert len(raw) == item["bytes"]
    vertices, result = audit_mesh(triangles)
    assert result["connected_solids"] == 1, (path.name, result)
    assert not any(result[k] for k in ("nonmanifold_edges", "inconsistent_winding_edges", "degenerate_triangles")), (path.name, result)
    assert result["signed_volume_mm3"] > 0
    close(result["bounds_mm"][0][2], 0, "print base")
    dimensions = {}
    if "face-ring" in path.name:
        code = int(path.stem[-2:])
        radii = [math.hypot(x, y) for x, y, z in vertices if 17.5 < math.hypot(x, y) < 18.0]
        assert len(radii) >= 256
        close(2*min(radii), 35.2+2*code/100, "minimum bore diameter")
        close(2*max(radii), 35.2+2*code/100, "maximum bore diameter")
        close(result["dimensions_mm"][0], 40, "ring outer X span")
        dimensions = {"bore_diameter_min_mm": 2*min(radii), "bore_diameter_max_mm": 2*max(radii),
                      "nominal_radial_gap_mm": code/100}
    elif "face-gauge" in path.name:
        radii = [math.hypot(x, y) for x, y, z in vertices if z < 0.5 and math.hypot(x, y) > 15]
        close(2*min(radii), 35.2, "face diameter")
        close(2*max(radii), 35.2, "face diameter")
        close(result["dimensions_mm"][0], 37.2, "retaining flange")
        dimensions = {"working_face_diameter_min_mm": 2*min(radii), "working_face_diameter_max_mm": 2*max(radii),
                      "retaining_flange_diameter_mm": result["dimensions_mm"][0]}
    elif "wall-bail" in path.name:
        for center, thickness in [(-20, 1), (-8, 1.2), (4, 1.5)]:
            xs = [x for x, y, z in vertices if abs(x-center) < 2 and z > 7]
            close(max(xs)-min(xs), thickness, "wall thickness")
            dimensions[f"wall_{thickness:.1f}_measured_mm"] = max(xs)-min(xs)
        radii = [math.hypot(y-5, z-3.35) for x, y, z in vertices
                 if (abs(x-18.4) < TOL or abs(x-23.6) < TOL) and 1.0 < math.hypot(y-5, z-3.35) < 1.6]
        assert len(radii) >= 256
        close(2*min(radii), 2.6, "bail bore")
        close(2*max(radii), 2.6, "bail bore")
        close(result["dimensions_mm"][0], 60, "card width")
        close(result["dimensions_mm"][1], 30, "card height")
        dimensions["bail_bore_diameter_min_mm"] = 2*min(radii)
        dimensions["bail_bore_diameter_max_mm"] = 2*max(radii)
    else:
        nominal = int(path.stem[-2:])/10
        radii = [math.hypot(x, y-1) for x, y, z in section_at_z(triangles, 4.0)]
        close(2*min(radii), nominal, "pin shaft")
        close(2*max(radii), nominal, "pin shaft")
        dimensions = {"shaft_diameter_min_mm": 2*min(radii), "shaft_diameter_max_mm": 2*max(radii)}
    reports.append({"file": path.name, "sha256": item["sha256"], **result, "functional_dimensions": dimensions})

result = {"status": "exported coupon mesh/dimension checks pass", "physical_qualification": False,
          "complete_device_parts": False, "units": "millimetres", "specimen_count": len(reports),
          "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "manifest_sha256": hashlib.sha256((ROOT/"coupon-manifest.json").read_bytes()).hexdigest(),
          "dimensional_comparison_tolerance_mm": TOL,
          "checks": "binary STL length/hash; welded closed oriented single solid; positive volume; actual exported bore/face/wall/pin dimensions",
          "limitations": "No printer/material accuracy, fit, strength, surface finish or self-intersection guarantee; measure real prints.",
          "parts": reports}
assert len(reports) == 9
(ROOT / "coupon-mesh-audit.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"specimens": len(reports), "topology_and_dimensions": "pass", "physical_qualification": False}))
