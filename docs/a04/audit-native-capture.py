"""Read-only audit of an MCP-exported netlist and native A04 source.

Writes a diagnostic JSON report only. Never creates or changes KiCad CAD.
An incomplete design deliberately returns a nonzero exit code.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
CAD = ROOT / "hardware/a04"
CONTRACT = ROOT / "docs/a04/schematic-contract.json"
NETLIST = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else CAD / "review/a04-candidate-2.net"
REPORT = ROOT / "docs/a04/native-capture-verification.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    tree = ET.parse(NETLIST).getroot()
    components = {c.attrib["ref"]: c for c in tree.findall("./components/comp")}
    actual = {}
    for net in tree.findall("./nets/net"):
        for node in net.findall("node"):
            key = (node.attrib["ref"], node.attrib["pin"])
            if key in actual:
                raise ValueError(f"Duplicate exported endpoint: {key}")
            actual[key] = net.attrib["name"]
    wanted_refs = {part["ref"] for part in contract["components"]}
    mismatches = []
    part_mismatches = []
    for part in contract["components"]:
        component = components.get(part["ref"])
        if component is not None:
            fields = {field.attrib["name"]: field.text for field in component.findall("./fields/field")}
            if fields.get("MPN") != part["mpn"]:
                part_mismatches.append({"reference": part["ref"], "field": "MPN",
                                        "expected": part["mpn"], "actual": fields.get("MPN")})
            if part.get("footprint") and component.findtext("footprint") != part["footprint"]:
                part_mismatches.append({"reference": part["ref"], "field": "Footprint",
                                        "expected": part["footprint"], "actual": component.findtext("footprint")})
        for pin, net in part["pins"].items():
            got = actual.get((part["ref"], pin))
            if got != net:
                mismatches.append({"reference": part["ref"], "pin": pin,
                                   "expected_net": net, "actual_net": got})
    duplicate_labels = []
    sources = {}
    for path in sorted(CAD.glob("*.kicad_sch")):
        sources[path.relative_to(ROOT).as_posix()] = digest(path)
        labels = Counter((name, round(float(x), 6), round(float(y), 6))
                         for name, x, y in re.findall(
                             r'\(global_label\s+"([^"\n]+)"\s+\(at\s+([-\d.]+)\s+([-\d.]+)',
                             path.read_text(encoding="utf-8")))
        duplicate_labels.extend({"sheet": path.name, "net": name, "at_mm": [x, y], "count": n}
                                for (name, x, y), n in labels.items() if n > 1)
    board = CAD / "aura-a04.kicad_pcb"
    board_text = board.read_text(encoding="utf-8")
    report = {
        "status": "incomplete candidate; not a fabrication or launch release",
        "cad_mutated_by_audit": False,
        "netlist_source": NETLIST.relative_to(ROOT).as_posix(),
        "netlist_sha256": digest(NETLIST), "contract_sha256": digest(CONTRACT),
        "schematic_source_sha256": sources, "board_sha256": digest(board),
        "expected_pcb_references": len(wanted_refs), "exported_pcb_references": len(components),
        "missing_references": sorted(wanted_refs - components.keys()),
        "extra_references": sorted(components.keys() - wanted_refs),
        "expected_connected_endpoints": sum(len(p["pins"]) for p in contract["components"]),
        "connectivity_mismatches": mismatches, "specified_part_mismatches": part_mismatches,
        "duplicate_global_labels": duplicate_labels,
        "native_board_thickness_mm": float(re.search(r'\(thickness\s+([\d.]+)\)', board_text)[1]),
        "placed_pcb_footprints": len(re.findall(r'\(footprint\s', board_text)),
        "pcb_track_segments": len(re.findall(r'\(segment\s', board_text)),
        "fabrication_release": False,
        "limitations": "Net-name and export checks only. No correctness, routing, stackup, assembly, physical fit or qualification claim.",
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{len(components)} PCB references; {report['expected_connected_endpoints']} expected endpoints; "
          f"{len(mismatches)} net mismatches; {len(duplicate_labels)} duplicate label positions; "
          f"{report['placed_pcb_footprints']} PCB footprints. Candidate remains incomplete.")
    return int(bool(mismatches or part_mismatches or duplicate_labels or report["missing_references"] or report["extra_references"]))


if __name__ == "__main__":
    raise SystemExit(main())
