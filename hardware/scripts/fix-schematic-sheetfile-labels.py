"""Lower only five overview sheet-file labels in both native schematic roots.

The source and paired overview are edited identically. Every byte outside the
five Y-coordinate fields is preserved, including all UUIDs and circuit content.
No board or child schematic is changed.
"""
import hashlib, json, re, shutil
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r'(\(property "Sheet file" "(?P<name>[^"\n]+)"\s*\(at (?P<x>[-\d.]+) )(?P<y>[-\d.]+)(?P<suffix> 0\))')
EXPECTED = {'a03-radio.kicad_sch': Decimal('73.81'), 'a03-audio.kicad_sch': Decimal('73.81'),
            'a03-storage.kicad_sch': Decimal('128.81'), 'a03-charging.kicad_sch': Decimal('128.81'),
            'a03-controls.kicad_sch': Decimal('183.81')}

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    backup = ROOT.parent / '.scratch/sheetfile-label-layout'
    backup.mkdir(exist_ok=True)
    records=[]; matched_positions=[]
    for rel in ('output/aura-a03-electrical.kicad_sch', 'native/aura-a03.kicad_sch'):
        path=ROOT/rel; text=path.read_bytes().decode('utf-8'); before=digest(path)
        matches=list(PATTERN.finditer(text))
        assert len(matches)==5 and {m['name'] for m in matches}==set(EXPECTED)
        changes=[]
        def replace(m):
            desired=EXPECTED[m['name']]; current=Decimal(m['y'])
            assert current in (desired,desired-Decimal('2.54')), 'Unexpected overview label coordinate'
            changes.append({'sheet':m['name'],'x':m['x'],'oldY':m['y'],'newY':str(desired)})
            return m.group(1)+str(desired)+m['suffix']
        updated=PATTERN.sub(replace,text)
        mask=lambda s:PATTERN.sub(lambda m:m.group(1)+'__SHEETFILE_Y__'+m['suffix'],s)
        assert mask(text)==mask(updated), 'Content beyond sheetfile Y positions changed'
        assert re.findall(r'\(uuid\s+[^)]+\)',text)==re.findall(r'\(uuid\s+[^)]+\)',updated)
        saved=backup/(path.parent.name+'-'+path.name)
        if not saved.exists():shutil.copy2(path,saved)
        path.write_bytes(updated.encode('utf-8'))
        positions=[(m['name'],m['x'],m['y']) for m in PATTERN.finditer(updated)]
        matched_positions.append(positions)
        records.append({'path':rel,'inputSha256':before,'outputSha256':digest(path),
                        'fieldPositions':changes,'allOtherBytesUnchanged':True,'allUuidsUnchanged':True})
    assert matched_positions[0]==matched_positions[1], 'Source/paired field positions differ'
    result={'status':'PASS','operation':'Only five Sheet file Y coordinates per overview moved down 2.54 mm',
            'boardTouched':False,'childSchematicsTouched':False,'roots':records}
    (ROOT/'output/native-sheetfile-layout-checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
