"""Strict host NAND model -> reboot -> AUR3 -> existing Python/SQLite -> FFmpeg.

This proves the portable journal under the described model, not physical NAND.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zlib

from verify_fixtures import make_ogg, pcm, signal_snr

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(WORKSPACE / "companion/src"))
from aura_companion.protocol_v2 import AUDIO, DurableReceiver, Receipt, read_archive


def main():
    tools = WORKSPACE / ".tools/a04-opus"
    source = pcm(ROOT / "fixtures/source-speech-16k.wav")
    raw = tools / "source-speech-16k.pcm"
    raw.write_bytes(source.tobytes())
    run = subprocess.run([str(tools / "host/aura_journal_test.exe"), str(raw),
                          str(ROOT / "fixtures/journal")], text=True, capture_output=True)
    (ROOT / "verification/journal-host.txt").write_text(run.stdout + run.stderr, encoding="utf-8", newline="\n")
    if run.returncode:
        raise RuntimeError(run.stdout + run.stderr)
    groups = re.search(r"^PASS journal groups=(\d+) journal_context=(\d+) model_is_host_only=(\d+)$", run.stdout, re.M)
    wrapped = re.search(r"^PASS wrapped_chain 3->0->1 captures=2 metadata_reads=12 payload_reads_at_mount=0 export_bytes=(\d+) exact_digest_and_receipt=true$", run.stdout, re.M)
    if (not groups or int(groups[1]) != 19 or not wrapped
            or "PASS conflicting_chains cases=12 no_source_erase=true" not in run.stdout
            or "PASS reclassified_continuation physical_orders=2 both_owners_faulted=true no_source_erase=true" not in run.stdout
            or "PASS owned_bindings exact_manifest=true one_use=true legacy_preserved=true durable_reservation_external=true" not in run.stdout
            or "PASS owned_chain_identity corruption_cases=13 wrapped_order=3->0->1 metadata_reads=18 legacy_crossowners_preserved=true" not in run.stdout
            or "PASS owned_power_cuts cases=52 header_checkpoint_identity=true no_binding_reuse=true" not in run.stdout):
        raise RuntimeError("Missing expected journal recovery coverage")
    results = []
    for mode, description in enumerate(("finalized_reboot", "staged_tail_lost", "partial_page_power_cut", "lost_program_completion", "wrapped_finalized_reboot", "owned_v2_wrapped_finalized_reboot")):
        case_source = source * 4 if mode in (4, 5) else source
        path = ROOT / f"fixtures/journal-{mode}.aura"
        archive = read_archive(path, allow_interrupted=True)
        physical = Receipt.parse(path.with_suffix(".receipt").read_bytes())
        if mode in (0, 4, 5):
            assert archive.status == "finalized" and physical == archive.receipt
            assert archive.original_source_samples == len(case_source)
        else:
            assert archive.status == "interrupted" and archive.original_source_samples is None
            assert not physical.sealed and archive.receipt.sealed
            assert physical.chain_sha256 == archive.termination.chain_sha256
            assert physical.next_sequence == archive.receipt.next_sequence
            assert physical.sample_count == archive.receipt.sample_count
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "capture.db"
            with DurableReceiver(db) as receiver:
                assert receiver.import_archive(archive) == archive.receipt
            with DurableReceiver(db) as receiver:
                assert receiver.import_archive(archive) == archive.receipt
                saved = list(receiver.packets(archive.capture))
        packets = [p.payload for p in saved if p.kind == AUDIO]
        meta = dict(source_samples=archive.source_samples, pre_skip=archive.termination.pre_skip, frame_ms=20)
        ogg, wav = tools / f"journal-{mode}.opus", tools / f"journal-{mode}.wav"
        ogg.write_bytes(make_ogg(meta, packets))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(ogg),
                        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], check=True)
        decoded = pcm(wav)
        assert len(decoded) == archive.source_samples
        snr = signal_snr(case_source[:len(decoded)], decoded)
        assert snr >= 8
        allocation_identity = dict(metadata_version=1, owned=False)
        if mode == 5:
            identity_path = path.with_suffix(".allocation")
            metadata = identity_path.read_bytes()
            assert len(metadata) == 1024
            incarnation = bytes((0xA4, *range(2, 17)))
            generation = 0x100000002
            for part, block in enumerate((7, 0)):
                header = metadata[part * 512:part * 512 + 256]
                checkpoint = metadata[part * 512 + 256:part * 512 + 512]
                for page, magic in ((header, b"A4NH"), (checkpoint, b"A4NC")):
                    assert page[:6] == magic + bytes((2, 0))
                    assert int.from_bytes(page[6:8], "little") == 256
                    assert int.from_bytes(page[8:12], "little") == block
                    assert int.from_bytes(page[252:256], "little") == zlib.crc32(page[:252])
                assert header[222:238] == checkpoint[122:138] == incarnation
                assert int.from_bytes(header[238:246], "little") == generation
                assert int.from_bytes(checkpoint[138:146], "little") == generation
                assert header[246:252] == bytes(6) and checkpoint[146:252] == bytes(106)
                assert header[60:128] == path.read_bytes()[:68]
                assert int.from_bytes(header[12:16], "little") == (0xFFFFFFFF if part == 0 else 7)
                assert int.from_bytes(header[16:20], "little") == part
                assert int.from_bytes(checkpoint[12:16], "little") == part
            assert metadata[512 + 128:512 + 222] == metadata[256 + 28:256 + 122]
            assert metadata[768 + 28:768 + 122] == path.with_suffix(".receipt").read_bytes()
            allocation_identity = dict(metadata_version=2, owned=True,
                incarnation_hex=incarnation.hex(), allocation_generation=generation,
                metadata_file_sha256=hashlib.sha256(metadata).hexdigest(),
                independent_metadata_crc_and_identity_checks=True,
                deletion_authority=False)
        results.append(dict(case=description, file=path.relative_to(ROOT).as_posix(),
            file_sha256=archive.sha256_hex, status=archive.status, bytes=path.stat().st_size,
            audio_packets=len(packets), decoded_samples=len(decoded), waveform_snr_db=snr,
            original_source_samples=archive.original_source_samples,
            tested_physical_block_order=[7, 0] if mode in (4, 5) else [0], allocation_identity=allocation_identity,
            physical_receipt_status="terminal" if physical.sealed else "open_prefix",
            physical_prefix_digest=physical.chain_sha256.hex(), export_terminal_digest=archive.receipt.chain_sha256.hex()))
    assert results[1]["decoded_samples"] == results[2]["decoded_samples"]
    assert results[3]["decoded_samples"] > results[2]["decoded_samples"]
    files = [ROOT / "src/aura_journal.c", ROOT / "include/aura_journal.h", ROOT / "include/aura_journal_cursor.h", ROOT / "include/aura_nand.h",
             ROOT / "src/aura_archive.c", ROOT / "include/aura_archive.h", ROOT / "src/aura_opus.c",
             ROOT / "include/aura_opus.h", ROOT / "tests/nand_model.c", ROOT / "tests/nand_model.h",
             ROOT / "tests/host_journal.c", ROOT / "tests/CMakeLists.txt", ROOT / "scripts/build.ps1",
             ROOT / "src/aura_w25n01gv.c", ROOT / "include/aura_w25n01gv.h", ROOT / "tests/host_w25n01gv.c",
             Path(__file__), WORKSPACE / "companion/src/aura_companion/protocol_v2.py"]
    report = dict(status="host_NAND_model_real_Opus_Python_SQLite_FFmpeg_passed_device_unmeasured",
        host_groups=int(groups[1]), journal_context_bytes=int(groups[2]), host_model_bytes=int(groups[3]),
        host_executable_sha256=hashlib.sha256((tools / "host/aura_journal_test.exe").read_bytes()).hexdigest(),
        host_transcript_sha256=hashlib.sha256((ROOT / "verification/journal-host.txt").read_bytes()).hexdigest(),
        wrapped_chain=dict(physical_order=[3, 0, 1], unrelated_capture_block=2, exact_export_bytes=int(wrapped[1]),
            identical_export_and_receipt=True, mount_metadata_reads=12, mount_payload_reads=0,
            malformed_chain_cases=12, reclassified_checkpoint_ownership_orders=2, additional_programs_or_erases=0),
        owned_allocation=dict(binding="exact68B manifest; single-use nonzero generation", namespace_bytes=16,
            metadata_version=2, corruption_cases=13, power_cut_cases=52, mixed_wrapped_mount_metadata_reads=18,
            per_capture_or_block_ram_arrays_added=False, additional_host_context_bytes=120,
            durable_reservation_and_authenticated_release_external=True),
        python=sys.version, cases=results, code_source_sha256={p.relative_to(WORKSPACE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        model_guarantees=["once per page across reset", "ascending page order", "1 to 0 only", "all six factory markers",
            "reserved BBM endpoints", "corrected and uncorrectable ECC", "partial and lost program completion",
            "partial and lost erase completion", "no populated erase", "no receipt from staging or metadata",
            "full scan beyond gaps and checkpoint declarations", "128 capture and media-full bounds",
            "bounded wrapped allocation and order-independent continuation recovery",
            "conflicting continuation chains preserve source and deny receipts",
            "v2 allocation namespace/generation consistency across headers and checkpoints",
            "exact single-use next-capture binding; no unbound owned capture",
            "full verification before returning physical allocation identity"],
        limitations=["physical SPI/NAND power failure unmeasured", "marker and LUT reads are separate from portable mount counters",
            "no populated block reclamation even after host acknowledgement", "128 captures maximum until product reclamation exists",
            "caller must service journal at a bounded cadence while paused", "no board GPIO or PDM integration"])
    (ROOT / "verification/journal-roundtrip.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(run.stdout, end="")
    for result in results:
        print(f"PASS {result['case']}: {result['decoded_samples']} decoded samples, SNR {result['waveform_snr_db']} dB")


if __name__ == "__main__":
    main()
