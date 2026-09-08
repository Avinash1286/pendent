"""A04 archive/receiver, experimental wire revision 3, incompatible with v1/v2.

Bounded streaming reader plus SQLite receipt after commit. Exhaust a reader's
packet iterator before publishing derived output: its final check binds the file.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3
import struct
import zlib

from .protocol import ProtocolError

WIRE_VERSION = 3
MANIFEST = struct.Struct("<4sBBBB16s16sIHHIBBBBQ")
FRAME = struct.Struct("<4sBBIQHH")
SEAL = struct.Struct("<4sBBH16s16sIIQQQQHH32s")
CRC = struct.Struct("<I")
ACK = struct.Struct("<4sBB16s16sIQQ32s")
PCM16, OPUS = 1, 2
AUDIO, BOOKMARK = 1, 2
OPEN, FINALIZED, INTERRUPTED = 0, 1, 2
MAX_PAYLOAD = 1275
MAX_FRAME_COUNT = 1_000_000
DEFAULT_MAX_PAYLOAD_BYTES = 256 * 1024 * 1024
UNKNOWN_SOURCE_SAMPLES = (1 << 64) - 1


def _integer(value, maximum, name):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ProtocolError(f"Invalid {name}")


def _identity(*values):
    if any(type(v) is not bytes or len(v) != 16 or v == bytes(16) for v in values):
        raise ProtocolError("Device and capture identities must be nonzero 128-bit values")


def _with_crc(data):
    return data + CRC.pack(zlib.crc32(data))


def _check_crc(data):
    if len(data) < 4 or zlib.crc32(data[:-4]) != CRC.unpack_from(data, len(data) - 4)[0]:
        raise ProtocolError("Record checksum mismatch")


@dataclass(frozen=True)
class Capture:
    device_id: bytes
    capture_id: bytes
    codec: int
    frame_samples: int = 320
    sample_rate: int = 16000
    started_at_ms: int = 0
    time_source: int = 0
    pre_skip: int = 40
    bitrate: int = 32000
    codec_profile: int = 1
    complexity: int = 3

    @property
    def key(self):
        return self.device_id.hex() + ":" + self.capture_id.hex()

    def encode(self):
        _identity(self.device_id, self.capture_id)
        if type(self.codec) is not int or self.codec not in (PCM16, OPUS):
            raise ProtocolError("Unsupported codec")
        if type(self.sample_rate) is not int or self.sample_rate != 16000:
            raise ProtocolError("Unsupported sample rate")
        if type(self.frame_samples) is not int or self.frame_samples not in (160, 320):
            raise ProtocolError("Unsupported frame duration")
        for v, limit, name in ((self.pre_skip, 320, "pre-skip"), (self.bitrate, 32000, "bitrate"),
                              (self.codec_profile, 1, "codec profile"), (self.complexity, 3, "complexity")):
            _integer(v, limit, name)
        profile = (self.pre_skip, self.bitrate, self.codec_profile, self.complexity)
        if self.codec == PCM16 and profile != (0, 0, 0, 0):
            raise ProtocolError("PCM profile requires zero codec controls/pre-skip")
        if self.codec == OPUS and profile != (40, 32000, 1, 3):
            raise ProtocolError("Unsupported Opus low-delay profile")
        _integer(self.started_at_ms, 4_102_444_800_000, "capture time")
        if type(self.time_source) is not int or self.time_source not in (0, 1):
            raise ProtocolError("Unsupported capture-time source")
        if (self.started_at_ms == 0) != (self.time_source == 0):
            raise ProtocolError("Unknown time must be zero; synchronized time must be nonzero")
        return _with_crc(MANIFEST.pack(b"AUR3", 3, self.codec, 1, 0, self.device_id, self.capture_id,
            self.sample_rate, self.frame_samples, self.pre_skip, self.bitrate, self.codec_profile,
            self.complexity, self.time_source, 0, self.started_at_ms))

    @classmethod
    def parse(cls, data):
        if len(data) != MANIFEST.size + 4:
            raise ProtocolError("Invalid revision-3 manifest length")
        _check_crc(data)
        magic, version, codec, channels, flags, device, capture, rate, samples, skip, bitrate, profile, complexity, clock, reserved, epoch = MANIFEST.unpack_from(data)
        if (magic, version, channels, flags, reserved) != (b"AUR3", 3, 1, 0, 0):
            raise ProtocolError("Unsupported manifest header; old v2 is not wire compatible")
        result = cls(device, capture, codec, samples, rate, epoch, clock, skip, bitrate, profile, complexity)
        result.encode()
        return result


@dataclass(frozen=True)
class Packet:
    sequence: int
    sample_offset: int
    sample_count: int
    payload: bytes
    kind: int = AUDIO

    def encode(self):
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
        return _with_crc(FRAME.pack(b"AFR3", 3, self.kind, self.sequence, self.sample_offset,
                                   self.sample_count, len(self.payload)) + self.payload)

    @classmethod
    def parse(cls, data):
        if not FRAME.size + 4 <= len(data) <= FRAME.size + MAX_PAYLOAD + 4:
            raise ProtocolError("Invalid packet length")
        magic, version, kind, sequence, offset, samples, count = FRAME.unpack_from(data)
        if (magic, version) != (b"AFR3", 3) or len(data) != FRAME.size + count + 4:
            raise ProtocolError("Invalid packet header or declared length")
        _check_crc(data)
        result = cls(sequence, offset, samples, data[FRAME.size:-4], kind)
        result.encode()
        return result


def validate_audio(capture, packet):
    """Profile-1 structure only; the decoder must also validate frame contents."""
    if packet.sample_count != capture.frame_samples:
        raise ProtocolError("Unsupported frame duration")
    if capture.codec == PCM16:
        if len(packet.payload) != packet.sample_count * 2:
            raise ProtocolError("PCM byte count does not match its sample count")
    else:
        toc = packet.payload[0]
        config = toc >> 3
        if len(packet.payload) < 2 or toc & 7 or not 16 <= config <= 23 or (40 << (config & 3)) != packet.sample_count:
            raise ProtocolError("Encoded Opus packet violates the negotiated profile")


@dataclass(frozen=True)
class Receipt:
    """Reader receipts describe expected bytes; only committed DB receipts ACK.

    A terminal chain_sha256 includes the exact seal, binding duration and status.
    This is neither deletion authority nor authenticated device identity.
    """
    device_id: bytes
    capture_id: bytes
    next_sequence: int
    encoded_bytes: int
    sample_count: int
    chain_sha256: bytes
    status: int = OPEN

    @property
    def sealed(self):
        return self.status != OPEN

    def encode(self):
        _identity(self.device_id, self.capture_id)
        _integer(self.next_sequence, MAX_FRAME_COUNT, "receipt sequence")
        _integer(self.encoded_bytes, 1 << 40, "receipt encoded length")
        _integer(self.sample_count, (1 << 63) - 1, "receipt sample count")
        if type(self.chain_sha256) is not bytes or len(self.chain_sha256) != 32:
            raise ProtocolError("Invalid receipt digest")
        if type(self.status) is not int or self.status not in (OPEN, FINALIZED, INTERRUPTED):
            raise ProtocolError("Invalid receipt status")
        return _with_crc(ACK.pack(b"ACK3", 3, self.status, self.device_id, self.capture_id,
            self.next_sequence, self.encoded_bytes, self.sample_count, self.chain_sha256))

    @classmethod
    def parse(cls, data):
        if len(data) != ACK.size + 4:
            raise ProtocolError("Invalid receipt length")
        _check_crc(data)
        magic, version, status, *fields = ACK.unpack_from(data)
        if (magic, version) != (b"ACK3", 3):
            raise ProtocolError("Unsupported receipt header")
        result = cls(*fields, status)
        result.encode()
        return result


@dataclass(frozen=True)
class Seal:
    device_id: bytes
    capture_id: bytes
    next_sequence: int
    audio_packets: int
    encoded_bytes: int
    encoded_samples: int
    source_samples: int
    original_source_samples: int | None
    pre_skip: int
    end_trim: int
    chain_sha256: bytes
    status: int = FINALIZED

    def encode(self):
        _identity(self.device_id, self.capture_id)
        if type(self.status) is not int or self.status not in (FINALIZED, INTERRUPTED):
            raise ProtocolError("Invalid termination status")
        for v, limit, name in ((self.next_sequence, MAX_FRAME_COUNT, "seal sequence"),
            (self.audio_packets, MAX_FRAME_COUNT, "audio packet count"), (self.encoded_bytes, 1 << 40, "seal encoded length"),
            (self.encoded_samples, (1 << 63) - 1, "seal encoded samples"), (self.source_samples, (1 << 63) - 1, "seal source samples"),
            (self.pre_skip, 320, "seal pre-skip"), (self.end_trim, 319, "seal end trim")):
            _integer(v, limit, name)
        if self.original_source_samples is not None:
            _integer(self.original_source_samples, (1 << 63) - 1, "original source samples")
        if type(self.chain_sha256) is not bytes or len(self.chain_sha256) != 32:
            raise ProtocolError("Invalid seal digest")
        return _with_crc(SEAL.pack(b"ASE3", 3, self.status, 0, self.device_id, self.capture_id,
            self.next_sequence, self.audio_packets, self.encoded_bytes, self.encoded_samples, self.source_samples,
            UNKNOWN_SOURCE_SAMPLES if self.original_source_samples is None else self.original_source_samples,
            self.pre_skip, self.end_trim, self.chain_sha256))

    @classmethod
    def parse(cls, data):
        if len(data) != SEAL.size + 4:
            raise ProtocolError("Invalid termination length")
        _check_crc(data)
        magic, version, status, reserved, device, capture, sequence, audio, size, encoded, source, original, pre, tail, digest = SEAL.unpack_from(data)
        if (magic, version, reserved) != (b"ASE3", 3, 0):
            raise ProtocolError("Unsupported termination header")
        result = cls(device, capture, sequence, audio, size, encoded, source,
            None if original == UNKNOWN_SOURCE_SAMPLES else original, pre, tail, digest, status)
        result.encode()
        return result


class _Prefix:
    def __init__(self, capture, max_payload_bytes):
        self.capture, self.max_payload_bytes = capture, max_payload_bytes
        self.sequence = self.audio_packets = self.encoded_bytes = self.samples = self.max_bookmark = 0
        self.digest = hashlib.sha256(capture.encode()).digest()

    def accept(self, packet, wire):
        if packet.sequence != self.sequence:
            raise ProtocolError("Sequence gap: resume at the committed prefix")
        if packet.kind == AUDIO:
            if packet.sample_offset != self.samples:
                raise ProtocolError("Noncontiguous audio timeline")
            validate_audio(self.capture, packet)
            self.audio_packets += 1
        else:
            if packet.sample_offset > self.samples:
                raise ProtocolError("Bookmark points beyond captured audio")
            self.max_bookmark = max(self.max_bookmark, packet.sample_offset)
        if self.encoded_bytes + len(packet.payload) > self.max_payload_bytes:
            raise ProtocolError("Capture storage quota reached; preserve device copy")
        self.sequence += 1
        self.encoded_bytes += len(packet.payload)
        self.samples += packet.sample_count
        self.digest = hashlib.sha256(self.digest + wire).digest()

    def validate_seal(self, seal):
        seal.encode()
        if (seal.device_id, seal.capture_id, seal.next_sequence, seal.audio_packets, seal.encoded_bytes,
            seal.encoded_samples, seal.chain_sha256) != (self.capture.device_id, self.capture.capture_id,
            self.sequence, self.audio_packets, self.encoded_bytes, self.samples, self.digest):
            raise ProtocolError("Final capture seal does not match the committed source")
        if seal.pre_skip != (self.capture.pre_skip if self.samples else 0) or seal.end_trim >= self.capture.frame_samples:
            raise ProtocolError("Invalid seal pre-skip/end trim")
        if seal.source_samples + seal.pre_skip + seal.end_trim != self.samples:
            raise ProtocolError("Seal does not preserve exact source duration")
        if seal.status == FINALIZED:
            if seal.original_source_samples != seal.source_samples or self.max_bookmark > seal.source_samples:
                raise ProtocolError("Finalized source length/bookmark is inconsistent")
        elif seal.original_source_samples is not None or seal.end_trim != 0:
            raise ProtocolError("Interrupted original duration must be unknown, without invented final trim")

    def interrupted(self):
        skip = self.capture.pre_skip if self.samples else 0
        return Seal(self.capture.device_id, self.capture.capture_id, self.sequence, self.audio_packets,
            self.encoded_bytes, self.samples, self.samples - skip, None, skip, 0, self.digest, INTERRUPTED)

    def receipt(self, seal=None):
        digest = self.digest
        if seal:
            self.validate_seal(seal)
            digest = hashlib.sha256(digest + seal.encode()).digest()
        return Receipt(self.capture.device_id, self.capture.capture_id, self.sequence, self.encoded_bytes,
            self.samples, digest, seal.status if seal else OPEN)


class _ArchiveStream:
    def __init__(self, path, allow_interrupted, max_payload_bytes):
        self.path, self.allow_interrupted, self.max_payload_bytes = path, allow_interrupted, max_payload_bytes
        self.file_digest = hashlib.sha256()
        self.file_bytes = self.discarded_tail_bytes = 0
        self.seal = None

    def _read(self, stream, size):
        data = stream.read(size)
        self.file_digest.update(data)
        self.file_bytes += len(data)
        return data

    def _recover(self, tail):
        if not self.allow_interrupted:
            raise ProtocolError("Archive has no complete final seal; explicit interrupted recovery required")
        self.discarded_tail_bytes = tail
        self.termination = self.prefix.interrupted()

    def __iter__(self):
        with self.path.open("rb") as stream:
            self.capture = Capture.parse(self._read(stream, MANIFEST.size + 4))
            self.prefix = _Prefix(self.capture, self.max_payload_bytes)
            while True:
                magic = self._read(stream, 4)
                if len(magic) < 4:
                    if magic and not any(expected.startswith(magic) for expected in (b"AFR3", b"ASE3")):
                        raise ProtocolError("Unknown partial record; corruption is not an interrupted tail")
                    self._recover(len(magic))
                    break
                if magic == b"ASE3":
                    wire = magic + self._read(stream, SEAL.size)
                    if ((len(wire) > 4 and wire[4] != 3) or
                        (len(wire) > 5 and wire[5] not in (FINALIZED, INTERRUPTED)) or
                        any(wire[6:8])):
                        raise ProtocolError("Unsupported termination header")
                    if len(wire) != SEAL.size + 4:
                        self._recover(len(wire))
                        break
                    self.seal = Seal.parse(wire)
                    self.prefix.validate_seal(self.seal)
                    if self._read(stream, 1):
                        raise ProtocolError("Unexpected bytes after terminal seal")
                    if self.seal.status == INTERRUPTED and not self.allow_interrupted:
                        raise ProtocolError("Explicit interrupted recovery required")
                    self.termination = self.seal
                    break
                if magic != b"AFR3":
                    raise ProtocolError("Unknown archive record; corruption is not an interrupted tail")
                header = magic + self._read(stream, FRAME.size - 4)
                if ((len(header) > 4 and header[4] != 3) or
                    (len(header) > 5 and header[5] not in (AUDIO, BOOKMARK))):
                    raise ProtocolError("Unsupported packet header")
                if len(header) != FRAME.size:
                    self._recover(len(header))
                    break
                _, _, kind, sequence, offset, samples, declared = FRAME.unpack(header)
                if declared > MAX_PAYLOAD:
                    raise ProtocolError("Declared packet exceeds bounded record size")
                if sequence != self.prefix.sequence or sequence >= MAX_FRAME_COUNT:
                    raise ProtocolError("Invalid packet sequence before interrupted tail")
                if kind == AUDIO:
                    if (offset != self.prefix.samples or samples != self.capture.frame_samples or
                        not declared or (self.capture.codec == PCM16 and declared != samples * 2) or
                        (self.capture.codec == OPUS and declared < 2)):
                        raise ProtocolError("Invalid audio header before interrupted tail")
                elif offset > self.prefix.samples or samples or declared:
                    raise ProtocolError("Invalid bookmark header before interrupted tail")
                wire = header + self._read(stream, declared + 4)
                if len(wire) != FRAME.size + declared + 4:
                    self._recover(len(wire))
                    break
                packet = Packet.parse(wire)
                self.prefix.accept(packet, wire)
                yield packet
            self.receipt = self.prefix.receipt(self.termination)
            self.sha256_hex = self.file_digest.hexdigest()


@dataclass(frozen=True)
class VerifiedArchive:
    path: Path
    capture: Capture
    seal: Seal | None
    termination: Seal
    receipt: Receipt
    sha256_hex: str
    discarded_tail_bytes: int
    file_bytes: int
    max_payload_bytes: int

    @property
    def status(self):
        return "finalized" if self.termination.status == FINALIZED else "interrupted"

    @property
    def source_samples(self):
        return self.termination.source_samples

    @property
    def original_source_samples(self):
        return self.termination.original_source_samples

    @property
    def end_trim(self):
        return self.termination.end_trim

    @property
    def duration_seconds(self):
        return self.source_samples / self.capture.sample_rate

    def iter_packets(self):
        """Exhaust before publication; final recheck detects replacement/edits."""
        reader = _ArchiveStream(self.path, self.status == "interrupted", self.max_payload_bytes)
        yield from reader
        if (reader.sha256_hex != self.sha256_hex or reader.capture != self.capture
                or reader.termination != self.termination or reader.receipt != self.receipt):
            raise ProtocolError("Archive changed after validation; discard derived output")


def read_archive(path, *, allow_interrupted=False, max_payload_bytes=DEFAULT_MAX_PAYLOAD_BYTES):
    _integer(max_payload_bytes, 1 << 40, "archive payload limit")
    if max_payload_bytes == 0 or type(allow_interrupted) is not bool:
        raise ProtocolError("Invalid archive reader limits")
    reader = _ArchiveStream(Path(path), allow_interrupted, max_payload_bytes)
    for _ in reader:
        pass
    return VerifiedArchive(Path(path), reader.capture, reader.seal, reader.termination, reader.receipt,
        reader.sha256_hex, reader.discarded_tail_bytes, reader.file_bytes, max_payload_bytes)


class DurableReceiver:
    """One serialized local owner. DELETE journal + synchronous EXTRA.

    Durability depends on the OS/filesystem/device honoring flushes. Keep DB and
    journal together, outside network/cloud-sync folders. Per-packet ACK checks
    the whole prefix; import_archive uses one linear transaction and one ACK.
    """
    def __init__(self, path, *, max_capture_bytes=DEFAULT_MAX_PAYLOAD_BYTES):
        _integer(max_capture_bytes, 1 << 40, "capture byte limit")
        if max_capture_bytes == 0 or str(path) in ("", ":memory:"):
            raise ProtocolError("A positive limit and persistent database path are required")
        self.max_capture_bytes = max_capture_bytes
        self.db = sqlite3.connect(str(path), timeout=5)
        main = next((row for row in self.db.execute("PRAGMA database_list") if row[1] == "main"), None)
        if main is None or not main[2]:
            self.db.close()
            raise ProtocolError("An on-disk persistent database is required before any receipt")
        self.db.execute("PRAGMA foreign_keys=ON")
        if self.db.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
            self.db.close()
            raise ProtocolError("Persistent rollback journaling is required")
        self.db.execute("PRAGMA synchronous=EXTRA")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS captures (
                identity TEXT PRIMARY KEY, manifest BLOB NOT NULL, next_sequence INTEGER NOT NULL,
                encoded_bytes INTEGER NOT NULL, sample_count INTEGER NOT NULL, chain_sha256 BLOB NOT NULL,
                sealed INTEGER NOT NULL DEFAULT 0, seal_wire BLOB);
            CREATE TABLE IF NOT EXISTS packets (
                identity TEXT NOT NULL REFERENCES captures(identity), sequence INTEGER NOT NULL,
                wire BLOB NOT NULL, PRIMARY KEY (identity, sequence));
        """)
        if "seal_wire" not in {r[1] for r in self.db.execute("PRAGMA table_info(captures)")}:
            self.db.execute("ALTER TABLE captures ADD COLUMN seal_wire BLOB")
            self.db.commit()

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _state(self, capture):
        row = self.db.execute("SELECT manifest,next_sequence,encoded_bytes,sample_count,chain_sha256,sealed,seal_wire "
                              "FROM captures WHERE identity=?", (capture.key,)).fetchone()
        if row is None:
            raise ProtocolError("Capture manifest has not been opened")
        if row[0] != capture.encode():
            raise ProtocolError("Capture identity is already bound to different metadata")
        return row

    def _insert_capture(self, capture):
        wire = capture.encode()
        self.db.execute("INSERT OR IGNORE INTO captures(identity,manifest,next_sequence,encoded_bytes,sample_count,chain_sha256,sealed,seal_wire) "
                        "VALUES(?,?,0,0,0,?,0,NULL)", (capture.key, wire, hashlib.sha256(wire).digest()))

    def _verified_prefix(self, capture):
        row = self._state(capture)
        prefix = _Prefix(capture, self.max_capture_bytes)
        for sequence, wire in self.db.execute("SELECT sequence,wire FROM packets WHERE identity=? ORDER BY sequence", (capture.key,)):
            packet = Packet.parse(wire)
            if sequence != packet.sequence:
                raise ProtocolError("Preserved source contains a sequence gap")
            prefix.accept(packet, wire)
        if (prefix.sequence, prefix.encoded_bytes, prefix.samples, prefix.digest) != row[1:5]:
            raise ProtocolError("Preserved source does not match its receipt; retain device copy")
        if row[5]:
            if row[6] is None:
                raise ProtocolError("Preserved source is missing terminal metadata")
            seal = Seal.parse(row[6])
            prefix.validate_seal(seal)
            if seal.status != row[5]:
                raise ProtocolError("Preserved termination status is inconsistent")
        elif row[6] is not None:
            raise ProtocolError("Unsealed capture contains inconsistent terminal metadata")
        return prefix, row

    @staticmethod
    def _receipt(prefix, row):
        return prefix.receipt(Seal.parse(row[6]) if row[5] else None)

    def begin(self, capture):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self._insert_capture(capture)
            prefix, row = self._verified_prefix(capture)
            result = self._receipt(prefix, row)
        return result

    def receipt(self, capture):
        with self.db:
            self.db.execute("BEGIN")
            prefix, row = self._verified_prefix(capture)
            result = self._receipt(prefix, row)
        return result

    def _save_prefix(self, capture, prefix):
        self.db.execute("UPDATE captures SET next_sequence=?,encoded_bytes=?,sample_count=?,chain_sha256=? WHERE identity=?",
            (prefix.sequence, prefix.encoded_bytes, prefix.samples, prefix.digest, capture.key))

    def accept(self, capture, wire):
        packet = Packet.parse(wire)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            prefix, row = self._verified_prefix(capture)
            previous = self.db.execute("SELECT wire FROM packets WHERE identity=? AND sequence=?", (capture.key, packet.sequence)).fetchone()
            if previous:
                if previous[0] != wire:
                    raise ProtocolError("Replayed packet conflicts with preserved source bytes")
            else:
                if row[5]:
                    raise ProtocolError("Finalized captures cannot accept additional packets")
                prefix.accept(packet, wire)
                self.db.execute("INSERT INTO packets VALUES(?,?,?)", (capture.key, packet.sequence, wire))
                self._save_prefix(capture, prefix)
            result = self._receipt(prefix, self._state(capture))
        return result

    def _save_seal(self, capture, prefix, seal):
        prefix.validate_seal(seal)
        row = self._state(capture)
        if row[6] is not None and row[6] != seal.encode():
            raise ProtocolError("Termination conflicts with preserved source metadata")
        self.db.execute("UPDATE captures SET sealed=?,seal_wire=? WHERE identity=?", (seal.status, seal.encode(), capture.key))
        return prefix.receipt(seal)

    def seal(self, capture, seal):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            prefix, _ = self._verified_prefix(capture)
            result = self._save_seal(capture, prefix, seal)
        return result

    def import_archive(self, archive):
        """No ACK before EOF/hash verification and the single transaction COMMIT."""
        capture = archive.capture
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self._insert_capture(capture)
            existing, row = self._verified_prefix(capture)
            prefix = _Prefix(capture, self.max_capture_bytes)
            for packet in archive.iter_packets():
                wire = packet.encode()
                prefix.accept(packet, wire)
                if packet.sequence < existing.sequence:
                    previous = self.db.execute("SELECT wire FROM packets WHERE identity=? AND sequence=?", (capture.key, packet.sequence)).fetchone()
                    if previous is None or previous[0] != wire:
                        raise ProtocolError("Imported packet conflicts with preserved source bytes")
                else:
                    if row[5]:
                        raise ProtocolError("Finalized captures cannot accept additional packets")
                    self.db.execute("INSERT INTO packets VALUES(?,?,?)", (capture.key, packet.sequence, wire))
            if prefix.sequence < existing.sequence:
                raise ProtocolError("Imported archive is shorter than the preserved prefix")
            self._save_prefix(capture, prefix)
            result = self._save_seal(capture, prefix, archive.termination)
            if result != archive.receipt:
                raise ProtocolError("Imported archive receipt differs from validated input")
        return result

    def packets(self, capture):
        """Validated snapshot. Exhaust before publishing any derived output."""
        with self.db:
            self.db.execute("BEGIN")
            self._verified_prefix(capture)
            for (wire,) in self.db.execute("SELECT wire FROM packets WHERE identity=? ORDER BY sequence", (capture.key,)):
                yield Packet.parse(wire)
