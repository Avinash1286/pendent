"""Build evidence and real Android instrumentation on an explicitly named device.

Uses the workspace-local Windows toolchain. Never selects, wipes, flashes or
uninstalls a device; runtime installs the development and test APKs with -r.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[1]
TOOLS = ROOT / '.tools/android'
REPORTS = APP / 'verification'
APK = APP / 'app/build/outputs/apk/debug/app-debug.apk'
TEST_APK = APP / 'app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk'
ADB = TOOLS / 'sdk/platform-tools/adb.exe'


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def source_inputs() -> dict[str, str]:
    files = [p for base in ('app/src', 'core/src') for p in (APP / base).rglob('*') if p.is_file()]
    files += [p for p in APP.glob('*.gradle.kts')]
    files += [APP / name for name in ('app/build.gradle.kts', 'core/build.gradle.kts',
                                    'gradle.properties', 'build.ps1', 'toolchain-lock.json')]
    return {relative(p): sha(p) for p in sorted(set(files))}


def run(args: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, encoding='utf-8', errors='replace',
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)


def checked(args: list[str], *, timeout: int = 300) -> str:
    result = run(args, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{Path(args[0]).name} failed ({result.returncode}): {result.stdout[-2000:]}')
    return result.stdout


def write_json(name: str, content: dict) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / name).write_text(json.dumps(content, indent=2) + '\n', encoding='utf-8')


def build() -> None:
    before = source_inputs()
    print('Building both APKs and running Android lint; core cross-language checks are separate.', flush=True)
    result = run(['pwsh', '-NoProfile', '-File', str(APP / 'build.ps1'), '-SkipCore'], timeout=1800)
    REPORTS.mkdir(parents=True, exist_ok=True)
    log = REPORTS / 'build-output.txt'
    log.write_text(result.stdout, encoding='utf-8')
    if result.returncode:
        print(result.stdout[-6000:])
        raise RuntimeError('Android build/lint failed; output retained, no passing report written')
    after = source_inputs()
    if before != after:
        raise RuntimeError('Build inputs changed while Gradle ran; report refused')
    lint = APP / 'app/build/reports/lint-results-debug.xml'
    issues = ET.parse(lint).getroot().findall('issue')
    counts = {kind: sum(x.get('severity') == kind for x in issues)
              for kind in ('Fatal', 'Error', 'Warning', 'Information')}
    if counts['Fatal'] or counts['Error']:
        raise RuntimeError('Lint contains unresolved errors')
    jdk = TOOLS / 'jdk17/jdk-17.0.20.1+1/bin'
    write_json('android-build.json', {
        'schema': 'aura.android.build.v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'passed': True, 'source_inputs': before, 'inputs_unchanged_during_build': True,
        'artifacts': {relative(p): {'sha256': sha(p), 'bytes': p.stat().st_size}
                      for p in (APK, TEST_APK)},
        'lint': {'counts': counts, 'issues': [{'id': x.get('id'), 'severity': x.get('severity'),
                   'message': x.get('message')} for x in issues]},
        'build_output_sha256': sha(log),
        'java': checked([str(jdk / 'java.exe'), '-version']).strip(),
        'javac': checked([str(jdk / 'javac.exe'), '-version']).strip(),
        'adb': checked([str(ADB), 'version']).strip(),
        'verification_script_sha256': sha(Path(__file__)),
        'runtime_tested_by_this_build': False, 'physical_hardware_verified': False,
        'note': 'Development debug signature; not a production-signed or Play Store release.'
    })
    print(f'Android build passed; lint: {counts}', flush=True)


def runtime(serial: str) -> None:
    # No shell interpolation, implicit device choice, wildcard or remote host.
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', serial):
        raise ValueError('Use an explicit adb serial from adb devices -l')
    build_report = REPORTS / 'android-build.json'
    prior = json.loads(build_report.read_text(encoding='utf-8'))
    if not prior['passed'] or prior['source_inputs'] != source_inputs():
        raise RuntimeError('Build evidence does not match current compiled source inputs')
    for path, artifact in prior['artifacts'].items():
        if sha(ROOT / path) != artifact['sha256']:
            raise RuntimeError('APK differs from its successful build report')
    prefix = [str(ADB), '-s', serial]
    if checked(prefix + ['get-state']).strip() != 'device':
        raise RuntimeError('Explicit Android device is not ready')
    fingerprint = checked(prefix + ['shell', 'getprop', 'ro.build.fingerprint']).strip()
    print(f'Installing development/test APKs on {serial}; running isolated synthetic fixtures.', flush=True)
    installation = []
    for path in (APK, TEST_APK):
        output = checked(prefix + ['install', '-r', str(path)], timeout=120)
        if 'Success' not in output:
            raise RuntimeError('APK installation did not report Success')
        installation.append({'apk_sha256': sha(path), 'output': output.strip()})
    result = run(prefix + ['shell', 'am', 'instrument', '-w', '-r',
                          'com.aura.notes.test/com.aura.notes.SmokeInstrumentation'], timeout=300)
    log = REPORTS / 'instrumentation-output.txt'
    log.write_text(result.stdout, encoding='utf-8')
    marker = 'INSTRUMENTATION_RESULT: resultdetailJSON='
    lines = [line[len(marker):] for line in result.stdout.splitlines() if line.startswith(marker)]
    detail = json.loads(lines[0]) if len(lines) == 1 else {'passed': False, 'failure': 'Missing unique test result'}
    unchanged = prior['source_inputs'] == source_inputs()
    passed = result.returncode == 0 and detail.get('passed') is True and unchanged
    write_json('android-runtime.json', {
        'schema': 'aura.android.runtime.v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'passed': passed, 'serial': serial, 'fingerprint': fingerprint,
        'emulator': serial.startswith('emulator-'), 'physical_hardware_verified': False,
        'build_report_sha256': sha(build_report), 'source_inputs': prior['source_inputs'],
        'inputs_unchanged_during_test': unchanged, 'installation': installation,
        'instrumentation_exit_code': result.returncode, 'result': detail,
        'instrumentation_output_sha256': sha(log), 'verification_script_sha256': sha(Path(__file__)),
        'scope': 'Actual Android codec and SQLite with public synthetic C fixtures; no radio, microphone or wear test.'
    })
    print(result.stdout[-9000:], flush=True)
    if not passed:
        raise RuntimeError('Android runtime checks failed; exact result retained')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('build', 'runtime'))
    parser.add_argument('--serial', help='Required for runtime: explicit adb device serial')
    args = parser.parse_args()
    if args.phase == 'runtime' and not args.serial:
        parser.error('runtime requires --serial; no automatic device selection')
    try:
        build() if args.phase == 'build' else runtime(args.serial)
    except Exception as error:
        print(f'VERIFICATION FAILED: {error}', file=sys.stderr)
        sys.exit(1)
