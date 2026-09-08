from dataclasses import replace
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zlib

from aura_companion.protocol import ProtocolError
from aura_companion.protocol_v2 import (
    ACK, AUDIO, BOOKMARK, FRAME, MANIFEST, OPUS, PCM16, SEAL,
    OPEN, FINALIZED, INTERRUPTED,
    Capture, DurableReceiver, Packet, Receipt, Seal, read_archive,
)


CAPTURE = Capture(bytes.fromhex("01" * 16), bytes.fromhex("02" * 16), OPUS)


def audio(sequence=0, offset=0, payload=b"\xb8\xff\xfe"):
    # Actual 20 ms CELT silence packet, also present in the C fixture.
    return Packet(sequence, offset, 320, payload)


def termination(receipt, *, source_samples=None, status=FINALIZED):
    source = receipt.sample_count - 40 if source_samples is None else source_samples
    return Seal(receipt.device_id, receipt.capture_id, receipt.next_sequence,
                receipt.sample_count // 320, receipt.encoded_bytes, receipt.sample_count,
                source, source if status == FINALIZED else None, 40,
                receipt.sample_count - 40 - source, receipt.chain_sha256, status)


def checked(data):
    return data + zlib.crc32(data).to_bytes(4, "little")


class FramingTests(unittest.TestCase):
    def test_manifest_round_trip_and_unknown_time(self):
        self.assertEqual(MANIFEST.size, 64)
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
        receipt = Receipt(CAPTURE.device_id, CAPTURE.capture_id, 5, 100, 1600, b"a" * 32, OPEN)
        self.assertEqual(Receipt.parse(receipt.encode()), receipt)
        self.assertEqual(len(receipt.encode()), ACK.size + 4)
        changed = bytearray(receipt.encode())
        changed[5] = 3
        with self.assertRaises(ProtocolError):
            Receipt.parse(checked(changed[:-4]))


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

    def test_temporary_and_memory_databases_cannot_issue_receipts(self):
        for path in ("", ":memory:"):
            with self.subTest(path=path), self.assertRaisesRegex(ProtocolError, "persistent"):
                DurableReceiver(path)

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
            self.receiver.accept(CAPTURE, audio(payload=b"\xb8\x00\x01").encode())
        self.assertEqual(self.receiver.receipt(CAPTURE), expected)
        self.assertEqual(list(self.receiver.packets(CAPTURE)), [audio()])

    def test_gap_offset_future_bookmark_and_pcm_length_fail_closed(self):
        for packet in (audio(1), audio(offset=10), Packet(0, 1, 0, b"", BOOKMARK)):
            with self.subTest(packet=packet), self.assertRaises(ProtocolError):
                self.receiver.accept(CAPTURE, packet.encode())
        pcm = replace(CAPTURE, capture_id=bytes.fromhex("03" * 16), codec=PCM16,
                      pre_skip=0, bitrate=0, codec_profile=0, complexity=0)
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
        final = termination(expected)
        for bad in (replace(final, next_sequence=2), replace(final, encoded_bytes=1),
                    replace(final, encoded_samples=321), replace(final, chain_sha256=b"x" * 32),
                    replace(final, device_id=b"x" * 16)):
            with self.subTest(bad=bad), self.assertRaises(ProtocolError):
                self.receiver.seal(CAPTURE, bad)
        sealed = self.receiver.seal(CAPTURE, final)
        self.assertTrue(sealed.sealed)
        self.assertEqual(self.receiver.seal(CAPTURE, final), sealed)
        self.assertEqual(sealed.chain_sha256, hashlib.sha256(expected.chain_sha256 + final.encode()).digest())
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


FIXTURES = Path(__file__).resolve().parents[2] / "firmware/a04/fixtures"


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.path = self.root / "test.aura"

    def tearDown(self):
        self.directory.cleanup()

    def write(self, data, **options):
        self.path.write_bytes(data)
        return read_archive(self.path, **options)

    def test_real_c_profiles_exact_receipt_source_duration_and_bookmarks(self):
        for ms, records in ((10, 758), (20, 380)):
            with self.subTest(ms=ms):
                path = FIXTURES / f"capture-{ms}ms.aura"
                archive = read_archive(path)
                packets = list(archive.iter_packets())
                self.assertEqual(len(packets), records)
                self.assertEqual([p.sample_offset for p in packets if p.kind == BOOKMARK], [8000, 32000])
                self.assertEqual((archive.source_samples, archive.original_source_samples,
                                  archive.capture.pre_skip, archive.end_trim), (120847, 120847, 40, 73))
                self.assertEqual(archive.receipt, Receipt.parse(path.with_suffix(".receipt").read_bytes()))
                self.assertEqual(archive.sha256_hex, hashlib.sha256(path.read_bytes()).hexdigest())
                with DurableReceiver(self.root / f"{ms}.db") as receiver:
                    self.assertEqual(receiver.import_archive(archive), archive.receipt)
                    self.assertEqual(list(receiver.packets(archive.capture)), packets)
                with DurableReceiver(self.root / f"{ms}.db") as receiver:
                    self.assertEqual(receiver.import_archive(archive), archive.receipt)

    def test_interrupted_and_unsealed_recovery_are_explicit(self):
        for name, record_count in (("capture-20ms-interrupted", 380), ("capture-20ms-open", 379)):
            with self.subTest(name=name):
                path = FIXTURES / (name + ".aura")
                with self.assertRaisesRegex(ProtocolError, "[Ee]xplicit interrupted"):
                    read_archive(path)
                archive = read_archive(path, allow_interrupted=True)
                self.assertEqual(archive.status, "interrupted")
                self.assertEqual((archive.source_samples, archive.original_source_samples, archive.end_trim), (120600, None, 0))
                self.assertEqual(len(list(archive.iter_packets())), record_count)
                c_receipt = Receipt.parse(path.with_suffix(".receipt").read_bytes())
                if archive.seal:
                    self.assertEqual(archive.receipt, c_receipt)
                    bookmarks = [p for p in archive.iter_packets() if p.kind == BOOKMARK]
                    self.assertGreater(bookmarks[-1].sample_offset, archive.source_samples)
                else:
                    self.assertEqual(archive.termination.chain_sha256, c_receipt.chain_sha256)
                    self.assertNotEqual(archive.receipt, c_receipt)
                    self.assertEqual(c_receipt.status, OPEN)

    def test_torn_tail_keeps_only_complete_checked_packets(self):
        archive = read_archive(FIXTURES / "capture-20ms.aura")
        packets = list(archive.iter_packets())
        prefix = archive.capture.encode() + b"".join(p.encode() for p in packets[:-1])
        last = packets[-1].encode()
        for size in (1, 3, 4, 5, 6, 10, FRAME.size - 1, FRAME.size, len(last) - 1):
            with self.subTest(size=size):
                recovered = self.write(prefix + last[:size], allow_interrupted=True)
                self.assertEqual(recovered.discarded_tail_bytes, size)
                self.assertEqual(recovered.receipt.next_sequence, len(packets) - 1)
                self.assertEqual(recovered.source_samples, 120600)
        full_prefix = prefix + last
        for size in (1, 4, 8, SEAL.size + 3):
            recovered = self.write(full_prefix + archive.seal.encode()[:size], allow_interrupted=True)
            self.assertEqual(recovered.discarded_tail_bytes, size)
            self.assertEqual(recovered.source_samples, 120920)
            self.assertIsNone(recovered.original_source_samples)

    def test_complete_corruption_and_impossible_partial_headers_do_not_recover(self):
        prefix = CAPTURE.encode()
        frame = audio().encode()
        corrupt = bytearray(frame)
        corrupt[-1] ^= 1
        for tail in (bytes(corrupt), b"X", b"junk", b"AFR3\x02", b"ASE3\x03\xff",
                     FRAME.pack(b"AFR3", 3, AUDIO, 0, 0, 320, 1276),
                     FRAME.pack(b"AFR3", 3, AUDIO, 9, 0, 320, 3),
                     FRAME.pack(b"AFR3", 3, AUDIO, 0, 1, 320, 3),
                     FRAME.pack(b"AFR3", 3, BOOKMARK, 0, 0, 0, 1)):
            with self.subTest(tail=tail), self.assertRaises(ProtocolError):
                self.write(prefix + tail, allow_interrupted=True)

    def test_full_seal_binds_identity_profile_counts_duration_and_eof(self):
        original = read_archive(FIXTURES / "capture-20ms.aura")
        raw = original.path.read_bytes()
        seal = original.seal
        for item in (replace(seal, device_id=b"z" * 16), replace(seal, capture_id=b"z" * 16),
                     replace(seal, next_sequence=1), replace(seal, audio_packets=1),
                     replace(seal, encoded_bytes=1), replace(seal, encoded_samples=1),
                     replace(seal, source_samples=1), replace(seal, original_source_samples=None),
                     replace(seal, pre_skip=41), replace(seal, end_trim=74),
                     replace(seal, chain_sha256=b"z" * 32), replace(seal, status=INTERRUPTED)):
            with self.subTest(item=item), self.assertRaises(ProtocolError):
                self.write(raw[:-120] + item.encode(), allow_interrupted=True)
        for suffix in (b"x", seal.encode(), CAPTURE.encode()):
            with self.assertRaisesRegex(ProtocolError, "after terminal"):
                self.write(raw + suffix, allow_interrupted=True)

    def test_valid_crc_manifest_still_rejects_unsupported_profile_and_v2(self):
        raw = bytearray(CAPTURE.encode()[:-4])
        for offset, value in ((4, 2), (5, 7), (6, 2), (7, 1), (46, 41), (48, 1), (52, 0), (53, 2), (55, 1)):
            changed = bytearray(raw)
            changed[offset] = value
            with self.subTest(offset=offset), self.assertRaises(ProtocolError):
                Capture.parse(checked(changed))
        for data in (b"AUR2" + bytes(52), b"AOC1" + bytes(64)):
            with self.assertRaises(ProtocolError):
                self.write(data, allow_interrupted=True)

    def test_negotiated_opus_packet_profile_rejects_alternate_modes(self):
        with DurableReceiver(self.root / "profile.db") as receiver:
            receiver.begin(CAPTURE)
            for payload in (b"\xb0\xff\xfe", b"\xbc\xff\xfe", b"\xb9\xff\xfe", b"\x78\xff\xfe", b"\xb8"):
                with self.subTest(payload=payload), self.assertRaises(ProtocolError):
                    receiver.accept(CAPTURE, audio(payload=payload).encode())
            self.assertEqual(receiver.receipt(CAPTURE).next_sequence, 0)

    def test_immutable_terminal_revisions_conflict_in_shared_receiver(self):
        raw = (FIXTURES / "capture-20ms.aura").read_bytes()
        final = self.write(raw)
        prefix_path = self.root / "prefix.aura"
        prefix_path.write_bytes(raw[:-120])
        recovered = read_archive(prefix_path, allow_interrupted=True)
        self.assertNotEqual(final.receipt.chain_sha256, recovered.receipt.chain_sha256)
        with DurableReceiver(self.root / "terminal.db") as receiver:
            receiver.import_archive(recovered)
            with self.assertRaisesRegex(ProtocolError, "Termination conflicts"):
                receiver.import_archive(final)
            self.assertEqual(receiver.receipt(recovered.capture), recovered.receipt)

    def test_changed_file_cannot_publish_or_commit_even_if_new_tail_recovers(self):
        raw = (FIXTURES / "capture-20ms-open.aura").read_bytes()
        archive = self.write(raw, allow_interrupted=True)
        self.path.write_bytes(raw + b"A")
        with self.assertRaisesRegex(ProtocolError, "changed after validation"):
            list(archive.iter_packets())
        with DurableReceiver(self.root / "changed.db") as receiver:
            with self.assertRaisesRegex(ProtocolError, "changed after validation"):
                receiver.import_archive(archive)
            self.assertEqual(receiver.db.execute("SELECT COUNT(*) FROM captures").fetchone()[0], 0)
            self.assertEqual(receiver.db.execute("SELECT COUNT(*) FROM packets").fetchone()[0], 0)

    def test_batch_import_is_linear_with_one_commit_and_rechecks_saved_prefix(self):
        archive = read_archive(FIXTURES / "capture-20ms.aura")
        with DurableReceiver(self.root / "batch.db") as receiver:
            statements = []
            receiver.db.set_trace_callback(statements.append)
            receiver.import_archive(archive)
            self.assertEqual(statements.count("COMMIT"), 1)
            self.assertEqual(sum(sql.startswith("SELECT sequence,wire FROM packets") for sql in statements), 1)
            receiver.db.set_trace_callback(None)
            with receiver.db:
                receiver.db.execute("DELETE FROM packets WHERE sequence=0")
            with self.assertRaises(ProtocolError):
                receiver.import_archive(archive)

    def test_process_exit_inside_batch_leaves_no_partial_capture(self):
        path = self.root / "crash.db"
        code = """
import os, sys
from aura_companion.protocol_v2 import DurableReceiver, read_archive
with DurableReceiver(sys.argv[1]) as receiver:
    archive = read_archive(sys.argv[2])
    receiver.db.set_trace_callback(lambda sql: os._exit(73) if sql.startswith('UPDATE captures SET next_sequence=') else None)
    receiver.import_archive(archive)
os._exit(74)
"""
        run = subprocess.run([sys.executable, "-c", code, str(path), str(FIXTURES / "capture-20ms.aura")],
                             capture_output=True, timeout=20)
        self.assertEqual(run.returncode, 73, run.stderr.decode())
        with DurableReceiver(path) as receiver:
            self.assertEqual(receiver.db.execute("SELECT COUNT(*) FROM captures").fetchone()[0], 0)
            self.assertEqual(receiver.db.execute("SELECT COUNT(*) FROM packets").fetchone()[0], 0)
            archive = read_archive(FIXTURES / "capture-20ms.aura")
            self.assertEqual(receiver.import_archive(archive), archive.receipt)

    def test_payload_limits_are_enforced_before_commit(self):
        path = FIXTURES / "capture-20ms.aura"
        with self.assertRaisesRegex(ProtocolError, "quota"):
            read_archive(path, max_payload_bytes=1)
        with DurableReceiver(self.root / "quota.db", max_capture_bytes=1) as receiver:
            with self.assertRaisesRegex(ProtocolError, "quota"):
                receiver.import_archive(read_archive(path))
            self.assertEqual(receiver.db.execute("SELECT COUNT(*) FROM packets").fetchone()[0], 0)
        for options in ({"max_payload_bytes": 0}, {"allow_interrupted": 1}):
            with self.assertRaises(ProtocolError):
                read_archive(path, **options)

    def test_old_receiver_schema_is_not_a_format_conversion(self):
        path = self.root / "old.db"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE captures (identity TEXT PRIMARY KEY, manifest BLOB, next_sequence INTEGER, encoded_bytes INTEGER, sample_count INTEGER, chain_sha256 BLOB, sealed INTEGER)")
            db.execute("INSERT INTO captures VALUES(?,?,0,0,0,?,0)", (CAPTURE.key, b"AUR2" + bytes(52), bytes(32)))
        with DurableReceiver(path) as receiver:
            with self.assertRaisesRegex(ProtocolError, "different metadata"):
                receiver.begin(CAPTURE)


if __name__ == "__main__":
    unittest.main()
