"""Compile actual bench orchestration/audio adapter with deterministic doubles.

No serial connection, target flash, hardware simulation or physical claim.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

BENCH = Path(__file__).resolve().parent
A04 = BENCH.parent
ROOT = A04.parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path)
    parser.add_argument("--report", type=Path)
    options = parser.parse_args()
    compiler = options.compiler or Path(os.environ.get("AURA_BENCH_CC", ""))
    if not compiler.is_file():
        compiler = ROOT / ".tools/zephyr/venv/Lib/site-packages/ziglang/zig.exe"
    if not compiler.is_file():
        found = shutil.which("clang") or shutil.which("cc")
        if not found:
            raise RuntimeError("Pass --compiler or install the documented A04 Zig host toolchain")
        compiler = Path(found)
    include_dirs = [BENCH / "tests/stub", A04 / "tests/audio_stub", A04 / "include",
                    A04 / "third_party/opus-1.6.1/include"]
    sources = [BENCH / "tests/control.c", A04 / "src/aura_audio_zephyr.c", A04 / "src/aura_archive.c"]
    command = [str(compiler)] + (["cc"] if compiler.stem.lower() == "zig" else [])
    command += ["-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-UNDEBUG"]
    for directory in include_dirs:
        command += ["-I", str(directory)]
    command += [str(path) for path in sources]
    evidence_sources = sources + [BENCH / "src/main.c", Path(__file__)]
    for directory in (BENCH / "tests/stub", A04 / "tests/audio_stub", A04 / "include"):
        evidence_sources += sorted(directory.rglob("*.h"))
    evidence_sources += [A04 / "third_party/opus-1.6.1/include" / name
                         for name in ("opus.h", "opus_defines.h", "opus_types.h")]
    identities = {path.relative_to(ROOT).as_posix(): digest(path) for path in evidence_sources}
    temporary_root = (ROOT / ".tools/a04-bench-control").resolve()
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="host-", dir=temporary_root) as temporary:
        # Validate the exact directory before TemporaryDirectory's recursive
        # cleanup. It must be an immediate child of this named workspace path.
        if Path(temporary).resolve().parent != temporary_root:
            raise RuntimeError("Unexpected host-test temporary directory")
        executable = Path(temporary) / ("control.exe" if os.name == "nt" else "control")
        subprocess.run(command + ["-o", str(executable)], check=True, timeout=120)
        result = subprocess.run([str(executable)], check=False, timeout=20, text=True,
                                capture_output=True)
        print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        result.check_returncode()
        if "BENCH_CONTROL_OK" not in result.stdout:
            raise RuntimeError("Missing successful C harness completion marker")
        if identities != {path.relative_to(ROOT).as_posix(): digest(path) for path in evidence_sources}:
            raise RuntimeError("Sources changed during compilation/execution; evidence not published")
        report = {"schema": 1, "scope": "deterministic bench orchestration and actual audio adapter",
                  "hardware_tested": False, "stdout": result.stdout,
                  "sources": identities}
        if options.report:
            options.report.parent.mkdir(parents=True, exist_ok=True)
            options.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
