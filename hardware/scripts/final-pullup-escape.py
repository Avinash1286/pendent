"""Place the pull-up escape via using clear outer copper, then reroute the
small number of inner-layer segments displaced by that through via."""
import importlib.util,json,math
from pathlib import Path
root=Path(__file__).resolve().parents[1]
DIAMETER=.35;DRILL=.15
spec=importlib.util.spec_from_file_location('router',root/'scripts/complete-native-routing.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
b=r.pcbnew.LoadBoard(str(r.BOARD));items,drills,smd=r.geometry(b)
pad=next(p for f in b.GetFootprints() if f.GetReference()=='R7' for p in f.Pads() if p.GetNumber()=='1');start=r.pt(pad.GetPosition());net=pad.GetNetname()
foreign=[it for it in items if it[1]!=net]
fcu=r.unary_union([it[3] for it in foreign if it[2]==0])
allpads=r.unary_union([it[3] for it in foreign if isinstance(it[4],r.pcbnew.PAD)])
allholes=r.unary_union([g for _,g in drills]);smds=r.unary_union(smd);candidates=[]
for dx in r.np.arange(-1.5,1.501,.05):
 for dy in r.np.arange(-1.5,1.501,.05):
    p=(round(start[0]+float(dx),3),round(start[1]+float(dy),3));point=r.Point(p)
    if point.distance(smds)<DIAMETER/2+.04 or point.distance(allpads)<DIAMETER/2+.123 or point.distance(allholes)<DRILL/2+.253:continue
    if point.distance(fcu)<DIAMETER/2+.123:continue
    trace=r.LineString([start,p])
    if trace.distance(fcu)<.174:continue
    conflicts={it[0]:it for it in foreign if it[3].distance(point)<DIAMETER/2+.123}
    if any(isinstance(it[4],r.pcbnew.PAD) for it in conflicts.values()):continue
    candidates.append((len(conflicts)*5+math.dist(start,p),p,conflicts))
assert candidates,'No physically clear pull-up escape candidate'
_,p,conflicts=min(candidates,key=lambda c:c[0]);print('Pull-up via',p,'displaces',[(it[1],it[0]) for it in conflicts.values()],flush=True)
for it in list(b.GetTracks()):
    g=next((v[3] for v in items if v[0]==it.m_Uuid.AsString()),None)
    ce=it.GetNetname()=='CHG_DISABLE' and it.GetLayer()==r.pcbnew.In2_Cu and g.intersects(r.box(93.25,108.75,94.35,109.85))
    if it.m_Uuid.AsString() in conflicts or ce:b.Remove(it);it.thisown=False
t=r.pcbnew.PCB_TRACK(b);t.SetStart(r.pos(start));t.SetEnd(r.pos(p));t.SetWidth(r.pcbnew.FromMM(.1));t.SetLayer(r.pcbnew.F_Cu);t.SetNet(pad.GetNet());b.Add(t)
v=r.pcbnew.PCB_VIA(b);v.SetPosition(r.pos(p));v.SetWidth(r.pcbnew.FromMM(DIAMETER));v.SetDrill(r.pcbnew.FromMM(DRILL));v.SetLayerPair(r.pcbnew.F_Cu,r.pcbnew.B_Cu);v.SetViaType(r.pcbnew.VIATYPE_THROUGH);v.SetNet(pad.GetNet());b.Add(v)
r.pcbnew.SaveBoard(str(r.BOARD),b)
(root/'output/aura-a03-pullup-escape.json').write_text(json.dumps({'ref':'R7','pin':'1','via':p,'displaced':[{'uuid':it[0],'net':it[1]} for it in conflicts.values()]},indent=2)+'\n')
