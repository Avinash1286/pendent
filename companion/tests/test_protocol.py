import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave
import zlib

from aura_companion.device import Device
from aura_companion.protocol import HEADER, CHUNK, RECORD, Recording, ProtocolError, parse_chunk
from aura_companion.notes import extractive_notes


class ProtocolTests(unittest.TestCase):
    def test_chunk_corruption_is_rejected(self):
        pcm = b"\x00\x01\x02\x03"
        good = CHUNK.pack(4, 0, len(pcm)) + pcm + struct.pack("<I", zlib.crc32(pcm))
        self.assertEqual(parse_chunk(good, 4, 0, 180), pcm)
        corrupt = bytearray(good)
        corrupt[CHUNK.size] ^= 1
        with self.assertRaises(ProtocolError):
            parse_chunk(bytes(corrupt), 4, 0, 180)
        with self.assertRaises(ProtocolError):
            parse_chunk(good, 4, 2, 180)

    def test_invalid_metadata_is_rejected(self):
        with self.assertRaises(ProtocolError):
            Recording.parse(RECORD.pack(1, 0, 17, 0, 16000, 1, 16, 0))
        with self.assertRaises(ProtocolError):
            Recording.parse(RECORD.pack(1, 0, 16, 0, 48000, 1, 16, 0))

    def test_extractive_summary_does_not_invent_an_action(self):
        text = "The light is beautiful. I should ask Maya about the garden."
        note = extractive_notes(text)
        self.assertEqual(note["suggested_actions"], ["I should ask Maya about the garden."])
        self.assertTrue(all(sentence in text for sentence in note["summary"]))


class FakeClient:
    def __init__(self, pcm, *, corrupt=False):
        self.pcm = pcm
        self.corrupt = corrupt
        self.commands = []
        self.response = b""

    async def write_gatt_char(self, _, command, response=True):
        version, opcode, tx = HEADER.unpack_from(command)
        self.commands.append(opcode)
        if opcode != 3:
            raise AssertionError("Sync must never issue DELETE or another mutation")
        record_id, offset, count = struct.unpack_from("<IIH", command, 4)
        pcm = self.pcm[offset:offset + count]
        crc = zlib.crc32(pcm) ^ int(self.corrupt)
        self.response = HEADER.pack(0, opcode, tx) + CHUNK.pack(record_id, offset, len(pcm)) + pcm + struct.pack("<I", crc)

    async def read_gatt_char(self, _):
        return self.response


class DownloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_verifies_full_audio_and_writes_standard_wav(self):
        pcm = struct.pack("<400h", *range(400))
        record = Recording(7, 0, len(pcm), zlib.crc32(pcm), 16000, 1, 16, 1)
        client = FakeClient(pcm)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            partial = root / f"aura-{record.id:08x}-{record.pcm_crc32:08x}.pcm.part"
            partial.write_bytes(pcm[:180])
            path = await Device(client).download(record, root)
            with wave.open(str(path), "rb") as wav:
                self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, 16000))
                self.assertEqual(wav.readframes(wav.getnframes()), pcm)
            self.assertFalse(partial.exists())
            metadata = json.loads(path.with_suffix(".json").read_text())
            self.assertTrue(metadata["verified"])
            self.assertEqual(metadata["flags"], 1)
            self.assertTrue(all(opcode == 3 for opcode in client.commands))

    async def test_corrupt_transfer_never_publishes_wav(self):
        pcm = b"\0\1" * 100
        record = Recording(1, 0, len(pcm), zlib.crc32(pcm), 16000, 1, 16, 0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ProtocolError):
                await Device(FakeClient(pcm, corrupt=True)).download(record, root)
            self.assertFalse(list(root.glob("*.wav")))


if __name__ == "__main__":
    unittest.main()
