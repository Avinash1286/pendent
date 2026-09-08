"""Rip up two blocking charger escapes so status pins receive first escape vias."""
import pcbnew,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
board=pcbnew.LoadBoard(str(root/'output/aura-a03-native-routing.kicad_pcb'))
removed=[]
for t in list(board.GetTracks()):
    net=t.GetNetname();p=t.GetPosition();x=p.x/1e6;y=p.y/1e6
    if net=='CHG_ISET' or (net=='VBAT' and t.GetLayer()==pcbnew.F_Cu and 92<x<96 and 108.4<y<111.5):
        removed.append({'uuid':t.m_Uuid.AsString(),'net':net});board.Remove(t);t.thisown=False
pcbnew.SaveBoard(str(root/'output/aura-a03-native-routing.kicad_pcb'),board)
(root/'output/aura-a03-priority-ripup.json').write_text(json.dumps(removed,indent=2)+'\n')
print('Removed',len(removed),'items for status escape priority')
