"""Build and run the bounded export cursor against the strict host NAND model.

Existing C-generated Opus fixtures are replayed exactly, not re-encoded. This
suite tests scheduling and source integrity; it does not measure physical NAND,
radio delivery, MCU timing, power loss, or audio decoding on a device.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
EXPECTED_CASES = [
    "all_chunk_capacities_final_interrupted_open",
    "record_boundary_resume_and_single_linear_replay",
    "wrapped_three_block_chain_maximum_AFR_and_bookmark",
    "exact_device_and_capture_identity_copied_at_open",
    "corrected_ECC_and_every_selected_unreadable_slot",
    "torn_tail_prefix_and_torn_checkpoint_policy",
    "valid_CRC_bad_framing_padding_and_holes",
    "global_unassociated_source_denies_selection_without_read",
    "source_mutation_between_verify_and_export_rejected",
    "third_verify_detects_mutation_of_already_emitted_source",
    "active_capture_epoch_remount_profile_and_binding_preempt",
    "cancel_all_phases_and_argument_bounds_no_NAND_writes",
    "coherent_v2_allocation_mutation_before_replay_and_after_DATA",
    "cancel_and_epoch_preempt_during_third_verify_and_after_DONE",
    "empty_interrupted_and_manifest_only_derived_archives",
    "OPEN_physical_manifest_bound_to_full_header_catalog_manifest",
    "real_Opus_fixture_finalized_export",
    "real_Opus_fixture_physical_OPEN_derived_export",
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    names = (
        "include/aura_journal_cursor.h", "include/aura_journal.h", "src/aura_journal.c",
        "include/aura_archive.h", "src/aura_archive.c", "include/aura_nand.h",
        "include/aura_opus.h", "tests/host_journal_cursor.c", "tests/nand_model.h",
        "tests/nand_model.c", "tests/CMakeLists.txt", "cmake/opus-profile.cmake",
        "dependencies/opus-1.6.1.json", "scripts/build.ps1", "scripts/verify_cursor.py",
        "fixtures/journal-0.aura", "fixtures/journal-0.receipt",
        "fixtures/journal-2.aura", "fixtures/journal-2.receipt",
    )
    return {(ROOT / name).relative_to(WORKSPACE).as_posix(): sha(ROOT / name) for name in names}


def command_output(command, timeout=30):
    run = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
    if run.returncode:
        raise RuntimeError(f"Command failed: {command!r}\n{run.stdout}{run.stderr}")
    return run.stdout + run.stderr


def main():
    tools = WORKSPACE / ".tools/a04-opus"
    build_dir = tools / "host"
    sources_before = source_hashes()
    dependency = json.loads((ROOT / "dependencies/opus-1.6.1.json").read_text())
    opus_dir = ROOT / "third_party" / dependency["directory"]
    # Check the actual linked upstream source tree against the repository lock.
    for name, digest in dependency["files"].items():
        if sha(opus_dir / name) != digest:
            raise ValueError(f"Opus dependency differs from lock: {name}")
    cmake = shutil.which("cmake") or str(WORKSPACE / ".tools/zephyr/venv/Lib/site-packages/cmake/data/bin/cmake.exe")
    build_command = [cmake, "--build", str(build_dir), "--target", "aura_journal_cursor_test", "-j", "2"]
    build = subprocess.run(build_command, text=True, capture_output=True, timeout=180)
    log_path = ROOT / "verification/journal-cursor-host.txt"
    report_path = ROOT / "verification/journal-cursor.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if build.returncode:
        log_path.write_text(build.stdout + build.stderr, encoding="utf-8", newline="\n")
        raise RuntimeError("Configure the pinned host build with build.ps1 first.\n" + build.stdout + build.stderr)
    executable = build_dir / "aura_journal_cursor_test.exe"
    artifacts = {"cursor_executable": executable, "linked_opus_library": build_dir / "opus/libopus.a"}
    binaries_before = {name: sha(path) for name, path in artifacts.items()}
    run_command = [str(executable)] + [str(ROOT / "fixtures" / name) for name in
        ("journal-0.aura", "journal-0.receipt", "journal-2.aura", "journal-2.receipt")]
    run = subprocess.run(run_command, text=True, capture_output=True, timeout=120)
    transcript = run.stdout + run.stderr
    log_path.write_text(transcript, encoding="utf-8", newline="\n")
    if run.returncode:
        raise RuntimeError(transcript)
    cases = re.findall(r"^CASE (\S+) PASS$", transcript, re.M)
    summary = re.search(r"^PASS cursor cases=(\d+) checks=(\d+) verify_calls=(\d+) read_calls=(\d+) "
                        r"max_reads_per_call=(\d+) cursor_bytes=(\d+) host_model_only=true$", transcript, re.M)
    if cases != EXPECTED_CASES or not summary or int(summary[1]) != len(cases):
        raise ValueError("Cursor suite did not report every required case")
    if int(summary[5]) != 1 or min(int(summary[n]) for n in (2, 3, 4, 6)) <= 0:
        raise ValueError("Missing bounded read or assertion evidence")
    fixture_rows = re.findall(r"^FIXTURE physical_open=([01]) export_bytes=(\d+) physical_bytes=(\d+) "
                             r"Opus_packets=(\d+) exact_file_and_receipt=true$", transcript, re.M)
    if len(fixture_rows) != 2 or [row[0] for row in fixture_rows] != ["0", "1"]:
        raise ValueError("Missing exact finalized and physical-OPEN fixture checks")
    fixtures = []
    for row, name in zip(fixture_rows, ("journal-0", "journal-2")):
        opened, exported, physical, packets = map(int, row)
        path = ROOT / f"fixtures/{name}.aura"
        if exported != path.stat().st_size or physical != exported - opened * 120 or packets <= 0:
            raise ValueError("Fixture size or derived-seal evidence mismatch")
        fixtures.append(dict(file=path.relative_to(WORKSPACE).as_posix(), sha256=sha(path),
            physical_receipt_sha256=sha(path.with_suffix(".receipt")), export_bytes=exported,
            physical_bytes=physical, audio_packets=packets, derived_seal=bool(opened),
            exact_file_and_physical_receipt=True, chunk_capacities=[1, 128, 256],
            reconstruction="Exact existing canonical records staged into host NAND, omit export-only ASE for OPEN, flush, reboot"))
    cache = (build_dir / "CMakeCache.txt").read_text()
    def cache_value(name):
        match = re.search(rf"^{re.escape(name)}:[^=]+=(.*)$", cache, re.M)
        if not match:
            raise ValueError(f"Missing configured toolchain value: {name}")
        return match[1].strip()
    compiler_command = [cache_value("CMAKE_C_COMPILER")] + shlex.split(cache_value("CMAKE_C_COMPILER_ARG1"))
    compiler_version = command_output(compiler_command + ["--version"])
    cmake_version = command_output([cmake, "--version"])
    if source_hashes() != sources_before:
        raise RuntimeError("Sources or fixtures changed during verification; rerun after they are stable")
    if {name: sha(path) for name, path in artifacts.items()} != binaries_before:
        raise RuntimeError("Executable or linked library changed during verification")
    for name, digest in dependency["files"].items():
        if sha(opus_dir / name) != digest:
            raise RuntimeError(f"Opus source changed during verification: {name}")
    report = dict(status="host_bounded_cursor_source_integrity_passed_device_unmeasured",
        generated_at_utc=datetime.now(timezone.utc).isoformat(), host_cases=len(cases),
        assertions=int(summary[2]), verify_step_calls=int(summary[3]), read_calls=int(summary[4]),
        max_NAND_reads_per_verify_or_read_call=int(summary[5]), cursor_context_bytes=int(summary[6]),
        case_names=cases, host_summary=summary[0], real_Opus_fixtures=fixtures,
        code_source_sha256=sources_before, executable_sha256=binaries_before["cursor_executable"],
        linked_Opus_library_sha256=binaries_before["linked_opus_library"],
        transcript_sha256=sha(log_path), build_command=build_command,
        build_output=(build.stdout + build.stderr).splitlines(), run_command=run_command,
        compiler=dict(command=compiler_command, version=compiler_version.splitlines(),
                      executable_sha256=sha(Path(compiler_command[0]))),
        cmake=dict(command=cmake, version=cmake_version.splitlines()), python=sys.version,
        Opus_dependency=dict(version=dependency["version"], locked_archive_sha256=dependency["sha256"],
                             files_verified_before_and_after=len(dependency["files"])),
        verified=["open/seek/cancel do not read NAND; verify/read each use at most one NAND read",
            "no NAND programs or erases during export/cancel operations",
            "capacities 1 through 256 for finalized/interrupted/open-derived synthetic captures",
            "exact record-boundary resume, manifest/physical/export EOF, non-boundary and UINT64_MAX rejection",
            "single linear replay plus mandatory third verification, including zero-DATA EOF resumes",
            "copied caller buffers remain immutable despite scratch overwrite and subsequent reads",
            "maximum AFR records, bookmarks and wrapped three-block chain with unrelated capture",
            "corrected ECC accepted; every inspected selected-chain unreadable slot fails closed",
            "conservative torn tail handling, malformed framing/padding/hole rejection, unassociated-source denial",
            "canonical first manifest must match full catalog/header manifest",
            "source payload and coherent allocation-identity changes fail before FINISHED",
            "source failure invalidates cached receipt; boundary/cancel/epoch cancellation preserves healthy cache",
            "cancel/epoch preemption during third verification and after DONE",
            "empty interrupted and manifest-only open-derived exports",
            "existing C-generated real Opus fixture files and physical receipts remain byte-identical"],
        not_verified=["physical NAND/SPI reads or power failures", "MCU wall-time/stack/power budget",
            "concurrent owners or raw-media mutations without invalidation",
            "BLE transaction retries, mobile durable acknowledgement, source reclamation",
            "fresh audio encode/decode in this cursor suite; existing speech fixture bytes are replayed"])
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(transcript, end="")
    print(f"PASS source-bound report: {report_path}")


if __name__ == "__main__":
    main()
