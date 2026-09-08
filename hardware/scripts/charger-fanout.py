"""Stagger three charger escape vias to preserve each 0.4mm-pitch channel."""
import importlib.util,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('router',root/'scripts/complete-native-routing.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
pcbnew=r.pcbnew;board=pcbnew.LoadBoard(str(r.BOARD))
items,_,_=r.geometry(board);area=r.box(93,108.6,95.6,110.6);right=r.box(96.5,107.9,99.2,111.7);ids=set()
for uuid,net,li,g,it in items:
    if net in ('VBAT','CHG_STAT2','CHG_DISABLE') and isinstance(it,(pcbnew.PCB_TRACK,pcbnew.PCB_VIA)) and (li==0 or isinstance(it,pcbnew.PCB_VIA)) and g.intersects(area):ids.add(uuid)
    if net in ('DOCK_IN','CHG_STAT1','CHG_ISET','CHG_VSET','TS_MON') and isinstance(it,(pcbnew.PCB_TRACK,pcbnew.PCB_VIA)) and (li==0 or isinstance(it,pcbnew.PCB_VIA)) and g.intersects(right):ids.add(uuid)
for it in list(board.GetTracks()):
    if it.m_Uuid.AsString() in ids:board.Remove(it);it.thisown=False
fanouts={
 'VBAT':(.15,[(94.85,109.15),(93.375,109.15)]),
 'CHG_STAT2':(.10,[(94.85,109.55),(94.525,109.55),(94.5,109.575),(94.0,109.575)]),
 'CHG_DISABLE':(.10,[(94.85,109.95),(94.525,109.95),(94.375,110.1),(93.375,110.1)]),
 'DOCK_IN':(.15,[(97.05,108.75),(97.3,108.75),(97.85,108.2)]),
 'CHG_STAT1':(.10,[(97.05,109.15),(97.6,109.15),(97.8,108.95),(97.85,108.95)]),
 'CHG_ISET':(.10,[(97.05,109.55),(97.65,109.55),(97.75,109.65),(97.85,109.65)]),
 'CHG_VSET':(.10,[(97.05,109.95),(97.55,109.95),(97.85,110.25),(97.85,110.35)]),
 'TS_MON':(.10,[(97.05,110.35),(97.55,110.85),(97.85,111.15)])}
protected=[]
for name,(width,points) in fanouts.items():
    net=board.FindNet(name)
    for a,b in zip(points,points[1:]):
        t=pcbnew.PCB_TRACK(board);t.SetStart(r.pos(a));t.SetEnd(r.pos(b));t.SetLayer(pcbnew.F_Cu);t.SetWidth(pcbnew.FromMM(width));t.SetNet(net);board.Add(t);protected.append(t.m_Uuid.AsString())
    via=pcbnew.PCB_VIA(board);via.SetPosition(r.pos(points[-1]));via.SetWidth(pcbnew.FromMM(.45));via.SetDrill(pcbnew.FromMM(.20));via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(net);board.Add(via);protected.append(via.m_Uuid.AsString())
pcbnew.SaveBoard(str(r.BOARD),board)
(root/'output/charger-fanout-protected.json').write_text(json.dumps(protected,indent=2)+'\n')
print('Replaced',len(ids),'local items with explicit staggered charger fanouts')
