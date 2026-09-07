"""Binary contract: docs/ble-protocol.md. No Bluetooth dependency for tests."""
from dataclasses import dataclass, asdict
import struct
import zlib

SERVICE = "7f510000-1b15-4f0d-8fe5-3f942170a001"
COMMAND = "7f510001-1b15-4f0d-8fe5-3f942170a001"
RESPONSE = "7f510002-1b15-4f0d-8fe5-3f942170a001"
HEADER = struct.Struct("<BBH")
RECORD = struct.Struct("<IQIIIBBB")
STATUS = struct.Struct("<BBBBHIH")
CHUNK = struct.Struct("<IIH")
ERRORS = {1: "busy", 2: "invalid command", 3: "recording not found", 4: "device I/O error", 5: "operation forbidden", 6: "end of recordings"}


class ProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class Recording:
    id: int
    started_unix_seconds: int
    pcm_bytes: int
    pcm_crc32: int
    sample_rate: int
    channels: int
    sample_bits: int
    flags: int

    @classmethod
    def parse(cls, payload: bytes):
        if len(payload) != RECORD.size:
            raise ProtocolError("Invalid recording metadata length")
        result = cls(*RECORD.unpack(payload))
        if result.sample_rate != 16000 or result.channels != 1 or result.sample_bits != 16:
            raise ProtocolError("Unsupported audio format")
        if result.pcm_bytes > 128 * 1024 * 1024 or result.pcm_bytes % 2:
            raise ProtocolError("Invalid PCM length")
        return result

    def to_dict(self):
        return asdict(self)


def parse_chunk(payload: bytes, record_id: int, offset: int, maximum: int) -> bytes:
    if len(payload) < CHUNK.size + 4:
        raise ProtocolError("Truncated audio packet")
    found_id, found_offset, count = CHUNK.unpack_from(payload)
    if found_id != record_id or found_offset != offset or count > maximum:
        raise ProtocolError("Audio packet identity/offset mismatch")
    if len(payload) != CHUNK.size + count + 4:
        raise ProtocolError("Audio packet length mismatch")
    pcm = payload[CHUNK.size:-4]
    expected_crc, = struct.unpack_from("<I", payload, len(payload) - 4)
    if zlib.crc32(pcm) != expected_crc:
        raise ProtocolError("Audio packet CRC mismatch")
    return pcm
