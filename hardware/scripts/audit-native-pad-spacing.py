"""Read-only native SMD copper spacing audit using KiCad effective pad shapes.

Uses the loaded routed board as authority, not the placement manifest. Distances
are bracketed by native SHAPE.Collide in 1 nm increments. Custom annular pads and
their holes use KiCad's native effective polygon geometry, without substituting
bounding boxes, component bodies, or a second polygon tessellation.
"""
import argparse, hashlib, json, math, sys, time, traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import pcbnew

ROOT=Path(__file__).resolve().parents[1]
LIMIT=150000  # KiCad internal units: 1 nm each = 0.15 mm.
SOURCE='https://jlcpcb.com/capabilities/pcb-capabilities'

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def shape_bbox(shape):
    b=shape.BBox()
    return (b.GetLeft(),b.GetTop(),b.GetRight(),b.GetBottom())
def bbox_distance(a,b):
    dx=max(0,a[0]-b[2],b[0]-a[2]);dy=max(0,a[1]-b[3],b[1]-a[3])
    return math.hypot(dx,dy)
def native_distance(a,b,ba,bb):
    if a.Collide(b,0): return 0,0
    low=0
    # This finite upper bound exceeds the separation of any point in the two
    # occupied shape bounding boxes. Bounding boxes do not decide clearance.
    high=math.ceil(max(math.hypot(x-u,y-v) for x,y in [(ba[0],ba[1]),(ba[2],ba[3])] for u,v in [(bb[0],bb[1]),(bb[2],bb[3])]))+2
    if not a.Collide(b,high): raise RuntimeError('Native shape distance upper bound failed')
    while high-low>1:
        mid=(low+high)//2
        if a.Collide(b,mid): high=mid
        else: low=mid
    return low,high
def public_pad(p):
    return {k:p[k] for k in ('reference','number','uuid','net','netCode','shape','positionMm')}

def write_markdown(report):
    lines=['# Native A03 SMD copper-pad spacing audit','',
           'Read-only audit at '+report['verifiedAt']+' of `hardware/'+report['board'].replace('\\','/')+'`, SHA-256 `'+report['inputSha256']+'`. The native board is the placement authority. No PCB or rule settings were changed.','',
           '**Result: '+report['status']+', '+str(report['violationCount'])+' violations across '+format(report['testedLayerPairs'],',')+' different-net pad pairs.** [JLCPCB rigid-board capabilities](https://jlcpcb.com/capabilities/pcb-capabilities) specify 0.15 mm SMD pad-to-pad clearance for different nets. [Assembly component spacing](https://jlcpcb.com/help/article/minimum-spacing-for-smd-components) is a separate requirement.','',
           '| Scope | Pair | Nets | Layer | Native gap (mm) | Result |',
           '|---|---|---|---|---|---|']
    for key in ('withinFootprint','betweenFootprints','B.Cu'):
        r=report['minimum'].get(key)
        if r:
            lines.append('| '+key+' | '+r['a']['reference']+'.'+r['a']['number']+' / '+r['b']['reference']+'.'+r['b']['number']+' | '+r['a']['net']+' / '+r['b']['net']+' | '+r['layer']+' | '+f"{r['clearanceLowerBoundMm']:.6f}–{r['clearanceUpperBoundMm']:.6f}"+' | '+r['status']+' |')
    if report['violations']:
        lines+=['','## All violations','',
                '| Pair | Nets | Layer | Native gap (mm) |',
                '|---|---|---|---|']
        for r in report['violations']:
            lines.append('| '+r['a']['reference']+'.'+r['a']['number']+' / '+r['b']['reference']+'.'+r['b']['number']+' | '+r['a']['net']+' / '+r['b']['net']+' | '+r['layer']+' | '+f"{r['clearanceLowerBoundMm']:.6f}–{r['clearanceUpperBoundMm']:.6f}"+' |')
    lines+=['', 'The audit examines '+str(report['smdPadObjects'])+' SMD pad objects representing '+str(report['uniqueSmdTerminals'])+' unique terminals, including custom microphone ground polygons with their holes. Non-SMD sound-port drill objects are outside this pad-pair check. Same-net pairs are excluded from this specific rule; different unassigned pads are treated as distinct electrical terminals, not as a shared net-zero. Both pairs within one footprint and between separate footprints are included.','',
            '[audit-native-pad-spacing.py](../hardware/scripts/audit-native-pad-spacing.py) uses `PAD.GetEffectiveShape(layer)` and native `SHAPE.Collide` on the loaded board. Actual polygons, holes, rectangles, circles and rounded shapes determine clearance; body rectangles and bounding boxes do not substitute for pad geometry. A binary search brackets distances within 1 nm. The pass/fail decision separately tests native collision at exactly 150,000 internal units. A rectangular pair with exactly 0.15 mm gap confirmed equality passes. These brackets describe computation resolution, not production tolerance.','',
            'The earlier board hash `b7a975bbb7aff69879f7040e7d914bfe41dc465224ab803978c5f10d15c5fd43` had one C7.2–U4.5 gap of 0.125 mm. The routing owner corrected C7 placement; the current report above is authoritative for the latest checked hash. No findings are suppressed.','',
            '[Complete JSON report](../hardware/output/native-smd-pad-spacing-audit.json) includes exact pad UUIDs, board hash, every violation, nearest 100 pairs, and minima within every footprint and between footprint pairs. The checksum stayed identical before and after the audit.','',
            "To repeat from the repository's `hardware/` directory:",'', '```powershell',
            "& 'C:/Program Files/KiCad/10.0/bin/python.exe' scripts/audit-native-pad-spacing.py", '```','',
            'A board edit during the run aborts this audit. Any later board change invalidates this exact hash-bound result. Tracks, vias, soldermask dams, assembly-body spacing and fabrication/assembly qualification are separate checks.','']
    (ROOT.parent/'docs/native-pad-spacing-audit.md').write_text('\n'.join(lines),encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--board',default='output/aura-a03-native-routing.kicad_pcb')
    args=ap.parse_args(); path=ROOT/args.board; before=digest(path); started=time.monotonic()
    board=pcbnew.LoadBoard(str(path))
    copper_layers=list(board.GetEnabledLayers().CuStack())
    records=[]; skipped=Counter(); native_pads=[]
    for f in board.GetFootprints():
        for p in f.Pads():
            native_pads.append(p)
            if p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD:
                skipped[str(p.GetAttribute())]+=1;continue
            layers=[l for l in copper_layers if p.IsOnLayer(l)]
            shapes={l:p.GetEffectiveShape(l) for l in layers}
            key=p.GetNetCode() if p.GetNetCode()!=0 else 'unconnected:'+f.GetReference()+'.'+p.GetNumber()
            records.append({'reference':f.GetReference(),'number':p.GetNumber(),'uuid':p.m_Uuid.AsString(),'net':p.GetNetname(),'netCode':p.GetNetCode(),'netKey':key,'shape':p.GetShape(),'positionMm':[p.GetPosition().x/1e6,p.GetPosition().y/1e6],'layers':layers,'shapes':shapes,'bounds':{l:shape_bbox(s)for l,s in shapes.items()}})
    records.sort(key=lambda p:(p['reference'],p['number'],p['uuid']))
    results=[]; violations=[]; counts=Counter(); comparisons=0; identical=0
    for i,a in enumerate(records):
        for b in records[i+1:]:
            if a['netKey']==b['netKey']:
                identical+=1;continue
            if a['reference']==b['reference'] and a['number']==b['number']:
                identical+=1;continue
            for layer in set(a['layers']) & set(b['layers']):
                sa=a['shapes'][layer];sb=b['shapes'][layer]
                low,high=native_distance(sa,sb,a['bounds'][layer],b['bounds'][layer])
                fail=sa.Collide(sb,LIMIT)
                same=a['reference']==b['reference']
                r={'a':public_pad(a),'b':public_pad(b),'layer':board.GetLayerName(layer),'sameFootprint':same,'clearanceLowerBoundMm':low/1e6,'clearanceUpperBoundMm':high/1e6,'nativeCollidesAt015mm':fail,'status':'FAIL'if fail else'PASS'}
                results.append(r);comparisons+=1;counts[r['layer']]+=1
                if fail:violations.append(r)
    if digest(path)!=before: raise RuntimeError('Board changed during audit; rerun the read-only audit on the latest stable board')
    results.sort(key=lambda r:(r['clearanceLowerBoundMm'],r['a']['reference'],r['a']['number']))
    violations.sort(key=lambda r:(r['clearanceLowerBoundMm'],r['a']['reference'],r['a']['number']))
    minimum={}
    for kind,predicate in [('overall',lambda r:True),('withinFootprint',lambda r:r['sameFootprint']),('betweenFootprints',lambda r:not r['sameFootprint'])]:
        minimum[kind]=next((r for r in results if predicate(r)),None)
    for layer in counts:minimum[layer]=next(r for r in results if r['layer']==layer)
    each_footprint={};each_pair={}
    for r in results:
        key=r['a']['reference'] if r['sameFootprint'] else '/'.join(sorted([r['a']['reference'],r['b']['reference']]))
        target=each_footprint if r['sameFootprint'] else each_pair
        if key not in target:target[key]=r
    report={'schemaVersion':1,'mode':'READ_ONLY','verifiedAt':datetime.now(timezone.utc).isoformat(),'board':str(path.relative_to(ROOT)),'inputSha256':before,'boardUnchanged':True,'nativeVersion':pcbnew.GetBuildVersion(),'thresholdMm':0.15,'source':SOURCE,'sourceDescription':'Rigid PCB capability: SMD pad-to-pad clearance on different nets is 0.15 mm. Retrieved 2026-09-08.','method':{'geometry':'PAD.GetEffectiveShape for each actual SMD copper layer; native SHAPE.Collide, including custom polygons, holes and rounded lands.','distanceResolutionMm':0.000001,'intervalMeaning':'Lower bound is greatest integer clearance with no native collision; upper bound is first colliding integer clearance. Copper overlap is [0,0].','thresholdDecision':'Direct native Collide at exactly 150000 internal units, calibrated against rectangular pads with exactly 0.15 mm gap (passes).','net0':'Distinct unassigned pads are treated as separate electrical nets; duplicates of the same reference/pad remain one terminal.','scope':'All different-net SMD pad pairs on a shared copper layer, including within one footprint; tracks, vias and component-body spacing belong to separate checks.','noRuleExclusions':True},'smdPadObjects':len(records),'uniqueSmdTerminals':len(set((p['reference'],p['number'])for p in records)),'customPadObjects':sum(p['shape']==pcbnew.PAD_SHAPE_CUSTOM for p in records),'nonSmdPadsSkipped':dict(skipped),'sameElectricalTerminalOrNetPairsSkipped':identical,'testedLayerPairs':comparisons,'testedLayerPairCounts':dict(counts),'violationCount':len(violations),'status':'PASS'if not violations else'FAIL','minimum':minimum,'violations':violations,'nearest100':results[:100],'minimumWithinEachFootprint':each_footprint,'minimumBetweenEachFootprintPair':each_pair,'elapsedSeconds':round(time.monotonic()-started,3)}
    output=ROOT/'output/native-smd-pad-spacing-audit.json';output.write_text(json.dumps(report,indent=2)+'\n')
    write_markdown(report)
    print(json.dumps({'status':report['status'],'boardSha256':before,'smdPadObjects':len(records),'testedLayerPairs':comparisons,'violationCount':len(violations),'minima':{k:{'pair':r['a']['reference']+'.'+r['a']['number']+' / '+r['b']['reference']+'.'+r['b']['number'],'layer':r['layer'],'lowerMm':r['clearanceLowerBoundMm'],'upperMm':r['clearanceUpperBoundMm']}for k,r in minimum.items()if r},'violations':[{'pair':r['a']['reference']+'.'+r['a']['number']+' / '+r['b']['reference']+'.'+r['b']['number'],'netA':r['a']['net'],'netB':r['b']['net'],'layer':r['layer'],'lowerMm':r['clearanceLowerBoundMm'],'upperMm':r['clearanceUpperBoundMm'],'sameFootprint':r['sameFootprint']}for r in violations],'elapsedSeconds':report['elapsedSeconds'],'report':str(output.relative_to(ROOT))},indent=2))

if __name__=='__main__':
    try: main()
    except Exception:
        traceback.print_exc(file=sys.stdout);sys.exit(1)
