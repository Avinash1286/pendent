import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from aura_companion.device import Device
from aura_companion.files import atomic_write_text
from aura_companion.protocol import CHUNK, HEADER, ProtocolError, Recording


class ReadPeer:
    def __init__(self, pcm):
        self.pcm, self.offsets, self.reply = pcm, [], b""

    async def write_gatt_char(self, _, command, response=True):
        version, opcode, tx = HEADER.unpack_from(command)
        if (version, opcode) != (1, 3):
            raise AssertionError("Download must only read committed audio")
        identity, offset, maximum = struct.unpack_from("<IIH", command, HEADER.size)
        self.offsets.append(offset)
        data = self.pcm[offset:offset + maximum]
        self.reply = HEADER.pack(0, 3, tx) + CHUNK.pack(identity, offset, len(data)) + data + struct.pack("<I", zlib.crc32(data))

    async def read_gatt_char(self, _):
        return self.reply


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.pcm = struct.pack("<400h", *range(400))
        self.record = Recording(7, 1720000000, len(self.pcm), zlib.crc32(self.pcm), 16000, 1, 16, 0)
        self.peer = ReadPeer(self.pcm)
        self.device = Device(self.peer)

    async def test_second_sync_checks_local_audio_without_ble_read(self):
        first = await self.device.download(self.record, self.root)
        self.peer.offsets.clear()
        second = await self.device.download(self.record, self.root)
        self.assertEqual(first, second)
        self.assertEqual(self.peer.offsets, [])

    async def test_corrupted_cached_audio_is_preserved_and_rejected(self):
        path = await self.device.download(self.record, self.root)
        data = bytearray(path.read_bytes())
        data[-1] ^= 1
        path.write_bytes(data)
        self.peer.offsets.clear()
        with self.assertRaisesRegex(ProtocolError, "checksum"):
            await self.device.download(self.record, self.root)
        self.assertEqual(path.read_bytes(), data)
        self.assertEqual(self.peer.offsets, [])

    async def test_metadata_cannot_claim_a_different_capture(self):
        path = await self.device.download(self.record, self.root)
        receipt = path.with_suffix(".json")
        saved = json.loads(receipt.read_text())
        saved["started_unix_seconds"] += 1
        receipt.write_text(json.dumps(saved))
        self.peer.offsets.clear()
        with self.assertRaisesRegex(ProtocolError, "metadata"):
            await self.device.download(self.record, self.root)
        self.assertEqual(self.peer.offsets, [])

    async def test_crash_between_wav_and_receipt_recovers_without_radio(self):
        with patch("aura_companion.device.atomic_write_text", side_effect=OSError("power interrupted")):
            with self.assertRaises(OSError):
                await self.device.download(self.record, self.root)
        self.assertEqual(len(list(self.root.glob("*.wav"))), 1)
        self.assertEqual(list(self.root.glob("*.json")), [])
        self.assertEqual(len(list(self.root.glob("*.pcm.part"))), 1)
        self.peer.offsets.clear()
        path = await self.device.download(self.record, self.root)
        self.assertTrue(json.loads(path.with_suffix(".json").read_text())["verified"])
        self.assertEqual(self.peer.offsets, [])

    async def test_missing_wav_is_redownloaded_even_with_verified_receipt(self):
        path = await self.device.download(self.record, self.root)
        path.unlink()
        self.peer.offsets.clear()
        await self.device.download(self.record, self.root)
        self.assertEqual(self.peer.offsets[0], 0)

    async def test_truncated_wav_is_not_trusted_from_header_or_receipt(self):
        path = await self.device.download(self.record, self.root)
        path.write_bytes(path.read_bytes()[:-2])
        with self.assertRaises(ProtocolError):
            await self.device.download(self.record, self.root)

    async def test_invalid_json_is_preserved_and_rejected(self):
        path = await self.device.download(self.record, self.root)
        path.with_suffix(".json").write_text("broken {")
        with self.assertRaises(ProtocolError):
            await self.device.download(self.record, self.root)
        self.assertEqual(path.with_suffix(".json").read_text(), "broken {")


class AtomicPublicationTests(unittest.TestCase):
    def test_failed_replace_preserves_previous_note(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "note.json"
            path.write_text("previous verified note")
            with patch("aura_companion.files.os.replace", side_effect=OSError("disk interrupted")):
                with self.assertRaises(OSError):
                    atomic_write_text(path, "new note")
            self.assertEqual(path.read_text(), "previous verified note")
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])
