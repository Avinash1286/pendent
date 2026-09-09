"""Actual GATT adapter/transfer code with deterministic Zephyr boundary doubles."""
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
A04 = HERE.parents[1]
ZIG = ROOT / ".tools/zephyr/venv/Lib/site-packages/ziglang/zig.exe"
OUT = ROOT / ".scratch/a04-radio-gatt-tests"
PRODUCTION = [A04 / "src" / name for name in (
    "aura_transfer.c", "aura_journal.c", "aura_archive.c", "aura_storage.c",
    "aura_control.c", "aura_release_auth.c")]


def sources():
    paths = [HERE / "host_gatt.c", HERE / "zephyr_stubs.h", HERE / "run_gatt.py",
             HERE.parent / "src/aura_gatt_zephyr.c", HERE.parent / "include/aura_gatt_zephyr.h"]
    paths += sorted((HERE / "stubs").rglob("*.h"))
    paths += [A04 / "include" / name for name in (
        "aura_transfer.h", "aura_journal_cursor.h", "aura_journal.h", "aura_archive.h",
        "aura_opus.h", "aura_nand.h", "aura_storage.h", "aura_control.h", "aura_release_auth.h")]
    paths += PRODUCTION
    return {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    before = sources()
    OUT.mkdir(parents=True, exist_ok=True)
    executable = OUT / "host_gatt.exe"
    command = [str(ZIG), "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-UNDEBUG",
               "-I" + str(HERE), "-I" + str(HERE / "stubs"),
               "-I" + str(HERE.parent / "include"), "-I" + str(A04 / "include"),
               "-I" + str(A04 / "third_party/opus-1.6.1/include"),
               str(HERE / "host_gatt.c"), *map(str, PRODUCTION), "-o", str(executable)]
    subprocess.run(command, cwd=ROOT, check=True, timeout=180)
    result = subprocess.run([str(executable)], capture_output=True, text=True,
                            cwd=ROOT, check=False, timeout=60)
    output = (result.stdout + result.stderr).replace("\r\n", "\n")
    print(output, end="")
    result.check_returncode()
    match = re.search(r"^(\d+) production GATT adapter / real transfer groups passed$", output, re.M)
    if not match or output.count("PASS ") != int(match[1]):
        raise RuntimeError("Missing actual successful test completion")
    if before != sources():
        raise RuntimeError("Adapter/engine/test source changed during verification")
    report = {
        "schema": 1, "status": "host_tests_passed", "groups": int(match[1]),
        "scope": "Actual Zephyr adapter and portable transfer engine; deterministic kernel/Bluetooth/clock boundary doubles",
        "physical_radio_tested": False, "zephyr_runtime_tested": False,
        "owner_proof_cryptography_tested": False,
        "sources": before, "transcript_sha256": sha256(output.encode()).hexdigest(),
        "compiler": subprocess.check_output([str(ZIG), "version"], text=True).strip(),
        "limits": ["No RF, pairing or physical security qualification", "No Zephyr scheduling/timing evidence",
                   "No synthetic callback implies durable phone receipt", "No Android-to-Zephyr link exercised"],
    }
    (HERE / "gatt-host-tests.txt").write_text(output, encoding="utf-8", newline="\n")
    (HERE / "gatt-host-tests.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
