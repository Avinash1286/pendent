"""Finish bounded fresh-DRC dangling cleanup on a trimmed .scratch candidate."""
import argparse, importlib.util, json, shutil, sys, traceback
from pathlib import Path
import pcbnew
spec=importlib.util.spec_from_file_location('safe_cleanup',Path(__file__).with_name('prepare-native-dangling-cleanup.py'))
safe=importlib.util.module_from_spec(spec);spec.loader.exec_module(safe)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--board',required=True)
    ap.add_argument('--expected-sha256',required=True);ap.add_argument('--max-passes',type=int,default=32)
    args=ap.parse_args();path=Path(args.board).resolve()
    if not path.is_relative_to(safe.WORKSPACE/'.scratch'):raise RuntimeError('Scratch candidates only')
    if safe.sha(path)!=args.expected_sha256.lower():raise RuntimeError('Candidate hash changed')
    history=path.parents[2]/'batch-history';history.mkdir(exist_ok=False)
    cli=Path(sys.executable).parent/'kicad-cli.exe';original=safe.signature(path)
    baseline=safe.run_drc(cli,path,history/'00-baseline-drc.json',60);safe.assert_drc(baseline)
    safe.unchanged_except_removals(original,safe.signature(path),set())
    report=baseline;removed_all=set();blocked_nets=set();passes=[];rejections=[]
    for number in range(1,args.max_passes+1):
        board=pcbnew.LoadBoard(str(path));items={t.m_Uuid.AsString():t for t in board.GetTracks()}
        wanted={v['items'][0]['uuid']:v for v in report['violations'] if v['type'] in safe.DANGLING}
        wanted={uid:v for uid,v in wanted.items() if items[uid].GetNetCode() not in blocked_nets}
        if not wanted:break
        snapshot=history/f'{number:02d}-before.kicad_pcb';shutil.copy2(path,snapshot)
        before=safe.signature(path)
        records=[{'uuid':uid,'net':items[uid].GetNetname(),'netCode':items[uid].GetNetCode(),
                  'finding':finding} for uid,finding in wanted.items()]
        netcodes={uid:t.GetNetCode() for uid,t in items.items()}
        netcodes.update({p.m_Uuid.AsString():p.GetNetCode() for f in board.GetFootprints() for p in f.Pads()})
        for uid in wanted:
            item=items[uid]
            if (item.GetClass()=='PCB_VIA')!=(wanted[uid]['type']=='via_dangling'):raise RuntimeError('DRC type mismatch')
            board.Remove(item);item.thisown=False
        pcbnew.SaveBoard(str(path),board)
        try:
            safe.unchanged_except_removals(before,safe.signature(path),set(wanted))
            trial=safe.run_drc(cli,path,history/f'{number:02d}-after-drc.json',60)
            safe.unchanged_except_removals(before,safe.signature(path),set(wanted))
            safe.assert_drc(trial,baseline)
        except safe.DrcSafetyError as exc:
            shutil.copy2(path,history/f'{number:02d}-rejected.kicad_pcb');shutil.copy2(snapshot,path)
            affected={netcodes[i['uuid']] for v in trial.get('unconnected_items',[]) for i in v['items'] if i['uuid'] in netcodes}
            if not affected:raise
            blocked_nets.update(affected)
            rejections.append({'pass':number,'reason':str(exc),'protectedNetCodes':sorted(affected),'attempted':records})
            print(json.dumps({'pass':number,'rejectedNetCodes':sorted(affected)}),flush=True)
            continue
        except Exception:
            shutil.copy2(snapshot,path);raise
        removed_all.update(wanted);report=trial;shutil.copy2(path,history/f'{number:02d}-after.kicad_pcb')
        passes.append({'pass':number,'removed':records,'drc':safe.drc_summary(report),'sha256':safe.sha(path)})
        print(json.dumps({'pass':number,'removed':len(wanted),'drc':safe.drc_summary(report)}),flush=True)
    safe.unchanged_except_removals(original,safe.signature(path),removed_all)
    result={'inputSha256':args.expected_sha256,'finalSha256':safe.sha(path),'board':str(path.relative_to(safe.WORKSPACE)),
            'passes':passes,'rejections':rejections,'removedItemCount':len(removed_all),
            'initialDrc':safe.drc_summary(baseline),'finalDrc':safe.drc_summary(report),
            'remainingDangling':[v for v in report['violations'] if v['type'] in safe.DANGLING],
            'allPadNetPlacementAndSurvivingCopperInvariantsPreserved':True}
    (history/'batch-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'result':str((history/'batch-result.json').relative_to(safe.WORKSPACE)),
                      'removed':len(removed_all),'drc':result['finalDrc'],'sha256':result['finalSha256']},indent=2))

if __name__=='__main__':
    try:main()
    except Exception:traceback.print_exc(file=sys.stdout);sys.exit(1)
