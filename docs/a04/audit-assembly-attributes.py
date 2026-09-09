"""Read-only A04 assembly-attribute audit; writes this audit's JSON only.

Run with KiCad's bundled Python (pcbnew). Footprints/board are parsed by native
pcbnew; native schematic instances are read with a structural S-expression parser.
Exit 0 means audit integrity passed, not assembly readiness. No CAD is saved,
placed, exported, corrected, or passed to an MCP project/session operation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import pcbnew


ROOT = Path(__file__).resolve().parents[2]
CAD = ROOT / "hardware/a04"
NETLIST = CAD / "review/a04-candidate-2.net"
REPORT = Path(__file__).with_name("assembly-attributes-verification.json")
CONTACTS = {
    "J1": "AuraA04:DockContacts", "J2": "AuraA04:BatteryPads",
    "J3": "AuraA04:SWDPads", "J4": "AuraA04:MotorPads",
}
CANDIDATE = "AuraA04:Nidec_CUS22TB_Candidate"
FLAGS = ("in_bom", "on_board", "in_pos_files", "dnp")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_sexpr(path):
    """Preserve scope: cached library symbols are not placed instances."""
    text = path.read_text(encoding="utf-8")
    stack, roots = [], []
    for token in re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+', text):
        if token == "(":
            node = []
            (stack[-1] if stack else roots).append(node)
            stack.append(node)
        elif token == ")":
            if not stack:
                raise ValueError(f"Unbalanced expression in {path.name}")
            stack.pop()
        else:
            if not stack:
                raise ValueError(f"Token outside expression in {path.name}")
            # Decode only KiCad's quoted-character escapes, retaining Unicode.
            stack[-1].append(re.sub(r'\\(.)', r'\1', token[1:-1])
                             if token.startswith('"') else token)
    if stack or len(roots) != 1:
        raise ValueError(f"Incomplete expression in {path.name}")
    return roots[0]


def children(node, name):
    return [x for x in node if isinstance(x, list) and x and x[0] == name]


def atom(node, name):
    values = children(node, name)
    return values[0][1] if len(values) == 1 and len(values[0]) > 1 else None


def props(node):
    return {x[1]: x[2] for x in children(node, "property") if len(x) >= 3}


def refkey(ref):
    m = re.fullmatch(r"([A-Za-z]+)(\d+)", ref)
    return (m[1], int(m[2])) if m else (ref, 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-library-root", type=Path,
                        default=Path(sys.executable).resolve().parents[1] / "share/kicad/footprints")
    args = parser.parse_args()
    stock = args.stock_library_root.resolve()
    source_paths, before, errors = {}, {}, []

    def record(path, label=None):
        label = label or path.relative_to(ROOT).as_posix()
        if label not in source_paths:
            source_paths[label] = path
            before[label] = digest(path)
        return label

    record(NETLIST)
    tree = ET.parse(NETLIST).getroot()
    components = tree.findall("./components/comp")
    by_ref = {c.attrib["ref"]: c for c in components}
    if len(by_ref) != len(components):
        errors.append("Duplicate component references in exported netlist")
    assigned = {ref: c.findtext("footprint") for ref, c in by_ref.items()}
    for ref, footprint in assigned.items():
        if not footprint or ":" not in footprint:
            errors.append(f"Missing/invalid assigned footprint for {ref}")

    schematic_rows, caches = {}, {}
    for path in sorted(CAD.glob("*.kicad_sch")):
        label = record(path)
        schematic = parse_sexpr(path)
        cached = children(schematic, "lib_symbols")
        caches[label] = {x[1]: x for x in children(cached[0], "symbol")} if cached else {}
        for symbol in children(schematic, "symbol"):
            fields = props(symbol)
            ref = fields.get("Reference", "")
            if ref.startswith("#") or not fields.get("Footprint"):
                continue
            if ref in schematic_rows:
                errors.append(f"Duplicate native schematic instance {ref}")
            schematic_rows[ref] = {
                "reference": ref, "sheet": label, "symbol": atom(symbol, "lib_id"),
                "footprint": fields["Footprint"], "mpn": fields.get("MPN"),
                **{flag: atom(symbol, flag) for flag in FLAGS},
            }
    if set(schematic_rows) != set(by_ref):
        errors.append("Native schematic footprint-bearing references differ from netlist")
    for ref, row in schematic_rows.items():
        if ref not in by_ref:
            continue
        net_fields = {x.attrib["name"]: x.text for x in by_ref[ref].findall("./fields/field")}
        if row["footprint"] != assigned[ref] or row["mpn"] != net_fields.get("MPN"):
            errors.append(f"Schematic/netlist footprint or MPN mismatch: {ref}")
        if any(row[flag] not in ("yes", "no") for flag in FLAGS):
            errors.append(f"Missing or invalid explicit native schematic flags: {ref}")
    record(CAD / "fp-lib-table")
    record(ROOT / "docs/a04/schematic-contract.json")
    library_path = CAD / "AuraA04.kicad_sym"
    record(library_path)
    library_symbols = {x[1]: x for x in children(parse_sexpr(library_path), "symbol")}
    for ref, footprint in CONTACTS.items():
        if assigned.get(ref) != footprint:
            errors.append(f"Contact policy assignment changed/missing: {ref}")
        row = schematic_rows.get(ref)
        if row:
            symbol_name = row["symbol"].split(":", 1)[1]
            cached = caches[row["sheet"]].get(row["symbol"], [])
            row["cached_symbol_in_bom"] = atom(cached, "in_bom")
            row["library_symbol_in_bom"] = atom(library_symbols.get(symbol_name, []), "in_bom")

    libraries = {"AuraA04": CAD / "AuraA04.pretty", "AuraVerified": ROOT / "hardware/library.pretty"}
    footprint_refs = defaultdict(list)
    for ref, fid in assigned.items():
        if fid and ":" in fid:
            footprint_refs[fid].append(ref)
    definitions = {}
    for fid in sorted(footprint_refs):
        nickname, name = fid.split(":", 1)
        folder = libraries.get(nickname, stock / f"{nickname}.pretty")
        path = folder / f"{name}.kicad_mod"
        label = (path.relative_to(ROOT).as_posix() if nickname in libraries else
                 "kicad_stock/" + path.relative_to(stock).as_posix())
        if not path.is_file():
            errors.append(f"Assigned footprint does not resolve: {fid}")
            continue
        record(path, label)
        fp = pcbnew.FootprintLoad(str(folder), name)
        if fp is None:
            errors.append(f"Native pcbnew parse failed: {fid}")
            continue
        attributes = fp.GetAttributes()
        pads = list(fp.Pads())
        definitions[fid] = {
            "references": sorted(footprint_refs[fid], key=refkey), "source": label,
            "sha256": before[label], "attribute_bits": attributes,
            "smd": bool(attributes & pcbnew.FP_SMD),
            "through_hole": bool(attributes & pcbnew.FP_THROUGH_HOLE),
            "excluded_from_position_files": fp.IsExcludedFromPosFiles(),
            "excluded_from_bom": fp.IsExcludedFromBOM(), "dnp": fp.IsDNP(),
            "pad_count": len(pads),
            "smd_pad_count": sum(p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD for p in pads),
            "front_paste_pad_count": sum(p.IsOnLayer(pcbnew.F_Paste) for p in pads),
            "back_paste_pad_count": sum(p.IsOnLayer(pcbnew.B_Paste) for p in pads),
            "paste_graphics_count": sum(g.GetLayer() in (pcbnew.F_Paste, pcbnew.B_Paste)
                                        for g in fp.GraphicalItems()),
        }
        if fp.IsExcludedFromBOM() != bool(attributes & pcbnew.FP_EXCLUDE_FROM_BOM):
            errors.append(f"Native attribute/BOM accessor disagreement: {fid}")
        if fp.IsExcludedFromPosFiles() != bool(attributes & pcbnew.FP_EXCLUDE_FROM_POS_FILES):
            errors.append(f"Native attribute/position accessor disagreement: {fid}")

    findings, purchased, contacts = [], [], []
    for ref in sorted(by_ref, key=refkey):
        data, flags = definitions.get(assigned[ref]), schematic_rows.get(ref)
        if data is None or flags is None:
            continue
        contact = ref in CONTACTS
        (contacts if contact else purchased).append(ref)
        codes = []
        if contact:
            if not data["excluded_from_bom"] or flags["in_bom"] != "no":
                codes.append("contact_not_excluded_from_purchased_bom")
            if not data["excluded_from_position_files"] or flags["in_pos_files"] != "no":
                codes.append("contact_not_excluded_from_position_files")
            if any(data[x] for x in ("front_paste_pad_count", "back_paste_pad_count", "paste_graphics_count")):
                codes.append("contact_has_paste_geometry")
            if flags["on_board"] != "yes":
                codes.append("contact_missing_from_board_intent")
        else:
            if not data["smd"]:
                codes.append("purchased_smd_part_missing_footprint_smd_attribute")
            if data["excluded_from_bom"] or flags["in_bom"] != "yes":
                codes.append("purchased_part_excluded_from_bom")
            if data["excluded_from_position_files"] or flags["in_pos_files"] != "yes":
                codes.append("purchased_part_excluded_from_position_files")
            if data["dnp"] or flags["dnp"] != "no" or flags["on_board"] != "yes":
                codes.append("purchased_part_not_fitted_or_not_on_board")
        if codes:
            findings.append({"reference": ref, "footprint": assigned[ref], "codes": codes})

    candidate_path = CAD / "AuraA04.pretty/Nidec_CUS22TB_Candidate.kicad_mod"
    record(candidate_path)
    candidate_refs = sorted(footprint_refs.get(CANDIDATE, []), key=refkey)
    if candidate_refs:
        errors.append("Separately audited CUS22 candidate is now assigned; scope needs review")
    board_path = CAD / "aura-a04.kicad_pcb"
    record(board_path)
    board = pcbnew.LoadBoard(str(board_path))
    after = {label: digest(path) for label, path in source_paths.items()}
    changed = [label for label in before if before[label] != after[label]]
    if changed:
        errors.append("A source changed during the audit")
    smd_refs = [ref for ref in purchased if definitions[assigned[ref]]["smd"]]
    missing_smd = [ref for ref in purchased if not definitions[assigned[ref]]["smd"]]
    report = {
        "status": "assembly attribute blockers present" if findings else "attribute policy satisfied; exports unverified",
        "parser": f"KiCad pcbnew {pcbnew.GetBuildVersion()}",
        "schematic_parser": "structural S-expression; top-level symbol instances only",
        "audit_integrity_pass": not errors, "errors": errors,
        "assembly_attribute_policy_pass": not errors and not findings,
        "policy": "Current purchased PCB parts are SMD; J1-J4 are copper contact features retained on board and excluded from component BOM/position files.",
        "source_sha256": before, "source_sha256_after": after,
        "changed_sources": changed, "sources_unchanged_during_audit": not changed,
        "audit_script_sha256": digest(Path(__file__)),
        "stock_library_root": stock.as_posix(),
        "stock_source_path_alias": "kicad_stock/ paths are relative to stock_library_root",
        "resolution_scope": "Assigned netlist footprints; AuraA04/AuraVerified project directories plus installed stock library root",
        "netlist_export_tool": tree.findtext("./design/tool"),
        "netlist_export_date": tree.findtext("./design/date"),
        "counts": {
            "assigned_pcb_references": len(by_ref), "distinct_assigned_footprints": len(footprint_refs),
            "native_schematic_footprint_instances": len(schematic_rows),
            "purchased_pcb_references": len(purchased), "contact_feature_references": len(contacts),
            "purchased_references_with_smd_attribute": len(smd_refs),
            "purchased_definitions_with_smd_attribute": len({assigned[r] for r in smd_refs}),
            "schematic_flags": {flag: dict(Counter(row[flag] for row in schematic_rows.values())) for flag in FLAGS},
            "assigned_reference_attribute_bits": dict(Counter(str(definitions[f]["attribute_bits"])
                                                             for f in assigned.values() if f in definitions)),
        },
        "purchased_references": purchased, "contact_references": contacts,
        "purchased_references_missing_smd_attribute": missing_smd,
        "findings": findings,
        "schematic_instances": [schematic_rows[r] for r in sorted(schematic_rows, key=refkey)],
        "footprint_definitions": definitions,
        "unassigned_candidate": {"footprint": CANDIDATE, "assigned_references": candidate_refs,
                                 "included_in_assigned_counts": bool(candidate_refs)},
        "native_board": {"footprints": len(list(board.GetFootprints())),
                         "thickness_mm": pcbnew.ToMM(board.GetDesignSettings().GetBoardThickness())},
        "cad_mutated_by_audit": False, "placement_file_exported": False,
        "bom_exported": False, "assembly_exports_verified": False, "fabrication_ready": False,
        "limitations": [
            "Library attributes and schematic flags are evidence of future export risks, not an actual placed-board CPL/BOM result.",
            "The audit does not qualify pads, stencil, reflow, orientation, side assignments, mechanical fit or manufacturing process.",
            "Motor, battery pack, mating dock and fixture hardware belong to the separate product/fixture BOM, not four connector purchases.",
            "After native placement and flag correction, inspect saved board instances and independently compare actual BOM/CPL exports against the intended reference sets.",
        ],
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "audit_integrity_pass", "assembly_attribute_policy_pass", "counts",
        "purchased_references_missing_smd_attribute", "native_board", "sources_unchanged_during_audit")}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
