"""Source-bound host command engine checks and C wire vectors for Kotlin.

No GATT service, enrollment, radio notification or phone acknowledgement is
implemented by this suite. Existing speech packets are reserialized unchanged
under deterministic public generation-derived owned identities.
"""
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from verify_cursor import sha, command_output

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
EXPECTED_CASES = [
    "real_owned_Opus_finalized_and_OPEN_full_wire_roundtrip",
    "pending_join_immutable_cached_retry_and_response_sent_gate",
    "malformed_admission_does_not_consume_transaction_or_replace_cache",
    "immediate_and_late_contextual_errors_are_exact_cached_four_bytes",
    "first_READ_boundary_resume_followed_by_arbitrary_chunk_offsets_and_EOF",
    "privileged_catalog_flags_and_owned_generation_identity_enforcement",
    "source_corruption_fails_SELECT_READ_and_final_third_verification",
    "epoch_change_invalidates_pending_work_cached_response_and_handle",
    "local_cancel_disconnect_reconnect_and_authorization_loss_drop_old_callbacks",
    "checked_transaction_handle_and_revision_limits_test_only_injection",
    "private_and_overlapping_output_aliases_reject_before_any_write",
    "empty_catalog_empty_archives_and_ordered_CANCEL_preserve_source",
]


def sources():
    files = [ROOT / name for name in (
        "include/aura_transfer.h", "src/aura_transfer.c", "tests/host_transfer.c",
        "include/aura_journal_cursor.h", "include/aura_journal.h", "src/aura_journal.c",
        "include/aura_archive.h", "src/aura_archive.c", "include/aura_nand.h", "include/aura_opus.h",
        "include/aura_storage.h", "src/aura_storage.c", "include/aura_control.h", "src/aura_control.c",
        "include/aura_release_auth.h", "src/aura_release_auth.c", "tests/nand_model.h", "tests/nand_model.c",
        "tests/CMakeLists.txt", "cmake/opus-profile.cmake", "dependencies/opus-1.6.1.json",
        "scripts/build.ps1", "scripts/verify_cursor.py", "scripts/verify_transfer.py",
        "fixtures/journal-0.aura", "fixtures/journal-2.aura",
    )]
    files += [WORKSPACE / "docs/a04/transfer-wire-v1.md"]
    return {p.relative_to(WORKSPACE).as_posix(): sha(p) for p in files}


def verify_golden(path):
    with path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.reader((line for line in file if line.strip() and not line.startswith("#")), delimiter="\t"))
    commands, responses, contexts, fragments = {}, {}, {}, {}
    for row in rows:
        if len(row) != 3:
            raise ValueError("Golden row must contain name, kind, hex")
        name, kind, value = row
        data = bytes.fromhex(value)
        if kind == "context":
            if name in contexts or len(data) != 16 or not any(data):
                raise ValueError("Invalid golden context")
            contexts[name] = data
        elif kind == "command":
            if name in commands or len(data) < 4 or data[0] != 1 or int.from_bytes(data[2:4], "little") == 0:
                raise ValueError("Invalid or duplicate golden command")
            lengths = {1: 4, 2: 10, 3: 20, 4: 18, 5: 16, 6: 8}
            if len(data) != lengths.get(data[1]):
                raise ValueError("Wrong command wire length")
            commands[name] = data
        elif kind == "response":
            command = commands[name]
            if name in responses or len(data) > 512 or data[:4] != bytes((0, command[1])) + command[2:4]:
                raise ValueError("Golden success response does not match its request")
            responses[name] = data
        elif kind in ("fragment23", "fragment517"):
            response = responses[name]
            mtu = int(kind.removeprefix("fragment"))
            chain = fragments.setdefault((name, mtu), bytearray())
            if (not 8 < len(data) <= mtu - 3 or data[:2] != b"\x01\x00"
                    or data[2:4] != response[2:4] or int.from_bytes(data[4:6], "little") != len(chain)
                    or int.from_bytes(data[6:8], "little") != len(response)):
                raise ValueError("Golden fragment has inconsistent bounds, identity or order")
            chain.extend(data[8:])
        else:
            raise ValueError(f"Unknown golden kind: {kind}")
    if set(contexts) != {"device_id", "incarnation"} or set(commands) != set(responses):
        raise ValueError("Golden owner context or command/response pairs missing")
    if {data[1] for data in commands.values()} != set(range(1, 7)) or len(fragments) != 4:
        raise ValueError("Golden must cover all six opcodes and both MTUs for two selections")
    for (name, _), wire in fragments.items():
        if wire != responses[name]:
            raise ValueError("Golden fragments do not reproduce exact logical response")
    return dict(path=path.relative_to(WORKSPACE).as_posix(), sha256=sha(path), rows=len(rows),
        command_response_pairs=len(commands), completed_fragment_chains=len(fragments),
        opcodes=sorted({data[1] for data in commands.values()}), actual_ATT_MTUs=[23, 517],
        contexts={name: data.hex() for name, data in contexts.items()},
        format="Comment header; name<TAB>kind<TAB>hex; same command/response names; fragment23/fragment517 share response name")


def main():
    build_dir = WORKSPACE / ".tools/a04-opus/host"
    sources_before = sources()
    dependency = json.loads((ROOT / "dependencies/opus-1.6.1.json").read_text())
    opus_dir = ROOT / "third_party" / dependency["directory"]
    def check_dependency():
        for name, digest in dependency["files"].items():
            if sha(opus_dir / name) != digest:
                raise ValueError(f"Opus source differs from lock: {name}")
    check_dependency()
    cmake = shutil.which("cmake") or str(WORKSPACE / ".tools/zephyr/venv/Lib/site-packages/cmake/data/bin/cmake.exe")
    build_command = [cmake, "--build", str(build_dir), "--target", "aura_transfer_test", "-j", "2"]
    build = subprocess.run(build_command, text=True, capture_output=True, timeout=180)
    log = ROOT / "verification/transfer-host.txt"
    golden = ROOT / "verification/transfer-wire-golden.tsv"
    if build.returncode:
        log.write_text(build.stdout + build.stderr, encoding="utf-8", newline="\n")
        raise RuntimeError("Configure the pinned host build with build.ps1 first.\n" + build.stdout + build.stderr)
    artifacts = {"transfer_executable": build_dir / "aura_transfer_test.exe", "linked_Opus_library": build_dir / "opus/libopus.a"}
    binaries_before = {name: sha(path) for name, path in artifacts.items()}
    run_command = [str(artifacts["transfer_executable"]), str(ROOT / "fixtures/journal-0.aura"),
                   str(ROOT / "fixtures/journal-2.aura"), str(golden)]
    run = subprocess.run(run_command, text=True, capture_output=True, timeout=120)
    transcript = run.stdout + run.stderr
    log.write_text(transcript, encoding="utf-8", newline="\n")
    if run.returncode:
        raise RuntimeError(transcript)
    cases = re.findall(r"^CASE (\S+) PASS$", transcript, re.M)
    summary = re.search(r"^PASS transfer cases=(\d+) checks=(\d+) step_calls=(\d+) no_io_calls=(\d+) "
                        r"max_reads_per_step=(\d+) transfer_bytes=(\d+) host_model_only=true$", transcript, re.M)
    if cases != EXPECTED_CASES or not summary or int(summary[1]) != len(cases):
        raise ValueError("Transfer suite did not report all expected cases")
    if int(summary[5]) != 1 or min(int(summary[n]) for n in (2, 3, 4, 6)) <= 0:
        raise ValueError("Missing operation-bound evidence")
    golden_evidence = verify_golden(golden)
    cache = (build_dir / "CMakeCache.txt").read_text()
    def cache_value(name):
        found = re.search(rf"^{re.escape(name)}:[^=]+=(.*)$", cache, re.M)
        if not found:
            raise ValueError(f"Missing configured toolchain value: {name}")
        return found[1].strip()
    compiler = [cache_value("CMAKE_C_COMPILER")] + shlex.split(cache_value("CMAKE_C_COMPILER_ARG1"))
    compiler_version = command_output(compiler + ["--version"])
    cmake_version = command_output([cmake, "--version"])
    if sources() != sources_before or {name: sha(path) for name, path in artifacts.items()} != binaries_before:
        raise RuntimeError("Source, fixture or executable changed during verification; rerun after freeze")
    check_dependency()
    report = dict(status="host_transfer_engine_and_C_wire_vectors_passed_no_GATT_or_phone_claim",
        generated_at_utc=datetime.now(timezone.utc).isoformat(), host_cases=len(cases), assertions=int(summary[2]),
        bounded_step_calls=int(summary[3]), no_IO_API_calls=int(summary[4]), max_NAND_reads_per_step=int(summary[5]),
        transfer_context_bytes=int(summary[6]), case_names=cases, host_summary=summary[0],
        golden_vectors=golden_evidence, code_source_sha256=sources_before, executable_sha256=binaries_before["transfer_executable"],
        linked_Opus_library_sha256=binaries_before["linked_Opus_library"], transcript_sha256=sha(log),
        build_command=build_command, build_output=(build.stdout + build.stderr).splitlines(), run_command=run_command,
        compiler=dict(command=compiler, version=compiler_version.splitlines(), executable_sha256=sha(Path(compiler[0]))),
        cmake=dict(command=cmake, version=cmake_version.splitlines()), python=sys.version,
        Opus_dependency=dict(version=dependency["version"], locked_archive_sha256=dependency["sha256"],
                             files_verified_before_and_after=len(dependency["files"])),
        verified=["real journal/cursor/NAND model with owned generation-derived captures",
            "unchanged existing real Opus payloads reserialized under deterministic public owners",
            "exact HELLO/LIST/SELECT/READ/FINISH/CANCEL layouts and physical receipt provenance",
            "at most one NAND read per step; no NAND programs or erases by transport APIs",
            "pending joins and completed cached retries do not repeat NAND I/O",
            "delivery token changes after completed retry; old fragment/completion cannot release newer gate",
            "first-READ complete-record resume then arbitrary sequential byte offsets and full EOF verification",
            "admission busy, malformed, changed/older transactions preserve work and transaction high-water",
            "contextual four-byte errors and late source failure before successful FINISH",
            "source epoch, owner profile, authorization and connection generation invalidate publication",
            "test-only near-limit transaction/handle/revision/delivery injection fails closed",
            "private and overlapping output aliases rejected before any output/state write",
            "empty catalog, empty interrupted/OPEN captures and ordered cancellation",
            "MTU23/517 fragments reconstruct exact immutable logical responses"],
        not_verified=["physical radio, GATT callbacks or actual phone download", "ownership enrollment or authentication implementation",
            "physical NAND/MCU timing, power failure or concurrent callers", "source deletion or storage release",
            "global connection-counter exhaustion injection; production counter is not exported",
            "Kotlin cross-language execution (reported separately by the Android core verifier)"])
    path = ROOT / "verification/transfer-host.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(transcript, end="")
    print(f"PASS source-bound transfer report: {path}")


if __name__ == "__main__":
    main()
