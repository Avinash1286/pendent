"""Promote one reviewed, verified scratch cleanup with exact-source guards.

Canonical changes are limited to removed copper and explicitly verified endpoint
trims. Full footprint/pad/net/placement state, zone definitions and all other
copper properties must match. Retain a byte-for-byte source backup and report.
"""
import argparse, importlib.util, json, shutil, sys, traceback
from pathlib import Path
spec=importlib.util.spec_from_file_location('safe_cleanup',Path(__file__).with_name('prepare-native-dangling-cleanup.py'))
safe=importlib.util.module_from_spec(spec);spec.loader.exec_module(safe)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate',required=True);ap.add_argument('--expected-source-sha256',required=True)
    ap.add_argument('--expected-candidate-sha256',required=True);ap.add_argument('--trim-report',required=True)
    ap.add_argument('--drc-report',required=True);args=ap.parse_args()
    source=safe.HARDWARE/'output/aura-a03-native-routing.kicad_pcb';candidate=Path(args.candidate).resolve()
    if not candidate.is_relative_to(safe.WORKSPACE/'.scratch'):raise RuntimeError('Candidate must be in isolated scratch')
    if safe.sha(source)!=args.expected_source_sha256:raise RuntimeError('Canonical input hash changed; do not overwrite')
    if safe.sha(candidate)!=args.expected_candidate_sha256:raise RuntimeError('Verified candidate hash changed')
    before=safe.signature(source);after=safe.signature(candidate)
    trim=json.loads(Path(args.trim_report).read_text());allowed={c['uuid']:c for c in trim['changes']}
    removed=set(before['copper'])-set(after['copper']);added=set(after['copper'])-set(before['copper'])
    if added:raise RuntimeError('Cleanup candidate introduced new copper UUIDs')
    changed={uid for uid in after['copper'] if before['copper'][uid]!=after['copper'][uid]}
    if not changed.issubset(allowed):raise RuntimeError('Unreviewed surviving copper changed')
    for uid in changed:
        old=json.loads(before['copper'][uid]);new=json.loads(after['copper'][uid]);change=allowed[uid]
        old_other=[x for x in old if not(isinstance(x,list)and x and x[0]in('start','end'))]
        new_other=[x for x in new if not(isinstance(x,list)and x and x[0]in('start','end'))]
        if old_other!=new_other:raise RuntimeError('Trim altered properties beyond endpoints')
        for key in ('start','end'):
            actual=safe.child(new,key)
            if [round(float(v)*1e6) for v in actual[1:3]]!=change[key]['point']:
                raise RuntimeError('Trim endpoint differs from verified native geometry trial')
    b={**before,'copper':{uid:v for uid,v in before['copper'].items() if uid not in changed}}
    a={**after,'copper':{uid:v for uid,v in after['copper'].items() if uid not in changed}}
    safe.unchanged_except_removals(b,a,removed)
    drc=json.loads(Path(args.drc_report).read_text());safe.assert_drc(drc)
    backup=safe.WORKSPACE/'.scratch'/('canonical-pre-cleanup-'+args.expected_source_sha256+'.kicad_pcb')
    if not backup.exists():shutil.copy2(source,backup)
    if safe.sha(backup)!=args.expected_source_sha256:raise RuntimeError('Pre-cleanup backup differs')
    if safe.sha(source)!=args.expected_source_sha256:raise RuntimeError('Canonical board changed before promotion')
    shutil.copy2(candidate,source)
    if safe.sha(source)!=args.expected_candidate_sha256:raise RuntimeError('Promoted bytes differ')
    result={'status':'CONNECTED_COPPER_CLEANUP_PROMOTED','sourceSha256':args.expected_source_sha256,
            'outputSha256':safe.sha(source),'sourceBackup':str(backup.relative_to(safe.WORKSPACE)),
            'removedCopperCount':len(removed),'removedCopperUuids':sorted(removed),
            'trimmedCopperCount':len(changed),'verifiedTrims':[allowed[u]for u in sorted(changed)],
            'padNetPlacementAllOtherGeometryUnchanged':True,'drcBeforeLibraryRestoration':safe.drc_summary(drc),
            'remainingDanglingFindings':[v for v in drc['violations'] if v['type'] in safe.DANGLING],
            'noRuleExclusionsAdded':True}
    output=safe.HARDWARE/'output/aura-a03-copper-cleanup.json';output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'output':str(output.relative_to(safe.WORKSPACE)),'removed':len(removed),'trimmed':len(changed),
                      'drc':safe.drc_summary(drc),'boardSha256':safe.sha(source)},indent=2))

if __name__=='__main__':
    try:main()
    except Exception:traceback.print_exc(file=sys.stdout);sys.exit(1)
