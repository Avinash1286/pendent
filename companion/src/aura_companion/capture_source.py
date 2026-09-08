"""Source metadata for an imported capture, checked against its local WAV.

Hashes detect accidental substitution, not authentication of a physical pendant.
The original archive and this sidecar remain local; only explicit upload sends
the bounded capture/transcript metadata to the owner's configured portal.
"""
import hashlib
import json
from pathlib import Path
import re
import wave


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_capture(capture: dict) -> dict:
    if not isinstance(capture, dict) or type(capture.get("version")) is not int or capture.get("version") != 2:
        raise ValueError("Unsupported capture provenance metadata")
    for key, length in (("deviceId", 32), ("captureId", 32), ("archiveDigest", 64)):
        value = capture.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{%d}" % length, value):
            raise ValueError("Invalid capture identity or archive digest")
        if length == 32 and value == "0" * length:
            raise ValueError("A capture identity cannot be zero")
    if capture.get("sampleRate") != 16000 or type(capture.get("sampleRate")) is not int:
        raise ValueError("Unsupported capture sample rate")
    samples = capture.get("sourceSamples")
    if type(samples) is not int or not 0 <= samples <= 320_000_000:
        raise ValueError("Invalid retained capture duration")
    epoch = capture.get("startedAtMs")
    if type(epoch) is not int or not 0 <= epoch <= 4_102_444_800_000:
        raise ValueError("Invalid capture time")
    if capture.get("timeConfidence") != ("host_synced" if epoch else "unknown"):
        raise ValueError("Capture time confidence does not match its timestamp")
    if type(capture.get("interrupted")) is not bool:
        raise ValueError("Invalid capture completion state")
    bookmarks = capture.get("bookmarks")
    if not isinstance(bookmarks, list) or len(bookmarks) > 1000:
        raise ValueError("Capture exceeds the supported bookmark limit")
    previous = -1
    for offset in bookmarks:
        if type(offset) is not int or not 0 <= offset <= 320_000_000 or offset < previous:
            raise ValueError("Invalid capture bookmark timeline")
        if not capture["interrupted"] and offset > samples:
            raise ValueError("Bookmark exceeds the finalized capture")
        previous = offset
    return capture


def load_capture_source(wav_path: Path) -> dict | None:
    sidecar = wav_path.with_suffix(".capture.json")
    if not sidecar.exists():
        return None
    if sidecar.stat().st_size > 100_000:
        raise ValueError("Capture provenance exceeds the size limit")
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or metadata.get("kind") != "aura-capture-export":
        raise ValueError("Invalid capture provenance sidecar")
    if metadata.get("wav") != wav_path.name or metadata.get("wavSha256") != file_sha256(wav_path):
        raise ValueError("Capture provenance does not match the local WAV; preserve source files")
    capture = validate_capture(metadata.get("capture"))
    with wave.open(str(wav_path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getnframes()) != (
                1, 2, capture["sampleRate"], capture["sourceSamples"]):
            raise ValueError("Capture provenance does not match decoded audio dimensions")
    # A hash of the WAV alone cannot bind the identity in an editable sidecar.
    # Rehydrate that identity and all source timing from the preserved archive.
    archive_name = metadata.get("archive")
    if not isinstance(archive_name, str) or Path(archive_name).name != archive_name:
        raise ValueError("Capture provenance requires a sibling source archive")
    archive_path = wav_path.parent / archive_name
    if not archive_path.is_file() or archive_path.resolve().parent != wav_path.resolve().parent:
        raise ValueError("Preserved source archive is missing from the capture bundle")
    if archive_path.stat().st_size > 320 * 1024 * 1024:
        raise ValueError("Preserved source archive exceeds the import limit")
    from . import protocol_v2 as protocol
    archive = protocol.read_archive(archive_path, allow_interrupted=capture["interrupted"])
    expected = capture_metadata(archive)
    if capture != expected or metadata.get("archiveSha256") != archive.sha256_hex:
        raise ValueError("Capture metadata conflicts with the preserved source archive")
    if metadata.get("receipt") != archive.receipt.encode().hex():
        raise ValueError("Capture receipt conflicts with the preserved source archive")
    for key, expected_value in (("binaryWireVersion", protocol.WIRE_VERSION),
                                ("originalSourceSamples", archive.original_source_samples),
                                ("discardedTailBytes", archive.discarded_tail_bytes)):
        value = metadata.get(key)
        if key not in metadata or type(value) is not type(expected_value) or value != expected_value:
            raise ValueError("Capture recovery metadata conflicts with the preserved source archive")
    return dict(capture)


def capture_metadata(archive) -> dict:
    from .protocol_v2 import BOOKMARK
    bookmarks = []
    for packet in archive.iter_packets():
        if packet.kind == BOOKMARK:
            bookmarks.append(packet.sample_offset)
            if len(bookmarks) > 1000:
                raise ValueError("Capture exceeds the supported bookmark limit")
    capture = archive.capture
    return validate_capture({
        "version": 2, "deviceId": capture.device_id.hex(), "captureId": capture.capture_id.hex(),
        "archiveDigest": archive.receipt.chain_sha256.hex(), "sampleRate": capture.sample_rate,
        "sourceSamples": archive.source_samples, "startedAtMs": capture.started_at_ms,
        "timeConfidence": "host_synced" if capture.time_source else "unknown",
        "interrupted": archive.status == "interrupted", "bookmarks": sorted(bookmarks),
    })


def attach_capture_source(note: dict, wav_path: Path) -> dict:
    capture = load_capture_source(wav_path)
    if capture is None:
        return note
    capture.update({
        "transcriptRevision": hashlib.sha256(note["transcript"].encode("utf-8")).hexdigest(),
        "segments": note["segments"],
        "transcription": note["transcription"],
    })
    return {**note, "capture": capture, "recordedAt": capture["startedAtMs"]}
