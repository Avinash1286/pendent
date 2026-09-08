"""Read-only A03 DRC classification. Requires KiCad 10 Python (pcbnew)."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def family(ref):
    if ref == "U1": return "radio module"
    if ref.startswith("MK"): return "acoustic LGA"
    if ref.startswith("SW"): return "mechanical switch"
    if ref in ("C3", "C4"): return "silicon capacitor"
    if ref in ("U2", "U3", "U5"): return "exposed-pad leadless IC"
    if ref in ("U6", "U8"): return "fine-pitch gull-wing IC"
    if ref in ("U4", "U7", "U9", "Q1"): return "SOT IC/transistor"
    if ref.startswith(("D", "LED")): return "discrete diode/LED"
    return "standard chip passive"


def group(a, b):
    families = {family(a), family(b)}
    for name in ("radio module", "acoustic LGA", "mechanical switch", "silicon capacitor", "exposed-pad leadless IC", "fine-pitch gull-wing IC", "SOT IC/transistor", "discrete diode/LED"):
        if name in families: return name
    return "standard chip passive"


def fab_bounds(footprint):
    boxes = [g.GetBoundingBox() for g in footprint.GraphicalItems() if isinstance(g, pcbnew.PCB_SHAPE) and g.GetLayer() == pcbnew.F_Fab]
    if not boxes: raise ValueError(f"Missing front Fab geometry: {footprint.GetReference()}")
    return [min(b.GetLeft() for b in boxes), min(b.GetTop() for b in boxes), max(b.GetRight() for b in boxes), max(b.GetBottom() for b in boxes)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name, default in {
        "board": "hardware/native/aura-a03.kicad_pcb",
        "drc": "hardware/native/review/drc.json",
        "manifest": "hardware/output/design-manifest.json",
        "pad-audit": "hardware/native/review/native-smd-pad-spacing-audit.json",
        "output": "docs/research/aura-a03-courtyard-classification.json",
    }.items():
        parser.add_argument("--" + name, type=Path, default=Path(default), help="Absolute path or path relative to repository root")
    parser.add_argument("--expected-sha256", default="b9ec8ebf1a0afaa7563ed4838e145cebb4f14055f71e25b2dbcb0329b0180064", help="Guard for the reviewed A03 board")
    args = parser.parse_args()
    paths = {name: (value if value.is_absolute() else ROOT / value).resolve() for name, value in vars(args).items() if isinstance(value, Path)}
    if paths["output"] in [paths[n] for n in ("board", "drc", "manifest", "pad_audit")]:
        raise ValueError("Output must not overwrite an input")
    inputs = {name: sha(paths[name]) for name in ("board", "drc", "manifest", "pad_audit")}
    if inputs["board"] != args.expected_sha256.lower(): raise ValueError("Board hash differs from expected A03 snapshot")
    board = pcbnew.LoadBoard(str(paths["board"]))
    parts = {p["ref"]: p for p in read_json(paths["manifest"])["parts"]}
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    drc, pad = read_json(paths["drc"]), read_json(paths["pad_audit"])
    assert inputs["board"] == pad["inputSha256"], "Stale pad audit"
    assert len(fps) == 61 and set(fps) == set(parts), "Not the A03 reference map"
    assert len(drc["violations"]) == 78 and all(v["type"] == "courtyards_overlap" for v in drc["violations"]), "Changed DRC scope"
    assert not drc["unconnected_items"] and not drc["schematic_parity"]
    rows = []
    for violation in drc["violations"]:
        a, b = sorted(i["description"].removeprefix("Footprint ") for i in violation["items"])
        fa, fb = fps[a], fps[b]
        assert {i["uuid"] for i in violation["items"]} == {fa.m_Uuid.AsString(), fb.m_Uuid.AsString()}, "DRC identity mismatch"
        # This only builds an in-memory cache; no KiCad save/export API is used.
        fa.BuildCourtyardCaches(); fb.BuildCourtyardCaches()
        assert fa.GetCourtyard(pcbnew.F_CrtYd).Collide(fb.GetCourtyard(pcbnew.F_CrtYd), 0), "DRC pair does not collide"
        ba, bb = fab_bounds(fa), fab_bounds(fb)
        gap = math.hypot(max(ba[0]-bb[2], bb[0]-ba[2], 0), max(ba[1]-bb[3], bb[1]-ba[3], 0)) / 1e6
        pg = pad["minimumBetweenEachFootprintPair"].get("/".join([a, b]))
        rows.append({"references": [a, b], "drcItemUuids": [i["uuid"] for i in violation["items"]], "classification": group(a, b), "packageFamilies": [family(a), family(b)], "footprints": [parts[a]["fp"], parts[b]["fp"]], "fabBoundsMm": [[round(v/1e6, 6) for v in ba], [round(v/1e6, 6) for v in bb]], "fabEnvelopeGapMm": round(gap, 6), "differentNetPadMinimumMm": pg["clearanceLowerBoundMm"] if pg else None, "disposition": "OPEN: assembler process acceptance or A04 spacing change required"})

    # Focused maximum-dimension check for these exact MPNs, with long axes along Y.
    assert parts["MK2"]["mpn"] == "SPH0641LU4H-1" and parts["U7"]["mpn"] == "TLV75530PDBVR"
    assert fps["MK2"].GetOrientationDegrees() == 0 and fps["U7"].GetOrientationDegrees() == 180
    centres = []
    for ref in ("MK2", "U7"):
        bounds = fab_bounds(fps[ref])
        centres.append([round((bounds[i]+bounds[i+2])/2e6, 6) for i in (0, 1)])
    dy = abs(centres[0][1]-centres[1][1])
    dx = abs(centres[0][0]-centres[1][0])
    assert dx < (2.75+1.75)/2, "Maximum body spans no longer overlap along X"
    native_mic = [fps["MK2"].GetPosition().x/1e6, fps["MK2"].GetPosition().y/1e6]
    max_check = {"references": ["MK2", "U7"], "alignedBodyCentresMm": centres, "nativeMicFootprintOriginMm": native_mic, "micOriginCorrectionYmm": round(centres[0][1]-native_mic[1], 6), "bodyCentreSeparationYmm": round(dy, 6), "nominalBodyLengthsMm": [3.5, 2.9], "maximumBodyLengthsMm": [3.6, 3.05], "maximumBodyGapYmm": round(dy-(3.6+3.05)/2, 6), "interpretation": "Allowed maximum body envelopes overlap in X and by 0.005 mm in Y even with perfect nominal centre placement; this is a worst-case tolerance-envelope conflict, not evidence every sample collides. Placement error and TI mold-flash allowance are not included. Requires A04 clearance redesign or controlled measured engineering deviation before assembly acceptance.", "sources": ["https://www.mouser.com/datasheet/2/218/sph0641lu4h_1_revb-3313002.pdf#page=9", "https://www.ti.com/lit/ds/symlink/tlv755p.pdf#page=41"]}
    assert max_check["maximumBodyGapYmm"] == -0.005, "Focused A03 tolerance result changed"
    next(r for r in rows if r["references"] == ["MK2", "U7"])["disposition"] = "MUST FIX: manufacturer maximum body dimensions produce negative clearance before placement tolerance"
    assert all(r["fabEnvelopeGapMm"] > 0 for r in rows)
    report = {"mode": "READ_ONLY", "board": str(paths["board"].relative_to(ROOT)).replace("\\", "/") if paths["board"].is_relative_to(ROOT) else paths["board"].name, "boardSha256": inputs["board"], "drcSha256": inputs["drc"], "courtyardCount": len(rows), "classificationCounts": dict(collections.Counter(r["classification"] for r in rows)), "nominalFabEnvelopeIntersections": 0, "minimumFabEnvelopeGapMm": min(r["fabEnvelopeGapMm"] for r in rows), "maximumBodyCheck": max_check, "method": "Each of 78 actual DRC footprint pairs is confirmed by native filled F.CrtYd polygon collision. Fab gap is Euclidean separation of axis-aligned bounding boxes of all restored native F.Fab PCB_SHAPE geometry, including stroke width. It is a conservative drawing-envelope lower bound, not a substitute for maximum supplier package/lead tolerances or pick-and-place access. Different-net pad gaps are exact effective native-pad results from the hash-bound existing audit. No acceptance is inferred from a positive Fab gap.", "noBoardOrRuleChanges": True, "rows": sorted(rows, key=lambda r: (r["classification"], r["references"]))}
    assert inputs == {name: sha(paths[name]) for name in inputs}, "An input changed during the review"
    paths["output"].parent.mkdir(parents=True, exist_ok=True)
    paths["output"].write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"output": str(paths["output"]), "boardSha256": inputs["board"], "courtyardPairs": len(rows), "maximumBodyGapYmm": max_check["maximumBodyGapYmm"], "inputFilesUnchanged": True}))


if __name__ == "__main__":
    main()
