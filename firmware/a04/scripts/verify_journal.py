"""Strict host NAND model -> reboot -> AUR3 -> existing Python/SQLite -> FFmpeg.

This proves the portable journal under the described model, not physical NAND.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

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
    results = []
    for mode, description in enumerate(("finalized_reboot", "staged_tail_lost", "partial_page_power_cut", "lost_program_completion")):
        path = ROOT / f"fixtures/journal-{mode}.aura"
        archive = read_archive(path, allow_interrupted=True)
        physical = Receipt.parse(path.with_suffix(".receipt").read_bytes())
        if mode == 0:
            assert archive.status == "finalized" and physical == archive.receipt
            assert archive.original_source_samples == len(source)
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
        snr = signal_snr(source[:len(decoded)], decoded)
        assert snr >= 8
        results.append(dict(case=description, file=path.relative_to(ROOT).as_posix(),
            file_sha256=archive.sha256_hex, status=archive.status, bytes=path.stat().st_size,
            audio_packets=len(packets), decoded_samples=len(decoded), waveform_snr_db=snr,
            original_source_samples=archive.original_source_samples,
            physical_receipt_status="terminal" if physical.sealed else "open_prefix",
            physical_prefix_digest=physical.chain_sha256.hex(), export_terminal_digest=archive.receipt.chain_sha256.hex()))
    assert results[1]["decoded_samples"] == results[2]["decoded_samples"]
    assert results[3]["decoded_samples"] > results[2]["decoded_samples"]
    files = [ROOT / "src/aura_journal.c", ROOT / "include/aura_journal.h", ROOT / "include/aura_nand.h",
             ROOT / "src/aura_archive.c", ROOT / "include/aura_archive.h", ROOT / "src/aura_opus.c",
             ROOT / "include/aura_opus.h", ROOT / "tests/nand_model.c", ROOT / "tests/nand_model.h",
             ROOT / "tests/host_journal.c", ROOT / "tests/CMakeLists.txt", ROOT / "scripts/build.ps1",
             ROOT / "src/aura_w25n01gv.c", ROOT / "include/aura_w25n01gv.h", ROOT / "tests/host_w25n01gv.c",
             Path(__file__), WORKSPACE / "companion/src/aura_companion/protocol_v2.py"]
    report = dict(status="host_NAND_model_real_Opus_Python_SQLite_FFmpeg_passed_device_unmeasured",
        python=sys.version, cases=results, code_source_sha256={p.relative_to(WORKSPACE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        model_guarantees=["once per page across reset", "ascending page order", "1 to 0 only", "all six factory markers",
            "reserved BBM endpoints", "corrected and uncorrectable ECC", "partial and lost program completion",
            "partial and lost erase completion", "no populated erase", "no receipt from staging or metadata",
            "full scan beyond gaps and checkpoint declarations", "128 capture and media-full bounds"],
        limitations=["physical SPI/NAND power failure unmeasured", "marker and LUT reads are separate from portable mount counters",
            "no populated block reclamation even after host acknowledgement", "128 captures maximum until product reclamation exists",
            "caller must service journal at a bounded cadence while paused", "no board GPIO or PDM integration"])
    (ROOT / "verification/journal-roundtrip.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(run.stdout, end="")
    for result in results:
        print(f"PASS {result['case']}: {result['decoded_samples']} decoded samples, SNR {result['waveform_snr_db']} dB")


if __name__ == "__main__":
    main()
