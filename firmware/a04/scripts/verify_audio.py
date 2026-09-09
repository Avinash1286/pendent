"""Bind deterministic audio-adapter interleavings to the tested production code."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    executable = WORKSPACE / ".tools/a04-opus/host/aura_audio_test.exe"
    result = subprocess.run([str(executable)], capture_output=True, text=True)
    output = result.stdout + result.stderr
    transcript = ROOT / "verification/audio-host.txt"
    transcript.write_text(output, encoding="utf-8", newline="\n")
    if result.returncode:
        raise RuntimeError(output)
    summary = re.search(r"interleavings: (\d+) groups PASS, (\d+) failed; context=(\d+) bytes", output)
    if not summary or int(summary[1]) != 10 or int(summary[2]) != 0:
        raise ValueError("Expected all 10 adapter test groups and zero failures")
    sources = [ROOT / name for name in (
        "src/aura_audio_zephyr.c", "src/aura_recorder.c", "src/aura_opus.c",
        "src/aura_archive.c", "src/aura_journal.c", "tests/host_audio.c",
        "tests/nand_model.c", "tests/nand_model.h", "tests/CMakeLists.txt",
        "cmake/opus-profile.cmake", "dependencies/opus-1.6.1.json",
        "scripts/verify_audio.py")]
    sources += list((ROOT / "include").glob("*.h"))
    sources += list((ROOT / "tests/audio_stub").rglob("*.h"))
    report = {
        "status": "deterministic_host_interleavings_passed",
        "passed_groups": int(summary[1]),
        "host_adapter_context_bytes": int(summary[3]),
        "scope": "Actual audio adapter, recorder, Opus, archive and journal; kernel/GPIO/DMIC boundaries are test doubles",
        "groups": ["mixing", "fifo_stop", "overflow_and_driver", "privacy_and_start_failure",
                   "quarantine_and_restart", "storage_failure", "startup_races",
                   "negative_driver_results", "publication_interleavings", "init_live_ownership"],
        "code_source_sha256": {p.relative_to(WORKSPACE).as_posix(): sha(p) for p in sorted(sources)},
        "executable_sha256": sha(executable),
        "transcript_sha256": sha(transcript),
        "compile_options": ["-Wall", "-Wextra", "-Werror", "-UNDEBUG"],
        "not_verified": ["physical PDM/DMA", "real concurrent execution", "interrupt latency",
                         "electrical privacy cutoff", "real storage/CPU deadlines", "wearable operation"],
    }
    (ROOT / "verification/audio-host.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(output, end="")


if __name__ == "__main__":
    main()
