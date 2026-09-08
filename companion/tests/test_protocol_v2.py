from dataclasses import replace
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from aura_companion.protocol import ProtocolError
from aura_companion.protocol_v2 import (
    ACK, AUDIO, BOOKMARK, FRAME, MANIFEST, OPUS, PCM16,
    Capture, DurableReceiver, Packet, Receipt,
)


CAPTURE = Capture(bytes.fromhex("01" * 16), bytes.fromhex("02" * 16), OPUS)


def audio(sequence=0, offset=0, payload=b"encoded-opus-test-payload"):
    # Synthetic opaque bytes deliberately do not claim to be decodable Opus.
    return Packet(sequence, offset, 320, payload)


class FramingTests(unittest.TestCase):
    def test_manifest_round_trip_and_unknown_time(self):
        self.assertEqual(MANIFEST.size, 56)
        self.assertEqual(Capture.parse(CAPTURE.encode()), CAPTURE)
        timed = replace(CAPTURE, started_at_ms=1_783_600_000_000, time_source=1)
        self.assertEqual(Capture.parse(timed.encode()), timed)
        for item in (replace(CAPTURE, device_id=bytes(16)), replace(CAPTURE, codec=42),
                     replace(CAPTURE, sample_rate=48000), replace(CAPTURE, frame_samples=80),
                     replace(CAPTURE, started_at_ms=1), replace(CAPTURE, time_source=1)):
            with self.subTest(item=item), self.assertRaises(ProtocolError):
                item.encode()

    def test_manifest_unknown_version_flags_or_truncation_rejected(self):
        wire = bytearray(CAPTURE.encode())
        for offset in (4, 6, 7, 55):
            changed = bytearray(wire)
            changed[offset] = 255
            with self.subTest(offset=offset), self.assertRaises(ProtocolError):
                Capture.parse(bytes(changed))
        with self.assertRaises(ProtocolError):
            Capture.parse(bytes(wire[:-1]))

    def test_packet_checksum_covers_header_and_payload(self):
        packet = audio()
        self.assertEqual(Packet.parse(packet.encode()), packet)
        for offset in (6, 10, FRAME.size, len(packet.encode()) - 1):
            changed = bytearray(packet.encode())
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ProtocolError):
                Packet.parse(bytes(changed))

    def test_malformed_packets_rejected(self):
        for packet in (audio(payload=b""), audio(payload=b"x" * 1276),
                       audio(sequence=-1), audio(sequence=1_000_000),
                       Packet(0, 0, 0, b"x"), Packet(0, 0, 1, b"", BOOKMARK),
                       Packet(0, 0, 0, b"x", BOOKMARK), Packet(True, 0, 320, b"x")):
            with self.subTest(packet=packet), self.assertRaises(ProtocolError):
                packet.encode()
        for wire in (audio().encode()[:-1], audio().encode() + b"x", b""):
            with self.assertRaises(ProtocolError):
                Packet.parse(wire)

    def test_receipt_wire_round_trip_and_unsupported_flags(self):
        receipt = Receipt(CAPTURE.device_id, CAPTURE.capture_id, 5, 100, 1600, b"a" * 32, False)
        self.assertEqual(Receipt.parse(receipt.encode()), receipt)
        self.assertEqual(len(receipt.encode()), ACK.size)
        changed = bytearray(receipt.encode())
        changed[5] = 2
        with self.assertRaises(ProtocolError):
            Receipt.parse(changed)


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.path = self.root / "captures.sqlite3"
        self.receiver = DurableReceiver(self.path)
        self.receiver.begin(CAPTURE)

    def tearDown(self):
        self.receiver.close()
        self.directory.cleanup()

    def test_audio_and_bookmarks_share_contiguous_archive(self):
        packets = [audio(), Packet(1, 160, 0, b"", BOOKMARK), audio(2, 320)]
        digest = hashlib.sha256(CAPTURE.encode()).digest()
        for packet in packets:
            receipt = self.receiver.accept(CAPTURE, packet.encode())
            digest = hashlib.sha256(digest + packet.encode()).digest()
        self.assertEqual((receipt.next_sequence, receipt.sample_count), (3, 640))
        self.assertEqual(receipt.encoded_bytes, len(packets[0].payload) + len(packets[2].payload))
        self.assertEqual(receipt.chain_sha256, digest)
        self.assertEqual(list(self.receiver.packets(CAPTURE)), packets)

    def test_replay_returns_current_prefix_without_duplicate_data(self):
        first = audio().encode()
        self.receiver.accept(CAPTURE, first)
        expected = self.receiver.accept(CAPTURE, audio(1, 320).encode())
        self.assertEqual(self.receiver.accept(CAPTURE, first), expected)
        self.assertEqual(len(list(self.receiver.packets(CAPTURE))), 2)

    def test_conflicting_replay_does_not_replace_original(self):
        expected = self.receiver.accept(CAPTURE, audio().encode())
        with self.assertRaisesRegex(ProtocolError, "conflicts"):
            self.receiver.accept(CAPTURE, audio(payload=b"different audio").encode())
        self.assertEqual(self.receiver.receipt(CAPTURE), expected)
        self.assertEqual(list(self.receiver.packets(CAPTURE)), [audio()])

    def test_gap_offset_future_bookmark_and_pcm_length_fail_closed(self):
        for packet in (audio(1), audio(offset=10), Packet(0, 1, 0, b"", BOOKMARK)):
            with self.subTest(packet=packet), self.assertRaises(ProtocolError):
                self.receiver.accept(CAPTURE, packet.encode())
        pcm = replace(CAPTURE, capture_id=bytes.fromhex("03" * 16), codec=PCM16)
        self.receiver.begin(pcm)
        with self.assertRaisesRegex(ProtocolError, "PCM"):
            self.receiver.accept(pcm, audio().encode())
        receipt = self.receiver.accept(pcm, audio(payload=b"\0\1" * 320).encode())
        self.assertEqual(receipt.encoded_bytes, 640)
        self.assertEqual(self.receiver.receipt(CAPTURE).next_sequence, 0)

    def test_identity_separates_devices_and_refuses_metadata_rebinding(self):
        other = replace(CAPTURE, device_id=bytes.fromhex("05" * 16))
        self.receiver.begin(other)
        self.receiver.accept(CAPTURE, audio().encode())
        self.assertEqual(self.receiver.receipt(other).next_sequence, 0)
        with self.assertRaisesRegex(ProtocolError, "different metadata"):
            self.receiver.begin(replace(CAPTURE, frame_samples=160))

    def test_quota_failure_keeps_committed_prefix(self):
        self.receiver.max_capture_bytes = len(audio().payload)
        expected = self.receiver.accept(CAPTURE, audio().encode())
        with self.assertRaisesRegex(ProtocolError, "quota"):
            self.receiver.accept(CAPTURE, audio(1, 320).encode())
        self.assertEqual(self.receiver.receipt(CAPTURE), expected)

    def test_final_seal_verifies_complete_identity_counts_and_digest(self):
        expected = self.receiver.accept(CAPTURE, audio().encode())
        for bad in (replace(expected, next_sequence=2), replace(expected, encoded_bytes=1),
                    replace(expected, sample_count=321), replace(expected, chain_sha256=b"x" * 32),
                    replace(expected, device_id=b"x" * 16)):
            with self.subTest(bad=bad), self.assertRaises(ProtocolError):
                self.receiver.seal(CAPTURE, bad)
        sealed = self.receiver.seal(CAPTURE, expected)
        self.assertTrue(sealed.sealed)
        self.assertEqual(self.receiver.seal(CAPTURE, expected), sealed)
        self.assertEqual(self.receiver.accept(CAPTURE, audio().encode()), sealed)
        with self.assertRaisesRegex(ProtocolError, "Finalized"):
            self.receiver.accept(CAPTURE, audio(1, 320).encode())

    def test_committed_audio_survives_restart_and_lost_ack(self):
        expected = self.receiver.accept(CAPTURE, audio().encode())
        self.receiver.close()
        self.receiver = DurableReceiver(self.path)
        self.assertEqual(self.receiver.begin(CAPTURE), expected)
        self.assertEqual(self.receiver.accept(CAPTURE, audio().encode()), expected)

    def test_process_exit_before_commit_does_not_ack_or_publish_packet(self):
        # Kill inside the real accept transaction, after INSERT and before its
        # receipt UPDATE. SQLite's rollback journal must restore the whole prefix.
        code = """
import os, sys
from pathlib import Path
from aura_companion.protocol_v2 import Capture, DurableReceiver, Packet
capture = Capture.parse(bytes.fromhex(sys.argv[2]))
receiver = DurableReceiver(Path(sys.argv[1]))
receiver.begin(capture)
receiver.db.set_trace_callback(lambda sql: os._exit(73) if sql.startswith('UPDATE captures SET next_sequence=') else None)
receiver.accept(capture, bytes.fromhex(sys.argv[3]))
os._exit(74)
"""
        run = subprocess.run([sys.executable, "-c", code, str(self.path), CAPTURE.encode().hex(),
                              audio().encode().hex()], capture_output=True, timeout=20)
        self.assertEqual(run.returncode, 73, run.stderr.decode())
        self.assertEqual(self.receiver.receipt(CAPTURE).next_sequence, 0)
        self.assertEqual(list(self.receiver.packets(CAPTURE)), [])
        self.assertEqual(self.receiver.accept(CAPTURE, audio().encode()).next_sequence, 1)

    def test_failed_sql_write_cannot_return_receipt(self):
        self.receiver.db.execute("PRAGMA query_only=ON")
        with self.assertRaises(sqlite3.OperationalError):
            self.receiver.accept(CAPTURE, audio().encode())
        self.assertEqual(self.receiver.receipt(CAPTURE).next_sequence, 0)

    def test_reconnect_rechecks_saved_bytes_before_acknowledging(self):
        expected = self.receiver.accept(CAPTURE, audio().encode())
        corrupted = bytearray(audio().encode())
        corrupted[FRAME.size] ^= 1
        with self.receiver.db:
            self.receiver.db.execute("UPDATE packets SET wire=? WHERE identity=?", (bytes(corrupted), CAPTURE.key))
        for operation in (lambda: self.receiver.begin(CAPTURE),
                          lambda: self.receiver.receipt(CAPTURE),
                          lambda: self.receiver.seal(CAPTURE, expected)):
            with self.assertRaisesRegex(ProtocolError, "checksum"):
                operation()

    def test_missing_saved_packet_cannot_be_covered_by_metadata_receipt(self):
        self.receiver.accept(CAPTURE, audio().encode())
        with self.receiver.db:
            self.receiver.db.execute("DELETE FROM packets WHERE identity=?", (CAPTURE.key,))
        with self.assertRaisesRegex(ProtocolError, "does not match"):
            self.receiver.begin(CAPTURE)

    def test_live_corruption_prevents_fresh_and_replayed_ack(self):
        self.receiver.accept(CAPTURE, audio().encode())
        second = audio(1, 320).encode()
        self.receiver.accept(CAPTURE, second)
        # Simulate corruption through a second DB connection while the receiver
        # stays open. Replaying the intact second frame must not ACK corrupt #0.
        corrupted = bytearray(audio().encode())
        corrupted[FRAME.size] ^= 1
        with closing(sqlite3.connect(self.path)) as other, other:
            other.execute("UPDATE packets SET wire=? WHERE identity=? AND sequence=0",
                          (bytes(corrupted), CAPTURE.key))
        for wire in (second, audio(2, 640).encode()):
            with self.subTest(wire=wire), self.assertRaisesRegex(ProtocolError, "checksum"):
                self.receiver.accept(CAPTURE, wire)
        count, = self.receiver.db.execute("SELECT COUNT(*) FROM packets").fetchone()
        self.assertEqual(count, 2)

    def test_live_missing_prefix_prevents_new_ack(self):
        self.receiver.accept(CAPTURE, audio().encode())
        with closing(sqlite3.connect(self.path)) as other, other:
            other.execute("DELETE FROM packets WHERE identity=?", (CAPTURE.key,))
        with self.assertRaisesRegex(ProtocolError, "does not match"):
            self.receiver.accept(CAPTURE, audio(1, 320).encode())
        count, = self.receiver.db.execute("SELECT COUNT(*) FROM packets").fetchone()
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
