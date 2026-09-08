"""A04 protocol-v2 reference receiver; not connected to A03 Bluetooth firmware.

The codec is opaque here: this validates framing and durably preserves encoded
bytes, not the acoustic validity of Opus. See docs/a04/software-contract.md.
No ACK is returned until SQLite has committed both the bytes and their receipt.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3
import struct
import zlib

from .protocol import ProtocolError

MANIFEST = struct.Struct("<4sBBBB16s16sIHQBB")
FRAME = struct.Struct("<4sBBIQHH")
CRC = struct.Struct("<I")
ACK = struct.Struct("<4sBB16s16sIQQ32s")
PCM16 = 1
OPUS = 2
AUDIO = 1
BOOKMARK = 2
MAX_PAYLOAD = 1275
MAX_FRAME_COUNT = 1_000_000


def _integer(value: int, maximum: int, name: str) -> None:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ProtocolError(f"Invalid {name}")


@dataclass(frozen=True)
class Capture:
    device_id: bytes
    capture_id: bytes
    codec: int
    frame_samples: int = 320
    sample_rate: int = 16000
    started_at_ms: int = 0
    time_source: int = 0

    @property
    def key(self) -> str:
        return self.device_id.hex() + ":" + self.capture_id.hex()

    def encode(self) -> bytes:
        if any(type(value) is not bytes or len(value) != 16 or value == bytes(16)
               for value in (self.device_id, self.capture_id)):
            raise ProtocolError("Device and capture identities must be nonzero 128-bit values")
        if type(self.codec) is not int or self.codec not in (PCM16, OPUS):
            raise ProtocolError("Unsupported codec")
        if self.sample_rate != 16000 or type(self.sample_rate) is not int:
            raise ProtocolError("Unsupported sample rate")
        if self.frame_samples not in (160, 320) or type(self.frame_samples) is not int:
            raise ProtocolError("Unsupported frame duration")
        _integer(self.started_at_ms, 4_102_444_800_000, "capture time")
        if type(self.time_source) is not int or self.time_source not in (0, 1):
            raise ProtocolError("Unsupported capture-time source")
        if (self.started_at_ms == 0) != (self.time_source == 0):
            raise ProtocolError("Unknown time must be zero; synchronized time must be nonzero")
        return MANIFEST.pack(b"AUR2", 2, self.codec, 1, 0, self.device_id,
                             self.capture_id, self.sample_rate, self.frame_samples,
                             self.started_at_ms, self.time_source, 0)

    @classmethod
    def parse(cls, data: bytes) -> "Capture":
        if len(data) != MANIFEST.size:
            raise ProtocolError("Invalid v2 manifest length")
        magic, version, codec, channels, reserved, device, capture, rate, samples, epoch, clock, tail = MANIFEST.unpack(data)
        if (magic, version, channels, reserved, tail) != (b"AUR2", 2, 1, 0, 0):
            raise ProtocolError("Unsupported v2 manifest header")
        result = cls(device, capture, codec, samples, rate, epoch, clock)
        result.encode()
        return result


@dataclass(frozen=True)
class Packet:
    sequence: int
    sample_offset: int
    sample_count: int
    payload: bytes
    kind: int = AUDIO

    def encode(self) -> bytes:
        _integer(self.sequence, MAX_FRAME_COUNT - 1, "packet sequence")
        _integer(self.sample_offset, (1 << 63) - 1, "sample offset")
        _integer(self.sample_count, 320, "sample count")
        if type(self.payload) is not bytes or len(self.payload) > MAX_PAYLOAD:
            raise ProtocolError("Invalid encoded payload")
        if type(self.kind) is not int or self.kind not in (AUDIO, BOOKMARK):
            raise ProtocolError("Unsupported packet kind")
        if self.kind == AUDIO and (not self.sample_count or not self.payload):
            raise ProtocolError("Audio packets must contain samples and encoded bytes")
        if self.kind == BOOKMARK and (self.sample_count or self.payload):
            raise ProtocolError("Bookmarks contain an offset, not audio bytes")
        data = FRAME.pack(b"AFR2", 2, self.kind, self.sequence, self.sample_offset,
                          self.sample_count, len(self.payload)) + self.payload
        return data + CRC.pack(zlib.crc32(data))

    @classmethod
    def parse(cls, data: bytes) -> "Packet":
        if not FRAME.size + CRC.size <= len(data) <= FRAME.size + MAX_PAYLOAD + CRC.size:
            raise ProtocolError("Invalid packet length")
        magic, version, kind, sequence, offset, samples, count = FRAME.unpack_from(data)
        if (magic, version) != (b"AFR2", 2) or len(data) != FRAME.size + count + CRC.size:
            raise ProtocolError("Invalid packet header or declared length")
        expected, = CRC.unpack_from(data, len(data) - CRC.size)
        if zlib.crc32(data[:-CRC.size]) != expected:
            raise ProtocolError("Packet checksum mismatch")
        result = cls(sequence, offset, samples, data[FRAME.size:-CRC.size], kind)
        result.encode()
        return result


@dataclass(frozen=True)
class Receipt:
    """Committed contiguous prefix, including bookmarks; no deletion authority."""
    device_id: bytes
    capture_id: bytes
    next_sequence: int
    encoded_bytes: int
    sample_count: int
    chain_sha256: bytes
    sealed: bool

    def encode(self) -> bytes:
        if any(type(value) is not bytes or len(value) != 16 or value == bytes(16)
               for value in (self.device_id, self.capture_id)):
            raise ProtocolError("Invalid receipt identity")
        _integer(self.next_sequence, MAX_FRAME_COUNT, "receipt sequence")
        _integer(self.encoded_bytes, 1 << 40, "receipt encoded length")
        _integer(self.sample_count, (1 << 63) - 1, "receipt sample count")
        if type(self.chain_sha256) is not bytes or len(self.chain_sha256) != 32 or type(self.sealed) is not bool:
            raise ProtocolError("Invalid receipt digest or finalization flag")
        return ACK.pack(b"ACK2", 2, int(self.sealed), self.device_id, self.capture_id,
                        self.next_sequence, self.encoded_bytes, self.sample_count, self.chain_sha256)

    @classmethod
    def parse(cls, data: bytes) -> "Receipt":
        if len(data) != ACK.size:
            raise ProtocolError("Invalid receipt length")
        magic, version, flags, *fields = ACK.unpack(data)
        if (magic, version) != (b"ACK2", 2) or flags not in (0, 1):
            raise ProtocolError("Unsupported receipt header")
        result = cls(*fields, bool(flags))
        result.encode()
        return result


class DurableReceiver:
    """Single local database owner. Call from one serialized transfer coordinator.

    SQLite DELETE journal + synchronous EXTRA syncs the directory after journal
    removal where supported. Durability still depends on the OS/filesystem/device
    honoring flushes. Do not place this database on a network/cloud-sync folder.
    Keep the database and journals together; no automatic deletion is implemented.
    """

    def __init__(self, path: Path, *, max_capture_bytes: int = 256 * 1024 * 1024):
        _integer(max_capture_bytes, 1 << 40, "capture byte limit")
        if max_capture_bytes == 0 or str(path) == ":memory:":
            raise ProtocolError("A positive limit and persistent database path are required")
        self.max_capture_bytes = max_capture_bytes
        self.db = sqlite3.connect(str(path), timeout=5)
        self.db.execute("PRAGMA foreign_keys=ON")
        mode, = self.db.execute("PRAGMA journal_mode=DELETE").fetchone()
        if mode != "delete":
            self.db.close()
            raise ProtocolError("Persistent rollback journaling is required")
        self.db.execute("PRAGMA synchronous=EXTRA")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS captures (
                identity TEXT PRIMARY KEY,
                manifest BLOB NOT NULL,
                next_sequence INTEGER NOT NULL,
                encoded_bytes INTEGER NOT NULL,
                sample_count INTEGER NOT NULL,
                chain_sha256 BLOB NOT NULL,
                sealed INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS packets (
                identity TEXT NOT NULL REFERENCES captures(identity),
                sequence INTEGER NOT NULL,
                wire BLOB NOT NULL,
                PRIMARY KEY (identity, sequence)
            );
        """)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "DurableReceiver":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def _state(self, capture: Capture):
        manifest = capture.encode()
        row = self.db.execute(
            "SELECT manifest,next_sequence,encoded_bytes,sample_count,chain_sha256,sealed "
            "FROM captures WHERE identity=?", (capture.key,)).fetchone()
        if row is None:
            raise ProtocolError("Capture manifest has not been opened")
        if row[0] != manifest:
            raise ProtocolError("Capture identity is already bound to different metadata")
        return row

    @staticmethod
    def _receipt(capture: Capture, row) -> Receipt:
        return Receipt(capture.device_id, capture.capture_id, *row[1:5], bool(row[5]))

    def _verified_receipt(self, capture: Capture) -> Receipt:
        """Re-read the saved prefix before reconnect acknowledgement/final seal."""
        row = self._state(capture)
        sequence = encoded_bytes = samples = 0
        digest = hashlib.sha256(capture.encode()).digest()
        for saved_sequence, wire in self.db.execute(
            "SELECT sequence,wire FROM packets WHERE identity=? ORDER BY sequence", (capture.key,)):
            packet = Packet.parse(wire)
            if packet.sequence != sequence or saved_sequence != sequence:
                raise ProtocolError("Preserved source contains a sequence gap")
            if packet.kind == AUDIO:
                if packet.sample_offset != samples or packet.sample_count != capture.frame_samples:
                    raise ProtocolError("Preserved audio timeline is inconsistent")
                if capture.codec == PCM16 and len(packet.payload) != packet.sample_count * 2:
                    raise ProtocolError("Preserved PCM byte count is inconsistent")
            elif packet.sample_offset > samples:
                raise ProtocolError("Preserved bookmark exceeds the captured timeline")
            sequence += 1
            encoded_bytes += len(packet.payload)
            samples += packet.sample_count
            digest = hashlib.sha256(digest + wire).digest()
        if (sequence, encoded_bytes, samples, digest) != row[1:5]:
            raise ProtocolError("Preserved source does not match its receipt; retain device copy")
        return self._receipt(capture, row)

    def begin(self, capture: Capture) -> Receipt:
        manifest = capture.encode()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute(
                "INSERT OR IGNORE INTO captures VALUES(?,?,0,0,0,?,0)",
                (capture.key, manifest, hashlib.sha256(manifest).digest()))
            result = self._verified_receipt(capture)
        return result

    def receipt(self, capture: Capture) -> Receipt:
        with self.db:
            self.db.execute("BEGIN")
            result = self._verified_receipt(capture)
        return result

    def accept(self, capture: Capture, wire: bytes) -> Receipt:
        packet = Packet.parse(wire)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            # Even a duplicate ACK covers the entire prefix. Re-check the bytes
            # under the same writer lock before extending/replaying that promise.
            # This intentionally favors a correctness reference over throughput;
            # production batching needs a separately tested integrity strategy.
            self._verified_receipt(capture)
            row = self._state(capture)
            previous = self.db.execute(
                "SELECT wire FROM packets WHERE identity=? AND sequence=?",
                (capture.key, packet.sequence)).fetchone()
            if previous:
                if previous[0] != wire:
                    raise ProtocolError("Replayed packet conflicts with preserved source bytes")
                result = self._receipt(capture, row)
            else:
                if row[5]:
                    raise ProtocolError("Finalized captures cannot accept additional packets")
                if packet.sequence != row[1]:
                    raise ProtocolError("Sequence gap: resume at the committed prefix")
                if packet.kind == AUDIO:
                    if packet.sample_offset != row[3] or packet.sample_count != capture.frame_samples:
                        raise ProtocolError("Noncontiguous audio or unsupported frame duration")
                    if capture.codec == PCM16 and len(packet.payload) != packet.sample_count * 2:
                        raise ProtocolError("PCM byte count does not match its sample count")
                elif packet.sample_offset > row[3]:
                    raise ProtocolError("Bookmark points beyond captured audio")
                if row[2] + len(packet.payload) > self.max_capture_bytes:
                    raise ProtocolError("Capture storage quota reached; preserve device copy")
                digest = hashlib.sha256(row[4] + wire).digest()
                self.db.execute("INSERT INTO packets VALUES(?,?,?)", (capture.key, packet.sequence, wire))
                self.db.execute(
                    "UPDATE captures SET next_sequence=?,encoded_bytes=?,sample_count=?,chain_sha256=? "
                    "WHERE identity=?",
                    (row[1] + 1, row[2] + len(packet.payload), row[3] + packet.sample_count, digest, capture.key))
                result = self._receipt(capture, self._state(capture))
        return result

    def seal(self, capture: Capture, expected: Receipt) -> Receipt:
        """Verify the device's final counts/digest, then commit local finalization."""
        expected.encode()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            current = self._verified_receipt(capture)
            if (expected.device_id, expected.capture_id, expected.next_sequence, expected.encoded_bytes,
                expected.sample_count, expected.chain_sha256) != (
                    current.device_id, current.capture_id, current.next_sequence, current.encoded_bytes,
                    current.sample_count, current.chain_sha256):
                raise ProtocolError("Final capture seal does not match the committed source")
            self.db.execute("UPDATE captures SET sealed=1 WHERE identity=?", (capture.key,))
            result = self._receipt(capture, self._state(capture))
        return result

    def packets(self, capture: Capture):
        """Read preserved source packets for export/decoding; never removes them."""
        self._state(capture)
        for (wire,) in self.db.execute(
            "SELECT wire FROM packets WHERE identity=? ORDER BY sequence", (capture.key,)):
            yield Packet.parse(wire)
