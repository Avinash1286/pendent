"""Finish finite native-DRC ratsnest gaps using a conservative four-layer grid.

The search respects every imported copper item, the rounded board, antenna
exclusion, drilled holes and no-via-in-SMD-pad constraint. Every result must be
accepted by the independent KiCad CLI DRC; this search is not a DRC substitute.
Run using KiCad Python after tools/python Shapely installation.
"""
import sys, json, heapq, math, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/python'))
import numpy as np
from scipy.ndimage import label
from shapely.geometry import Point, Polygon, LineString, box
from shapely.ops import unary_union
from shapely import intersects_xy,STRtree
import pcbnew

BOARD=ROOT/'output/aura-a03-native-routing.kicad_pcb'
DRC=ROOT/'output/kicad-a03-manufacturer-rules-drc.json'
STEP=.025; CLEAR=.12; WIDTH=.10; MARGIN=.004
LAYERS=[pcbnew.F_Cu,pcbnew.In1_Cu,pcbnew.In2_Cu,pcbnew.B_Cu]
xs=np.arange(88,112.0001,STEP);ys=np.arange(79,121.0001,STEP)
X,Y=np.meshgrid(xs,ys);NY,NX=X.shape;PLANE=NX*NY
def mm(v):return v/1e6
def pt(v):return(mm(v.x),mm(v.y))
def pos(p):return pcbnew.VECTOR2I(round(p[0]*1e6),round(p[1]*1e6))
def poly(item,layer):
    s=pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(s,layer,0,1000,pcbnew.ERROR_OUTSIDE)
    result=[]
    for i in range(s.OutlineCount()):
        c=s.Outline(i);outer=[pt(c.CPoint(k)) for k in range(c.PointCount())]
        holes=[]
        for h in range(s.HoleCount(i)):
            c=s.Hole(i,h);holes.append([pt(c.CPoint(k)) for k in range(c.PointCount())])
        if len(outer)>2:result.append(Polygon(outer,holes))
    return unary_union(result)
def geometry(board):
    items=[];drills=[];smd=[]
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            for li,l in enumerate(LAYERS):
                if pad.IsOnLayer(l):
                    g=poly(pad,l)
                    if not g.is_empty:items.append((pad.m_Uuid.AsString(),pad.GetNetname(),li,g,pad))
            if pad.GetDrillSize().x:
                drills.append((pad.GetNetname(),Point(pt(pad.GetPosition())).buffer(mm(max(pad.GetDrillSize().x,pad.GetDrillSize().y))/2)))
            elif pad.GetAttribute()==pcbnew.PAD_ATTRIB_SMD:
                smd.append(poly(pad,pad.GetLayer()))
    for t in board.GetTracks():
        if isinstance(t,pcbnew.PCB_VIA):
            g=Point(pt(t.GetPosition())).buffer(mm(t.GetWidth(pcbnew.F_Cu))/2)
            for li,l in enumerate(LAYERS):items.append((t.m_Uuid.AsString(),t.GetNetname(),li,g,t))
            drills.append((t.GetNetname(),Point(pt(t.GetPosition())).buffer(mm(t.GetDrill())/2)))
        else:
            g=LineString([pt(t.GetStart()),pt(t.GetEnd())]).buffer(mm(t.GetWidth())/2)
            items.append((t.m_Uuid.AsString(),t.GetNetname(),LAYERS.index(t.GetLayer()),g,t))
    return items,drills,smd
def mask(g):
    out=np.zeros((NY,NX),dtype=bool)
    if g.is_empty:return out
    x0,y0,x1,y1=g.bounds
    ix0=max(0,int((x0-88)/STEP)-1);ix1=min(NX,int((x1-88)/STEP)+2)
    iy0=max(0,int((y0-79)/STEP)-1);iy1=min(NY,int((y1-79)/STEP)+2)
    out[iy0:iy1,ix0:ix1]=intersects_xy(g,X[iy0:iy1,ix0:ix1],Y[iy0:iy1,ix0:ix1])
    return out
def index(x,y,li):return li*PLANE+y*NX+x
def decode(i):li,rem=divmod(i,PLANE);y,x=divmod(rem,NX);return x,y,li
def search(board,a,b):
    items,drills,smd=geometry(board)
    source=[it for it in items if it[0]==a];target=[it for it in items if it[0]==b]
    assert source and target,(a,b)
    net=source[0][1];print('Search',net,a,b,flush=True)
    assert target[0][1]==net
    # A native ratsnest chooses one nearby item, which can be a boxed-in stub.
    # Search between the full physical copper islands instead, preserving every
    # real pad attachment while allowing connection at any accessible point.
    netitems=[it for it in items if it[1]==net]
    roots={it[0]:it[0] for it in netitems}
    def root_of(v):
        while roots[v]!=v:roots[v]=roots[roots[v]];v=roots[v]
        return v
    for layer in range(4):
        group=[it for it in netitems if it[2]==layer]
        if not group:continue
        geometries=[it[3].buffer(.000001) for it in group]
        for ia,ib in STRtree(geometries).query(geometries,predicate='intersects').T:
            roots[root_of(group[ia][0])]=root_of(group[ib][0])
    ar=root_of(a);br=root_of(b)
    if ar==br:print('Already physically connected',flush=True);return True
    source=[it for it in netitems if root_of(it[0])==ar];target=[it for it in netitems if root_of(it[0])==br]
    outline=box(98,89,102,111).buffer(10,resolution=64)
    area=outline.buffer(-(.3+WIDTH/2+MARGIN)).intersection(box(0,88.05+WIDTH/2+MARGIN,200,200))
    inside=mask(area);free=np.broadcast_to(inside,(4,NY,NX)).copy()
    foreign=[]
    for li in range(4):
        g=unary_union([it[3] for it in items if it[2]==li and it[1]!=net])
        foreign.append(g);free[li]&=~mask(g.buffer(CLEAR+WIDTH/2+MARGIN))
    holes=unary_union([g for n,g in drills])
    foreign_holes=unary_union([g for n,g in drills if n!=net or not n])
    free&=~mask(foreign_holes.buffer(.20+WIDTH/2+MARGIN))
    # Own holes may be entered by their matching copper: do not block existing
    # via annuli as track destinations, but never allow crossing bare NPTH.
    for it in items:
        if it[1]==net and isinstance(it[4],pcbnew.PCB_VIA):
            free[it[2]]|=mask(it[3].buffer(-WIDTH/2)) & inside
    via_area=outline.buffer(-(.3+.225+MARGIN)).intersection(box(0,88.05+.225+MARGIN,200,200))
    via_ok=mask(via_area)
    via_ok&=~mask(unary_union(foreign).buffer(.225+CLEAR+MARGIN))
    via_ok&=~mask(holes.buffer(.1+.25+MARGIN))
    via_ok&=~mask(unary_union(smd).buffer(.225+.03))
    # Existing same-net through vias already connect every copper layer. Reuse
    # their conductive annulus rather than requiring space for a duplicate via.
    existing_vias=set()
    for it in items:
        if it[1]==net and isinstance(it[4],pcbnew.PCB_VIA):
            px,py=pt(it[4].GetPosition());xx=round((px-88)/STEP);yy=round((py-79)/STEP)
            if 0<=xx<NX and 0<=yy<NY and free[:,yy,xx].all():via_ok[yy,xx]=True;existing_vias.add((xx,yy))
    start=np.zeros_like(free);goal=np.zeros_like(free)
    for it in source:start[it[2]]|=mask(it[3].buffer(-WIDTH/2*.8))&free[it[2]]
    for it in target:goal[it[2]]|=mask(it[3].buffer(-WIDTH/2*.8))&free[it[2]]
    starts=np.flatnonzero(start);goals=np.flatnonzero(goal)
    if '--debug' in sys.argv:
        colors=['#ed5e62','#73b8e8','#d099ef','#7de2b8']
        parts=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="88 98 20 16" width="1200" height="960"><rect x="88" y="98" width="20" height="16" fill="#111827"/>']
        for it in items:
            if it[2]==0:parts.append('<g fill="'+('#60fa99' if it[1]==net else '#9ca3af')+'" stroke="none">'+it[3].svg(fill_color=('#60fa99' if it[1]==net else '#9ca3af')).replace('stroke-width="2.0"','stroke-width="0.01"').replace('stroke="#555555"','stroke="none"')+'</g>')
        for y in range(0,NY,5):
            for x in range(0,NX,5):
                if via_ok[y,x] and 98<ys[y]<114:parts.append(f'<circle cx="{xs[x]}" cy="{ys[y]}" r=".012" fill="#38bdf8"/>')
        for arr,color in [(source,'#facc15'),(target,'#fb7185')]:
            for it in arr:
                p=it[3].centroid;parts.append(f'<circle cx="{p.x}" cy="{p.y}" r=".1" fill="{color}"/>')
        parts.append('</svg>');(ROOT/'output/route-debug.svg').write_text(''.join(parts))
    if not len(starts) or not len(goals):print('No valid endpoint samples',len(starts),len(goals),flush=True);return False
    # Prove the endpoint regions communicate before searching a large grid.
    region=np.zeros_like(free,dtype=np.int32);offset=0
    for l in range(4):
        rr,n=label(free[l]);region[l]=np.where(rr,rr+offset,0);offset+=n
    parents=list(range(offset+1))
    def find(a):
        while parents[a]!=a:parents[a]=parents[parents[a]];a=parents[a]
        return a
    for la in range(4):
        for lb in range(la+1,4):
            ids=via_ok&free[la]&free[lb]
            for ra,rb in np.unique(np.stack([region[la][ids],region[lb][ids]],axis=1),axis=0):parents[find(int(ra))]=find(int(rb))
    roots={find(int(v)) for v in region.ravel()[starts]}
    if not any(find(int(v)) in roots for v in region.ravel()[goals]):
        print('Source pads',[(it[4].GetParentFootprint().GetReference(),it[4].GetNumber()) for it in source if isinstance(it[4],pcbnew.PAD)],flush=True)
        print('Target pads',[(it[4].GetParentFootprint().GetReference(),it[4].GetNumber()) for it in target if isinstance(it[4],pcbnew.PAD)],flush=True)
        for tag,ids in [('source',starts),('target',goals)]:
            vals=np.unique(region.ravel()[ids])
            for val in vals:
                zz,yy,xx=np.where(region==val)
                print(tag,'island',int(val),'layers',np.unique(zz).tolist(),'bounds',xs[xx.min()],ys[yy.min()],xs[xx.max()],ys[yy.max()],flush=True)
        print('Endpoints are in isolated copper-free regions; reroute surrounding tracks before retry',flush=True);return False
    gy,gx=np.where(np.any(goal,axis=0));gx0,gx1=gx.min(),gx.max();gy0,gy1=gy.min(),gy.max()
    goal_layers=set(np.where(goal)[0].tolist())
    def h(x,y,l):return math.hypot(max(gx0-x,0,x-gx1),max(gy0-y,0,y-gy1))+(0 if l in goal_layers else 30)
    costs=np.full(4*PLANE,np.inf,dtype=np.float32);parent=np.full(4*PLANE,-2,dtype=np.int32)
    heap=[]
    for i in starts:
        x,y,l=decode(int(i));costs[i]=0;parent[i]=-1;heapq.heappush(heap,(h(x,y,l),0,int(i)))
    goalflat=goal.ravel();freeflat=free.ravel();count=0;done=None;t0=time.time()
    directions=[(-1,0,1),(1,0,1),(0,-1,1),(0,1,1),(-1,-1,math.sqrt(2)),(1,-1,math.sqrt(2)),(-1,1,math.sqrt(2)),(1,1,math.sqrt(2))]
    while heap:
        _,cost,i=heapq.heappop(heap)
        if cost>costs[i]+.001:continue
        if goalflat[i]:done=i;break
        x,y,l=decode(i);count+=1
        if count%100000==0:print(' expanded',count,'queue',len(heap),'sec',round(time.time()-t0,1),flush=True)
        if count>2200000:break
        for dx,dy,w in directions:
            xx=x+dx;yy=y+dy
            if not(0<=xx<NX and 0<=yy<NY):continue
            j=index(xx,yy,l)
            if not freeflat[j]:continue
            if dx and dy and not(free[l,y,xx] and free[l,yy,x]):continue
            c=cost+w
            if c+1e-4<costs[j]:costs[j]=c;parent[j]=i;heapq.heappush(heap,(c+h(xx,yy,l),c,j))
        if via_ok[y,x]:
            for ll in range(4):
                if ll==l or not free[ll,y,x]:continue
                j=index(x,y,ll);c=cost+30
                if c+1e-4<costs[j]:costs[j]=c;parent[j]=i;heapq.heappush(heap,(c+h(x,y,ll),c,j))
    if done is None:print('No route',count,flush=True);return False
    raw=[]
    while done>=0:raw.append(decode(done));done=int(parent[done])
    raw.reverse();path=[]
    for i,p in enumerate(raw):
        if i==0 or i==len(raw)-1 or tuple(np.subtract(p,raw[i-1]))!=tuple(np.subtract(raw[i+1],p)):path.append(p)
    code=source[0][4].GetNetCode();added=[];vias=set()
    for a,b in zip(path,path[1:]):
        x,y,l=a;xx,yy,ll=b
        if l!=ll:
            if (x,y) not in vias and (x,y) not in existing_vias:
                v=pcbnew.PCB_VIA(board);v.SetPosition(pos((xs[x],ys[y])));v.SetWidth(pcbnew.FromMM(.45));v.SetDrill(pcbnew.FromMM(.2));v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNetCode(code);board.Add(v);added.append(v);vias.add((x,y))
        else:
            t=pcbnew.PCB_TRACK(board);t.SetStart(pos((xs[x],ys[y])));t.SetEnd(pos((xs[xx],ys[yy])));t.SetWidth(pcbnew.FromMM(WIDTH));t.SetLayer(LAYERS[l]);t.SetNetCode(code);board.Add(t);added.append(t)
    pcbnew.SaveBoard(str(BOARD),board)
    print('Added',net,len(added),'segments/vias',len(vias),'expanded',count,'seconds',round(time.time()-t0,1),flush=True)
    log=ROOT/'output/aura-a03-manual-route-log.jsonl'
    with log.open('a') as f:f.write(json.dumps({'net':net,'source':source[0][0],'target':target[0][0],'width':WIDTH,'grid':STEP,'newVias':len(vias),'items':[it.m_Uuid.AsString() for it in added],'path':[[round(float(xs[x]),4),round(float(ys[y]),4),pcbnew.LayerName(LAYERS[l])] for x,y,l in path]})+'\n')
    return True

if __name__=='__main__':
    board=pcbnew.LoadBoard(str(BOARD))
    report=json.loads(DRC.read_text())
    if '--pair' in sys.argv:
        first,second=sys.argv[sys.argv.index('--pair')+1:sys.argv.index('--pair')+3]
        def named_pad(name):
            ref,pin=name.split('.')
            return next(p for f in board.GetFootprints() if f.GetReference()==ref for p in f.Pads() if p.GetNumber()==pin).m_Uuid.AsString()
        search(board,named_pad(first),named_pad(second))
    elif '--all-signals' in sys.argv:
        for gap in report['unconnected_items']:
            if '[GND]' not in gap['items'][0]['description']:
                search(board,gap['items'][0]['uuid'],gap['items'][1]['uuid'])
    else:
        n=int(sys.argv[1]) if len(sys.argv)>1 else 0
        gap=report['unconnected_items'][n]
        search(board,gap['items'][0]['uuid'],gap['items'][1]['uuid'])
