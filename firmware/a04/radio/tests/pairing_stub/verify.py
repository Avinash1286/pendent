"""Exercise actual pairing policy with bounded host callback/clock/ref mocks.

No Zephyr SMP, controller, Android pairing or physical UART executes here.
Only a temporary host executable is written; report is printed to stdout.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
RADIO = HERE.parents[1]
A04 = RADIO.parent
WORKSPACE = A04.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    compiler = WORKSPACE / ".tools/zephyr/venv/Lib/site-packages/ziglang/zig.exe"
    bindings = [RADIO / "src/aura_pairing_zephyr.c", RADIO / "include/aura_pairing_zephyr.h",
                RADIO / "include/aura_gatt_zephyr.h", A04 / "include/aura_transfer.h",
                A04 / "include/aura_journal_cursor.h", A04 / "include/aura_journal.h",
                A04 / "include/aura_archive.h", A04 / "include/aura_opus.h"]
    bindings += sorted(p for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    opus = A04 / "third_party/opus-1.6.1/include"
    bindings += [opus / name for name in ("opus.h", "opus_types.h", "opus_defines.h")]
    before = {p.relative_to(WORKSPACE).as_posix(): sha(p) for p in bindings}
    flags = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-UNDEBUG", "-O2"]
    with tempfile.TemporaryDirectory(prefix="aura-pairing-") as temporary:
        executable = Path(temporary) / "pairing.exe"
        command = [str(compiler), "cc"] + flags
        command += ["-I" + str(path) for path in (HERE, RADIO / "include", A04 / "include", opus)]
        command += [str(HERE / "test.c"), "-o", str(executable)]
        built = subprocess.run(command, capture_output=True, text=True, cwd=WORKSPACE)
        if built.returncode:
            raise RuntimeError("Compile failed:\n" + built.stdout + built.stderr)
        run = subprocess.run([str(executable)], capture_output=True, text=True, cwd=WORKSPACE)
        if run.returncode:
            raise RuntimeError("Checks failed:\n" + run.stdout + run.stderr)
        output = run.stdout.replace("\r\n", "\n")
        groups = re.findall(r"^PASS (?!pairing )(.+)$", output, re.MULTILINE)
        summary = re.findall(r"^PASS pairing groups=9 checks=(\d+) mocked_callbacks=true SMP_tested=false$", output, re.MULTILINE)
        if len(groups) != 9 or len(summary) != 1:
            raise RuntimeError("Expected nine pairing groups")
        binary = sha(executable)
    after = {p.relative_to(WORKSPACE).as_posix(): sha(p) for p in bindings}
    if before != after:
        raise RuntimeError("Source changed during verification")
    print(json.dumps({"schema": "aura.pairing-policy.host.v1", "passed": True,
                      "c_groups": 9, "c_checks": int(summary[0]), "groups": groups,
                      "source_sha256": after, "inputs_unchanged": True,
                      "compiler": str(compiler), "compile_options": flags,
                      "compiler_output": built.stdout + built.stderr,
                      "executable_sha256": binary, "transcript": output,
                      "transcript_sha256": hashlib.sha256(output.encode()).hexdigest(),
                      "SMP_tested": False, "physical_hardware_tested": False,
                      "scope": "Actual policy callbacks with mocked Zephyr callback registration, monotonic clock, connection generations/refs and work scheduling. No real SMP/controller/passkey exchange or physical interaction."}, indent=2))


if __name__ == "__main__":
    main()
