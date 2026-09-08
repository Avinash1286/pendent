import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import struct
import time
import wave
import zlib

from .files import atomic_write_text
from .protocol import COMMAND, RESPONSE, SERVICE, HEADER, STATUS, ERRORS, Recording, ProtocolError, parse_chunk


def verify_saved_wav(path: Path, record: Recording):
    """Re-read local PCM: a metadata flag alone never proves a complete download."""
    try:
        with wave.open(str(path), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) != (
                record.channels, record.sample_bits // 8, record.sample_rate,
                record.pcm_bytes // (record.channels * (record.sample_bits // 8)),
            ):
                raise ProtocolError("Saved WAV format or length mismatch")
            size, crc = 0, 0
            for block in iter(lambda: wav.readframes(32768), b""):
                size += len(block)
                crc = zlib.crc32(block, crc)
            if size != record.pcm_bytes or crc != record.pcm_crc32:
                raise ProtocolError("Saved WAV checksum mismatch")
    except (wave.Error, EOFError) as error:
        raise ProtocolError("Saved WAV is incomplete or invalid") from error


def _check_saved_metadata(path: Path, record: Recording, wav_name: str):
    try:
        if path.stat().st_size > 100_000:
            raise ValueError("metadata exceeds size limit")
        saved = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(saved, dict) or saved.get("verified") is not True or saved.get("wav") != wav_name:
            raise ValueError("invalid verification receipt")
        if any(type(saved.get(key)) is not int or saved[key] != value
               for key, value in record.to_dict().items()):
            raise ValueError("recording identity or format differs")
    except (ValueError, UnicodeError) as error:
        raise ProtocolError(f"Saved metadata does not match this recording: {path}. Use a separate output directory or inspect the files before retrying.") from error


class Device:
    def __init__(self, client):
        self.client = client
        self.transaction = 0
        self.lock = asyncio.Lock()

    async def request(self, opcode: int, payload=b"", *, allow_end=False, timeout=30):
        async with self.lock:
            self.transaction = (self.transaction + 1) & 65535
            tx = self.transaction
            await self.client.write_gatt_char(COMMAND, HEADER.pack(1, opcode, tx) + payload, response=True)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                reply = bytes(await self.client.read_gatt_char(RESPONSE))
                if len(reply) < HEADER.size:
                    raise ProtocolError("Truncated response")
                status, actual_opcode, actual_tx = HEADER.unpack_from(reply)
                if actual_tx != tx or actual_opcode != opcode or status == 1:
                    await asyncio.sleep(.5 if opcode == 6 else .01)
                    continue
                if status == 6 and allow_end:
                    return None
                if status:
                    raise ProtocolError(ERRORS.get(status, f"Unknown status {status}"))
                return reply[HEADER.size:]
            if opcode == 6:
                raise TimeoutError("Maintenance timed out. Do not resend automatically. Keep the pendant powered and reconnect to check recovery.")
            raise TimeoutError("Device command timed out; reconnect and resume sync")

    async def status(self):
        payload = await self.request(1)
        if len(payload) != STATUS.size:
            raise ProtocolError("Invalid status length")
        keys = ["version", "state", "privacy_off", "flags", "battery_mV", "free_bytes", "recording_count"]
        return dict(zip(keys, STATUS.unpack(payload)))

    async def recordings(self):
        for index in range(65536):
            payload = await self.request(2, struct.pack("<H", index), allow_end=True)
            if payload is None:
                return
            yield Recording.parse(payload)
        raise ProtocolError("Recording list exceeded protocol limit")

    async def set_time(self):
        await self.request(5, struct.pack("<Q", int(time.time())))

    async def format_storage(self, *, confirmed=False):
        if not confirmed:
            raise ValueError("Maintenance requires explicit confirmation")
        status = await self.status()
        if status["recording_count"] != 0 or status["state"] in (1, 2):
            raise ProtocolError("Stop recording, export, and explicitly delete every device note before maintenance")
        # The firmware independently requires committed tombstones and a recent physical hold.
        await self.request(6, struct.pack("<I", 0x53415245), timeout=600)

    async def download(self, record: Recording, output: Path):
        output.mkdir(parents=True, exist_ok=True)
        stem = f"aura-{record.id:08x}-{record.pcm_crc32:08x}"
        partial = output / f"{stem}.pcm.part"
        wav_path = output / f"{stem}.wav"
        meta_path = output / f"{stem}.json"
        if meta_path.exists():
            _check_saved_metadata(meta_path, record, wav_path.name)
        metadata = json.dumps({**record.to_dict(), "verified": True, "wav": wav_path.name}, indent=2)
        if wav_path.exists():
            # Repeated sync costs a local checksum, not another complete BLE transfer.
            # A crash after WAV publication can leave no receipt; rebuild it only
            # after the current device listing and the full local PCM agree.
            verify_saved_wav(wav_path, record)
            if not meta_path.exists():
                atomic_write_text(meta_path, metadata)
            return wav_path
        # Resume only an existing prefix; the complete CRC is checked before WAV publication.
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > record.pcm_bytes or offset % 2:
            raise ProtocolError(f"Invalid partial file: {partial}")
        crc = 0
        if offset:
            with partial.open("rb") as stream:
                for block in iter(lambda: stream.read(65536), b""):
                    crc = zlib.crc32(block, crc)
        with partial.open("ab") as stream:
            while offset < record.pcm_bytes:
                count = min(180, record.pcm_bytes - offset)
                payload = await self.request(3, struct.pack("<IIH", record.id, offset, count))
                pcm = parse_chunk(payload, record.id, offset, count)
                if not pcm or len(pcm) % 2:
                    raise ProtocolError("Unexpected audio EOF or odd sample length")
                stream.write(pcm)
                crc = zlib.crc32(pcm, crc)
                offset += len(pcm)
            stream.flush()
            os.fsync(stream.fileno())
        if crc != record.pcm_crc32:
            raise ProtocolError(f"Complete CRC mismatch. Retained {partial}; device recording was not deleted. Move this partial aside before retrying.")
        temporary = output / f"{stem}.wav.tmp"
        with wave.open(str(temporary), "wb") as wav, partial.open("rb") as stream:
            wav.setnchannels(record.channels)
            wav.setsampwidth(record.sample_bits // 8)
            wav.setframerate(record.sample_rate)
            for block in iter(lambda: stream.read(65536), b""):
                wav.writeframesraw(block)
        with temporary.open("rb+") as stream:
            os.fsync(stream.fileno())
        temporary.replace(wav_path)
        atomic_write_text(meta_path, metadata)
        partial.unlink()
        return wav_path


async def discover():
    from bleak import BleakScanner
    found = await BleakScanner.discover(timeout=8, return_adv=True)
    return [(device, adv) for device, adv in found.values() if SERVICE in [s.lower() for s in adv.service_uuids] or (adv.local_name or "").startswith("AURA")]


@asynccontextmanager
async def connect(address: str):
    from bleak import BleakClient
    # OS pairing may show a system dialog; physical pairing is enabled on the pendant.
    async with BleakClient(address, pair=True, timeout=45) as client:
        yield Device(client)
