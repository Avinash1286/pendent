#!/usr/bin/env python3
"""Explicit local A04B developer client; never flashes, releases or repairs media."""
from contextlib import contextmanager
from dataclasses import dataclass
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import struct
import sys
import tempfile
import time
import zlib

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "companion" / "src"))
from aura_companion.files import sync_directory
from aura_companion.protocol import ProtocolError
from aura_companion.protocol_v2 import (
    Capture, DurableReceiver, Receipt, OPEN, FINALIZED, INTERRUPTED, read_archive,
)
from aura_companion.release import TrustedReleaseContext

MAX_LINE = 512
MAX_EXPORT = 128 * 1024 * 1024
MAX_NOISE_LINES = 64
MAX_NOISE_BYTES = 8192
CONTEXT = struct.Struct("<16s16s16sQ32s")


class BenchError(Exception):
    """Messages deliberately exclude raw device lines, arguments and secrets."""


def require(condition, message):
    if not condition:
        raise BenchError(message)


def hex_bytes(text, size):
    require(isinstance(text, str) and re.fullmatch(r"[0-9a-fA-F]{%d}" % (size * 2), text),
            "Invalid binary field")
    return bytes.fromhex(text)


def number(text, low, high):
    require(re.fullmatch(r"-?[0-9]{1,20}", text) is not None, "Invalid numeric field")
    result = int(text)
    require(low <= result <= high, "Numeric field outside protocol limits")
    return result


def context_wire(context):
    return CONTEXT.pack(context.device_id, context.storage_incarnation, context.owner_id,
                        context.owner_generation, context.key)


def private_path(value):
    """Repository-local personal material must use already ignored directories."""
    raw = Path(value).expanduser().absolute()
    require(not any(p.is_symlink() for p in (raw, *raw.parents)), "Private path contains a symbolic link")
    path = raw.resolve()
    try:
        parts = path.relative_to(ROOT).parts
    except ValueError:
        return path
    require(parts and (parts[0] == ".scratch" or "recordings" in parts[:-1]),
            "Use .scratch/privatebench or a recordings directory for private bench material")
    return path


def make_private_parent(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(path.parent.is_dir(), "Private parent is not a directory")


def save_new_context(path, device_id):
    """Keep the context even on failure: never replace uncertain enrollment."""
    path = private_path(path)
    make_private_parent(path)
    def nonzero(size):
        while True:
            value = secrets.token_bytes(size)
            if any(value):
                return value
    context = TrustedReleaseContext(device_id, nonzero(16), nonzero(16), 1, nonzero(32))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(context_wire(context))
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path.parent)
    return context


def load_context(path):
    path = private_path(path)
    require(path.is_file(), "Existing private enrollment context required")
    if os.name != "nt":
        require(path.stat().st_mode & 0o077 == 0, "Enrollment context must be private (mode 0600)")
    with path.open("rb") as stream:
        wire = stream.read(CONTEXT.size + 1)
    require(len(wire) == CONTEXT.size, "Invalid enrollment context length")
    try:
        return TrustedReleaseContext(*CONTEXT.unpack(wire))
    except (ValueError, ProtocolError):
        raise BenchError("Invalid enrollment context") from None


def _fail_closed(method):
    def checked(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except BaseException:
            self.broken = True
            raise
    return checked


@dataclass(frozen=True)
class DeviceInfo:
    device_id: bytes
    ready: int
    audio_state: int
    fault: int
    catalog_count: int
    free_blocks: int


class Client:
    """One outstanding request, exact request IDs, bounded input and time."""
    def __init__(self, serial, device_id=None, *, timeout=300.0, provision_timeout=2400.0, export_timeout=7200.0,
                 idle_timeout=10.0, max_export=MAX_EXPORT, clock=time.monotonic,
                 sleep=time.sleep, rid_source=lambda: secrets.token_hex(4)):
        require(device_id is None or (isinstance(device_id, bytes) and len(device_id) == 16 and any(device_id)),
                "An explicit nonzero expected device ID is required")
        require(all(isinstance(x, (float, int)) and math.isfinite(x) and 0 < x <= 28800
                    for x in (timeout, provision_timeout, export_timeout, idle_timeout)), "Invalid timeout")
        require(type(max_export) is int and 1 <= max_export <= MAX_EXPORT, "Invalid export limit")
        self.serial, self.device_id = serial, device_id
        self.expected_device_id = device_id
        self.timeout, self.export_timeout, self.idle_timeout = timeout, export_timeout, idle_timeout
        self.provision_timeout = provision_timeout
        self.max_export, self.clock, self.sleep, self.rid_source = max_export, clock, sleep, rid_source
        self.ids, self.verified, self.opened, self.broken = set(), False, False, False

    def _request(self, verb, argument=None, *, export=False):
        require(not self.broken, "Reconnect after a failed or uncertain request")
        rid = self.rid_source()
        require(re.fullmatch(r"[0-9a-fA-F]{8}", rid) is not None and rid.lower() not in self.ids,
                "Request ID was invalid or reused")
        rid = rid.lower()
        self.ids.add(rid)
        wire = (f"A04B {rid} {verb}" + (f" {argument}" if argument is not None else "") + "\n").encode("ascii")
        require(len(wire) <= 256, "Request exceeds protocol limit")
        request_timeout = self.export_timeout if export else (self.provision_timeout if verb == "PROVISION" else self.timeout)
        self.deadline = self.clock() + request_timeout
        self.response_idle = self.idle_timeout if export else request_timeout
        self.idle_deadline = self.clock() + self.response_idle
        self.noise_lines = self.noise_bytes = 0
        try:
            written = self.serial.write(wire)
            require(written == len(wire), "Incomplete UART write; reconnect and recover")
        except Exception:
            self.broken = True
            raise BenchError("UART write failed; reconnect and recover") from None
        return rid

    def _response(self, rid):
        try:
            while True:
                line = bytearray()
                while not line.endswith(b"\n"):
                    require(self.clock() < min(self.deadline, self.idle_deadline),
                            "UART response timed out; reconnect and recover source")
                    chunk = self.serial.read(1)
                    require(isinstance(chunk, bytes) and len(chunk) <= 1, "Invalid UART transport result")
                    if not chunk:
                        self.sleep(0.001)
                        continue
                    line.extend(chunk)
                    require(len(line) <= MAX_LINE, "UART line exceeds protocol limit")
                raw = bytes(line).rstrip(b"\r\n")
                if not raw.startswith(b"A04B"):
                    self.noise_lines += 1
                    self.noise_bytes += len(line)
                    require(self.noise_lines <= MAX_NOISE_LINES and self.noise_bytes <= MAX_NOISE_BYTES,
                            "Too much unrelated UART output")
                    continue
                try:
                    fields = raw.decode("ascii").split(" ")
                except UnicodeError:
                    raise BenchError("Non-ASCII protocol response") from None
                require(len(fields) >= 3 and all(fields) and fields[0] == "A04B" and
                        re.fullmatch(r"[0-9a-fA-F]{8}", fields[1]) is not None,
                        "Malformed protocol response")
                require(fields[1].lower() == rid, "Unexpected request ID; reconnect to avoid stale replies")
                if fields[2] == "ERROR":
                    require(len(fields) == 4, "Malformed device error")
                    code = number(fields[3], -(1 << 31), (1 << 31) - 1)
                    raise BenchError(f"Device rejected request ({code}); retain source and context")
                self.idle_deadline = self.clock() + self.response_idle
                return fields[2:]
        except BenchError:
            self.broken = True
            raise
        except Exception:
            self.broken = True
            raise BenchError("UART read failed; reconnect and recover") from None

    @_fail_closed
    def info(self):
        fields = self._response(self._request("INFO"))
        require(len(fields) == 8 and fields[:2] == ["OK", "INFO"], "Invalid INFO reply")
        identity = hex_bytes(fields[2], 16)
        require(any(identity) and (self.expected_device_id is None or identity == self.expected_device_id),
                "Device ID differs from explicitly selected hardware")
        result = DeviceInfo(identity, number(fields[3], 0, 1), number(fields[4], 0, 7),
                            number(fields[5], -(1 << 31), (1 << 31) - 1),
                            number(fields[6], 0, 128), number(fields[7], 0, 1022))
        self.device_id = identity
        self.verified = self.expected_device_id is not None
        return result

    @_fail_closed
    def enroll(self, context, *, provision=False):
        require(self.verified and context.device_id == self.device_id, "INFO and matching context required")
        verb = "PROVISION" if provision else "OPEN"
        fields = self._response(self._request(verb, context_wire(context).hex()))
        require(fields == ["OK", verb], "Unexpected enrollment reply")
        self.opened = True

    @_fail_closed
    def catalog(self):
        require(self.opened, "OPEN is required")
        rid, items, seen = self._request("LIST"), [], set()
        while True:
            fields = self._response(rid)
            if fields[:2] == ["END", "LIST"]:
                require(len(fields) == 3 and number(fields[2], 0, 128) == len(items), "LIST count differs")
                return items
            require(len(fields) == 4 and fields[0] == "ITEM" and len(items) < 128, "Invalid LIST item")
            capture = Capture.parse(hex_bytes(fields[1], 68))
            require(capture.device_id == self.device_id and capture.capture_id not in seen,
                    "LIST contains foreign or duplicate capture")
            seen.add(capture.capture_id)
            items.append((capture, number(fields[2], 0, 4), number(fields[3], 1, 1022)))

    @_fail_closed
    def stats(self):
        require(self.verified, "INFO is required")
        fields = self._response(self._request("STATS"))
        names = ("service_max_us", "late_service_count", "fifo_high_water", "reader_stack_free",
                 "storage_stack_free", "nand_reads", "nand_programs", "nand_erases",
                 "peak_first", "peak_second", "clip_first", "clip_second")
        require(len(fields) == 14 and fields[:2] == ["OK", "STATS"], "Invalid STATS reply")
        return {name: number(value, 0, (1 << 64) - 1) for name, value in zip(names, fields[2:])}

    @_fail_closed
    def record(self, seconds=10):
        require(self.opened, "OPEN is required")
        require(isinstance(seconds, (int, float)) and math.isfinite(seconds) and 1 <= seconds <= 60,
                "Bench recording duration must be from 1 to 60 seconds")
        fields = self._response(self._request("START"))
        require(len(fields) == 3 and fields[:2] == ["OK", "START"], "Invalid START reply")
        capture_id = hex_bytes(fields[2], 16)
        require(any(capture_id), "Invalid capture ID")
        interrupted = False
        until = self.clock() + seconds
        try:
            while self.clock() < until:
                self.sleep(min(0.1, until - self.clock()))
        except KeyboardInterrupt:
            interrupted = True
        fields = self._response(self._request("STOP"))
        require(len(fields) == 5 and fields[:2] == ["OK", "STOP"] and
                hex_bytes(fields[4], 16) == capture_id, "STOP differs from active capture")
        state = number(fields[2], 4, 7)
        fault = number(fields[3], -(1 << 31), (1 << 31) - 1)
        return {"capture_id": capture_id.hex(), "audio_state": state, "fault": fault,
                "user_stopped": interrupted, "host_receipt": False}

    @_fail_closed
    def download(self, capture_id, stream):
        require(self.opened, "OPEN is required")
        require(isinstance(capture_id, bytes) and len(capture_id) == 16 and any(capture_id), "Invalid capture ID")
        rid, count = self._request("EXPORT", capture_id.hex(), export=True), 0
        while True:
            fields = self._response(rid)
            if fields[:2] == ["END", "EXPORT"]:
                require(len(fields) == 4 and int.from_bytes(hex_bytes(fields[2], 8), "big") == count,
                        "EXPORT terminal length differs")
                receipt = Receipt.parse(hex_bytes(fields[3], 94))
                require(receipt.device_id == self.device_id and receipt.capture_id == capture_id,
                        "EXPORT receipt identifies a different recording")
                require(count >= 68, "EXPORT is shorter than a manifest")
                return receipt, count
            require(len(fields) == 4 and fields[0] == "DATA", "Invalid EXPORT response")
            require(int.from_bytes(hex_bytes(fields[1], 8), "big") == count, "EXPORT offset gap or replay")
            require(2 <= len(fields[2]) <= 256 and len(fields[2]) % 2 == 0, "Invalid DATA payload length")
            payload = hex_bytes(fields[2], len(fields[2]) // 2)
            require(zlib.crc32(payload) == int.from_bytes(hex_bytes(fields[3], 4), "big"), "DATA checksum differs")
            require(count + len(payload) <= self.max_export, "EXPORT exceeds configured bound")
            require(stream.write(payload) == len(payload), "Incomplete private export write")
            count += len(payload)


def verify_physical_receipt(archive, physical):
    require(archive.seal is not None and archive.discarded_tail_bytes == 0,
            "UART export must contain a complete terminal seal")
    if physical.status != OPEN:
        require(physical == archive.receipt, "Physical terminal receipt differs from verified archive")
        return
    require(archive.termination.status == INTERRUPTED, "OPEN physical source requires an interrupted export")
    digest = hashlib.sha256(archive.capture.encode()).digest()
    encoded_bytes = sample_count = sequence = 0
    for packet in archive.iter_packets():
        digest = hashlib.sha256(digest + packet.encode()).digest()
        encoded_bytes += len(packet.payload)
        sample_count += packet.sample_count
        sequence += 1
    expected = Receipt(archive.capture.device_id, archive.capture.capture_id, sequence,
                       encoded_bytes, sample_count, digest, OPEN)
    require(physical == expected, "Physical OPEN receipt differs from verified pre-seal prefix")


def _write_private(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def _publication_lock(parent):
    """Cooperative OS lock; a crashed process releases it without resetting data."""
    descriptor = os.open(parent / ".a04b-publication.lock", os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+b") as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise BenchError("Another export owns the publication directory") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _hash(path):
    digest, count = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while block := stream.read(65536):
            count += len(block)
            require(count <= MAX_EXPORT, "Existing publication exceeds size limit")
            digest.update(block)
    return digest.digest()


def _publish_bundle(temporary, destination):
    if destination.exists():
        require(destination.is_dir() and not destination.is_symlink(), "Existing publication conflicts")
        names = {"capture.aura", "physical.ack3", "metadata.json"}
        require({p.name for p in destination.iterdir()} == names, "Existing publication is incomplete or conflicts")
        for name in names:
            old = destination / name
            require(old.is_file() and not old.is_symlink() and _hash(old) == _hash(temporary / name),
                    "Existing publication differs; both sources retained")
            with old.open("r+b") as stream:
                os.fsync(stream.fileno())
        sync_directory(destination)
        sync_directory(destination.parent)
        return True
    # Serialized local owner. Windows rename refuses existing destinations;
    # POSIX callers share the parent lock and never overwrite a populated bundle.
    temporary.rename(destination)
    sync_directory(destination.parent)
    return False


def export_capture(client, capture_id, destination, receiver_path):
    destination, receiver_path = private_path(destination), private_path(receiver_path)
    require(destination != receiver_path and destination not in receiver_path.parents and
            receiver_path not in destination.parents, "Export and receiver paths overlap")
    make_private_parent(destination)
    make_private_parent(receiver_path)
    with _publication_lock(destination.parent):
        temporary = Path(tempfile.mkdtemp(prefix=".a04b-unpublished-", dir=destination.parent))
        # Unfinished and failed bundles are intentionally retained for diagnosis,
        # never treated as completed downloads or automatically removed on retry.
        archive_path = temporary / "capture.aura"
        descriptor = os.open(archive_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            physical, count = client.download(capture_id, stream)
            stream.flush()
            os.fsync(stream.fileno())
        archive = read_archive(archive_path, allow_interrupted=True, max_payload_bytes=client.max_export)
        require(archive.file_bytes == count and archive.capture.device_id == client.device_id and
                archive.capture.capture_id == capture_id, "Archive differs from requested source")
        verify_physical_receipt(archive, physical)
        _write_private(temporary / "physical.ack3", physical.encode())
        metadata = {"format": "A04B-export-1", "device_id": client.device_id.hex(),
                    "capture_id": capture_id.hex(), "archive_sha256": archive.sha256_hex,
                    "archive_bytes": count, "archive_status": archive.status,
                    "physical_status": {OPEN: "open", FINALIZED: "finalized", INTERRUPTED: "interrupted"}[physical.status],
                    "derived_export_seal": physical.status == OPEN,
                    "archive_receipt": archive.receipt.encode().hex(), "physical_receipt": physical.encode().hex(),
                    "release_sent": False}
        _write_private(temporary / "metadata.json", (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode())
        sync_directory(temporary)
        # Create a new receiver privately; never truncate an existing one.
        try:
            descriptor = os.open(receiver_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            require(receiver_path.is_file(), "Receiver must be a persistent file")
        else:
            os.close(descriptor)
        with DurableReceiver(receiver_path, max_capture_bytes=client.max_export) as receiver:
            committed = receiver.import_archive(archive)
            require(committed == archive.receipt and receiver.receipt(archive.capture) == committed,
                    "Committed receiver differs from verified archive")
        with receiver_path.open("r+b") as stream:
            os.fsync(stream.fileno())
        sync_directory(receiver_path.parent)
        reused = _publish_bundle(temporary, destination)
        return {"bundle": str(destination), "receiver": str(receiver_path),
                "reused": reused, "physical_status": metadata["physical_status"],
                "archive_status": archive.status, "bytes": count, "release_sent": False}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--port", required=True, help="Explicit serial port; no auto-discovery")
    result.add_argument("--device-id", help="Expected 32-hex hardware identity; optional only for public INFO discovery")
    result.add_argument("--context", help="Explicit private 88-byte enrollment file")
    result.add_argument("--timeout", type=float, default=300)
    result.add_argument("--provision-timeout", type=float, default=2400)
    result.add_argument("--export-timeout", type=float, default=7200)
    commands = result.add_subparsers(dest="command", required=True)
    for command in ("info", "open", "list", "stats"):
        commands.add_parser(command)
    provision = commands.add_parser("provision")
    provision.add_argument("--resume", action="store_true", help="Explicitly retry blank-only provisioning with the existing context")
    record = commands.add_parser("record")
    record.add_argument("--seconds", type=float, default=10)
    export = commands.add_parser("export")
    export.add_argument("capture_id")
    export.add_argument("--output", required=True, help="New bundle directory (exact retries allowed)")
    export.add_argument("--receiver", required=True, help="Private persistent receiver SQLite file")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        require(args.command == "info" or args.device_id, "An explicit --device-id is required")
        identity = hex_bytes(args.device_id, 16) if args.device_id else None
        require(identity is None or any(identity), "Expected device ID must be nonzero")
        require(args.command in ("info", "stats") or args.context, "An explicit --context file is required")
        # Validate existing authority before opening UART, never auto-create it.
        context = load_context(args.context) if (args.command not in ("info", "stats", "provision") or
                  (args.command == "provision" and args.resume)) else None
        if context:
            require(context.device_id == identity, "Context differs from expected device ID")
        try:
            import serial
        except ImportError:
            raise BenchError("Install the pinned bench requirements before using a serial port") from None
        # Finite reads and writes bound the application's own deadline checks.
        with serial.Serial(args.port, 115200, timeout=0.1, write_timeout=5,
                           bytesize=8, parity="N", stopbits=1, rtscts=False, dsrdtr=False) as port:
            client = Client(port, identity, timeout=args.timeout, provision_timeout=args.provision_timeout,
                            export_timeout=args.export_timeout)
            info = client.info()
            if args.command == "info":
                result = {**info.__dict__, "device_id": info.device_id.hex(), "identity_authenticated": False}
            elif args.command == "stats":
                result = client.stats()
            elif args.command == "provision":
                if context is None:
                    context = save_new_context(args.context, identity)
                client.enroll(context, provision=True)
                result = {"provisioned": True, "device_id": identity.hex()}
            else:
                client.enroll(context)
                if args.command == "open":
                    result = {"opened": True, "device_id": identity.hex()}
                elif args.command == "list":
                    result = [{"capture_id": c.capture_id.hex(), "verification": v, "blocks": b}
                              for c, v, b in client.catalog()]
                elif args.command == "record":
                    result = client.record(args.seconds)
                else:
                    result = export_capture(client, hex_bytes(args.capture_id, 16), args.output, args.receiver)
        print(json.dumps(result, sort_keys=True, indent=2))
        if args.command == "record" and (result["audio_state"] != 4 or result["fault"] != 0):
            return 2
        return 0
    except BenchError as error:
        print(f"A04B: {error}", file=sys.stderr)
    except KeyboardInterrupt:
        print("A04B: interrupted; reconnect and inspect source before retrying", file=sys.stderr)
    except Exception:
        # Exceptions from serial/OS/SQLite/parsers may contain raw payloads or
        # secrets. Neither their repr nor a chained traceback is printed.
        print("A04B: operation failed; retain context and source, reconnect and inspect", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
