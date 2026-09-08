"""Prepare and verify a dangling-copper cleanup candidate in .scratch only.

Never saves, replaces, or promotes the canonical board. Each iteration removes
only fresh native DRC track_dangling / via_dangling UUIDs, refills scratch zones,
and requires unchanged pads, nets, component placement, other board geometry,
surviving copper, zero unconnected items, zero DRC errors and no new warnings.
"""
import argparse, hashlib, json, re, shutil, subprocess, sys, time, traceback
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import pcbnew

HARDWARE = Path(__file__).resolve().parents[1]
WORKSPACE = HARDWARE.parent
DANGLING = {'track_dangling', 'via_dangling'}
TOKENS = re.compile(r'"(?:[^"\\]|\\.)*"|[()]|[^\s()]+')

class DrcSafetyError(RuntimeError):
    pass

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def canon_atom(atom):
    if atom.startswith('"'): return atom
    try: return str(Decimal(atom).normalize())
    except InvalidOperation: return atom

def parse(path):
    stack = []; result = None
    for token in TOKENS.findall(path.read_text(encoding='utf-8')):
        if token == '(':
            node = []
            if stack: stack[-1].append(node)
            stack.append(node)
        elif token == ')':
            result = stack.pop()
        else:
            if not stack: raise RuntimeError('Unexpected token outside board expression')
            stack[-1].append(canon_atom(token))
    if stack or not result or result[0] != 'kicad_pcb':
        raise RuntimeError('Malformed native board expression')
    return result

def child(node, name):
    return next((x for x in node if isinstance(x, list) and x and x[0] == name), None)

def stable_json(value): return json.dumps(value, sort_keys=True, separators=(',', ':'))
def signature(path):
    """Semantic token fingerprints preserve exact custom pad/paste/zone outlines.

    Ignore whitespace and equivalent number formatting. Only removed tracks/vias
    and regenerated zone-fill caches may differ. Footprints are compared in full,
    including every pad and all properties; no body approximation is involved.
    """
    root = parse(path); fixed = []; copper = {}; zones = {}
    for node in root[1:]:
        if not isinstance(node, list): raise RuntimeError('Unexpected scalar root field')
        tag = node[0]
        if tag in ('segment', 'arc', 'via'):
            uuid = child(node, 'uuid')
            if not uuid: raise RuntimeError('Copper item without UUID')
            key = uuid[1].strip('"')
            if key in copper: raise RuntimeError('Duplicate copper UUID')
            copper[key] = stable_json(node)
        elif tag == 'zone':
            uuid = child(node, 'uuid')
            if not uuid: raise RuntimeError('Zone without UUID')
            unfilled = [x for x in node if not (isinstance(x, list) and x and x[0] in ('filled_polygon', 'fill_segments'))]
            zones[uuid[1].strip('"')] = stable_json(unfilled)
        elif tag in ('generator', 'generator_version'):
            # Native SaveBoard may restate the writer identity; not geometry.
            continue
        else:
            fixed.append(stable_json(node))
    return {'fixed': sorted(fixed), 'zones': zones, 'copper': copper}

def unchanged_except_removals(before, after, removed):
    if before['fixed'] != after['fixed']:
        old = Counter(before['fixed']); new = Counter(after['fixed'])
        raise RuntimeError('Non-copper board/pad/net/placement state changed: '
                           + str([x[:150] for x in list((old-new).elements())[:3]]))
    if before['zones'] != after['zones']:
        raise RuntimeError('Zone settings or boundaries changed beyond fill-cache regeneration')
    expected = {k: v for k, v in before['copper'].items() if k not in removed}
    if expected != after['copper']:
        raise RuntimeError('Surviving copper geometry, net or properties changed')

def violation_key(v):
    return (v['type'], v.get('severity'), tuple(sorted(i['uuid'] for i in v.get('items', []))))

def drc_summary(report):
    return {'unconnected': len(report.get('unconnected_items', [])),
            'errors': sum(v.get('severity') == 'error' for v in report.get('violations', [])),
            'violationCounts': dict(Counter(v['type'] for v in report.get('violations', []))),
            'totalViolations': len(report.get('violations', []))}

def assert_drc(report, baseline=None):
    summary = drc_summary(report)
    if summary['unconnected'] or summary['errors']:
        raise DrcSafetyError('DRC safety gate failed: ' + json.dumps(summary))
    if baseline is not None:
        allowed = Counter(violation_key(v) for v in baseline['violations'] if v['type'] not in DANGLING)
        current = Counter(violation_key(v) for v in report['violations'] if v['type'] not in DANGLING)
        if current - allowed:
            raise DrcSafetyError('Cleanup introduced new non-dangling DRC findings: ' + str(current-allowed))
        if baseline.get('ignored_checks') != report.get('ignored_checks'):
            raise RuntimeError('Native DRC ignored-check context changed')

def run_drc(cli, board, output, timeout):
    command = [str(cli), 'pcb', 'drc', '--format', 'json', '--all-track-errors',
               '--refill-zones', '--save-board', '--output', str(output), str(board)]
    done = subprocess.run(command, cwd=board.parent, capture_output=True, text=True,
                          timeout=timeout, check=False)
    output.with_suffix('.log').write_text(done.stdout + '\n' + done.stderr, encoding='utf-8')
    if done.returncode:
        raise RuntimeError('Native DRC failed with code ' + str(done.returncode) + ': ' + done.stdout + done.stderr)
    return json.loads(output.read_text(encoding='utf-8'))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--expected-sha256', required=True)
    ap.add_argument('--board', default='output/aura-a03-native-routing.kicad_pcb')
    ap.add_argument('--max-passes', type=int, default=128)
    ap.add_argument('--drc-timeout-seconds', type=int, default=60)
    args = ap.parse_args()
    source = (HARDWARE / args.board).resolve()
    if not source.is_relative_to(HARDWARE / 'output'):
        raise RuntimeError('Source must be an existing board under hardware/output')
    before_hash = sha(source)
    if before_hash != args.expected_sha256.lower():
        raise RuntimeError('Current canonical board differs from the explicitly supplied hash')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    scratch_root = WORKSPACE / '.scratch' / ('native-dangling-cleanup-' + stamp)
    target_root = scratch_root / 'hardware'
    target_dir = target_root / 'output'
    target_dir.mkdir(parents=True, exist_ok=False)
    history_dir = scratch_root / 'history'
    history_dir.mkdir()
    target = target_dir / source.name
    shutil.copy2(source, target)
    context = []
    # Keep identical project basename and relative library hierarchy. No symlinks
    # or junctions can redirect scratch writes into the canonical project.
    for suffix in ('.kicad_pro', '.kicad_dru'):
        path = source.with_suffix(suffix)
        if path.exists():
            shutil.copy2(path, target.with_suffix(suffix))
            context.append((path, target.with_suffix(suffix), sha(path)))
    for name in ('fp-lib-table', 'sym-lib-table'):
        path = source.parent / name
        if path.exists():
            shutil.copy2(path, target_dir / name)
            context.append((path, target_dir / name, sha(path)))
    for name in ('library', 'library.pretty', 'pcb-snapshot.pretty'):
        path = HARDWARE / name
        if path.exists(): shutil.copytree(path, target_root / name)
    if sha(source) != before_hash:
        raise RuntimeError('Canonical board changed during project snapshot; rerun')
    for src, dst, checksum in context:
        if sha(src) != checksum or sha(dst) != checksum:
            raise RuntimeError('Project context changed during snapshot')
    original = signature(target)
    shutil.copy2(target, history_dir / '00-source.kicad_pcb')
    cli = Path(sys.executable).parent / 'kicad-cli.exe'
    if not cli.exists(): raise RuntimeError('Run with the Python shipped beside kicad-cli.exe')
    baseline_path = history_dir / '00-baseline-drc.json'
    baseline = run_drc(cli, target, baseline_path, args.drc_timeout_seconds)
    unchanged_except_removals(original, signature(target), set())
    assert_drc(baseline)
    shutil.copy2(target, history_dir / '00-baseline-refilled.kicad_pcb')
    report = baseline
    passes = []; removed_all = set(); rejected = {}
    for number in range(1, args.max_passes + 1):
        dangling = [v for v in report['violations'] if v['type'] in DANGLING]
        if not dangling: break
        requested = {}
        for violation in dangling:
            if len(violation['items']) != 1:
                raise RuntimeError('Expected exactly one copper UUID per dangling finding')
            uuid = violation['items'][0]['uuid']
            if uuid in requested: raise RuntimeError('Duplicate dangling UUID in DRC')
            requested[uuid] = violation
        eligible = [uuid for uuid in requested if uuid not in rejected]
        if not eligible: break
        # A DRC dangling item can still bridge overlapping copper away from its
        # reported free end. Single-item trials expose that case without deleting
        # electrically necessary copper, even when a whole dangling batch fails.
        chosen = eligible[0]
        requested = {chosen: requested[chosen]}
        snapshot = history_dir / f'{number:02d}-before.kicad_pcb'
        shutil.copy2(target, snapshot)
        before_signature = signature(target)
        board = pcbnew.LoadBoard(str(target))
        copper = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
        if not set(requested).issubset(copper):
            raise RuntimeError('Fresh DRC UUID does not resolve to native copper')
        removed = []
        for uuid, violation in requested.items():
            item = copper[uuid]
            isvia = isinstance(item, pcbnew.PCB_VIA)
            if isvia != (violation['type'] == 'via_dangling'):
                raise RuntimeError('Native copper type differs from fresh DRC finding')
            removed.append({'uuid': uuid, 'type': violation['type'], 'net': item.GetNetname(),
                            'netCode': item.GetNetCode(), 'nativeClass': item.GetClass(),
                            'drcItem': violation['items'][0]})
            board.Remove(item)
            item.thisown = False
        board.BuildConnectivity()
        pcbnew.SaveBoard(str(target), board)
        try:
            unchanged_except_removals(before_signature, signature(target), set(requested))
            after_path = history_dir / f'{number:02d}-after-drc.json'
            next_report = run_drc(cli, target, after_path, args.drc_timeout_seconds)
            unchanged_except_removals(before_signature, signature(target), set(requested))
            assert_drc(next_report, baseline)
        except DrcSafetyError as exc:
            shutil.copy2(target, history_dir / f'{number:02d}-rejected.kicad_pcb')
            shutil.copy2(snapshot, target)
            unchanged_except_removals(before_signature, signature(target), set())
            rejected[chosen] = {'uuid': chosen, 'finding': requested[chosen],
                                'reason': str(exc), 'trialDrc': str(after_path.relative_to(scratch_root))}
            (scratch_root / 'rejected.json').write_text(json.dumps(rejected, indent=2) + '\n')
            print(json.dumps({'pass': number, 'rejected': chosen, 'reason': str(exc)}), flush=True)
            continue
        except Exception:
            shutil.copy2(target, history_dir / f'{number:02d}-rejected.kicad_pcb')
            shutil.copy2(snapshot, target)
            raise
        removed_all.update(requested)
        report = next_report
        shutil.copy2(target, history_dir / f'{number:02d}-after.kicad_pcb')
        record = {'pass': number, 'beforeSha256': sha(snapshot), 'afterSha256': sha(target),
                  'removed': removed, 'drc': drc_summary(report), 'allInvariantsPreserved': True}
        passes.append(record)
        (scratch_root / 'progress.json').write_text(json.dumps(passes, indent=2) + '\n')
        print(json.dumps({'pass': number, 'removed': len(removed), 'drc': record['drc']}), flush=True)
    else:
        raise RuntimeError('Cleanup pass limit reached; candidate is not final')
    remaining = [v for v in report['violations'] if v['type'] in DANGLING]
    unchanged_except_removals(original, signature(target), removed_all)
    for src, dst, checksum in context:
        if sha(src) != checksum or sha(dst) != checksum:
            raise RuntimeError('Canonical or scratch project/rule/table context changed')
    canonical_unchanged = sha(source) == before_hash
    result = {'status': 'CONNECTED_CANDIDATE_WITH_RETAINED_FINDINGS' if remaining else 'VERIFIED_SCRATCH_CANDIDATE', 'canonicalBoardMutated': False,
              'canonicalStillMatchesInput': canonical_unchanged,
              'inputBoard': str(source.relative_to(WORKSPACE)), 'inputSha256': before_hash,
              'candidateBoard': str(target.relative_to(WORKSPACE)), 'candidateSha256': sha(target),
              'initialDrc': drc_summary(baseline), 'finalDrc': drc_summary(report),
              'removedItemCount': len(removed_all), 'passes': passes, 'rejectedRemovals': rejected,
              'remainingDanglingFindings': remaining,
              'invariants': {'exactFootprintPadsNetsPropertiesAndPlacements': True,
                             'zoneBoundariesAndSettings': True, 'survivingCopperUnchanged': True,
                             'projectRulesTablesUnchanged': True, 'zeroUnconnectedEachPass': True,
                             'zeroDrcErrorsEachPass': True, 'noNewNonDanglingWarnings': True},
              'promotion': 'Not performed. Routing owner must first verify canonical input hash and review this candidate; never copy over a changed live board.'}
    result_path = scratch_root / 'cleanup-result.json'
    result_path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'result': str(result_path.relative_to(WORKSPACE)),
                      'candidateBoard': result['candidateBoard'],
                      'candidateSha256': result['candidateSha256'],
                      'removedItemCount': result['removedItemCount'],
                      'initialDrc': result['initialDrc'], 'finalDrc': result['finalDrc'],
                      'canonicalStillMatchesInput': canonical_unchanged}, indent=2), flush=True)

if __name__ == '__main__':
    try: main()
    except Exception:
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
