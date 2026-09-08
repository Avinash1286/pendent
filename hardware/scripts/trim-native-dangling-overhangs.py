"""Trim only DRC-flagged track overhangs on an isolated scratch candidate.

Each new endpoint lies on the original segment centerline, inside a real same-net
native pad/via/track shape. A trial must remove that exact dangling finding while
preserving all pad/net/placement state, zero unconnected nets and zero DRC errors.
"""
import argparse, importlib.util, json, math, shutil, sys, traceback
from pathlib import Path
import pcbnew

spec = importlib.util.spec_from_file_location('safe_cleanup', Path(__file__).with_name('prepare-native-dangling-cleanup.py'))
safe = importlib.util.module_from_spec(spec); spec.loader.exec_module(safe)

def point(v): return (v.x, v.y)
def dot(a,b): return a[0]*b[0]+a[1]*b[1]
def cross(a,b): return a[0]*b[1]-a[1]*b[0]
def sub(a,b): return (a[0]-b[0],a[1]-b[1])

def proposal(board, item):
    a,b = point(item.GetStart()),point(item.GetEnd()); d=sub(b,a); length2=dot(d,d)
    if not length2: return None
    layer=item.GetLayer(); contacts=[]
    others=list(board.GetTracks())+[p for f in board.GetFootprints() for p in f.Pads()]
    shape=item.GetEffectiveShape(layer)
    for other in others:
        if other.m_Uuid==item.m_Uuid or other.GetNetCode()!=item.GetNetCode() or not other.IsOnLayer(layer): continue
        other_shape=other.GetEffectiveShape(layer)
        if not shape.Collide(other_shape,0): continue
        istrack=other.GetClass() in ('PCB_TRACK','PCB_ARC')
        anchors=[point(other.GetStart()),point(other.GetEnd())] if istrack else [point(other.GetPosition())]
        candidates=[max(0,min(1,dot(sub(p,a),d)/length2)) for p in anchors]
        if other.GetClass()=='PCB_TRACK':
            c,e=point(other.GetStart()),point(other.GetEnd()); od=sub(e,c); denominator=cross(d,od)
            if denominator:
                t=cross(sub(c,a),od)/denominator; u=cross(sub(c,a),d)/denominator
                if 0<=t<=1 and 0<=u<=1: candidates.append(t)
        # Existing endpoints count only when their centers are inside another
        # native shape. Projection points are accepted by the same exact test.
        candidates.extend((0,1))
        for t in candidates:
            p=pcbnew.VECTOR2I(round(a[0]+t*d[0]),round(a[1]+t*d[1]))
            if other_shape.Collide(p,0):
                contacts.append({'fraction':t,'point':point(p),'otherUuid':other.m_Uuid.AsString(),
                                 'otherClass':other.GetClass()})
    if len(contacts)<2: return None
    first=min(contacts,key=lambda x:x['fraction']);last=max(contacts,key=lambda x:x['fraction'])
    if first['point']==last['point'] or (first['fraction']<=1e-10 and last['fraction']>=1-1e-10): return None
    return {'start':first,'end':last,'oldStart':a,'oldEnd':b,
            'oldLengthMm':math.sqrt(length2)/1e6,
            'newLengthMm':math.dist(first['point'],last['point'])/1e6}

def invariant(before,after,uuid):
    a={**before,'copper':{k:v for k,v in before['copper'].items() if k!=uuid}}
    b={**after,'copper':{k:v for k,v in after['copper'].items() if k!=uuid}}
    safe.unchanged_except_removals(a,b,set())

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--board',required=True)
    ap.add_argument('--expected-sha256',required=True);ap.add_argument('--max-trials',type=int,default=16)
    args=ap.parse_args();path=Path(args.board).resolve()
    if not path.is_relative_to(safe.WORKSPACE/'.scratch'): raise RuntimeError('Only isolated .scratch boards are accepted')
    if safe.sha(path)!=args.expected_sha256.lower(): raise RuntimeError('Scratch board hash changed')
    cli=Path(sys.executable).parent/'kicad-cli.exe';history=path.parents[2]/'trim-history';history.mkdir(exist_ok=False)
    baseline=safe.run_drc(cli,path,history/'00-baseline-drc.json',60);safe.assert_drc(baseline)
    report=baseline;attempted=set();changes=[];rejected=[]
    for number in range(1,args.max_trials+1):
        findings=[v for v in report['violations'] if v['type']=='track_dangling' and v['items'][0]['uuid'] not in attempted]
        if not findings:break
        uid=findings[0]['items'][0]['uuid'];attempted.add(uid)
        board=pcbnew.LoadBoard(str(path));item=next(t for t in board.GetTracks() if t.m_Uuid.AsString()==uid)
        if item.GetClass()!='PCB_TRACK': rejected.append({'uuid':uid,'reason':'Not a straight segment'});continue
        change=proposal(board,item)
        if change is None: rejected.append({'uuid':uid,'reason':'No strict shortening with both endpoints inside real native same-net geometry'});continue
        change.update(uuid=uid,net=item.GetNetname(),layer=item.GetLayerName(),widthMm=item.GetWidth()/1e6)
        snapshot=history/f'{number:02d}-before.kicad_pcb';shutil.copy2(path,snapshot)
        before=safe.signature(path)
        item.SetStart(pcbnew.VECTOR2I(*change['start']['point']));item.SetEnd(pcbnew.VECTOR2I(*change['end']['point']))
        pcbnew.SaveBoard(str(path),board)
        try:
            invariant(before,safe.signature(path),uid)
            trial=safe.run_drc(cli,path,history/f'{number:02d}-after-drc.json',60)
            invariant(before,safe.signature(path),uid);safe.assert_drc(trial,baseline)
            if any(v['type']=='track_dangling' and any(i['uuid']==uid for i in v['items']) for v in trial['violations']):
                raise safe.DrcSafetyError('Native DRC still flags the trimmed endpoint')
        except safe.DrcSafetyError as exc:
            shutil.copy2(path,history/f'{number:02d}-rejected.kicad_pcb');shutil.copy2(snapshot,path)
            rejected.append({'uuid':uid,'reason':str(exc),'proposed':change});continue
        except Exception:
            shutil.copy2(snapshot,path);raise
        report=trial;changes.append(change);shutil.copy2(path,history/f'{number:02d}-after.kicad_pcb')
        print(json.dumps({'trimmed':uid,'net':change['net'],'oldMm':change['oldLengthMm'],'newMm':change['newLengthMm'],'drc':safe.drc_summary(report)}),flush=True)
    result={'mode':'SCRATCH_ONLY','inputSha256':args.expected_sha256,'finalSha256':safe.sha(path),
            'board':str(path.relative_to(safe.WORKSPACE)),'changes':changes,'rejected':rejected,
            'initialDrc':safe.drc_summary(baseline),'finalDrc':safe.drc_summary(report),
            'remainingDangling':[v for v in report['violations'] if v['type'] in safe.DANGLING],
            'padNetPlacementAndOtherCopperUnchanged':True}
    (history/'trim-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'result':str((history/'trim-result.json').relative_to(safe.WORKSPACE)),
                      'trimmed':len(changes),'rejected':len(rejected),'drc':result['finalDrc'],'finalSha256':result['finalSha256']},indent=2))

if __name__=='__main__':
    try:main()
    except Exception:traceback.print_exc(file=sys.stdout);sys.exit(1)
