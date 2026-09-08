"""Remove disconnected copper islands containing no component pad.

Use before ground zones: geometry connectivity is independent of the ratsnest
distance heuristic. This never deletes pads or ignores intended connections.
"""
import importlib.util,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('router',root/'scripts/complete-native-routing.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
from shapely import STRtree
board=r.pcbnew.LoadBoard(str(r.BOARD));assert not board.Zones(),'Run before zones only'
items,_,_=r.geometry(board);parents={it[0]:it[0] for it in items}
def find(a):
    while parents[a]!=a:parents[a]=parents[parents[a]];a=parents[a]
    return a
for net in sorted(set(it[1] for it in items)):
    for layer in range(4):
        group=[it for it in items if it[1]==net and it[2]==layer]
        if not group:continue
        geoms=[it[3].buffer(.000001) for it in group]
        pairs=STRtree(geoms).query(geoms,predicate='intersects')
        for a,b in pairs.T:
            ra=find(group[a][0]);rb=find(group[b][0]);parents[ra]=rb
has_pad={find(it[0]) for it in items if isinstance(it[4],r.pcbnew.PAD)}
removed=[]
for t in list(board.GetTracks()):
    if find(t.m_Uuid.AsString()) not in has_pad:
        removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()});board.Remove(t);t.thisown=False
r.pcbnew.SaveBoard(str(r.BOARD),board)
with (root/'output/aura-a03-orphan-copper-removal.jsonl').open('a') as f:f.write(json.dumps(removed)+'\n')
print('Removed',len(removed),'orphan copper items in groups without a physical pad')
