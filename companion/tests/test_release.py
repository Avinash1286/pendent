"""Actual receiver/outbox transactions. All IDs/keys are public test data."""
from dataclasses import replace
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zlib

from aura_companion import release
from aura_companion.protocol import ProtocolError
from aura_companion.protocol_v2 import (
    Capture, DurableReceiver, Packet, Receipt, Seal, OPUS, OPEN, FINALIZED, INTERRUPTED, read_archive,
)
from aura_companion.release import (
    TrustedReleaseContext, ReleaseOutbox, ReleaseError, RELEASE_PERMISSION,
)

CONTEXT = TrustedReleaseContext(b"\x11" * 16, b"\x33" * 16, b"\x44" * 16,
                                0x0102030405060708, bytes(range(1, 33)))
CAPTURE_ID = b"\x22" * 16
OTHER_ID = b"\x23" * 16
FAILURES = (ProtocolError, sqlite3.Error, OSError, ValueError)


def committed_source(path, capture_id=CAPTURE_ID, status=FINALIZED, device_id=CONTEXT.device_id):
    capture = Capture(device_id, capture_id, OPUS)
    packet = Packet(0, 0, 320, b"\xb8\xff\xfe")
    with DurableReceiver(path) as receiver:
        receiver.begin(capture)
        prefix = receiver.accept(capture, packet.encode())
        if status == OPEN:
            return capture, prefix, None
        seal = Seal(device_id, capture_id, 1, 1, 3, 320, 280,
                    280 if status == FINALIZED else None, 40, 0, prefix.chain_sha256, status)
        receipt = receiver.seal(capture, seal)
    return capture, receipt, seal


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "receiver.sqlite"
        self.path = self.root / "outbox.sqlite"
        self.capture, self.receipt, self.seal = committed_source(self.source)
        self.outbox = ReleaseOutbox.provision(self.path, CONTEXT, initial_sequence_floor=8)

    def tearDown(self):
        self.temporary.cleanup()

    def request(self, request_id="request_1", *, source=None, capture_id=CAPTURE_ID):
        return self.outbox.request_release(request_id, source or self.source, capture_id,
                                          permission=RELEASE_PERMISSION)

    def completed(self, request_id="request_1"):
        wire = self.request(request_id)
        self.outbox.mark_completed(request_id, envelope=wire, receipt=self.receipt.encode())
        return wire

    def test_exact_rls1_and_independent_standard_library_mac(self):
        wire = self.request()
        self.assertEqual(len(wire), 182)
        self.assertEqual(wire[:8], b"RLS1\x01\x01\x01\0")
        self.assertEqual(wire[8:24], CONTEXT.storage_incarnation)
        self.assertEqual(wire[24:40], CONTEXT.owner_id)
        self.assertEqual(struct.unpack_from("<QQ", wire, 40), (CONTEXT.owner_generation, 9))
        self.assertEqual(wire[56:150], self.receipt.encode())
        self.assertEqual(wire[150:], hmac.digest(CONTEXT.key,
                         b"AURA-A04-OWNER-RELEASE-v1\0" + wire[:150], "sha256"))
        self.assertNotEqual(wire[150:], hmac.digest(CONTEXT.key,
                            b"AURA-A04-OWNER-RELEASE-v1" + wire[:150], "sha256"))

    def test_firmware_golden_rls1_interoperability(self):
        # Exact output of production C host_release_auth.c roundtrip, publicly fixed.
        ack = Receipt(CONTEXT.device_id, CAPTURE_ID, 7, 80, 320, bytes(range(0x60, 0x80)), FINALIZED)
        expected = bytes.fromhex(
            "524c5331010101003333333333333333333333333333333344444444444444444444444444444444"
            "0807060504030201090000000000000041434b33030111111111111111111111111111111111"
            "222222222222222222222222222222220700000050000000000000004001000000000000"
            "606162636465666768696a6b6c6d6e6f707172737475767778797a7b7c7d7e7f596cf06e"
            "20e36d1ca8f4d5cd74649390c99cbebffd49bdcce5d03ca664ecf00186b43c23")
        self.assertEqual(release._envelope(CONTEXT, 9, ack.encode()), expected)

    def test_permission_is_required_and_exact(self):
        with self.assertRaises(TypeError):
            self.outbox.request_release("r", self.source, CAPTURE_ID)
        for permission in (None, True, "", "authenticated", "release", RELEASE_PERMISSION + " "):
            with self.subTest(permission=permission), self.assertRaises(ReleaseError):
                self.outbox.request_release("r", self.source, CAPTURE_ID, permission=permission)
        self.assertIsNone(self.outbox.pending())

    def test_request_id_exact_retry_survives_reopen(self):
        wire = self.request()
        self.outbox = ReleaseOutbox(self.path, CONTEXT)
        self.assertEqual(self.request(), wire)
        self.assertEqual(self.outbox.retry("request_1"), wire)
        pending = self.outbox.pending()
        self.assertEqual((pending.request_id, pending.sequence, pending.envelope), ("request_1", 9, wire))
        self.assertEqual(pending.receipt, self.receipt.encode())

    def test_request_id_source_and_capture_conflicts(self):
        self.request()
        copied = self.root / "copy.sqlite"; shutil.copyfile(self.source, copied)
        with self.assertRaises(ReleaseError):
            self.request(source=copied)
        committed_source(self.source, OTHER_ID)
        with self.assertRaises(ReleaseError):
            self.request(capture_id=OTHER_ID)

    def test_one_pending_request_then_monotonic_next_sequence(self):
        wire = self.request()
        _, other_receipt, _ = committed_source(self.source, OTHER_ID)
        with self.assertRaises(ReleaseError):
            self.request("second", capture_id=OTHER_ID)
        self.outbox.mark_completed("request_1", envelope=wire, receipt=self.receipt.encode())
        second = self.request("second", capture_id=OTHER_ID)
        self.assertEqual(int.from_bytes(second[48:56], "little"), 10)
        self.assertEqual(second[56:150], other_receipt.encode())

    def test_completion_is_exact_idempotent_local_bookkeeping(self):
        wire = self.request()
        with self.assertRaises(ReleaseError):
            self.outbox.mark_completed("request_1", envelope=wire[:-1] + bytes([wire[-1] ^ 1]),
                                       receipt=self.receipt.encode())
        with self.assertRaises(ReleaseError):
            self.outbox.mark_completed("request_1", envelope=wire, receipt=bytes(94))
        with self.assertRaises(TypeError):
            self.outbox.mark_completed("request_1", envelope=wire)
        for _ in range(2):
            self.outbox.mark_completed("request_1", envelope=wire, receipt=self.receipt.encode())
        self.assertIsNone(self.outbox.pending())
        self.assertEqual(self.outbox.retry("request_1"), wire)

    def test_completed_capture_cannot_allocate_a_second_request(self):
        wire = self.completed()
        with self.assertRaises(ReleaseError):
            self.request("different_id")
        self.assertEqual(self.request(), wire)

    def test_unknown_requests_and_invalid_request_identifiers(self):
        for request_id in ("", "has spaces", "x" * 129, "../bad", 1, None):
            with self.subTest(request_id=request_id), self.assertRaises(ReleaseError):
                self.request(request_id)
        with self.assertRaises(ReleaseError):
            self.outbox.retry("unknown")
        with self.assertRaises(ReleaseError):
            self.outbox.mark_completed("unknown", envelope=bytes(182), receipt=bytes(94))

    def test_missing_or_memory_source_is_not_created(self):
        missing = self.root / "missing.sqlite"
        for source in (missing, "", ":memory:"):
            with self.subTest(source=source), self.assertRaises(FAILURES):
                self.outbox.request_release("r", source, CAPTURE_ID, permission=RELEASE_PERMISSION)
        self.assertFalse(missing.exists())
        self.assertIsNone(self.outbox.pending())

    def test_empty_non_sqlite_and_missing_schema_sources_refused(self):
        for number, data in enumerate((b"", b"not SQLite")):
            path = self.root / f"bad{number}.sqlite"; path.write_bytes(data)
            with self.assertRaises(FAILURES):
                self.request(source=path)
        path = self.root / "schema.sqlite"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE unrelated (v INTEGER)")
        with self.assertRaises(FAILURES):
            self.request(source=path)
        self.assertIsNone(self.outbox.pending())

    def test_open_and_physically_unproven_interrupted_receipts_refused(self):
        for status in (OPEN, INTERRUPTED):
            path = self.root / f"status{status}.sqlite"; committed_source(path, status=status)
            with self.subTest(status=status), self.assertRaises(ReleaseError):
                self.request(source=path)
        self.assertIsNone(self.outbox.pending())

    def test_synthesized_interrupted_archive_import_refused(self):
        raw = self.root / "open.aura"
        raw.write_bytes(self.capture.encode() + Packet(0, 0, 320, b"\xb8\xff\xfe").encode())
        archive = read_archive(raw, allow_interrupted=True)
        self.assertIsNone(archive.seal)
        receiver_path = self.root / "recovered.sqlite"
        with DurableReceiver(receiver_path) as receiver:
            receiver.import_archive(archive)
        with self.assertRaises(ReleaseError):
            self.request(source=receiver_path)

    def test_corrupt_packet_missing_packet_or_terminal_metadata_refused(self):
        for index, statement in enumerate(("DELETE FROM packets", "UPDATE packets SET wire=zeroblob(29)",
                                            "UPDATE captures SET seal_wire=NULL", "UPDATE captures SET sample_count=999")):
            path = self.root / f"corrupt{index}.sqlite"; shutil.copyfile(self.source, path)
            with closing(sqlite3.connect(path)) as db, db:
                db.execute(statement)
            with self.subTest(statement=statement), self.assertRaises(FAILURES):
                self.request(source=path)

    def test_changed_source_denies_pending_retry_and_duplicate_request(self):
        self.request()
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute("DELETE FROM packets")
        for method in (self.outbox.pending, lambda: self.outbox.retry("request_1"), self.request):
            with self.assertRaises(FAILURES):
                method()

    def test_wrong_device_and_capture_refused(self):
        other = self.root / "foreign.sqlite"; committed_source(other, device_id=b"\x77" * 16)
        with self.assertRaises(ReleaseError):
            self.request(source=other)
        with self.assertRaises(ReleaseError):
            self.request(capture_id=OTHER_ID)

    def test_readonly_source_allowed_and_unchanged(self):
        before = self.source.read_bytes()
        self.source.chmod(stat.S_IREAD)
        try:
            self.assertEqual(len(self.request()), 182)
            self.assertEqual(self.source.read_bytes(), before)
        finally:
            self.source.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_nonwritable_outbox_cannot_allocate(self):
        original = release._connect
        def readonly_outbox(path, *, readonly):
            return original(path, readonly=readonly or path == self.path)
        with patch.object(release, "_connect", side_effect=readonly_outbox):
            with self.assertRaises(sqlite3.OperationalError):
                self.request()
        self.assertIsNone(self.outbox.pending())
        self.assertEqual(int.from_bytes(self.request()[48:56], "little"), 9)

    def test_missing_outbox_never_creates_or_resets_authority(self):
        missing = self.root / "missing-outbox.sqlite"
        with self.assertRaises(FAILURES):
            ReleaseOutbox(missing, CONTEXT)
        self.assertFalse(missing.exists())
        with self.assertRaises(TypeError):
            ReleaseOutbox.provision(missing, CONTEXT)
        with self.assertRaises(FileExistsError):
            ReleaseOutbox.provision(self.path, CONTEXT, initial_sequence_floor=0)

    def test_invalid_context_and_rekey_never_reset_floor(self):
        self.request()
        for context in (replace(CONTEXT, device_id=b"\x12" * 16),
                        replace(CONTEXT, storage_incarnation=b"\x34" * 16),
                        replace(CONTEXT, owner_id=b"\x45" * 16),
                        replace(CONTEXT, owner_generation=CONTEXT.owner_generation + 1),
                        replace(CONTEXT, key=b"\xaa" * 32)):
            with self.subTest(context=context), self.assertRaises(ReleaseError):
                ReleaseOutbox(self.path, context)
        self.assertEqual(ReleaseOutbox(self.path, CONTEXT).pending().sequence, 9)

    def test_zero_or_nonbytes_keys_and_ids_refused(self):
        for field, value in (("key", bytes(32)), ("key", b"x"), ("key", bytearray(32)),
                             ("device_id", bytes(16)), ("storage_incarnation", b""),
                             ("owner_id", bytes(16)), ("owner_generation", 0), ("owner_generation", True)):
            with self.subTest(field=field), self.assertRaises(ReleaseError):
                replace(CONTEXT, **{field: value})
        self.assertNotIn("key=", repr(CONTEXT))

    def test_no_plaintext_key_is_persisted(self):
        self.request()
        for path in self.root.iterdir():
            if path.is_file():
                self.assertNotIn(CONTEXT.key, path.read_bytes())

    def test_corrupt_authority_floor_or_tag_fails_closed(self):
        self.request()
        for variant in ("floor", "tag", "delete"):
            target = self.root / f"authority-{variant}.sqlite"; shutil.copyfile(self.path, target)
            with closing(sqlite3.connect(target)) as db, db:
                if variant == "floor":
                    body = json.loads(db.execute("SELECT body FROM authority").fetchone()[0]); body["floor"] = 0
                    db.execute("UPDATE authority SET body=?", (release._canonical(body),))
                elif variant == "tag":
                    db.execute("UPDATE authority SET tag=zeroblob(32)")
                else:
                    db.execute("DELETE FROM authority")
            with self.subTest(variant=variant), self.assertRaises(FAILURES):
                ReleaseOutbox(target, CONTEXT)

    def test_request_permission_source_envelope_and_history_tampering_refused(self):
        self.request()
        for variant in ("permission", "receiver_db", "envelope", "delete", "sequence"):
            target = self.root / f"request-{variant}.sqlite"; shutil.copyfile(self.path, target)
            with closing(sqlite3.connect(target)) as db, db:
                if variant == "delete":
                    db.execute("DELETE FROM requests")
                elif variant == "sequence":
                    db.execute("UPDATE requests SET sequence=zeroblob(8)")
                else:
                    body = json.loads(db.execute("SELECT body FROM requests").fetchone()[0])
                    body[variant] = "tampered"
                    db.execute("UPDATE requests SET body=?", (release._canonical(body),))
            with self.subTest(variant=variant), self.assertRaises(FAILURES):
                ReleaseOutbox(target, CONTEXT)

    def test_uint64_floor_without_sqlite_signed_overflow(self):
        path = self.root / "high.sqlite"
        high = ReleaseOutbox.provision(path, CONTEXT, initial_sequence_floor=(1 << 64) - 2)
        wire = high.request_release("last", self.source, CAPTURE_ID, permission=RELEASE_PERMISSION)
        self.assertEqual(int.from_bytes(wire[48:56], "little"), (1 << 64) - 1)
        high.mark_completed("last", envelope=wire, receipt=self.receipt.encode())
        committed_source(self.source, OTHER_ID)
        with self.assertRaises(ReleaseError):
            high.request_release("beyond", self.source, OTHER_ID, permission=RELEASE_PERMISSION)

    def test_mutation_failure_rolls_back_request_and_floor_together(self):
        with patch.object(ReleaseOutbox, "_save_state", side_effect=sqlite3.OperationalError("injected")):
            with self.assertRaises(sqlite3.OperationalError):
                self.request()
        self.assertIsNone(ReleaseOutbox(self.path, CONTEXT).pending())
        self.assertEqual(int.from_bytes(self.request()[48:56], "little"), 9)

    def test_source_remains_committed_when_outbox_commit_fails(self):
        with patch.object(release, "_commit", side_effect=sqlite3.OperationalError("injected commit")):
            with self.assertRaises(sqlite3.OperationalError):
                self.request()
        with DurableReceiver(self.source) as receiver:
            self.assertEqual(receiver.receipt(self.capture), self.receipt)
        self.assertIsNone(self.outbox.pending())

    def test_commit_succeeded_but_reply_lost_retries_exact_bytes(self):
        original = release._commit
        def lost_reply(db):
            original(db)
            raise sqlite3.OperationalError("injected lost commit reply")
        with patch.object(release, "_commit", side_effect=lost_reply):
            with self.assertRaises(sqlite3.OperationalError):
                self.request()
        reopened = ReleaseOutbox(self.path, CONTEXT)
        wire = reopened.retry("request_1")
        self.assertEqual(self.request(), wire)
        self.assertEqual(int.from_bytes(wire[48:56], "little"), 9)

    def test_real_process_exit_before_and_after_sqlite_commit(self):
        code = r'''
import os, sys
from aura_companion import release
c = release.TrustedReleaseContext(b"\x11"*16,b"\x33"*16,b"\x44"*16,
                                  0x0102030405060708,bytes(range(1,33)))
outbox = release.ReleaseOutbox(sys.argv[1],c)
original = release._commit
def cut(db):
    if sys.argv[3] == "before": os._exit(71)
    original(db)
    os._exit(72)
release._commit = cut
outbox.request_release("crash",sys.argv[2],b"\x22"*16,permission=release.RELEASE_PERMISSION)
'''
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(release.__file__).resolve().parents[1])
        for stage, expected_code in (("before", 71), ("after", 72)):
            path = self.root / f"crash-{stage}.sqlite"
            ReleaseOutbox.provision(path, CONTEXT, initial_sequence_floor=8)
            result = subprocess.run([sys.executable, "-c", code, str(path), str(self.source), stage],
                                    env=environment, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, expected_code, result.stderr)
            reopened = ReleaseOutbox(path, CONTEXT)
            if stage == "before":
                self.assertIsNone(reopened.pending())
            else:
                self.assertEqual(reopened.pending().sequence, 9)
            wire = reopened.request_release("crash", self.source, CAPTURE_ID, permission=RELEASE_PERMISSION)
            self.assertEqual(int.from_bytes(wire[48:56], "little"), 9)

    def test_source_delete_journal_read_lock_covers_outbox_commit(self):
        original = release._commit
        blocked = []
        def observe(db):
            writer = sqlite3.connect(self.source, timeout=0)
            try:
                writer.execute("UPDATE captures SET sample_count=999")
                with self.assertRaises(sqlite3.OperationalError):
                    writer.commit()
                blocked.append(True)
            finally:
                writer.close()
            original(db)
        with patch.object(release, "_commit", side_effect=observe):
            self.request()
        self.assertEqual(blocked, [True])
        with DurableReceiver(self.source) as receiver:
            self.assertEqual(receiver.receipt(self.capture), self.receipt)

    def test_source_uncommitted_changes_never_become_receipt(self):
        writer = sqlite3.connect(self.source)
        try:
            writer.execute("UPDATE captures SET sample_count=999")
            wire = self.request()
            self.assertEqual(wire[56:150], self.receipt.encode())
        finally:
            writer.close()

    def test_concurrent_same_request_commits_one_sequence_and_exact_retry(self):
        second = ReleaseOutbox(self.path, CONTEXT)
        barrier = threading.Barrier(2)
        original = release._ExistingReceiver.terminal

        def both_sources_verified(receiver, device_id, capture_id):
            result = original(receiver, device_id, capture_id)
            barrier.wait(timeout=10)
            return result

        def request(outbox):
            return outbox.request_release("same", self.source, CAPTURE_ID,
                                          permission=RELEASE_PERMISSION)

        with patch.object(release._ExistingReceiver, "terminal", both_sources_verified):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(request, outbox) for outbox in (self.outbox, second)]
                wires = [future.result(timeout=20) for future in futures]
        self.assertEqual(wires[0], wires[1])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM requests").fetchone(), (1,))
        self.assertEqual(ReleaseOutbox(self.path, CONTEXT).pending().sequence, 9)

    def test_concurrent_different_requests_cannot_allocate_a_second_pending(self):
        committed_source(self.source, OTHER_ID)
        second = ReleaseOutbox(self.path, CONTEXT)
        barrier = threading.Barrier(2)
        original = release._ExistingReceiver.terminal

        def both_sources_verified(receiver, device_id, capture_id):
            result = original(receiver, device_id, capture_id)
            barrier.wait(timeout=10)
            return result

        def request(outbox, request_id, capture_id):
            try:
                return outbox.request_release(request_id, self.source, capture_id,
                                              permission=RELEASE_PERMISSION)
            except ReleaseError as error:
                return error

        with patch.object(release._ExistingReceiver, "terminal", both_sources_verified):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(request, self.outbox, "first", CAPTURE_ID),
                           pool.submit(request, second, "second", OTHER_ID)]
                results = [future.result(timeout=20) for future in futures]
        self.assertEqual(sum(type(result) is bytes for result in results), 1)
        self.assertEqual(sum(isinstance(result, ReleaseError) for result in results), 1)
        pending = ReleaseOutbox(self.path, CONTEXT).pending()
        self.assertEqual(pending.sequence, 9)
        self.assertIn(pending.envelope, results)

    def test_completion_failure_keeps_pending_sequence_and_source(self):
        wire = self.request()
        committed_source(self.source, OTHER_ID)
        with patch.object(ReleaseOutbox, "_save_state", side_effect=sqlite3.OperationalError("injected")):
            with self.assertRaises(sqlite3.OperationalError):
                self.outbox.mark_completed("request_1", envelope=wire, receipt=self.receipt.encode())
        self.outbox = ReleaseOutbox(self.path, CONTEXT)
        self.assertEqual(self.outbox.pending().envelope, wire)
        with self.assertRaises(ReleaseError):
            self.request("second", capture_id=OTHER_ID)
        self.outbox.mark_completed("request_1", envelope=wire, receipt=self.receipt.encode())
        self.assertEqual(int.from_bytes(self.request("second", capture_id=OTHER_ID)[48:56], "little"), 10)
        with DurableReceiver(self.source) as receiver:
            self.assertEqual(receiver.receipt(self.capture), self.receipt)

    def test_completion_commit_lost_reply_reopens_completed_exact_history(self):
        wire = self.request()
        original = release._commit

        def lost_reply(db):
            original(db)
            raise sqlite3.OperationalError("injected lost completion reply")

        with patch.object(release, "_commit", side_effect=lost_reply):
            with self.assertRaises(sqlite3.OperationalError):
                self.outbox.mark_completed("request_1", envelope=wire, receipt=self.receipt.encode())
        self.outbox = ReleaseOutbox(self.path, CONTEXT)
        self.assertIsNone(self.outbox.pending())
        self.assertEqual(self.outbox.retry("request_1"), wire)
        self.outbox.mark_completed("request_1", envelope=wire, receipt=self.receipt.encode())
        committed_source(self.source, OTHER_ID)
        self.assertEqual(int.from_bytes(self.request("second", capture_id=OTHER_ID)[48:56], "little"), 10)

    def test_wal_source_and_outbox_refused_without_changing_journal_mode(self):
        with closing(sqlite3.connect(self.source)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
        with self.assertRaises(ReleaseError):
            self.request()
        with closing(sqlite3.connect(self.source)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone(), ("wal",))
        self.assertIsNone(self.outbox.pending())
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
        with self.assertRaises(ReleaseError):
            ReleaseOutbox(self.path, CONTEXT)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone(), ("wal",))


if __name__ == "__main__":
    unittest.main()
