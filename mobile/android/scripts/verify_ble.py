"""Exercise real Android GATT through a task-owned public Netsim peripheral.

Requires an already booted explicitly selected API33+ emulator and its local
Netsim gRPC port. This runner owns only its Bumble child process. It never boots,
wipes, pairs with, scans for or flashes a physical device.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from verify_android import ADB, APK, TEST_APK, APP, ROOT, sha, source_inputs, run, checked


def verify(serial: str, port: int, mtu: int, output: Path, duration: int) -> None:
    if not re.fullmatch(r'emulator-\d{4,5}', serial) or not 1 <= port <= 65535:
        raise ValueError('Explicit emulator serial and local Netsim port required')
    if output.exists():
        raise ValueError('Use a new output directory; prior evidence is retained')
    output.mkdir(parents=True)
    inputs = source_inputs()
    build_path = APP / 'verification/android-build.json'
    build_bytes = build_path.read_bytes()
    build_digest = hashlib.sha256(build_bytes).hexdigest()
    build = json.loads(build_bytes)
    if not build['passed'] or build['source_inputs'] != inputs:
        raise ValueError('Current inputs differ from the successful Android build')
    for path, expected in build['artifacts'].items():
        if sha(ROOT / path) != expected['sha256']:
            raise ValueError('APK differs from successful build')
    adb = [str(ADB), '-s', serial]
    hardware = checked(adb + ['shell', 'getprop', 'ro.hardware']).strip()
    sdk = int(checked(adb + ['shell', 'getprop', 'ro.build.version.sdk']).strip())
    if hardware not in ('ranchu', 'goldfish') or sdk < 33:
        raise ValueError('Virtual BLE evidence requires an API33+ emulator')
    fingerprint = checked(adb + ['shell', 'getprop', 'ro.build.fingerprint']).strip()
    bumble = ROOT / '.tools/android/bumble-venv/Scripts/python.exe'
    peripheral_path = output / 'peripheral.json'
    stop = output / 'stop-request'
    log = output / 'peripheral-output.txt'
    server_args = [str(bumble), str(APP / 'ble-fixture/peripheral.py'), '--netsim-port', str(port),
        '--mtu', str(mtu), '--duration-seconds', str(min(1800, duration * 2 + 90)),
        '--report', str(peripheral_path), '--stop-file', str(stop)]
    server = None
    detail = None
    terminal = []
    instrumentation_exit = None
    installations = []
    failure = None
    cleanup_errors = []
    try:
        # Installation is outside the peripheral lifetime. A slow valid APK
        # install must not consume either of the two bounded transfer passes.
        for apk in (APK, TEST_APK):
            result = checked(adb + ['install', '-r', str(apk)], timeout=180)
            if 'Success' not in result:
                raise RuntimeError('APK installation did not report success')
            installations.append({'apk': apk.relative_to(ROOT).as_posix(), 'sha256': sha(apk), 'result': result.strip()})
        with log.open('w', encoding='utf-8') as stream:
            server = subprocess.Popen(server_args, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                env={**os.environ, 'PYTHONUNBUFFERED': '1', 'PYTHONIOENCODING': 'utf-8'})
            print(f'Bumble child pid={server.pid}; waiting for virtual advertising', flush=True)
            ready_by = time.monotonic() + 30
            while time.monotonic() < ready_by:
                if server.poll() is not None:
                    raise RuntimeError('Virtual peripheral exited before advertising')
                try:
                    if json.loads(peripheral_path.read_bytes()).get('state') == 'advertising':
                        break
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError('Virtual peripheral did not advertise within 30 seconds')
            print(f'Running real Android GATT instrumentation at configured ATT MTU {mtu}', flush=True)
            result = run(adb + ['shell', 'am', 'instrument', '-w', '-r', '-e', 'address', 'F0:F1:F2:F3:F4:F5',
                '-e', 'timeoutMillis', str(duration * 1000), '-e', 'fixtureOnly', 'true',
                '-e', 'suite', 'virtualBle',
                'com.aura.notes.test/com.aura.notes.SmokeInstrumentation'], timeout=duration * 2 + 60)
            (output / 'instrumentation-output.txt').write_text(result.stdout, encoding='utf-8')
            instrumentation_exit = result.returncode
            terminal = re.findall(r'^INSTRUMENTATION_CODE:\s*(-?\d+)\s*$', result.stdout, re.MULTILINE)
            values = re.findall(r'^INSTRUMENTATION_RESULT: resultdetailJSON=(.+)$', result.stdout, re.MULTILINE)
            if len(values) != 1:
                raise RuntimeError('Missing or repeated Android result detail')
            detail = json.loads(values[0])
            if result.returncode or terminal != ['-1'] or detail.get('passed') is not True:
                raise RuntimeError('Virtual GATT instrumentation did not pass')
    except Exception as error:
        failure = type(error).__name__ + ': ' + str(error)
    finally:
        if server is not None:
            try:
                stop.write_text('Stop the task-owned public virtual peripheral.\n', encoding='utf-8')
            except OSError as error:
                cleanup_errors.append('Stop request: ' + type(error).__name__)
            finally:
                # Even a full or unavailable evidence filesystem cannot skip
                # cleanup of the exact child this runner created.
                for action in (None, server.terminate, server.kill):
                    if server.poll() is not None:
                        break
                    try:
                        if action is not None:
                            action()
                        server.wait(timeout=10)
                    except (OSError, subprocess.TimeoutExpired) as error:
                        cleanup_errors.append('Child cleanup: ' + type(error).__name__)
                if server.poll() is None:
                    cleanup_errors.append('Owned peripheral remains alive')
            if cleanup_errors:
                failure = failure or 'Virtual peripheral cleanup did not complete normally'
    try:
        peripheral = json.loads(peripheral_path.read_bytes())
    except (FileNotFoundError, json.JSONDecodeError):
        peripheral = None
    if server is None or server.returncode != 0 or peripheral is None or peripheral.get('state') != 'stopped':
        failure = failure or 'No successful terminal peripheral result'
    if peripheral is not None:
        if peripheral.get('errors') or not peripheral.get('connections') or any(
                c['att_mtu'] != mtu for c in peripheral['connections']):
            failure = failure or 'Peripheral reported errors or an unexpected negotiated MTU'
        completed = [name for c in peripheral.get('connections', []) for name in c['finished_sources']]
        if completed.count('finalized') < 2 or completed.count('open') < 2:
            failure = failure or 'Peripheral did not observe both complete sources on two passes'
    unchanged = inputs == source_inputs()
    if not unchanged:
        failure = failure or 'Sources changed during virtual BLE verification'
    artifacts_unchanged = all(sha(ROOT / path) == expected['sha256']
                              for path, expected in build['artifacts'].items())
    build_unchanged = sha(build_path) == build_digest
    if not artifacts_unchanged or not build_unchanged:
        failure = failure or 'Build report or APKs changed during virtual BLE verification'
    evidence = {
        'schema': 'aura.android.virtual-ble.v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'passed': failure is None, 'failure': failure, 'serial': serial, 'android_sdk': sdk,
        'fingerprint': fingerprint, 'configured_att_mtu': mtu, 'source_inputs': inputs,
        'inputs_unchanged_during_test': unchanged, 'build_report_sha256': build_digest,
        'build_report_unchanged_during_test': build_unchanged,
        'artifacts_unchanged_during_test': artifacts_unchanged, 'cleanup_errors': cleanup_errors,
        'installation': installations, 'instrumentation_exit_code': instrumentation_exit,
        'instrumentation_terminal_codes': terminal, 'result': detail,
        'peripheral_child_pid': server.pid if server else None,
        'peripheral_exit_code': server.returncode if server else None,
        'bumble_python_sha256': sha(bumble), 'server_command': server_args,
        'output_sha256': {p.name: sha(p) for p in output.iterdir() if p.is_file() and p.name != 'verification.json'},
        'physical_radio_tested': False, 'zephyr_firmware_executed': False,
        'ownership_enrollment_tested': False,
    }
    (output / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    if failure:
        raise RuntimeError(failure)
    print(f'PASS virtual Android GATT at MTU {mtu}; evidence {output}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--netsim-port', required=True, type=int)
    parser.add_argument('--mtu', required=True, type=int, choices=(23, 517))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--duration-seconds', type=int, default=180)
    args = parser.parse_args()
    if not 30 <= args.duration_seconds <= 600:
        parser.error('Use a 30..600 second per-pass duration')
    verify(args.serial, args.netsim_port, args.mtu, args.output.resolve(), args.duration_seconds)


if __name__ == '__main__':
    main()
