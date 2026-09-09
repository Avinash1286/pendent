"""Run release, receiver and complete companion tests with source-bound evidence.

Run with the installed companion environment, for example from companion/:
  .venv/Scripts/python.exe scripts/verify_release.py --report verification/release.json
No pendant transport or real owner credentials are used by these synthetic tests.
The report is written only after successful tests and unchanged-input checks.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import sys


COMPANION = Path(__file__).resolve().parents[1]
WORKSPACE = COMPANION.parent


def digest(path):
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(),
            "lf_normalized_sha256": hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()}


def bindings():
    files = set(COMPANION.glob("src/aura_companion/*.py"))
    files.update(COMPANION.glob("tests/test_*.py"))
    files.update(p for p in (COMPANION / "tests/assets").rglob("*") if p.is_file())
    files.update(COMPANION / name for name in ("pyproject.toml", "uv.lock", "RELEASE.md"))
    files.add(Path(__file__).resolve())
    fixtures = WORKSPACE / "firmware/a04/fixtures"
    files.update(fixtures.glob("capture-*.aura"))
    files.update(fixtures.glob("capture-*.receipt"))
    for duration in (10, 20):
        files.add(fixtures / f"speech-{duration}ms.aoc")
        files.add(fixtures / f"speech-{duration}ms-ffmpeg.wav")
    return {path.relative_to(WORKSPACE).as_posix(): digest(path) for path in sorted(files)}


def run_suite(pattern):
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v"]
    environment = os.environ.copy()
    # Test precisely this source checkout; do not silently use another installed package.
    environment["PYTHONPATH"] = str(COMPANION / "src")
    environment["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(command, cwd=COMPANION, env=environment,
                            capture_output=True, text=True, encoding="utf-8", timeout=300)
    transcript = (result.stdout + result.stderr).replace("\r\n", "\n")
    sys.stderr.write(transcript)
    count = re.search(r"^Ran (\d+) tests? in ([0-9.]+)s$", transcript, re.MULTILINE)
    if result.returncode != 0 or count is None or not re.search(r"^OK$", transcript, re.MULTILINE):
        raise RuntimeError(f"{pattern} did not complete without failures, errors or skips")
    # Asyncio diagnostics may appear between unittest's test prefix and "ok".
    # Plain final OK excludes errors/failures/skips; count each discovered prefix.
    passed = re.findall(r"^(test_\S+) \(([^)]+)\) \.\.\. ", transcript, re.MULTILINE)
    if len(passed) != int(count[1]):
        raise RuntimeError(f"{pattern} did not provide one passing result for every discovered test")
    per_module = {}
    for _, identity in passed:
        module = identity.split(".")[0]
        per_module[module] = per_module.get(module, 0) + 1
    return {"cwd": "companion", "command": ["<companion-python>"] + command[1:],
            "exit_code": result.returncode, "tests_passed": int(count[1]),
            "failures": 0, "errors": 0, "skipped": 0, "tests_by_module": per_module,
            "transcript_sha256": hashlib.sha256(transcript.encode("utf-8")).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Write successful JSON evidence to this path")
    args = parser.parse_args()
    before = bindings()
    runs = [run_suite(pattern) for pattern in ("test_release.py", "test_protocol_v2.py", "test_*.py")]
    after = bindings()
    if before != after:
        raise RuntimeError("A tested source or fixture changed during verification")
    if any(runs[2]["tests_by_module"].get(name) != run["tests_passed"]
           for name, run in (("test_release", runs[0]), ("test_protocol_v2", runs[1]))):
        raise RuntimeError("Full discovery omitted targeted release/receiver tests")
    report = {
        "schema": "aura-companion-release-verification-v1",
        "status": "synthetic_local_release_and_companion_tests_passed",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": {"executable": sys.executable, "version": platform.python_version()},
        "platform": platform.platform(), "sqlite_version": sqlite3.sqlite_version,
        "dependencies": {name: importlib.metadata.version(name)
                         for name in ("aura-companion", "av", "bleak", "faster-whisper")},
        "runs": runs,
        "unique_tests_passed": runs[2]["tests_passed"],
        "sources_and_fixtures": after,
        "c_interoperability": {
            "scope": "fixed production-C RLS1 golden bytes compared with Python encoding",
            "reference_source": "firmware/a04/tests/host_release_auth.c",
            "reference_source_identity": digest(WORKSPACE / "firmware/a04/tests/host_release_auth.c"),
            "firmware_controller_execution": False,
        },
        "limits": [
            "All owner keys, captures and database contents are synthetic test data.",
            "Completion is exact local bookkeeping, not authenticated device confirmation.",
            "No BLE, enrollment, OS keychain, pendant erase or physical device is exercised.",
            "Process interruption and transaction faults do not qualify physical power-loss durability.",
            "A valid whole-database rollback needs an external protected monotonic anchor to detect.",
            "The source read lock covers outbox COMMIT; this is not cross-database atomic commit.",
        ],
    }
    encoded = json.dumps(report, indent=2) + "\n"
    if args.report:
        target = args.report.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        # Reporting is separate from the authorization path and contains no real secrets.
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(encoded, encoding="utf-8", newline="\n")
        os.replace(temporary, target)
    else:
        print(encoded, end="")
    print(f"Verified {runs[0]['tests_passed']} release, {runs[1]['tests_passed']} receiver, "
          f"{runs[2]['tests_passed']} total companion tests.", file=sys.stderr)


if __name__ == "__main__":
    main()
