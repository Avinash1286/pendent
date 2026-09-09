"""Run the UART client tests and bind their actual source/fixture identities."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parents[2]


def identities():
    paths = [BENCH / name for name in ("host.py", "test_host.py", "verify_host.py", "requirements.txt")]
    paths += sorted((ROOT / "companion/src/aura_companion").rglob("*.py"))
    paths += sorted((ROOT / "firmware/a04/fixtures").glob("journal-*.aura"))
    paths += sorted((ROOT / "firmware/a04/fixtures").glob("journal-*.receipt"))
    paths.append(ROOT / "firmware/a04/fixtures/capture-20ms-open.aura")
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths}


def main():
    before = identities()
    result = subprocess.run([sys.executable, str(BENCH / "test_host.py"), "-v"],
                            capture_output=True, text=True, timeout=180, check=False)
    output = result.stdout + result.stderr
    print(output, end="")
    evidence = BENCH / "verification"
    evidence.mkdir(exist_ok=True)
    (evidence / "host-tests.txt").write_text(output, encoding="utf-8", newline="\n")
    result.check_returncode()
    match = re.search(r"^Ran (\d+) tests? in ", output, re.M)
    if not match or not re.search(r"^OK$", output, re.M):
        raise RuntimeError("Missing successful unittest completion")
    if before != identities():
        raise RuntimeError("Client sources or fixtures changed during verification")
    report = {"schema": 1, "status": "host_tests_passed", "tests": int(match[1]),
              "scope": "scripted UART and real C archive/SQLite/process interruption tests",
              "hardware_tested": False, "port_opened": False,
              "python": sys.version, "sources": before,
              "transcript_sha256": hashlib.sha256(output.encode()).hexdigest(),
              "limits": ["No physical UART or NAND", "No hostile local writer test",
                         "Process termination is not storage power-loss qualification",
                         "No authenticated UART enrollment or release command"]}
    (evidence / "host-tests.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
