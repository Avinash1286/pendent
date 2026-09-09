"""Run storage fault tests and real C/Opus -> durable Python -> C release.

Known public test identities/keys only. This is a host NAND model, not physical
storage, authenticated BLE transport, key enrollment, or device qualification.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from verify_fixtures import make_ogg, pcm, signal_snr

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(WORKSPACE / "companion/src"))
from aura_companion.protocol_v2 import AUDIO, DurableReceiver, Receipt, read_archive
from aura_companion.release import RELEASE_PERMISSION, ReleaseOutbox, TrustedReleaseContext


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    files = [ROOT / name for name in (
        "include/aura_storage.h", "src/aura_storage.c", "include/aura_control.h", "src/aura_control.c",
        "include/aura_release_auth.h", "src/aura_release_auth.c", "include/aura_recorder.h", "src/aura_recorder.c",
        "include/aura_journal.h", "src/aura_journal.c", "include/aura_archive.h", "src/aura_archive.c",
        "include/aura_opus.h", "src/aura_opus.c", "include/aura_nand.h", "tests/nand_model.h",
        "tests/nand_model.c", "tests/host_storage.c", "tests/host_storage_roundtrip.c", "tests/CMakeLists.txt",
        "scripts/verify_storage.py", "scripts/verify_fixtures.py", "cmake/opus-profile.cmake",
        "dependencies/opus-1.6.1.json", "fixtures/source-speech-16k.wav")]
    files += [WORKSPACE / f"companion/src/aura_companion/{name}.py"
              for name in ("protocol_v2", "release", "protocol", "files")]
    return {p.relative_to(WORKSPACE).as_posix(): sha(p) for p in files}


def main():
    tools = WORKSPACE / ".tools/a04-opus"
    sources_before = source_hashes()
    cmake = shutil.which("cmake") or str(WORKSPACE / ".tools/zephyr/venv/Lib/site-packages/cmake/data/bin/cmake.exe")
    build_command = [cmake, "--build", str(tools / "host"), "--target",
                     "aura_storage_test", "aura_storage_roundtrip", "-j", "6"]
    build = subprocess.run(build_command, text=True, capture_output=True, timeout=180)
    if build.returncode:
        raise RuntimeError("Configure the pinned host build with build.ps1 first.\n" + build.stdout + build.stderr)
    executables = {name: tools / f"host/aura_storage_{name}.exe" for name in ("test", "roundtrip")}
    binary_before = {name: sha(path) for name, path in executables.items()}
    fault_run = subprocess.run([str(executables["test"])], text=True, capture_output=True, timeout=120)
    fault_text = fault_run.stdout + fault_run.stderr
    (ROOT / "verification/storage-host.txt").write_text(fault_text, encoding="utf-8", newline="\n")
    if fault_run.returncode:
        raise RuntimeError(fault_text)
    groups = len(re.findall(r"^PASS storage \d+ ", fault_text, re.M))
    if groups != 12 or "cases=" not in fault_text:
        raise ValueError("Storage fault suite did not report expected coverage")

    source = pcm(ROOT / "fixtures/source-speech-16k.wav")
    raw = tools / "source-speech-16k.pcm"
    raw.write_bytes(source.tobytes())
    with tempfile.TemporaryDirectory(prefix="storage-", dir=tools) as temporary:
        tmp = Path(temporary)
        prefix = tmp / "storage"
        command = [str(executables["roundtrip"]), str(raw), str(prefix)]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        try:
            # Bounded handshake on Windows pipes; do not leave a child waiting if
            # import or authorization fails in Python.
            with ThreadPoolExecutor(max_workers=1) as pool:
                first = pool.submit(process.stdout.readline)
                try:
                    ready = first.result(timeout=45)
                except BaseException:
                    process.kill()
                    raise
            if ready != "READY durable receiver authorization required\n":
                if process.poll() is None:
                    process.kill()
                remaining, errors = process.communicate(timeout=10)
                raise ValueError("C fixture did not reach durable-receiver handoff: " + ready + remaining + errors)
            capture = read_archive(prefix.with_name("storage-release.aura"))
            receipt = prefix.with_name("storage-release.receipt").read_bytes()
            assert Receipt.parse(receipt) == capture.receipt
            receiver_db = tmp / "receiver.db"
            with DurableReceiver(receiver_db) as receiver:
                assert receiver.import_archive(capture).encode() == receipt
            with DurableReceiver(receiver_db) as receiver:
                assert receiver.import_archive(capture).encode() == receipt
            context = TrustedReleaseContext(bytes([0x11])*16, bytes([0x33])*16,
                                            bytes([0x44])*16, 1, bytes(range(1,33)))
            outbox_path = tmp / "release.db"
            outbox = ReleaseOutbox.provision(outbox_path, context, initial_sequence_floor=0)
            envelope = outbox.request_release("real-opus-1", receiver_db, capture.capture.capture_id,
                                             permission=RELEASE_PERMISSION)
            reopened = ReleaseOutbox(outbox_path, context)
            assert reopened.retry("real-opus-1") == envelope
            assert reopened.pending().envelope == envelope
            rest, errors = process.communicate(envelope.hex() + "\n", timeout=60)
            transcript = ready + rest + errors
            if process.returncode or "PASS real storage roundtrip" not in rest:
                raise RuntimeError(transcript)
            # Only the actual successful C result above is the completion oracle
            # here. No radio notification or unauthenticated remote reply is used.
            reopened.mark_completed("real-opus-1", envelope=envelope, receipt=receipt)
            assert ReleaseOutbox(outbox_path, context).pending() is None
            assert ReleaseOutbox(outbox_path, context).retry("real-opus-1") == envelope
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream and not stream.closed:
                    stream.close()

        retained = (tmp / "storage-retained.aura").read_bytes()
        assert retained == (tmp / "storage-retained-after.aura").read_bytes()
        assert retained == (tmp / "storage-retained-after-reuse.aura").read_bytes()
        assert (tmp / "storage-retained.receipt").read_bytes() == (tmp / "storage-retained-after.receipt").read_bytes()
        assert (tmp / "storage-retained.receipt").read_bytes() == (tmp / "storage-retained-after-reuse.receipt").read_bytes()
        cases = []
        for generation, label in enumerate(("retained", "release", "replacement"), 1):
            path = tmp / f"storage-{label}.aura"
            archive = read_archive(path)
            assert archive.status == "finalized" and archive.source_samples == len(source)
            expected_id = hashlib.sha256(b"AURA-A04-CAPTURE-v1\0" + context.device_id +
                                        context.storage_incarnation + generation.to_bytes(8,"little")).digest()[:16]
            assert archive.capture.capture_id == expected_id
            assert Receipt.parse(path.with_suffix(".receipt").read_bytes()) == archive.receipt
            with DurableReceiver(tmp / f"{label}.db") as receiver:
                assert receiver.import_archive(archive) == archive.receipt
                packets = [p.payload for p in receiver.packets(archive.capture) if p.kind == AUDIO]
            ogg, wav = tmp / f"{label}.opus", tmp / f"{label}.wav"
            ogg.write_bytes(make_ogg(dict(source_samples=archive.source_samples,
                                        pre_skip=archive.termination.pre_skip, frame_ms=20), packets))
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(ogg),
                            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], check=True)
            decoded = pcm(wav)
            assert len(decoded) == len(source)
            snr = signal_snr(source, decoded)
            assert snr >= 8
            # Keep inspectable recordings/receipts; local SQLite databases and
            # process-model state are ephemeral, with no real user data.
            saved = ROOT / "fixtures" / path.name
            saved.write_bytes(path.read_bytes())
            saved.with_suffix(".receipt").write_bytes(path.with_suffix(".receipt").read_bytes())
            cases.append(dict(capture=label, generation=generation, capture_id=expected_id.hex(),
                              sha256=sha(saved), decoded_samples=len(decoded), waveform_snr_db=snr,
                              receipt_sha256=sha(saved.with_suffix(".receipt"))))
    assert source_hashes() == sources_before, "Sources changed during verification"
    assert {name:sha(path) for name,path in executables.items()} == binary_before
    report = dict(status="host_storage_owner_durable_python_outbox_real_Opus_roundtrip_passed",
        fault_test_groups=groups, fault_test_summary=fault_text.strip().splitlines()[-1],
        real_roundtrip=transcript.strip().splitlines(), recordings=cases,
        retained_recording_byte_identical=True, release_sequence=1,
        authorization_sha256=hashlib.sha256(envelope).hexdigest(),
        executable_sha256=binary_before, code_source_sha256=sources_before,
        build_command=build_command, build_output=(build.stdout + build.stderr).splitlines(),
        verified=["real C recorder/Opus/owned NAND journal", "Python SQLite commit and reopen before RLS1",
                  "persisted exact outbox retry", "C authenticated grant before any audio erase",
                  "cold mount before and after release", "retained source byte identity",
                  "fresh generation after reclaimed-space reuse", "independent FFmpeg decode"],
        not_verified=["physical NAND or power cuts", "production privileged audio-erase adapter",
                      "secure enrollment/key storage", "authenticated BLE completion", "mobile background recovery",
                      "physical anti-rollback", "real-time latency and power", "wearable firmware"])
    (ROOT / "verification/storage-roundtrip.json").write_text(json.dumps(report, indent=2)+"\n",
                                                            encoding="utf-8", newline="\n")
    print(fault_text, end="")
    print(transcript, end="")
    for case in cases:
        print(f"PASS {case['capture']}: {case['decoded_samples']} samples, SNR {case['waveform_snr_db']} dB")


if __name__ == "__main__":
    main()
