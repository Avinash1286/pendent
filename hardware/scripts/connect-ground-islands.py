"""Inspect actual filled-ground polygons and bridge separated islands with
checked through vias, preserving the RF exclusion and every foreign net."""
import importlib.util,json,math
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('router',root/'scripts/complete-native-routing.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
board=r.pcbnew.LoadBoard(str(r.BOARD));allitems,drills,smd=r.geometry(board);items=[it for it in allitems if it[1]=='GND'];zoneitems=[]
for z in board.Zones():
    if z.GetIsRuleArea() or z.GetNetname()!='GND':continue
    layer=z.GetLayer();s=z.GetFilledPolysList(layer)
    for i in range(s.OutlineCount()):
        c=s.Outline(i);outer=[r.pt(c.CPoint(k)) for k in range(c.PointCount())];holes=[]
        for h in range(s.HoleCount(i)):
            c=s.Hole(i,h);holes.append([r.pt(c.CPoint(k)) for k in range(c.PointCount())])
        g=r.Polygon(outer,holes);item=(z.m_Uuid.AsString()+':'+str(i),'GND',r.LAYERS.index(layer),g,z);items.append(item);zoneitems.append(item)
parents={it[0]:it[0] for it in items}
def find(a):
    while parents[a]!=a:parents[a]=parents[parents[a]];a=parents[a]
    return a
for layer in range(4):
    group=[it for it in items if it[2]==layer];geoms=[it[3].buffer(.000001) for it in group]
    for a,b in r.STRtree(geoms).query(geoms,predicate='intersects').T:parents[find(group[a][0])]=find(group[b][0])
groups={}
for it in items:groups.setdefault(find(it[0]),[]).append(it)
summary=[]
for key,arr in groups.items():
    area=sum(it[3].area for it in arr if isinstance(it[4],r.pcbnew.ZONE))
    pads=sorted(set((it[4].GetParentFootprint().GetReference(),it[4].GetNumber()) for it in arr if isinstance(it[4],r.pcbnew.PAD)))
    summary.append({'id':key,'area':area,'pads':pads,'items':len(arr),'bounds':r.unary_union([it[3] for it in arr]).bounds})
summary.sort(key=lambda g:g['area'],reverse=True);print(json.dumps(summary,indent=2),flush=True)
main=groups[summary[0]['id']];maincopper=r.unary_union([it[3] for it in main])
foreign=r.unary_union([it[3] for it in allitems if it[1]!='GND']);holes=r.unary_union([g for _,g in drills]);pads=r.unary_union(smd)
boardarea=r.box(98,89,102,111).buffer(10).buffer(-.65).intersection(r.box(0,88.5,200,200))
added=[]
for row in summary[1:]:
    arr=groups[row['id']];island=r.unary_union([it[3] for it in arr]);candidates=r.Polygon()
    for diameter,drill in [(.45,.20),(.40,.20),(.35,.15)]:
        safe=boardarea.difference(foreign.buffer(diameter/2+.123)).difference(holes.buffer(drill/2+.253)).difference(pads.buffer(diameter/2+.04))
        candidates=safe.intersection(island.buffer(-.01)).intersection(maincopper)
        if not candidates.is_empty:break
    if candidates.is_empty:print('No stitch candidate for',row['id'],flush=True);continue
    point=candidates.representative_point();p=(round(point.x,4),round(point.y,4))
    v=r.pcbnew.PCB_VIA(board);v.SetPosition(r.pos(p));v.SetWidth(r.pcbnew.FromMM(diameter));v.SetDrill(r.pcbnew.FromMM(drill));v.SetLayerPair(r.pcbnew.F_Cu,r.pcbnew.B_Cu);v.SetViaType(r.pcbnew.VIATYPE_THROUGH);v.SetNet(board.FindNet('GND'));board.Add(v);added.append({'position':p,'diameter':diameter,'drill':drill})
if added:
    board.BuildConnectivity();assert r.pcbnew.ZONE_FILLER(board).Fill(board.Zones());r.pcbnew.SaveBoard(str(r.BOARD),board)
(root/'output/aura-a03-ground-islands.json').write_text(json.dumps({'groupsBefore':summary,'addedVias':added},indent=2)+'\n')
print('Added ground island bridges',added)
