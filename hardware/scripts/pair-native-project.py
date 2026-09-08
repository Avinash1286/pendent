"""Package the frozen routed board and schematic as a linked, editable project.

Run with KiCad's Python after routing/library restoration. This writes native/;
it does not overwrite the working routing or original schematic files.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import pcbnew

ROOT = Path(__file__).resolve().parents[1]
CLI = Path(pcbnew.__file__).parents[2] / 'kicad-cli.exe'
if not CLI.exists():
    CLI = Path('C:/Program Files/KiCad/10.0/bin/kicad-cli.exe')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def blocks(text):
    """Offsets of direct children of a complete s-expression; honor strings."""
    depth = 0
    quoted = escaped = False
    start = None
    for i, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == '(':
            if depth == 1:
                start = i
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 1:
                yield start, i + 1
    assert depth == 0 and not quoted


STACK = '''(stackup
      (layer "F.SilkS" (type "Top Silk Screen") (color "White"))
      (layer "F.Mask" (type "Top Solder Mask") (color "Green"))
      (layer "F.Cu" (type "copper") (thickness 0.035))
      (layer "dielectric 1" (type "prepreg") (thickness 0.0994) (material "FR4 3313"))
      (layer "In1.Cu" (type "copper") (thickness 0.0152))
      (layer "dielectric 2" (type "core") (thickness 0.5) (material "FR4"))
      (layer "In2.Cu" (type "copper") (thickness 0.0152))
      (layer "dielectric 3" (type "prepreg") (thickness 0.0994) (material "FR4 3313"))
      (layer "B.Cu" (type "copper") (thickness 0.035))
      (layer "B.Mask" (type "Bottom Solder Mask") (color "Green"))
      (layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))
      (copper_finish "ENIG")
      (dielectric_constraints no)
    )'''


def memberships(xml):
    return {net.attrib['name']: sorted((n.attrib['ref'], n.attrib['pin'])
            for n in net.findall('node')) for net in xml.find('nets')}


def routed_geometry(board):
    # Native save can renumber numeric net codes after adding named NC nets.
    # Electrical net names, not transient integers, identify routed copper.
    return sorted((t.m_Uuid.AsString(), t.GetClass(), t.GetLayer(), t.GetNetname(),
                   t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y,
                   t.GetWidth(pcbnew.F_Cu) if isinstance(t, pcbnew.PCB_VIA) else t.GetWidth(),
                   t.GetDrillValue() if isinstance(t, pcbnew.PCB_VIA) else 0)
                  for t in board.GetTracks())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    working = ROOT / 'output/aura-a03-native-routing.kicad_pcb'
    initial = sha(working)
    assert initial == args.expected_sha256.lower(), 'Working board changed'
    out = ROOT / 'native'
    out.mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location('fingerprints', ROOT / 'scripts/restore-native-footprint-library.py')
    fp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fp)
    board = pcbnew.LoadBoard(str(working))
    before_pads, before_copper = fp.pad_fingerprint(board), routed_geometry(board)
    original = ET.parse(ROOT / 'output/aura-a03-native.net.xml').getroot()
    comps = {c.attrib['ref']: c for c in original.find('components')}
    nc_names = {}
    for net in original.find('nets'):
        if net.attrib['name'].startswith('unconnected-'):
            members = net.findall('node')
            assert len(members) == 1
            member = members[0]
            nc_names[(member.attrib['ref'], member.attrib['pin'])] = net.attrib['name']
    assert len(nc_names) == 37
    paths = {}
    ids = {}
    for footprint in board.GetFootprints():
        ref = footprint.GetReference()
        comp = comps[ref]
        ids[ref] = str(footprint.GetFPID().GetLibItemName())
        assert footprint.GetFPID().GetLibNickname() == 'AURA_PCB', 'Restore native snapshot library first'
        parts = comp.find('sheetpath').attrib['tstamps'].strip('/').split('/')
        parts += comp.findtext('tstamps').split()
        path = pcbnew.KIID_PATH()
        for part in filter(None, parts):
            path.push_back(pcbnew.KIID(part))
        footprint.SetPath(path)
        footprint.SetValue(comp.findtext('value'))
        footprint.SetSheetname(comp.find('sheetpath').attrib['names'].strip('/'))
        props = {p.attrib['name']: p.attrib.get('value', '') for p in comp.findall('property')}
        footprint.SetSheetfile(props.get('Sheetfile', ''))
        for field in comp.findall('fields/field'):
            name = field.attrib['name']
            if name in ('Footprint', 'Reference', 'Value'):
                continue
            footprint.SetField(name, field.text or '')
            footprint.GetField(name).SetVisible(False)
            footprint.GetField(name).SetLayer(pcbnew.F_Fab)
        for pad in footprint.Pads():
            nc_name = nc_names.get((ref, pad.GetNumber()))
            if nc_name:
                assert not pad.GetNetname(), 'Expected an intentional unassigned NC pad'
                net = pcbnew.NETINFO_ITEM(board, nc_name)
                board.Add(net)
                pad.SetNet(net)
        paths[ref] = path.AsString()
    assert len(paths) == 61 == len(set(paths.values()))
    board.GetDesignSettings().SetAuxOrigin(pcbnew.VECTOR2I(pcbnew.FromMM(100), pcbnew.FromMM(100)))
    target = out / 'aura-a03.kicad_pcb'
    pcbnew.SaveBoard(str(target), board)
    text = target.read_text()
    assert '(stackup' not in text, 'Review existing stackup before replacing it'
    text = text.replace('(setup', '(setup\n    ' + STACK, 1)
    target.write_text(text)
    saved = pcbnew.LoadBoard(str(target))
    expected_pads = sorted(tuple(list(p[:3]) + [nc_names.get((p[0], p[2]), p[3])] + list(p[4:]))
                           for p in before_pads)
    assert expected_pads == fp.pad_fingerprint(saved), 'Pad geometry or intended net identity changed'
    assert before_copper == routed_geometry(saved), 'Routed copper changed'
    assert all(f.GetPath().AsString() == paths[f.GetReference()] for f in saved.GetFootprints())
    assert saved.GetDesignSettings().m_HasStackup
    changed_refs = []
    schematics = ['aura-a03-electrical'] + ['a03-' + n for n in ('radio', 'audio', 'storage', 'charging', 'controls')]
    for name in schematics:
        text = (ROOT / 'output' / (name + '.kicad_sch')).read_text()
        edits = []
        for start, end in blocks(text):
            block = text[start:end]
            if not re.match(r'\(symbol\s', block):
                continue
            ref_match = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
            if not ref_match or ref_match[1] not in ids:
                continue
            ref = ref_match[1]
            block, count = re.subn(r'(\(property\s+"Footprint"\s+)"[^"]*"',
                                  lambda m: m[1] + json.dumps('AURA_PCB:' + ids[ref]), block, count=1)
            assert count == 1
            edits.append((start, end, block))
            changed_refs.append(ref)
        for start, end, block in reversed(edits):
            text = text[:start] + block + text[end:]
        # MCP created individual symbols under two temporary project names.
        # Each symbol has one instance project; preserve paths/annotations while
        # giving the packaged hierarchy one consistent project name.
        text = re.sub(r'\(project\s+"aura-a03-(?:electrical|native-routing|working)"',
                      '(project "aura-a03"', text)
        dest = 'aura-a03' if name == 'aura-a03-electrical' else name
        (out / (dest + '.kicad_sch')).write_text(text)
    assert sorted(changed_refs) == sorted(ids)
    project = json.loads((ROOT / 'output/aura-a03-native-routing.kicad_pro').read_text())
    schematic_project = json.loads((ROOT / 'output/aura-a03-electrical.kicad_pro').read_text())
    for key in ('erc', 'schematic'):
        if key in schematic_project:
            project[key] = schematic_project[key]
    project['meta']['filename'] = 'aura-a03.kicad_pro'
    (out / 'aura-a03.kicad_pro').write_text(json.dumps(project, indent=2) + '\n')
    for table in ('fp-lib-table', 'sym-lib-table'):
        shutil.copyfile(ROOT / 'output' / table, out / table)
    xml_path = out / 'aura-a03.net.xml'
    subprocess.run([str(CLI), 'sch', 'export', 'netlist', '--format', 'kicadxml', '-o', str(xml_path), str(out / 'aura-a03.kicad_sch')], check=True, timeout=60)
    exported = ET.parse(xml_path).getroot()
    assert memberships(original) == memberships(exported), 'Schematic connectivity changed'
    for comp in exported.find('components'):
        ref = comp.attrib['ref']
        assert comp.findtext('footprint') == 'AURA_PCB:' + ids[ref]
    assert initial == sha(working), 'Working board changed during packaging; redo on freeze'
    result = {'status': 'PASS', 'inputBoardSha256': initial, 'pairedBoardSha256': sha(target),
              'linkedReferences': 61, 'schematicNetSetsUnchanged': True, 'padGeometryUnchanged': True,
              'intendedConnectedPinAssignmentsUnchanged': True, 'intentionalNcNamesAssigned': 37,
              'internalNetCodesMayBeRenumbered': True,
              'routedCopperUnchanged': True, 'uniqueSchematicPaths': paths,
              'stackup': {'template': 'JLC04081H-3313', 'nominalThicknessMm': 0.8, 'materialSumMm': 0.7992,
                          'layersMm': [0.035, 0.0994, 0.0152, 0.5, 0.0152, 0.0994, 0.035]},
              'plotOriginNativeMm': [100, 100], 'physicalQualification': False}
    (out / 'project-linkage.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'uniqueSchematicPaths'}, indent=2))


if __name__ == '__main__':
    main()
