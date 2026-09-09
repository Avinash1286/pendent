"""Source-bound host command engine checks and C wire vectors for Kotlin.

No GATT service, enrollment, radio notification or phone acknowledgement is
implemented by this suite. Existing speech packets are reserialized unchanged
under deterministic public generation-derived owned identities.
"""
import csv
import array
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from verify_cursor import sha, command_output
from verify_fixtures import make_ogg, pcm, signal_snr

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(WORKSPACE / "companion/src"))
from aura_companion.protocol_v2 import AUDIO, OPEN, FINALIZED, Receipt, read_archive
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
        "scripts/build.ps1", "scripts/verify_cursor.py", "scripts/verify_transfer.py", "scripts/verify_fixtures.py",
        "fixtures/journal-0.aura", "fixtures/journal-2.aura", "fixtures/source-speech-16k.wav",
    )]
    files += [WORKSPACE / "docs/a04/transfer-wire-v1.md"]
    files += [WORKSPACE / f"companion/src/aura_companion/{name}.py" for name in ("protocol", "protocol_v2")]
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


def verify_receiver_fixtures(directory, golden_path, transcript):
    with golden_path.open(encoding="utf-8", newline="") as file:
        response_rows = {name: bytes.fromhex(value) for name, kind, value in
            csv.reader((line for line in file if line.strip() and not line.startswith("#")), delimiter="\t")
            if kind == "response"}
    device = bytes([0x11]) * 16
    incarnation = bytes((0xA4, *range(2, 17)))
    source = pcm(ROOT / "fixtures/source-speech-16k.wav")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Existing FFmpeg is required for independent fixture decode")
    ffmpeg_identity = dict(path=ffmpeg, sha256=sha(Path(ffmpeg)),
                           version=command_output([ffmpeg, "-version"]).splitlines()[0])
    results = []
    for name, generation, original, prefix in (("finalized", 42, "journal-0.aura", "final"), ("open", 43, "journal-2.aura", "open")):
        path = directory / f"{name}.aura"
        ack_path = directory / f"{name}.physical.ack3"
        archive = read_archive(path, allow_interrupted=True)
        if archive.seal is None or archive.discarded_tail_bytes:
            raise ValueError("Saved receiver fixture must contain its exact terminal export seal with no recovered tail")
        physical = Receipt.parse(ack_path.read_bytes())
        original_archive = read_archive(ROOT / "fixtures" / original, allow_interrupted=True)
        packets, original_packets = list(archive.iter_packets()), list(original_archive.iter_packets())
        if [packet.encode() for packet in packets] != [packet.encode() for packet in original_packets]:
            raise ValueError("Owned fixture changed original encoded audio/bookmark records")
        expected_capture = hashlib.sha256(b"AURA-A04-CAPTURE-v1\0" + device + incarnation + generation.to_bytes(8, "little")).digest()[:16]
        if archive.capture.device_id != device or archive.capture.capture_id != expected_capture:
            raise ValueError("Owned fixture identity does not match independent generation derivation")
        selected, finished = response_rows[prefix + ".select"], response_rows[prefix + ".finish"]
        expected_physical_bytes = archive.file_bytes - (120 if name == "open" else 0)
        if (selected[8:76] != archive.capture.encode() or selected[76:170] != physical.encode()
                or finished[8:102] != physical.encode()
                or int.from_bytes(selected[170:178], "little") != expected_physical_bytes
                or int.from_bytes(selected[178:186], "little") != archive.file_bytes
                or int.from_bytes(finished[102:110], "little") != archive.file_bytes
                or selected[186] != (name == "open") or finished[110] != selected[186]
                or int.from_bytes(selected[187:195], "little") != generation
                or int.from_bytes(finished[111:119], "little") != generation):
            raise ValueError("Saved fixture differs from exact SELECT/FINISH wire vectors")
        if name == "finalized":
            if archive.status != "finalized" or physical != archive.receipt or physical.status != FINALIZED:
                raise ValueError("Finalized physical receipt differs from full export receipt")
        else:
            if (archive.status != "interrupted" or archive.original_source_samples is not None or physical.status != OPEN
                    or (physical.device_id, physical.capture_id, physical.next_sequence, physical.encoded_bytes, physical.sample_count)
                    != (archive.receipt.device_id, archive.receipt.capture_id, archive.receipt.next_sequence,
                        archive.receipt.encoded_bytes, archive.receipt.sample_count)
                    or physical.chain_sha256 != archive.termination.chain_sha256
                    or 68 + 26 * physical.next_sequence + physical.encoded_bytes != expected_physical_bytes):
                raise ValueError("OPEN physical prefix was not preserved distinctly from derived export seal")
        audio_packets = [packet.payload for packet in packets if packet.kind == AUDIO]
        ogg = make_ogg(dict(source_samples=archive.source_samples, pre_skip=archive.termination.pre_skip,
                            frame_ms=archive.capture.frame_samples // 16), audio_packets)
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-ar", "16000", "-ac", "1",
                   "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1"]
        decoded_run = subprocess.run(command, input=ogg, capture_output=True, timeout=30)
        if decoded_run.returncode or len(decoded_run.stdout) % 2:
            raise RuntimeError("FFmpeg fixture decode failed: " + decoded_run.stderr.decode(errors="replace"))
        decoded = array.array("h")
        decoded.frombytes(decoded_run.stdout)
        if sys.byteorder != "little":
            decoded.byteswap()
        if len(decoded) != archive.source_samples:
            raise ValueError("Independent decode did not preserve exact source sample count")
        snr = signal_snr(source[:len(decoded)], decoded)
        if snr < 8:
            raise ValueError("Owned fixture failed the existing speech SNR regression floor")
        evidence_line = (f"FIXTURE {name} generation={generation} export_bytes={archive.file_bytes} "
                         f"physical_bytes={expected_physical_bytes} physical_status={physical.status} export_status={archive.termination.status}")
        if evidence_line not in transcript.splitlines():
            raise ValueError("C output did not report saved receiver fixture")
        results.append(dict(name=name, allocation_generation=generation, capture_id=expected_capture.hex(),
            file=path.relative_to(WORKSPACE).as_posix(), file_sha256=sha(path), export_bytes=archive.file_bytes,
            physical_receipt_file=ack_path.relative_to(WORKSPACE).as_posix(), physical_receipt_sha256=sha(ack_path),
            physical_receipt_bytes=ack_path.stat().st_size, physical_bytes=expected_physical_bytes,
            physical_status=physical.status, export_status=archive.status, derived_seal=name == "open",
            source_fixture=f"firmware/a04/fixtures/{original}", source_fixture_sha256=sha(ROOT / "fixtures" / original),
            original_record_bytes_unchanged=True, audio_packets=len(audio_packets), source_samples=archive.source_samples,
            original_source_samples=archive.original_source_samples, decoded_samples=len(decoded), waveform_snr_db=snr,
            matches_SELECT_and_FINISH_vectors=True,
            provenance="Real existing C Opus packets rebound to generation-derived owned v2 NAND, remounted, cursor READ bytes compared to exact full export, FINISH verified before fixture write"))
    return dict(directory=directory.relative_to(WORKSPACE).as_posix(), fixtures=results, independent_decoder=ffmpeg_identity,
                scope="Deterministic public host-model test inputs; physical ACK3 remains distinct from export or phone durable receipt")


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
    golden_before = sha(golden) if golden.exists() else None
    fixture_dir = ROOT / "verification/transfer-fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    if build.returncode:
        log.write_text(build.stdout + build.stderr, encoding="utf-8", newline="\n")
        raise RuntimeError("Configure the pinned host build with build.ps1 first.\n" + build.stdout + build.stderr)
    artifacts = {"transfer_executable": build_dir / "aura_transfer_test.exe", "linked_Opus_library": build_dir / "opus/libopus.a"}
    binaries_before = {name: sha(path) for name, path in artifacts.items()}
    run_command = [str(artifacts["transfer_executable"]), str(ROOT / "fixtures/journal-0.aura"),
                   str(ROOT / "fixtures/journal-2.aura"), str(golden), str(fixture_dir)]
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
    if golden_before is not None and sha(golden) != golden_before:
        raise ValueError("Existing transfer wire golden bytes changed; review before replacing cross-language vectors")
    golden_evidence["unchanged_from_pre_run"] = golden_before is not None
    receiver_fixtures = verify_receiver_fixtures(fixture_dir, golden, transcript)
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
        golden_vectors=golden_evidence, receiver_fixtures=receiver_fixtures,
        code_source_sha256=sources_before, executable_sha256=binaries_before["transfer_executable"],
        linked_Opus_library_sha256=binaries_before["linked_Opus_library"], transcript_sha256=sha(log),
        build_command=build_command, build_output=(build.stdout + build.stderr).splitlines(), run_command=run_command,
        compiler=dict(command=compiler, version=compiler_version.splitlines(), executable_sha256=sha(Path(compiler[0]))),
        cmake=dict(command=cmake, version=cmake_version.splitlines()), python=sys.version,
        Opus_dependency=dict(version=dependency["version"], locked_archive_sha256=dependency["sha256"],
                             files_verified_before_and_after=len(dependency["files"])),
        verified=["real journal/cursor/NAND model with owned generation-derived captures",
            "unchanged existing real Opus payloads reserialized under deterministic public owners",
            "saved owned finalized and physical-OPEN archives/ACK3 match full transfers and independent Python validation",
            "independent FFmpeg decode of saved fixtures preserves exact source duration and speech regression SNR",
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
