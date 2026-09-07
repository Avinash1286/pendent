import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import struct
import time
import wave
import zlib

from .protocol import COMMAND, RESPONSE, SERVICE, HEADER, STATUS, ERRORS, Recording, ProtocolError, parse_chunk


class Device:
    def __init__(self, client):
        self.client = client
        self.transaction = 0
        self.lock = asyncio.Lock()

    async def request(self, opcode: int, payload=b"", *, allow_end=False):
        async with self.lock:
            self.transaction = (self.transaction + 1) & 65535
            tx = self.transaction
            await self.client.write_gatt_char(COMMAND, HEADER.pack(1, opcode, tx) + payload, response=True)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                reply = bytes(await self.client.read_gatt_char(RESPONSE))
                if len(reply) < HEADER.size:
                    raise ProtocolError("Truncated response")
                status, actual_opcode, actual_tx = HEADER.unpack_from(reply)
                if actual_tx != tx or actual_opcode != opcode or status == 1:
                    await asyncio.sleep(.05)
                    continue
                if status == 6 and allow_end:
                    return None
                if status:
                    raise ProtocolError(ERRORS.get(status, f"Unknown status {status}"))
                return reply[HEADER.size:]
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

    async def download(self, record: Recording, output: Path):
        output.mkdir(parents=True, exist_ok=True)
        stem = f"aura-{record.id:08x}-{record.pcm_crc32:08x}"
        partial = output / f"{stem}.pcm.part"
        wav_path = output / f"{stem}.wav"
        meta_path = output / f"{stem}.json"
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
        temporary.replace(wav_path)
        meta_temp = output / f"{stem}.json.tmp"
        meta_temp.write_text(json.dumps({**record.to_dict(), "verified": True, "wav": wav_path.name}, indent=2), encoding="utf-8")
        meta_temp.replace(meta_path)
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
