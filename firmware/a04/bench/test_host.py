"""Deterministic UART/failure/publication tests; these do not connect hardware."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zlib

import host
from aura_companion.protocol import ProtocolError
from aura_companion.protocol_v2 import DurableReceiver, Receipt, OPEN, FINALIZED, INTERRUPTED, read_archive

FIXTURES = host.ROOT / "firmware/a04/fixtures"
FINAL = FIXTURES / "journal-0.aura"
FINAL_RECEIPT = (FIXTURES / "journal-0.receipt").read_bytes()
CAPTURE = read_archive(FINAL).capture
CONTEXT = host.TrustedReleaseContext(CAPTURE.device_id, b"i" * 16, b"o" * 16, 1, b"k" * 32)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class UART:
    """A bounded byte transport with replies generated from actual request IDs."""
    def __init__(self, reply):
        self.reply, self.buffer, self.writes = reply, bytearray(), []
        self.short_write = False

    def write(self, wire):
        self.writes.append(wire)
        fields = wire.decode().strip().split(" ")
        self.buffer.extend(self.reply(fields[1], fields[2], fields[3:]))
        return len(wire) - int(self.short_write)

    def read(self, count):
        result = bytes(self.buffer[:count])
        del self.buffer[:count]
        return result

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def line(rid, body):
    return f"A04B {rid} {body}\n".encode()


def export_lines(rid, data, receipt):
    result = []
    for offset in range(0, len(data), 128):
        block = data[offset:offset + 128]
        result.append(line(rid, f"DATA {offset:016x} {block.hex()} {zlib.crc32(block):08x}"))
    result.append(line(rid, f"END EXPORT {len(data):016x} {receipt.hex()}"))
    return result


def transport(data=None, receipt=FINAL_RECEIPT, alter=None, extra=None):
    data = FINAL.read_bytes() if data is None else data
    def reply(rid, verb, args):
        if extra:
            result = extra(rid, verb, args)
            if result is not None:
                return result
        if verb == "INFO":
            return b"boot: developer bench\n" + line(rid, f"OK INFO {CAPTURE.device_id.hex()} 0 0 0 0 1022")
        if verb in ("OPEN", "PROVISION"):
            return line(rid, f"OK {verb}")
        if verb == "LIST":
            return line(rid, f"ITEM {CAPTURE.encode().hex()} 2 1") + line(rid, "END LIST 1")
        if verb == "START":
            return line(rid, f"OK START {CAPTURE.capture_id.hex()}")
        if verb == "STOP":
            return line(rid, f"OK STOP 4 0 {CAPTURE.capture_id.hex()}")
        if verb == "STATS":
            return line(rid, "OK STATS 12000 0 3 1024 2048 9 8 7 100 200 0 1")
        if verb == "EXPORT":
            replies = export_lines(rid, data, receipt)
            return b"".join(alter(replies, rid) if alter else replies)
        raise AssertionError("Unexpected host verb")
    return UART(reply)


def client(uart=None, **kwargs):
    timer = Clock()
    ids = iter(f"{n:08x}" for n in range(1, 1000))
    result = host.Client(uart or transport(), CAPTURE.device_id, timeout=1, idle_timeout=0.5,
                         clock=timer, sleep=timer.sleep, rid_source=lambda: next(ids), **kwargs)
    result.info()
    result.enroll(CONTEXT)
    return result


class ProtocolTests(unittest.TestCase):
    def test_public_info_discovery_cannot_authorize_context(self):
        uart = transport()
        c = host.Client(uart)
        self.assertEqual(c.info().device_id, CAPTURE.device_id)
        self.assertFalse(c.verified)
        with self.assertRaises(host.BenchError):
            c.enroll(CONTEXT, provision=True)
        self.assertEqual(len(uart.writes), 1)

    def test_session_verifies_id_then_opens_exact_context(self):
        uart = transport()
        c = client(uart)
        self.assertTrue(c.opened)
        self.assertEqual(uart.writes[1].split()[3], host.context_wire(CONTEXT).hex().encode())
        self.assertTrue(all(len(w) <= 256 for w in uart.writes))
        self.assertEqual(len({w.split()[1] for w in uart.writes}), 2)

    def test_wrong_identity_prevents_enrollment(self):
        uart = transport(extra=lambda rid, verb, args: line(rid, f"OK INFO {'ab' * 16} 0 0 0 0 1"))
        c = host.Client(uart, CAPTURE.device_id)
        with self.assertRaises(host.BenchError):
            c.info()
        with self.assertRaises(host.BenchError):
            c.enroll(CONTEXT)
        self.assertEqual(len(uart.writes), 1)

    def test_stale_request_id_rejected_and_session_locked(self):
        c = client()
        c.serial.reply = lambda *_: line("eeeeeeee", "END LIST 0")
        with self.assertRaises(host.BenchError):
            c.catalog()
        writes = len(c.serial.writes)
        with self.assertRaises(host.BenchError):
            c.info()
        self.assertEqual(len(c.serial.writes), writes)

    def test_reused_request_id_is_not_transmitted(self):
        uart = transport()
        c = host.Client(uart, CAPTURE.device_id, rid_source=lambda: "00000001")
        c.info()
        with self.assertRaises(host.BenchError):
            c.enroll(CONTEXT)
        self.assertEqual(len(uart.writes), 1)

    def test_timeout_and_partial_line_do_not_succeed(self):
        for reply in (b"", b"A04B 00000003 END LIST 0"):
            with self.subTest(reply=reply):
                c = client()
                c.serial.reply = lambda *_: reply
                with self.assertRaisesRegex(host.BenchError, "timed out"):
                    c.catalog()
                self.assertTrue(c.broken)

    def test_line_noise_and_non_ascii_bounds(self):
        for reply in (b"x" * 513, b"noise\n" * 65, b"A04B 00000003 \xff\n",
                      b"A04B 00000003  END LIST 0\n", b"A04B BAD END LIST 0\n"):
            with self.subTest(size=len(reply)):
                c = client()
                c.serial.reply = lambda *_: reply
                with self.assertRaises(host.BenchError):
                    c.catalog()

    def test_short_write_and_secret_bearing_transport_error_sanitized(self):
        c = client()
        c.serial.short_write = True
        with self.assertRaises(host.BenchError):
            c.catalog()
        c = client()
        c.serial.write = lambda _: (_ for _ in ()).throw(OSError(CONTEXT.key.hex()))
        with self.assertRaises(host.BenchError) as error:
            c.catalog()
        self.assertNotIn(CONTEXT.key.hex(), str(error.exception))

    def test_device_error_is_numeric_and_no_arguments_echoed(self):
        c = client()
        c.serial.reply = lambda rid, *_: line(rid, "ERROR -402")
        with self.assertRaisesRegex(host.BenchError, "-402"):
            c.catalog()
        c = client()
        c.serial.reply = lambda rid, *_: line(rid, "ERROR " + CONTEXT.key.hex())
        with self.assertRaises(host.BenchError) as error:
            c.catalog()
        self.assertNotIn(CONTEXT.key.hex(), str(error.exception))

    def test_catalog_count_duplicates_and_foreign_ids(self):
        self.assertEqual(client().catalog(), [(CAPTURE, 2, 1)])
        variants = [f"ITEM {CAPTURE.encode().hex()} 2 1\nEND LIST 0",
                    f"ITEM {CAPTURE.encode().hex()} 2 1\nITEM {CAPTURE.encode().hex()} 2 1\nEND LIST 2",
                    f"ITEM {replace(CAPTURE, device_id=b'z' * 16).encode().hex()} 2 1\nEND LIST 1",
                    f"ITEM {CAPTURE.encode().hex()} 5 1\nEND LIST 1"]
        for body in variants:
            c = client()
            c.serial.reply = lambda rid, *_, body=body: b"".join(line(rid, b) for b in body.split("\n"))
            with self.assertRaises(host.BenchError):
                c.catalog()

    def test_record_and_stats_are_status_not_host_acknowledgement(self):
        c = client()
        result = c.record(1)
        self.assertEqual(result["capture_id"], CAPTURE.capture_id.hex())
        self.assertFalse(result["host_receipt"])
        self.assertEqual(c.stats()["service_max_us"], 12000)
        self.assertEqual(c.stats()["clip_second"], 1)

    def test_record_limits_and_mismatched_stop(self):
        for seconds in (0, 0.9, 61, float("inf"), float("nan")):
            c = client()
            with self.assertRaises(host.BenchError):
                c.record(seconds)
            self.assertEqual(len(c.serial.writes), 2)
        c = client(transport(extra=lambda rid, verb, args: line(rid, f"OK STOP 4 0 {'cc' * 16}") if verb == "STOP" else None))
        with self.assertRaises(host.BenchError):
            c.record(1)

    def test_ctrl_c_after_start_sends_exactly_one_stop(self):
        c = client()
        c.sleep = lambda _: (_ for _ in ()).throw(KeyboardInterrupt())
        result = c.record()
        self.assertTrue(result["user_stopped"])
        self.assertEqual([wire.split()[2] for wire in c.serial.writes], [b"INFO", b"OPEN", b"START", b"STOP"])

    def test_export_total_deadline_is_not_extended_by_valid_chunks(self):
        c = client(export_timeout=0.05)
        original = c.serial.read
        def slow(count):
            c.clock.now += 0.001
            return original(count)
        c.serial.read = slow
        with self.assertRaisesRegex(host.BenchError, "timed out"):
            c.download(CAPTURE.capture_id, io.BytesIO())

    def test_exact_real_c_export_bytes_and_ack(self):
        stream = io.BytesIO()
        receipt, count = client().download(CAPTURE.capture_id, stream)
        self.assertEqual(stream.getvalue(), FINAL.read_bytes())
        self.assertEqual(count, FINAL.stat().st_size)
        self.assertEqual(receipt.encode(), FINAL_RECEIPT)

    def test_export_crc_order_missing_end_and_bounds(self):
        def changes(which):
            def change(lines, rid):
                if which == "crc":
                    parts = lines[0].decode().split()
                    parts[-1] = "00000000"
                    lines[0] = (" ".join(parts) + "\n").encode()
                elif which == "gap":
                    lines = lines[1:]
                elif which == "duplicate":
                    lines.insert(1, lines[0])
                elif which == "noend":
                    lines.pop()
                elif which == "length":
                    lines[-1] = line(rid, f"END EXPORT {1:016x} {FINAL_RECEIPT.hex()}")
                elif which == "foreign":
                    receipt = replace(Receipt.parse(FINAL_RECEIPT), capture_id=b"f" * 16)
                    lines[-1] = line(rid, f"END EXPORT {FINAL.stat().st_size:016x} {receipt.encode().hex()}")
                elif which == "payload":
                    lines[0] = line(rid, f"DATA {0:016x} {'ff' * 129} 00000000")
                return lines
            return change
        for which in ("crc", "gap", "duplicate", "noend", "length", "foreign", "payload"):
            with self.subTest(which=which), self.assertRaises((host.BenchError, ProtocolError)):
                client(transport(alter=changes(which))).download(CAPTURE.capture_id, io.BytesIO())
        with self.assertRaisesRegex(host.BenchError, "configured bound"):
            client(max_export=128).download(CAPTURE.capture_id, io.BytesIO())

    def test_physical_open_is_verified_against_pre_seal_prefix(self):
        archive = read_archive(FIXTURES / "journal-2.aura", allow_interrupted=True)
        physical = Receipt.parse((FIXTURES / "journal-2.receipt").read_bytes())
        self.assertEqual(physical.status, OPEN)
        self.assertEqual(archive.termination.status, INTERRUPTED)
        host.verify_physical_receipt(archive, physical)
        self.assertNotEqual(physical, archive.receipt)
        with self.assertRaises(host.BenchError):
            host.verify_physical_receipt(archive, replace(physical, chain_sha256=b"x" * 32))
        with self.assertRaises(host.BenchError):
            host.verify_physical_receipt(read_archive(FINAL), replace(Receipt.parse(FINAL_RECEIPT), status=OPEN))

    def test_physically_sealed_interrupted_and_torn_export(self):
        archive = read_archive(FIXTURES / "journal-1.aura", allow_interrupted=True)
        physical = Receipt.parse((FIXTURES / "journal-1.receipt").read_bytes())
        host.verify_physical_receipt(archive, physical)
        # A raw unsealed .aura is recoverable by the general reader but not a
        # successful UART export, which must include its explicit derived seal.
        torn = read_archive(FIXTURES / "capture-20ms-open.aura", allow_interrupted=True)
        with self.assertRaises(host.BenchError):
            host.verify_physical_receipt(torn, physical)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        (host.ROOT / ".scratch").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="bench-host-test-", dir=host.ROOT / ".scratch")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_context_exact_restart_private_no_overwrite(self):
        path = self.root / "context.bin"
        context = host.save_new_context(path, CAPTURE.device_id)
        self.assertEqual(host.load_context(path), context)
        self.assertEqual(path.stat().st_size, 88)
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            host.save_new_context(path, CAPTURE.device_id)
        self.assertEqual(path.read_bytes(), before)
        next_context = host.save_new_context(self.root / "other.bin", CAPTURE.device_id)
        self.assertNotEqual(context.key, next_context.key)
        self.assertNotEqual(context.storage_incarnation, next_context.storage_incarnation)

    def test_context_corrupt_oversized_nonprivate_repository_refused(self):
        for data in (b"", bytes(88), b"x" * 89):
            path = self.root / f"context-{len(data)}.bin"
            path.write_bytes(data)
            os.chmod(path, 0o600)
            with self.assertRaises(host.BenchError):
                host.load_context(path)
        with self.assertRaises(host.BenchError):
            host.private_path(host.ROOT / "enrollment-secret.bin")

    def test_context_fsync_failure_sends_no_provision_and_retains_file(self):
        path = self.root / "context.bin"
        uart, err = transport(), io.StringIO()
        fake_serial = types.SimpleNamespace(Serial=lambda *a, **k: uart)
        with patch.dict(sys.modules, serial=fake_serial), patch.object(host.os, "fsync", side_effect=OSError("flush")), redirect_stderr(err):
            code = host.main(["--port", "TEST", "--device-id", CAPTURE.device_id.hex(), "--context", str(path), "provision"])
        self.assertEqual(code, 1)
        self.assertTrue(path.exists())
        self.assertEqual([wire.split()[2] for wire in uart.writes], [b"INFO"])
        self.assertNotIn(path.read_bytes().hex(), err.getvalue())

    def test_explicit_resume_reuses_exact_saved_authority_after_restart(self):
        path = self.root / "context.bin"
        context = host.save_new_context(path, CAPTURE.device_id)
        before = path.read_bytes()
        uart = transport()
        with patch.dict(sys.modules, serial=types.SimpleNamespace(Serial=lambda *a, **k: uart)), redirect_stdout(io.StringIO()):
            code = host.main(["--port", "TEST", "--device-id", CAPTURE.device_id.hex(), "--context", str(path), "provision", "--resume"])
        self.assertEqual(code, 0)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(uart.writes[1].split()[3], host.context_wire(context).hex().encode())

    def test_finalized_export_published_after_receiver_and_idempotent_retry(self):
        bundle, database = self.root / "export", self.root / "receiver.sqlite"
        result = host.export_capture(client(), CAPTURE.capture_id, bundle, database)
        self.assertFalse(result["reused"])
        self.assertEqual((bundle / "capture.aura").read_bytes(), FINAL.read_bytes())
        self.assertEqual((bundle / "physical.ack3").read_bytes(), FINAL_RECEIPT)
        with DurableReceiver(database) as receiver:
            self.assertEqual(receiver.receipt(CAPTURE).encode(), FINAL_RECEIPT)
        result = host.export_capture(client(), CAPTURE.capture_id, bundle, database)
        self.assertTrue(result["reused"])
        self.assertFalse(result["release_sent"])

    def test_open_source_bundle_explicitly_distinguishes_derived_seal(self):
        fixture = FIXTURES / "journal-2.aura"
        archive = read_archive(fixture, allow_interrupted=True)
        physical = (FIXTURES / "journal-2.receipt").read_bytes()
        result = host.export_capture(client(transport(fixture.read_bytes(), physical)), archive.capture.capture_id,
                                     self.root / "open", self.root / "receiver.sqlite")
        metadata = json.loads((self.root / "open/metadata.json").read_text())
        self.assertEqual(result["physical_status"], "open")
        self.assertEqual(result["archive_status"], "interrupted")
        self.assertTrue(metadata["derived_export_seal"])
        self.assertEqual(metadata["physical_receipt"], physical.hex())
        with DurableReceiver(self.root / "receiver.sqlite") as receiver:
            self.assertEqual(receiver.receipt(archive.capture), archive.receipt)
            self.assertNotEqual(receiver.receipt(archive.capture), Receipt.parse(physical))

    def test_failed_download_never_publishes_or_imports(self):
        bundle, database = self.root / "export", self.root / "receiver.sqlite"
        with self.assertRaises(host.BenchError):
            host.export_capture(client(transport(alter=lambda lines, rid: lines[:-1])), CAPTURE.capture_id, bundle, database)
        self.assertFalse(bundle.exists())
        self.assertFalse(database.exists())
        self.assertEqual(len(list(self.root.glob(".a04b-unpublished-*"))), 1)

    def test_invalid_archive_or_receipt_never_imported(self):
        data = bytearray(FINAL.read_bytes())
        data[80] ^= 1
        for name, wire, receipt in (("corrupt", bytes(data), FINAL_RECEIPT),
                ("receipt", FINAL.read_bytes(), replace(Receipt.parse(FINAL_RECEIPT), chain_sha256=b"z" * 32).encode())):
            with self.subTest(name=name), self.assertRaises((host.BenchError, ProtocolError)):
                host.export_capture(client(transport(wire, receipt)), CAPTURE.capture_id,
                                    self.root / name, self.root / f"{name}.sqlite")
            self.assertFalse((self.root / name).exists())
            self.assertFalse((self.root / f"{name}.sqlite").exists())

    def test_conflicting_existing_bundle_is_preserved(self):
        bundle, database = self.root / "export", self.root / "receiver.sqlite"
        host.export_capture(client(), CAPTURE.capture_id, bundle, database)
        (bundle / "capture.aura").write_bytes(b"preserve this existing file")
        with self.assertRaisesRegex(host.BenchError, "differs"):
            host.export_capture(client(), CAPTURE.capture_id, bundle, database)
        self.assertEqual((bundle / "capture.aura").read_bytes(), b"preserve this existing file")
        with DurableReceiver(database) as receiver:
            self.assertEqual(receiver.receipt(CAPTURE).encode(), FINAL_RECEIPT)

    def test_receiver_commit_failure_never_publishes(self):
        bundle, database = self.root / "export", self.root / "receiver.sqlite"
        with patch.object(DurableReceiver, "import_archive", side_effect=OSError("disk full")), self.assertRaises(OSError):
            host.export_capture(client(), CAPTURE.capture_id, bundle, database)
        self.assertFalse(bundle.exists())
        result = host.export_capture(client(), CAPTURE.capture_id, bundle, database)
        self.assertFalse(result["reused"])

    def test_archive_fsync_failure_never_imports_or_publishes(self):
        bundle, database = self.root / "export", self.root / "receiver.sqlite"
        with patch.object(host.os, "fsync", side_effect=OSError("flush failed")), self.assertRaises(OSError):
            host.export_capture(client(), CAPTURE.capture_id, bundle, database)
        self.assertFalse(bundle.exists())
        self.assertFalse(database.exists())

    def test_sync_failure_after_rename_is_uncertain_and_exact_retry_recovers(self):
        bundle, database = self.root / "export", self.root / "receiver.sqlite"
        real_sync = host.sync_directory
        def fail_after_rename(path):
            if path == bundle.parent and bundle.exists():
                raise OSError("directory flush failed")
            real_sync(path)
        with patch.object(host, "sync_directory", side_effect=fail_after_rename), self.assertRaises(OSError):
            host.export_capture(client(), CAPTURE.capture_id, bundle, database)
        self.assertTrue(bundle.exists())
        self.assertTrue(host.export_capture(client(), CAPTURE.capture_id, bundle, database)["reused"])

    def test_real_process_exit_before_and_after_publication_recovers(self):
        for when, expected in (("before", 81), ("after", 82)):
            bundle, database = self.root / when, self.root / f"{when}.sqlite"
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--crash-export", when,
                                     str(bundle), str(database)], timeout=30, capture_output=True)
            self.assertEqual(result.returncode, expected, result.stderr.decode())
            self.assertEqual(bundle.exists(), when == "after")
            with DurableReceiver(database) as receiver:
                self.assertEqual(receiver.receipt(CAPTURE).encode(), FINAL_RECEIPT)
            resumed = host.export_capture(client(), CAPTURE.capture_id, bundle, database)
            self.assertEqual(resumed["reused"], when == "after")
            self.assertEqual((bundle / "capture.aura").read_bytes(), FINAL.read_bytes())


def crash_export(when, bundle, database):
    publish = host._publish_bundle
    def crash(temporary, destination):
        if when == "before":
            os._exit(81)
        publish(temporary, destination)
        os._exit(82)
    host._publish_bundle = crash
    host.export_capture(client(), CAPTURE.capture_id, bundle, database)


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--crash-export":
        crash_export(*sys.argv[2:])
    else:
        unittest.main()
