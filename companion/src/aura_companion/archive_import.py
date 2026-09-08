"""Verified A04 file import into ordinary local audio and source-backed notes.

The experimental binary revision is deliberately separate from A03 Bluetooth.
This path consumes a local archive; it does not impersonate a radio connection,
acknowledge a physical pendant, delete its data, or schedule an upload.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import struct
import tempfile
import wave

from .capture_source import capture_metadata, file_sha256, load_capture_source
from .files import atomic_write_text
from .protocol import ProtocolError
from . import protocol_v2 as protocol

MAX_ARCHIVE_BYTES = 320 * 1024 * 1024


@dataclass(frozen=True)
class ImportedCapture:
    wav: Path
    archive: Path
    metadata: Path
    status: str
    reused: bool


@contextmanager
def _output_lock(directory: Path):
    """OS-held, nonblocking cooperative lock, released if the process exits."""
    with (directory / ".aura-import.lock").open("a+b") as lock:
        lock.seek(0, 2)
        if not lock.tell():
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("Another capture import owns this output directory") from None
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _copy_source(source: Path, destination: Path):
    count = 0
    with source.open("rb") as inp, destination.open("xb") as out:
        for block in iter(lambda: inp.read(65536), b""):
            count += len(block)
            if count > MAX_ARCHIVE_BYTES:
                raise ValueError("Capture archive exceeds the 320 MiB import limit")
            out.write(block)
        out.flush()
        os.fsync(out.fileno())


def _sync_directory(directory: Path):
    if os.name != "nt":
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _publish_or_verify(source: Path, destination: Path):
    if destination.is_symlink():
        raise ValueError("Capture publication target is a symbolic link")
    if destination.exists():
        if not destination.is_file() or file_sha256(destination) != file_sha256(source):
            raise ValueError("Existing capture artifact conflicts; preserved both sources in their original locations")
        return
    with source.open("r+b") as stream:
        os.fsync(stream.fileno())
    os.replace(source, destination)
    _sync_directory(destination.parent)


def _crc_table():
    table = []
    for value in range(256):
        crc = value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04C11DB7 if crc & 0x80000000 else 0)) & 0xFFFFFFFF
        table.append(crc)
    return table


_OGG_CRC_TABLE = _crc_table()


def _ogg_page(payload: bytes, serial: int, sequence: int, granule: int, flags: int) -> bytes:
    lace = [255] * (len(payload) // 255) + [len(payload) % 255]
    raw = struct.pack("<4sBBQIIIB", b"OggS", 0, flags, granule, serial, sequence, 0, len(lace))
    raw += bytes(lace) + payload
    crc = 0
    for byte in raw:
        crc = ((crc << 8) ^ _OGG_CRC_TABLE[((crc >> 24) ^ byte) & 0xFF]) & 0xFFFFFFFF
    return raw[:22] + struct.pack("<I", crc) + raw[26:]


def _write_ogg(archive, path: Path) -> list[int]:
    """One complete Opus packet per Ogg page; RFC 7845 granules use 48 kHz."""
    capture = archive.capture
    serial = int.from_bytes(capture.capture_id[:4], "little")
    head = struct.pack("<8sBBHIhB", b"OpusHead", 1, 1, capture.pre_skip * 3, 16000, 0, 0)
    vendor = b"AURA verified local capture export"
    tags = b"OpusTags" + struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", 0)
    bookmarks = []
    pending = None
    page_sequence = 2
    encoded_samples = 0
    with path.open("xb") as out:
        out.write(_ogg_page(head, serial, 0, 0, 2))
        out.write(_ogg_page(tags, serial, 1, 0, 0))
        for packet in archive.iter_packets():
            if packet.kind == protocol.BOOKMARK:
                bookmarks.append(packet.sample_offset)
                if len(bookmarks) > 1000:
                    raise ValueError("Capture exceeds the supported bookmark limit")
                continue
            if pending is not None:
                out.write(_ogg_page(pending.payload, serial, page_sequence, encoded_samples * 3, 0))
                page_sequence += 1
            encoded_samples += packet.sample_count
            pending = packet
        if pending is not None:
            final_granule = (archive.source_samples + capture.pre_skip) * 3
            out.write(_ogg_page(pending.payload, serial, page_sequence, final_granule, 4))
        elif archive.source_samples:
            raise ProtocolError("Capture has a duration without any audio packets")
        out.flush()
        os.fsync(out.fileno())
    return bookmarks


def _decode_ogg(source: Path, target: Path, expected_samples: int):
    import av
    actual_samples = 0
    with wave.open(str(target), "wb") as out:
        out.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        if expected_samples == 0:
            return
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)

        def write(frames):
            nonlocal actual_samples
            for frame in frames:
                actual_samples += frame.samples
                if actual_samples > expected_samples:
                    raise ProtocolError("Decoded audio exceeds the sealed source duration")
                # Plane allocation can include padding. Write only actual samples.
                out.writeframesraw(bytes(frame.planes[0])[:frame.samples * 2])

        try:
            with av.open(str(source), mode="r", format="ogg") as container:
                for frame in container.decode(audio=0):
                    write(resampler.resample(frame))
                write(resampler.resample(None))
        except ProtocolError:
            raise
        except Exception:
            raise ProtocolError("The preserved Opus payload could not be decoded") from None
        if actual_samples != expected_samples:
            raise ProtocolError("Decoded audio does not match the sealed source duration")


def _write_pcm(archive, target: Path) -> list[int]:
    bookmarks = []
    count = 0
    start = archive.capture.pre_skip
    end = start + archive.source_samples
    with wave.open(str(target), "wb") as out:
        out.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        for packet in archive.iter_packets():
            if packet.kind == protocol.BOOKMARK:
                bookmarks.append(packet.sample_offset)
                if len(bookmarks) > 1000:
                    raise ValueError("Capture exceeds the supported bookmark limit")
                continue
            lo = max(0, start - packet.sample_offset)
            hi = min(packet.sample_count, end - packet.sample_offset)
            if hi > lo:
                out.writeframesraw(packet.payload[lo * 2:hi * 2])
                count += hi - lo
        if count != archive.source_samples:
            raise ProtocolError("Preserved PCM does not match its terminal duration")
    return bookmarks


def import_capture(path: Path, output: Path, *, allow_interrupted=False) -> ImportedCapture:
    output.mkdir(parents=True, exist_ok=True)
    with _output_lock(output), tempfile.TemporaryDirectory(prefix=".aura-import-", dir=output) as temporary:
        work = Path(temporary)
        raw = work / "source.aur"
        _copy_source(path, raw)
        archive = protocol.read_archive(raw, allow_interrupted=allow_interrupted)
        capture = archive.capture
        digest = archive.receipt.chain_sha256.hex()
        stem = f"aura-{capture.device_id.hex()}-{capture.capture_id.hex()}-{digest}"
        destination_wav = output / f"{stem}.wav"
        destination_raw = output / f"{stem}.aur"
        destination_metadata = output / f"{stem}.capture.json"
        source = capture_metadata(archive)
        receipts = output / ".receipts"
        receipts.mkdir(exist_ok=True)
        if destination_metadata.exists():
            # A different decoder version may produce slightly different PCM.
            # Verify an already published bundle instead of decoding it again.
            saved_source = load_capture_source(destination_wav)
            saved = json.loads(destination_metadata.read_text(encoding="utf-8"))
            if (saved_source != source or saved.get("archiveSha256") != archive.sha256_hex
                    or saved.get("archive") != destination_raw.name):
                raise ValueError("Existing capture bundle conflicts with the supplied source archive")
            with protocol.DurableReceiver(receipts / f"{digest}.sqlite") as receiver:
                receipt = receiver.import_archive(archive)
                if receipt.encode() != archive.receipt.encode():
                    raise ProtocolError("Local archive receipt does not match the verified source")
            return ImportedCapture(destination_wav, destination_raw, destination_metadata, archive.status, True)
        wav = work / "decoded.wav"
        opus = work / "audio.opus"
        if capture.codec == protocol.OPUS:
            bookmarks = _write_ogg(archive, opus)
            _decode_ogg(opus, wav, archive.source_samples)
        else:
            bookmarks = _write_pcm(archive, wav)
        if sorted(bookmarks) != source["bookmarks"]:
            raise ProtocolError("Source bookmark metadata changed during export")
        # A recovered prefix and a later completed source have different terminal
        # digests. Preserve both revisions until an explicit review promotes one.
        with protocol.DurableReceiver(receipts / f"{digest}.sqlite") as receiver:
            receipt = receiver.import_archive(archive)
            if receipt.encode() != archive.receipt.encode():
                raise ProtocolError("Local archive receipt does not match the verified source")
        decoder = {"engine": "PCM16LE", "version": "1"}
        if capture.codec == protocol.OPUS:
            import av
            decoder = {"engine": "PyAV", "version": av.__version__,
                       "libraries": {key: list(value) for key, value in av.library_versions.items()}}
        metadata = {
            "kind": "aura-capture-export", "binaryWireVersion": 3, "capture": source,
            "wav": destination_wav.name, "wavSha256": file_sha256(wav),
            "archive": destination_raw.name, "archiveSha256": archive.sha256_hex,
            "originalSourceSamples": archive.original_source_samples,
            "discardedTailBytes": archive.discarded_tail_bytes,
            "receipt": receipt.encode().hex(), "decoder": decoder,
        }
        staged_metadata = work / "source.capture.json"
        atomic_write_text(staged_metadata, json.dumps(metadata, indent=2, ensure_ascii=False))
        _publish_or_verify(raw, destination_raw)
        if capture.codec == protocol.OPUS and archive.source_samples:
            _publish_or_verify(opus, output / f"{stem}.opus")
        _publish_or_verify(wav, destination_wav)
        # Publish evidence last. A restart verifies earlier artifacts and repairs
        # a missing sidecar; conflicting files are never silently overwritten.
        _publish_or_verify(staged_metadata, destination_metadata)
        return ImportedCapture(destination_wav, destination_raw, destination_metadata, archive.status, False)
