"""Generate prototype manufacturing/review files from native/aura-a03.

Requires KiCad Python. Unconnected items, schematic mismatch, ERC findings, or
non-assembly DRC errors stop the export. Courtyard findings remain visible.
"""
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import pcbnew

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'native'
BOARD = NATIVE / 'aura-a03.kicad_pcb'
CLI = Path('C:/Program Files/KiCad/10.0/bin/kicad-cli.exe')
if not CLI.exists():
    CLI = Path('kicad-cli')


def run(*args):
    result = subprocess.run([str(CLI), *map(str, args)], check=True, capture_output=True, text=True, timeout=90)
    print(result.stdout.strip(), flush=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def attach_clearance_audits(review, board_sha):
    """Keep additional manufacturing checks bound to the exact exported board."""
    names = ('native-smd-pad-spacing-audit.json', 'native-via-aperture-audit.json')
    reports = []
    for name, expected in zip(names, ('PASS', 'PASS_NO_INTERSECTIONS')):
        source = ROOT / 'output' / name
        report = json.loads(source.read_text())
        assert report['inputSha256'] == board_sha and report['boardUnchanged'], 'Stale clearance audit: ' + name
        assert report['status'] == expected, 'Failed clearance audit: ' + name
        reports.append(report)
    assert reports[0]['violationCount'] == 0 and reports[1]['summary']['intersections'] == 0
    for name in names:
        shutil.copyfile(ROOT / 'output' / name, review / name)
    return {'padSpacing': {'status': reports[0]['status'], 'differentNetPairs': reports[0]['testedLayerPairs'],
                           'violations': 0, 'thresholdMm': reports[0]['thresholdMm']},
            'viaApertures': {'status': reports[1]['status'], 'vias': reports[1]['summary']['viaCount'],
                             'comparisons': sum(reports[1]['summary']['comparisons'].values()), 'intersections': 0}}


def exported_files():
    return [{'path': str(p.relative_to(NATIVE)).replace('\\', '/'), 'bytes': p.stat().st_size, 'sha256': sha(p)}
            for directory in (NATIVE / 'fabrication', NATIVE / 'assembly', NATIVE / 'review')
            for p in sorted(directory.rglob('*')) if p.is_file() and p.name != 'manufacturing-checks.json']


def main():
    initial = sha(BOARD)
    review = NATIVE / 'review'
    gerbers = NATIVE / 'fabrication/gerbers'
    drills = NATIVE / 'fabrication/drills'
    assembly = NATIVE / 'assembly'
    stencil = assembly / 'stencil'
    for directory in (review, gerbers, drills, assembly, stencil):
        directory.mkdir(parents=True, exist_ok=True)
    clearance_audits = attach_clearance_audits(review, initial)
    run('pcb', 'drc', '--format', 'json', '--all-track-errors', '--schematic-parity',
        '--severity-all', '-o', review / 'drc.json', BOARD)
    run('sch', 'erc', '--format', 'json', '--severity-all', '-o', review / 'erc.json', NATIVE / 'aura-a03.kicad_sch')
    drc = json.loads((review / 'drc.json').read_text())
    erc = json.loads((review / 'erc.json').read_text())
    violations = drc['violations']
    assert not drc['unconnected_items'], 'Unconnected board; do not export'
    assert not drc.get('schematic_parity'), 'Schematic/PCB parity findings; do not export'
    assert not [v for v in violations if v['severity'] == 'error' and v['type'] != 'courtyards_overlap'], 'Non-assembly DRC errors; do not export'
    assert not [v for sheet in erc['sheets'] for v in sheet.get('violations', [])], 'ERC findings; do not export'
    run('pcb', 'export', 'gerbers', '--layers', 'F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,Edge.Cuts',
        '--use-drill-file-origin', '--subtract-soldermask', '--check-zones', '-o', gerbers, BOARD)
    run('pcb', 'export', 'drill', '--format', 'excellon', '--drill-origin', 'plot', '--excellon-units', 'mm',
        '--excellon-separate-th', '--generate-map', '--map-format', 'pdf', '--generate-report',
        '--report-path', drills / 'drill-report.txt', '-o', drills, BOARD)
    run('pcb', 'export', 'gerbers', '--layers', 'F.Paste,B.Paste', '--use-drill-file-origin', '-o', stencil, BOARD)
    run('pcb', 'export', 'ipcd356', '-o', NATIVE / 'fabrication/aura-a03.ipc', BOARD)
    run('pcb', 'export', 'pos', '--format', 'csv', '--units', 'mm', '--use-drill-file-origin',
        '--side', 'both', '-o', assembly / 'native-footprint-origins.csv', BOARD)
    run('pcb', 'export', 'pdf', '--layers', 'F.Cu,In1.Cu,In2.Cu,B.Cu,F.Fab,B.Fab,Edge.Cuts',
        '--common-layers', 'Edge.Cuts', '--mode-multipage', '-o', review / 'board-layers.pdf', BOARD)
    run('sch', 'export', 'pdf', '-o', review / 'schematic.pdf', NATIVE / 'aura-a03.kicad_sch')
    parts = json.loads((ROOT / 'output/design-manifest.json').read_text())['parts']
    source = {p['ref']: p for p in parts}
    board = pcbnew.LoadBoard(str(BOARD))
    footprints = {f.GetReference(): f for f in board.GetFootprints()}
    assert set(footprints) == set(source) and len(source) == 61
    rows = []
    origin_checks = []
    libraries = json.loads((ROOT / 'src/footprints.json').read_text())
    for part in parts:
        if part['mpn'].startswith('AURA-'):
            continue  # Custom copper contacts are not placement-machine components.
        f = footprints[part['ref']]
        assert abs((f.GetOrientationDegrees() - part.get('r', 0)) % 360) < 1e-6
        library_name = libraries[part['fp']]['library'].split(':')[1]
        original = pcbnew.FootprintLoad(str(ROOT / 'library'), library_name)
        assert original is not None, 'Missing original component land pattern'
        original.SetParent(board)
        original.SetOrientation(f.GetOrientation())
        n1 = next(p for p in f.Pads() if p.GetNumber() == '1')
        o1 = next(p for p in original.Pads() if p.GetNumber() == '1')
        original.SetPosition(original.GetPosition() + n1.GetPosition() - o1.GetPosition())
        for pad in f.Pads():
            if not pad.GetNumber():
                continue
            candidates = [p for p in original.Pads() if p.GetNumber() == pad.GetNumber()]
            residual = min(math.hypot(p.GetPosition().x-pad.GetPosition().x,
                                     p.GetPosition().y-pad.GetPosition().y) / 1e6 for p in candidates)
            assert residual <= 0.000002, 'Native pad alignment differs: ' + part['ref']
        actual_x = pcbnew.ToMM(original.GetPosition().x) - 100
        actual_y = 100 - pcbnew.ToMM(original.GetPosition().y)
        assert abs(actual_x - part['x']) <= 0.000002 and abs(actual_y - part['y']) <= 0.000002, \
            'Source component centre differs from native PCB: ' + part['ref']
        origin_checks.append({'reference': part['ref'], 'nativeAlignedCentreMm': [actual_x, actual_y],
                              'sourceCentreMm': [part['x'], part['y']], 'status': 'PASS'})
        rows.append([part['ref'], part['mpn'], part['x'], part['y'], part.get('r', 0) % 360, 'Top',
                     'Manufacturer body/reference origin; verify assembler zero-angle convention'])
    assert len(rows) == 57
    with (assembly / 'component-centres.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['Designator', 'MPN', 'MidX_mm', 'MidY_mm', 'Rotation_deg', 'Layer', 'Convention'])
        writer.writerows(rows)
    with (assembly / 'bom.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['Reference', 'Quantity', 'MPN', 'Value', 'NativeFootprint', 'AssemblyStatus'])
        for part in parts:
            if part['mpn'].startswith('AURA-'):
                continue
            writer.writerow([part['ref'], 1, part['mpn'], part['value'], 'AURA_PCB:A03_' + part['ref'],
                             'Candidate; dense assembly and supplier qualification pending'])
    via_sizes = Counter((round(pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)), 4), round(pcbnew.ToMM(t.GetDrillValue()), 4))
                        for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA))
    drill_files = sorted(drills.glob('*.drl'))
    assert len(drill_files) == 2, 'Expected separate PTH and NPTH drill files'
    for path in drill_files:
        content = path.read_text()
        assert 'M48' in content and 'METRIC' in content and 'M30' in content
    plotted = list(gerbers.glob('*'))
    gerber_content = '\n'.join(p.read_text() for p in plotted if p.suffix != '.gbrjob')
    for function in ('Copper,L1,Top', 'Copper,L2,Inr', 'Copper,L3,Inr', 'Copper,L4,Bot', 'Profile,NP'):
        assert function in gerber_content, 'Missing Gerber X2 layer: ' + function
    assert all('M02*' in p.read_text() for p in plotted if p.suffix != '.gbrjob')
    assert sha(BOARD) == initial, 'Export unexpectedly changed native board'
    report = {'status': 'CONNECTED_PROTOTYPE_FABRICATION_REVIEW', 'boardSha256': initial,
              'boardUnchangedDuringExport': True, 'unconnectedItems': 0, 'schematicParityFindings': 0,
              'ercErrors': 0, 'ercWarnings': 0, 'bareBoardDrcErrors': 0,
              'drcFindingsByType': dict(Counter(v['type'] for v in violations)),
              'assemblyApproved': False, 'physicalQualification': False,
              'additionalClearanceAudits': clearance_audits,
              'componentCount': 61, 'placementCandidates': 57,
              'componentOriginChecks': origin_checks,
              'throughVias': [{'diameterMm': size[0], 'drillMm': size[1], 'count': count} for size, count in sorted(via_sizes.items())],
              'plotOrigin': 'Board centre; positive Y toward necklace bail; all Gerber/drill files use the same auxiliary origin',
              'positionFiles': {'component-centres.csv': 'Body/reference centres from checked source, not converter origins',
                                'native-footprint-origins.csv': 'Raw native CAD origins for comparison; includes custom contacts'},
              'files': exported_files()}
    (review / 'manufacturing-checks.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('files', 'componentOriginChecks')}, indent=2))


if __name__ == '__main__':
    main()
