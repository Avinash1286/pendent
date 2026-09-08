"""Read-only KiCad land-pattern audit; writes JSON evidence, never CAD.

Run with KiCad's bundled Python, which provides pcbnew. The candidate is
unassigned. Proposed placement calculations are not native placement checks.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parents[2]
FOOTPRINT = ROOT / "hardware/a04/AuraA04.pretty/Nidec_CUS22TB_Candidate.kicad_mod"
BOARD = ROOT / "hardware/a04/aura-a04.kicad_pcb"
REPORT = Path(__file__).with_name("cus22-candidate-verification.json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mm(vector):
    return [pcbnew.ToMM(vector.x), pcbnew.ToMM(vector.y)]


def same(actual, expected):
    return len(actual) == len(expected) and all(
        abs(a - b) <= 1e-6 for a, b in zip(actual, expected)
    )


def main():
    before = {str(p.relative_to(ROOT)): digest(p) for p in (FOOTPRINT, BOARD)}
    fp = pcbnew.FootprintLoad(str(FOOTPRINT.parent), FOOTPRINT.stem)
    if fp is None:
        raise RuntimeError("KiCad could not parse the candidate")
    expected = {
        "1": (-2.25, -2.55, .7, 1.5), "2": (.75, -2.55, .7, 1.5),
        "3": (2.25, -2.55, .7, 1.5), "4": (-2.25, 2.55, .7, 1.5),
        "5": (.75, 2.55, .7, 1.5), "6": (2.25, 2.55, .7, 1.5),
        "MP1": (-3.65, -1.8, 1, .8), "MP2": (3.65, -1.8, 1, .8),
        "MP3": (-3.65, 1.8, 1, .8), "MP4": (3.65, 1.8, 1, .8),
    }
    errors, rows, holes, seen = [], [], [], set()
    for pad in fp.Pads():
        number = pad.GetNumber()
        at, size = mm(pad.GetPosition()), mm(pad.GetSize())
        if not number:
            holes.append(at)
            if (pad.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH
                    or pad.GetShape() != pcbnew.PAD_SHAPE_CIRCLE
                    or not same(size, [.9, .9])
                    or not same(mm(pad.GetDrillSize()), [.9, .9])
                    or pad.IsOnLayer(pcbnew.F_Paste)
                    or pad.IsOnLayer(pcbnew.B_Paste)):
                errors.append("Unnumbered locator is not a paste-free 0.9 mm NPTH")
            continue
        if number in seen or number not in expected:
            errors.append(f"Unexpected/duplicate numbered pad: {number}")
            continue
        seen.add(number)
        if (not same(at + size, expected[number])
                or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                or pad.GetShape() != pcbnew.PAD_SHAPE_RECT
                or set(pad.GetLayerSet().Seq()) != {
                    pcbnew.F_Cu, pcbnew.F_Mask, pcbnew.F_Paste
                } or not same(mm(pad.GetDrillSize()), [0, 0])
                or abs(pad.GetOrientationDegrees()) > 1e-6):
            errors.append(f"Pad {number} differs from independently transcribed land drawing")
        # Algebraic prediction ONLY. Never flip, place, save or export CAD here.
        cx, cy = 13.5 + at[1], -at[0]
        width, height = size[1], size[0]
        corners = [(cx + sx * width / 2, cy + sy * height / 2)
                   for sx in (-1, 1) for sy in (-1, 1)]
        edge_margin = 17.6 - max(math.hypot(x, y) for x, y in corners)
        # Euclidean distance from M1's upper-right notch centre to pad rectangle.
        nx, ny, nr = 16.5, 6.5, 3.05
        dx = max(abs(nx - cx) - width / 2, 0)
        dy = max(abs(ny - cy) - height / 2, 0)
        notch_margin = math.hypot(dx, dy) - nr
        rows.append({
            "pad": number, "sourceCentreMm": at, "sourceSizeMm": size,
            "proposedCadCentreMm": [round(cx, 6), round(cy, 6)],
            "proposedNativeCentreMm": [round(100 + cx, 6), round(100 - cy, 6)],
            "proposedNativeSizeMm": [width, height],
            "unnotchedCircleCopperMarginMm": round(edge_margin, 6),
            "oldM1UpperRightNotchMarginMm": round(notch_margin, 6),
        })
    if seen != set(expected):
        errors.append("Missing numbered pads")
    if len(holes) != 2 or not all(same(a, b) for a, b in zip(
            sorted(holes), [[-1.5, 0], [1.5, 0]])):
        errors.append("Locator count/coordinates differ from drawing")
    rects = list(fp.GraphicalItems())
    for layer, start, end, stroke in (
        (pcbnew.F_CrtYd, [-4.45, -3.6], [4.45, 3.6], .05),
        (pcbnew.F_Fab, [-3.35, -2.05], [3.35, 2.05], .1),
    ):
        matches = [item for item in rects if item.GetLayer() == layer]
        if (len(matches) != 1 or not same(mm(matches[0].GetStart()), start)
                or not same(mm(matches[0].GetEnd()), end)
                or matches[0].GetShape() != pcbnew.S_RECT
                or abs(pcbnew.ToMM(matches[0].GetWidth()) - stroke) > 1e-6):
            errors.append(f"Unexpected rectangle on layer {layer}")
    native = pcbnew.LoadBoard(str(BOARD))
    count = len(list(native.GetFootprints()))
    unchanged = all(digest(ROOT / path) == value for path, value in before.items())
    if not unchanged:
        errors.append("A CAD source changed during read-only audit")
    report = {
        "status": "unassigned candidate; not fabrication or placement approval",
        "source": "https://www.nidec-components.com/e/catalog/switch/cus.pdf",
        "sourceView": "component-side interpretation inferred from drawing geometry",
        "authoredThrough": "mcp__kicad__create_footprint",
        "parser": f"KiCad {pcbnew.GetBuildVersion()}",
        "hashes": before, "auditScriptSha256": digest(Path(__file__)),
        "landPatternCheckPass": not errors, "errors": errors,
        "landPatternCheckScope": "numbered pads, NPTHs and fab/courtyard rectangles only; excludes adoption gates below",
        "footprintAttributeBits": fp.GetAttributes(),
        "classifiedAsSmd": bool(fp.GetAttributes() & pcbnew.FP_SMD),
        "silkscreenGraphicsCount": sum(g.GetLayer() == pcbnew.F_SilkS for g in rects),
        "cadSourcesUnchangedByAudit": unchanged,
        "nativeBoardFootprints": count,
        "nativeBoardThicknessMm": pcbnew.ToMM(native.GetDesignSettings().GetBoardThickness()),
        "nativePlacementVerified": False,
        "schematicAssignmentCheckedByThisAudit": False,
        "groundTabContinuityQualified": False,
        "fabricationReady": False,
        "padCount": len(list(fp.Pads())), "locatorsMm": sorted(holes),
        "proposedUndersideTransform": "CAD X=13.5+sourceY; CAD Y=-sourceX; native X=100+CAD X; native Y=100-CAD Y",
        "proposedPadGeometry": rows,
        "minimumUnnotchedCopperMarginMm": min(r["unnotchedCircleCopperMarginMm"] for r in rows),
        "minimumOldM1NotchMarginMm": min(r["oldM1UpperRightNotchMarginMm"] for r in rows),
        "proposedCourtyardCircleMarginMm": round(17.6 - math.hypot(13.5 + 3.6, 4.45), 6),
        "nominalActuatorCadXMm": 14.85,
        "derivedActuatorTransverseEnvelopeMm": [14.1, 15.6],
        "actuatorEnvelopeExcludes": "locator, part-placement and assembly play",
        "exclusions": [
            "Footprint-level SMD classification, pin1/actuator orientation marking and assembly-export inclusion",
            "Stencil/reflow suitability, actual terminal and solder envelopes, actuation forces and safe overtravel",
            "Actual native bottom flip and placement; the table is an algebraic prediction",
            "Final M2 outline, all populated parts, tolerance stack and reflow qualification",
            "MP1-MP4 symbol/net mapping and supplier tab-continuity confirmation",
            "NPTH finished-hole tolerance and supplier process approval",
        ],
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "landPatternCheckPass", "errors", "padCount", "minimumUnnotchedCopperMarginMm",
        "minimumOldM1NotchMarginMm", "nativeBoardFootprints", "fabricationReady"
    )}))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
