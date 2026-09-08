"""Remove only imported copper that collides with relocated passive pads.

The native DRC report is retained as an audit of every removal; all resulting
connections are explicitly rerouted and rechecked, never excluded from DRC.
"""
import pcbnew,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
report=json.loads((root/'output/kicad-a03-shifted-charger-drc.json').read_text())
board=pcbnew.LoadBoard(str(root/'output/aura-a03-native-routing.kicad_pcb'))
ids=set()
for v in report['violations']:
    if v['type'] in ('shorting_items','clearance','hole_clearance','solder_mask_bridge'):
        if any(i['description'].startswith('Pad ') for i in v['items']):
            ids.update(i['uuid'] for i in v['items'] if i['description'].startswith(('Track ','Via ')))
removed=[]
for t in list(board.GetTracks()):
    if t.m_Uuid.AsString() in ids:
        removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()});board.Remove(t);t.thisown=False
pcbnew.SaveBoard(str(root/'output/aura-a03-native-routing.kicad_pcb'),board)
(root/'output/aura-a03-displaced-copper.json').write_text(json.dumps(removed,indent=2)+'\n')
print('Removed',len(removed),'colliding items; subsequent routing and DRC required')
