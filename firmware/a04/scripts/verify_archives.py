"""Real C AUR3 -> Python durable receipt -> independent Ogg/FFmpeg decode.

Small checked-in synthetic fixtures only. The public archive reader streams;
this fixture reporter intentionally collects packets to reuse the Ogg helper.
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
from aura_companion.protocol_v2 import AUDIO, BOOKMARK, DurableReceiver, Receipt, read_archive


def main():
    tools = WORKSPACE / ".tools/a04-opus"
    source = pcm(ROOT / "fixtures/source-speech-16k.wav")
    raw_source = tools / "source-speech-16k.pcm"
    raw_source.write_bytes(source.tobytes())
    run = subprocess.run([str(tools / "host/aura_archive_test.exe"), str(raw_source),
                          str(ROOT / "fixtures/capture")], text=True, capture_output=True, check=True)
    (ROOT / "verification/archive-host.txt").write_text(run.stdout, encoding="utf-8", newline="\n")
    metrics = []
    for name in ("capture-10ms", "capture-20ms", "capture-20ms-interrupted", "capture-20ms-open"):
        path = ROOT / f"fixtures/{name}.aura"
        archive = read_archive(path, allow_interrupted=True)
        c_receipt = Receipt.parse(path.with_suffix(".receipt").read_bytes())
        if archive.seal:
            assert c_receipt == archive.receipt, "C/Python terminal receipts diverged"
        else:
            assert c_receipt.chain_sha256 == archive.termination.chain_sha256
            assert not c_receipt.sealed and archive.receipt.sealed
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "capture.db"
            with DurableReceiver(database) as receiver:
                assert receiver.import_archive(archive) == archive.receipt
            with DurableReceiver(database) as receiver:
                assert receiver.import_archive(archive) == archive.receipt
                saved = list(receiver.packets(archive.capture))
        packets = [p.payload for p in saved if p.kind == AUDIO]
        metadata = dict(source_samples=archive.source_samples, pre_skip=archive.termination.pre_skip,
                        frame_ms=archive.capture.frame_samples // 16)
        ogg = tools / f"{name}.opus"
        wav = tools / f"{name}.wav"
        ogg.write_bytes(make_ogg(metadata, packets))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(ogg),
                        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], check=True)
        decoded = pcm(wav)
        snr = signal_snr(source[:archive.source_samples], decoded)
        if snr < 8:
            raise ValueError("Unexpected codec/trim regression in archived synthetic speech")
        expected = 120847 if archive.status == "finalized" else 120600
        assert len(decoded) == expected
        bookmarks = [{"source_sample": p.sample_offset,
                      "available": p.sample_offset <= archive.source_samples}
                     for p in saved if p.kind == BOOKMARK]
        metrics.append(dict(file=path.relative_to(ROOT).as_posix(), status=archive.status,
            file_sha256=archive.sha256_hex, terminal_digest=archive.receipt.chain_sha256.hex(),
            packet_prefix_digest=archive.termination.chain_sha256.hex(),
            bytes=path.stat().st_size, records=len(saved), audio_packets=len(packets),
            encoded_bytes=archive.receipt.encoded_bytes, encoded_samples=archive.receipt.sample_count,
            source_samples=archive.source_samples, original_source_samples=archive.original_source_samples,
            pre_skip=archive.termination.pre_skip, end_trim=archive.end_trim,
            decoded_samples=len(decoded), waveform_snr_db=snr, bookmarks=bookmarks,
            c_terminal_receipt_match=c_receipt == archive.receipt,
            c_open_prefix_match=c_receipt.chain_sha256 == archive.termination.chain_sha256))
    report = dict(status="C_Python_durable_receiver_FFmpeg_passed_device_unmeasured", wire_version=3,
        source_sha256=hashlib.sha256((ROOT / "fixtures/source-speech-16k.wav").read_bytes()).hexdigest(),
        fixtures=metrics,
        code_source_sha256={path.relative_to(WORKSPACE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [ROOT / "src/aura_archive.c", ROOT / "include/aura_archive.h", ROOT / "src/aura_opus.c",
                         ROOT / "tests/host_archive.c", Path(__file__),
                         WORKSPACE / "companion/src/aura_companion/protocol_v2.py",
                         WORKSPACE / "companion/tests/test_protocol_v2.py"]},
        guarantees_exercised=["real Opus encode", "exact C/Python CRC and SHA256 chain",
            "idempotent partial-write retries at exact offsets", "terminal metadata binding",
            "durable SQLite batch import and restart/replay", "independent decoded duration", "source-timeline bookmarks"],
        not_verified=["physical MCU execution", "PDM input", "NAND journal/reboot recovery",
            "BLE/mobile lifecycle", "runtime stack/timing/current", "ownership/authentication", "signed boot/OTA"])
    (ROOT / "verification/archive-roundtrip.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(run.stdout, end="")
    for item in metrics:
        print(f"PASS {item['file']}: {item['status']}, {item['decoded_samples']} decoded source samples, "
              f"SNR {item['waveform_snr_db']} dB, {len(item['bookmarks'])} bookmarks")


if __name__ == "__main__":
    main()
