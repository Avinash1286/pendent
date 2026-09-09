"""Portable source owner -> real Opus/NAND -> recovery -> Python/FFmpeg.

The upstream physical PDM driver's continuity and quiescence are not simulated
by assigning application block sequence numbers. Those require separate tests.
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
    run = subprocess.run([str(tools / "host/aura_recorder_test.exe"), str(raw),
                          str(ROOT / "fixtures/recorder")], text=True, capture_output=True)
    (ROOT / "verification/recorder-host.txt").write_text(run.stdout + run.stderr, encoding="utf-8", newline="\n")
    if run.returncode:
        raise RuntimeError(run.stdout + run.stderr)
    cases = []
    names = ("clean_stop", "queue_overflow", "block_gap", "source_fault_and_seal_power_cut", "missing_final_block")
    for mode, description in enumerate(names):
        path = ROOT / f"fixtures/recorder-{mode}.aura"
        archive = read_archive(path, allow_interrupted=True)
        physical = Receipt.parse(path.with_suffix(".receipt").read_bytes())
        assert archive.capture.started_at_ms == 0 and archive.capture.time_source == 0
        if mode == 0:
            assert archive.status == "finalized" and archive.original_source_samples == len(source)
        else:
            assert archive.status == "interrupted" and archive.original_source_samples is None
        if mode == 3:
            assert not physical.sealed and physical.chain_sha256 == archive.termination.chain_sha256
        else:
            assert physical == archive.receipt
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "capture.db"
            with DurableReceiver(db) as receiver:
                assert receiver.import_archive(archive) == archive.receipt
            with DurableReceiver(db) as receiver:
                assert receiver.import_archive(archive) == archive.receipt
                packets = [p.payload for p in receiver.packets(archive.capture) if p.kind == AUDIO]
        meta = dict(source_samples=archive.source_samples, pre_skip=archive.termination.pre_skip, frame_ms=20)
        ogg, wav = tools / f"recorder-{mode}.opus", tools / f"recorder-{mode}.wav"
        ogg.write_bytes(make_ogg(meta, packets))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(ogg),
                        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], check=True)
        decoded = pcm(wav)
        assert len(decoded) == archive.source_samples
        snr = signal_snr(source[:len(decoded)], decoded)
        assert snr >= 8
        if mode in (1, 2, 4):
            assert len(decoded) == 47960
        cases.append(dict(case=description, file=path.relative_to(ROOT).as_posix(),
            sha256=archive.sha256_hex, status=archive.status, audio_packets=len(packets),
            decoded_samples=len(decoded), original_source_samples=archive.original_source_samples,
            waveform_snr_db=snr, capture_time="unknown", physical_receipt="terminal" if physical.sealed else "open_prefix",
            physical_digest=physical.chain_sha256.hex(), export_digest=archive.receipt.chain_sha256.hex()))
    assert cases[3]["decoded_samples"] < cases[1]["decoded_samples"]
    files = [ROOT / p for p in ("include/aura_recorder.h", "src/aura_recorder.c", "tests/host_recorder.c",
        "include/aura_opus.h", "src/aura_opus.c", "include/aura_archive.h", "src/aura_archive.c",
        "include/aura_journal.h", "src/aura_journal.c", "tests/nand_model.h", "tests/nand_model.c")]
    files += [Path(__file__), WORKSPACE / "companion/src/aura_companion/protocol_v2.py"]
    report = dict(status="portable_recorder_real_Opus_NAND_model_Python_FFmpeg_passed_physical_ingress_unmeasured",
        python=sys.version, cases=cases,
        code_source_sha256={p.relative_to(WORKSPACE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        guarantees_exercised=["prepare/service before microphone start permission", "startup failure and immediate cancellation without PCM",
            "zero-sample clean stop", "stale epoch isolation", "block sequence/source offset and final watermark checks",
            "exact 2-of-320 consumed on program failure, no double feed", "overflow/gap explicit interrupted seal",
            "separate source failure and close I/O error", "unknown capture time through startup", "real encode/reopen/import/decode"],
        not_verified=["physical PDM continuity or exact sample clock", "upstream driver error/STOP quiescence",
            "actual queue concurrency and overflow signaling", "microphone warmup/privacy electrical behavior",
            "physical NAND power failure", "real-time CPU/storage deadlines", "BLE/OTA/reclamation"])
    (ROOT / "verification/recorder-roundtrip.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(run.stdout, end="")
    for case in cases:
        print(f"PASS {case['case']}: {case['decoded_samples']} decoded samples, SNR {case['waveform_snr_db']} dB")


if __name__ == "__main__":
    main()
