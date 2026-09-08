"""Rip up displaced imported routes crossing explicitly planned charger vias."""
import pcbnew,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
report=json.loads((root/'output/kicad-a03-manufacturer-rules-drc.json').read_text())
protected=set(json.loads((root/'output/charger-fanout-protected.json').read_text()))
ids=set()
for v in report['violations']:
    if v['type'] in ('shorting_items','clearance','hole_clearance','solder_mask_bridge','hole_to_hole'):
        candidates=[i for i in v['items'] if i['uuid'] not in protected and i['description'].startswith(('Track ','Via '))]
        assert candidates, 'No removable displaced copper: '+str(v)
        ids.update(i['uuid'] for i in candidates)
board=pcbnew.LoadBoard(str(root/'output/aura-a03-native-routing.kicad_pcb'))
removed=[]
for t in list(board.GetTracks()):
    if t.m_Uuid.AsString() in ids:removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()});board.Remove(t);t.thisown=False
pcbnew.SaveBoard(str(root/'output/aura-a03-native-routing.kicad_pcb'),board)
(root/'output/fanout-displaced-copper.json').write_text(json.dumps(removed,indent=2)+'\n')
print('Removed',len(removed),'conflicting imported tracks/vias; independent rerouting required')
