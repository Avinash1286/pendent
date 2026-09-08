"""Read-only via-to-SMD-copper and via-to-paste audit of actual native geometry.

Uses KiCad's SHAPE collision engine, including custom pads and exact arc strokes.
Paste pad dimensions follow KiCad PCB_IO plot_board_layers.cpp: resolved per-axis
GetSolderPasteMargin includes both absolute and relative margins. No board save.
"""
import argparse, hashlib, json, sys, time, traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import pcbnew

ROOT = Path(__file__).resolve().parents[1]
PLOT_SOURCE = 'https://docs.kicad.org/doxygen/plot__board__layers_8cpp_source.html'
CAPABILITY_SOURCE = 'https://jlcpcb.com/capabilities/pcb-capabilities'

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def xy(point): return [point.x / 1e6, point.y / 1e6]

def native_clearance(a, b):
    if a.Collide(b, 0): return [0, 0]
    lo, hi = 0, 1000000
    while not a.Collide(b, hi): hi *= 2
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if a.Collide(b, mid): hi = mid
        else: lo = mid
    return [lo / 1e6, hi / 1e6]

def paste_clone(pad, layer):
    """Reproduce the native paste plotting transformations for supported lands.

    Reject unsupported non-empty shapes instead of approximating them. Current
    board's pasted pads are rectangles or circles; mic ring paste is arc graphics.
    Keep the clone alive while the returned effective SHAPE is used.
    """
    clone = pcbnew.PAD(pad)
    margin = pad.GetSolderPasteMargin(layer)
    size = pad.GetSize(layer)
    newsize = pcbnew.VECTOR2I(size.x + 2 * margin.x, size.y + 2 * margin.y)
    shape = pad.GetShape(layer)
    if shape != pcbnew.PAD_SHAPE_CUSTOM and (newsize.x <= 0 or newsize.y <= 0):
        return clone, None, margin
    if shape in (pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL):
        clone.SetSize(layer, newsize)
    elif shape == pcbnew.PAD_SHAPE_RECT:
        clone.SetSize(layer, newsize)
        if margin.x > 0:
            clone.SetShape(layer, pcbnew.PAD_SHAPE_ROUNDRECT)
            clone.SetRoundRectCornerRadius(layer, margin.x)
    elif shape == pcbnew.PAD_SHAPE_ROUNDRECT:
        radius = pad.GetRoundRectCornerRadius(layer)
        ratio = pad.GetRoundRectRadiusRatio(layer)
        clone.SetSize(layer, newsize)
        if margin.x == margin.y:
            clone.SetRoundRectCornerRadius(layer, max(0, radius + margin.x))
        else:
            clone.SetRoundRectRadiusRatio(layer, ratio)
    elif shape == pcbnew.PAD_SHAPE_CUSTOM and margin.x == 0 and margin.y == 0:
        pass
    else:
        raise RuntimeError('Unsupported paste land, require native plotting implementation: '
                           + pad.GetParentFootprint().GetReference() + '.' + pad.GetNumber()
                           + ' shape=' + str(shape) + ' margin=' + str(xy(margin)))
    return clone, clone.GetEffectiveShape(layer), margin

def public_target(target):
    return {k: v for k, v in target.items() if k not in ('nativeShape', 'owner', 'nativeLayer')}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', default='output/aura-a03-native-routing.kicad_pcb')
    args = parser.parse_args()
    path = ROOT / args.board
    before = digest(path)
    start = time.monotonic()
    board = pcbnew.LoadBoard(str(path))
    targets = []
    suppressed = []
    inventory = Counter()
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            base = {'reference': footprint.GetReference(), 'pad': pad.GetNumber(),
                    'uuid': pad.m_Uuid.AsString(), 'net': pad.GetNetname(),
                    'netCode': pad.GetNetCode(), 'positionMm': xy(pad.GetPosition()),
                    'padShape': int(pad.GetShape())}
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
                    if pad.IsOnLayer(layer):
                        targets.append(dict(base, kind='smd_copper', layer=board.GetLayerName(layer),
                                            nativeLayer=layer, nativeShape=pad.GetEffectiveShape(layer), owner=pad))
                        inventory['smd_copper_' + board.GetLayerName(layer)] += 1
            for layer in (pcbnew.F_Paste, pcbnew.B_Paste):
                if not pad.IsOnLayer(layer): continue
                clone, shape, margin = paste_clone(pad, layer)
                desc = dict(base, kind='pad_paste', layer=board.GetLayerName(layer),
                            resolvedPasteMarginMm=xy(margin), plottedSizeMm=xy(clone.GetSize(layer)))
                if shape is None:
                    suppressed.append(desc)
                    continue
                targets.append(dict(desc, nativeLayer=layer, nativeShape=shape, owner=clone))
                inventory['pad_paste_' + board.GetLayerName(layer)] += 1
        for graphic in footprint.GraphicalItems():
            if graphic.GetLayer() not in (pcbnew.F_Paste, pcbnew.B_Paste): continue
            if not isinstance(graphic, pcbnew.PCB_SHAPE):
                raise RuntimeError('Unsupported footprint paste graphic: ' + type(graphic).__name__)
            layer = graphic.GetLayer()
            targets.append({'reference': footprint.GetReference(), 'pad': None,
                            'uuid': graphic.m_Uuid.AsString(), 'net': None, 'netCode': None,
                            'kind': 'graphic_paste', 'graphicShape': int(graphic.GetShape()),
                            'strokeWidthMm': graphic.GetWidth() / 1e6,
                            'layer': board.GetLayerName(layer), 'nativeLayer': layer,
                            'nativeShape': graphic.GetEffectiveShape(layer), 'owner': graphic})
            inventory['graphic_paste_' + board.GetLayerName(layer)] += 1
    for graphic in board.GetDrawings():
        if graphic.GetLayer() in (pcbnew.F_Paste, pcbnew.B_Paste):
            raise RuntimeError('Board-level paste drawing requires an explicit native shape audit: '
                               + graphic.m_Uuid.AsString())
    vias = []
    intersections = []
    tests = Counter()
    for item in board.GetTracks():
        if not isinstance(item, pcbnew.PCB_VIA): continue
        if item.GetViaType() != pcbnew.VIATYPE_THROUGH:
            raise RuntimeError('Unexpected non-through via requires explicit layer-range drill handling')
        position = item.GetPosition()
        drill = item.GetDrillValue()
        hole = pcbnew.SHAPE_CIRCLE(position, drill // 2)
        disks = {layer: pcbnew.SHAPE_CIRCLE(position, item.GetWidth(layer) // 2)
                 for layer in (pcbnew.F_Cu, pcbnew.B_Cu) if item.IsOnLayer(layer)}
        via = {'uuid': item.m_Uuid.AsString(), 'positionMm': xy(position),
               'net': item.GetNetname(), 'netCode': item.GetNetCode(),
               'drillMm': drill / 1e6,
               'diameterMm': {board.GetLayerName(layer): item.GetWidth(layer) / 1e6 for layer in disks},
               'nativeViaType': int(item.GetViaType()),
               'nativeCappingMode': int(item.GetCappingMode()),
               'nativeFillingMode': int(item.GetFillingMode()),
               'nativePrimaryDrillCappedFlag': item.GetPrimaryDrillCappedFlag(),
               'nativePrimaryDrillFilledFlag': item.GetPrimaryDrillFilledFlag(),
               'tented': {board.GetLayerName(layer): item.IsTented(layer) for layer in disks}}
        vias.append(via)
        for target in targets:
            layer = pcbnew.F_Cu if target['nativeLayer'] in (pcbnew.F_Cu, pcbnew.F_Paste) else pcbnew.B_Cu
            if layer not in disks: continue
            shape = target['nativeShape']
            tests[target['kind']] += 1
            copper_hit = shape.Collide(disks[layer], 0)
            drill_hit = shape.Collide(hole, 0)
            if not copper_hit and not drill_hit: continue
            center_inside = shape.Collide(position, 0)
            # Use exact integer engine decisions; never substitute a body or
            # aperture bounding rectangle. Same-net hits remain in the report.
            intersections.append({'via': via, 'target': public_target(target),
                                  'copperDiscIntersects': copper_hit,
                                  'drillOpeningIntersects': drill_hit,
                                  'drillCenterInside': center_inside,
                                  'drillToTargetClearanceBoundsMm': native_clearance(shape, hole),
                                  'classification': 'drill_overlap' if drill_hit else 'annulus_only_overlap',
                                  'sameNet': None if target['netCode'] is None else item.GetNetCode() == target['netCode']})
    if digest(path) != before:
        raise RuntimeError('Board changed during audit; rerun on the latest stable native board')
    intersections.sort(key=lambda r: (r['via']['positionMm'], r['target']['layer'],
                                      r['target']['reference'], r['target']['pad'] or '', r['target']['uuid']))
    classes = Counter((r['target']['kind'], r['classification']) for r in intersections)
    paste_hits = [r for r in intersections if r['target']['kind'] != 'smd_copper']
    copper_hits = [r for r in intersections if r['target']['kind'] == 'smd_copper']
    summary = {'viaCount': len(vias), 'targetInventory': dict(inventory), 'comparisons': dict(tests),
               'intersections': len(intersections), 'uniqueIntersectingVias': len({r['via']['uuid'] for r in intersections}),
               'pasteIntersections': len(paste_hits), 'uniquePasteIntersectingVias': len({r['via']['uuid'] for r in paste_hits}),
               'pasteDrillOverlaps': sum(r['drillOpeningIntersects'] for r in paste_hits),
               'pasteAnnulusOnlyOverlaps': sum(not r['drillOpeningIntersects'] for r in paste_hits),
               'smdCopperIntersections': len(copper_hits),
               'smdCopperDrillOverlaps': sum(r['drillOpeningIntersects'] for r in copper_hits),
               'smdCopperAnnulusOnlyOverlaps': sum(not r['drillOpeningIntersects'] for r in copper_hits),
               'differentNetCopperIntersections': sum(r['sameNet'] is False for r in copper_hits),
               'classCounts': {' / '.join(k): v for k, v in classes.items()}}
    report = {'schemaVersion': 1, 'mode': 'READ_ONLY', 'verifiedAt': datetime.now(timezone.utc).isoformat(),
              'board': str(path.relative_to(ROOT)), 'inputSha256': before, 'boardUnchanged': True,
              'nativeVersion': pcbnew.GetBuildVersion(),
              'status': 'INTERSECTIONS_REQUIRE_REVIEW' if intersections else 'PASS_NO_INTERSECTIONS',
              'method': {'copper': 'Native PAD.GetEffectiveShape on actual front/back SMD copper; custom holes retained.',
                         'paste': 'Resolved GetSolderPasteMargin per axis; native clone shape follows KiCad plotter size/corner changes. Separate paste-only microphone arcs use PCB_SHAPE.GetEffectiveShape.',
                         'collision': 'Native SHAPE.Collide at zero clearance against the actual drill disk and outer copper disk. Same-net pairs included. Coordinates in mm; native units 1 nm.',
                         'interpretation': 'A hole intersecting paste or an SMD land is a via-in-pad manufacturing concern. Annular-ring-only overlap is reported separately. Normal mask tenting is not epoxy filling plus capping, and no fabrication acceptance is inferred.',
                         'plotSource': PLOT_SOURCE, 'manufacturingSource': CAPABILITY_SOURCE,
                         'scope': 'All through-vias versus front/back SMD copper and actual paste apertures. Does not claim drill-wall, copper-trace clearance, soldermask dam, or component-body compliance.',
                         'noRuleExclusions': True},
              'summary': summary, 'suppressedZeroAreaPastePads': suppressed,
              'vias': vias, 'intersections': intersections, 'elapsedSeconds': round(time.monotonic() - start, 3)}
    output = ROOT / 'output/native-via-aperture-audit.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    lines = [
        '# Native A03 via, SMD copper and paste aperture audit', '',
        'Read-only native KiCad geometry audit, ' + report['verifiedAt'] + '.', '',
        '**Board:** `hardware/' + report['board'].replace('\\', '/') + '`.', '',
        '**Board SHA-256:** `' + before + '`. The checksum was unchanged before and after the audit. No PCB, aperture, via, rule or library was changed.', '',
        '**Result:** ' + str(summary['viaCount']) + ' through-vias checked; '
        + str(summary['pasteDrillOverlaps']) + ' drill-to-paste intersections; '
        + str(summary['smdCopperDrillOverlaps']) + ' drill-to-SMD-copper intersections. '
        + str(summary['uniqueIntersectingVias']) + ' via(s) have at least one copper-disc or drill intersection.', '',
        '## All intersections', '',
        '| Via UUID | Via center (mm) | Net | Diameter / drill (mm) | Target | Layer | Classification | Drill-to-target gap (mm) |',
        '|---|---|---|---|---|---|---|---|'
    ]
    for hit in intersections:
        v, t = hit['via'], hit['target']
        gap = hit['drillToTargetClearanceBoundsMm']
        lines.append('| `' + v['uuid'] + '` | ' + ', '.join(f'{x:.6f}' for x in v['positionMm'])
                     + ' | ' + v['net'] + ' | ' + str(v['diameterMm']['F.Cu']) + ' / ' + str(v['drillMm'])
                     + ' | ' + t['reference'] + ('.' + t['pad'] if t['pad'] is not None else ' paste arc `' + t['uuid'] + '`')
                     + ' | ' + t['layer'] + ' | ' + hit['classification'].replace('_', ' ')
                     + ' | ' + f'{gap[0]:.6f}–{gap[1]:.6f}' + ' |')
    if not intersections: lines.append('| None | — | — | — | — | — | — | — |')
    lines += ['', 'An annulus-only overlap means the via\'s copper disk intersects the target while its complete drilled opening remains outside. Both the hole disk and hole center are tested separately. A small positive computed gap is not a fabrication-tolerance allowance; the board owner must review and correct marginal geometry.', '',
              'Normal soldermask tenting is distinct from a specified filled and capped via-in-pad process. Native tenting and filling/capping flags are recorded per via in the JSON; no acceptance of a via-in-pad process is inferred from tenting. This audit introduces no exclusions.', '',
              '## Geometry and coverage', '',
              '- ' + str(inventory['smd_copper_F.Cu']) + ' front and ' + str(inventory['smd_copper_B.Cu']) + ' back SMD copper objects; custom microphone annuli retain their actual holes.',
              '- ' + str(inventory['pad_paste_F.Paste']) + ' front and ' + str(inventory['pad_paste_B.Paste']) + ' back pad paste apertures, plus ' + str(inventory['graphic_paste_F.Paste']) + ' independent microphone paste arc strokes.',
              '- Paste sizes use KiCad\'s resolved per-axis absolute-plus-ratio margin. C3/C4 have −0.100 mm on each edge. The copper-only microphone rings are not incorrectly treated as solid paste rings.',
              '- ' + str(sum(tests.values())) + ' native shape comparisons: ' + str(tests['smd_copper']) + ' copper, ' + str(tests['pad_paste']) + ' pad paste, ' + str(tests['graphic_paste']) + ' graphic paste. Same-net geometry is included.',
              '- No bounding-box substitute determines any intersection. Native pad shapes and native graphic arc strokes use `SHAPE.Collide` against exact native circles. Distance brackets have 1 nm computational resolution and do not describe production tolerance.', '',
              'The paste construction follows the [KiCad native plotter](https://docs.kicad.org/doxygen/plot__board__layers_8cpp_source.html). Manufacturing context comes from [JLCPCB rigid-board capabilities](https://jlcpcb.com/capabilities/pcb-capabilities).', '',
              '## Reproduce', '',
              "From the repository's `hardware/` directory:", '', '```powershell',
              "& 'C:/Program Files/KiCad/10.0/bin/python.exe' scripts/audit-native-via-apertures.py", '```', '',
              '[Audit script](../hardware/scripts/audit-native-via-apertures.py) · [Complete machine-readable results](../hardware/output/native-via-aperture-audit.json)', '',
              'This bounded audit does not substitute for trace/via DRC, drill-wall spacing, soldermask-dam checks, assembly-body clearance, or fabrication/assembly qualification. Any later board edit invalidates this exact hash-bound result.', '']
    (ROOT.parent / 'docs/native-via-aperture-audit.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'boardSha256': before,
                      'summary': summary, 'report': str(output.relative_to(ROOT)),
                      'elapsedSeconds': report['elapsedSeconds']}, indent=2))

if __name__ == '__main__':
    try: main()
    except Exception:
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
