"""Read-only pad-centroid alignment audit; never saves a board."""
from pathlib import Path
import json, math
import pcbnew
root=Path(__file__).resolve().parents[1]
board=pcbnew.LoadBoard(str(root/'output/aura-a03-native-routing.kicad_pcb'))
manifest=json.loads((root/'output/design-manifest.json').read_text())
specs=json.loads((root/'src/footprints.json').read_text())
parts={p['ref']:p for p in manifest['parts']}
def xy(v): return [round(v.x/1e6,6),round(v.y/1e6,6)]
records=[]
for f in sorted(board.GetFootprints(),key=lambda f:f.GetReference()):
    ref=f.GetReference(); part=parts[ref]
    if ref.startswith('J'):
        directory=root/'library.pretty'; name=part['mpn']
    else:
        directory=root/'library'; name=specs[part['fp']]['library'].split(':')[1]
    orig=pcbnew.FootprintLoad(str(directory),name)
    if orig is None: raise RuntimeError(f'Missing source {directory/name}')
    orig.SetParent(board)
    orig.SetOrientation(f.GetOrientation())
    if ref.startswith('J'):
        orig.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    elif f.GetLayer()==pcbnew.B_Cu:
        orig.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
    n1=next(p for p in f.Pads() if p.GetNumber()=='1')
    o1=next(p for p in orig.Pads() if p.GetNumber()=='1')
    delta=n1.GetPosition()-o1.GetPosition()
    orig.SetPosition(orig.GetPosition()+delta)
    errors=[]
    for p in f.Pads():
        number=p.GetNumber()
        if not number: continue
        other=[q for q in orig.Pads() if q.GetNumber()==number]
        if not other: errors.append({'pin':number,'missingInSource':True}); continue
        error=min(math.hypot(p.GetPosition().x-q.GetPosition().x,p.GetPosition().y-q.GetPosition().y)/1e6 for q in other)
        if error>0.000002: errors.append({'pin':number,'errorMm':round(error,6),'native':xy(p.GetPosition()),'source':xy(other[0].GetPosition())})
    graphics=[g for g in orig.GraphicalItems() if g.GetLayer() in [pcbnew.F_Fab,pcbnew.B_Fab,pcbnew.F_CrtYd,pcbnew.B_CrtYd] and isinstance(g,pcbnew.PCB_SHAPE)]
    records.append({'ref':ref,'source':str((directory/(name+'.kicad_mod')).relative_to(root)),'layer':board.GetLayerName(f.GetLayer()),'rotation':f.GetOrientationDegrees(),'nativeOrigin':xy(f.GetPosition()),'alignedSourceOrigin':xy(orig.GetPosition()),'graphics':len(graphics),'errors':errors})
out={'board':'output/aura-a03-native-routing.kicad_pcb','mode':'READ_ONLY','footprints':records,'failedAlignments':sum(bool(r['errors']) for r in records)}
(root/'output/native-footprint-alignment-audit.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'footprints':len(records),'failedAlignments':out['failedAlignments'],'details':[r for r in records if r['errors'] or r['ref'] in ['MK1','U1','SW1','J1']]},indent=2))
