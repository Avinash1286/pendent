"""Local charger escape refinement; electrical pins and external interfaces fixed."""
from pathlib import Path
import pcbnew,json
root=Path(__file__).resolve().parents[1]
path=root/'output/aura-a03-native-routing.kicad_pcb'
board=pcbnew.LoadBoard(str(path))
changes={'C7':(-1.3,-9.85),'C8':(-8.0,-9.05),'R22':(-8.5,-13.4),'R23':(-8.5,-11.5),'D1':(.8,-9.05),'C10':(.9,-10.55),'C18':(-2.05,-13.3),'R7':(-3.55,-1.4),'C17':(-5.55,-1.8)}
report=[]
for fp in board.GetFootprints():
    ref=fp.GetReference()
    if ref in changes:
        x,y=changes[ref];old=fp.GetPosition()
        report.append({'ref':ref,'before':[old.x/1e6-100,100-old.y/1e6],'after':[x,y]})
        fp.SetPosition(pcbnew.VECTOR2I(round((100+x)*1e6),round((100-y)*1e6)))
pcbnew.SaveBoard(str(path),board)
(root/'output/aura-a03-placement-refinement.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
