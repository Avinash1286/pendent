"""Explicit finalized-capture RLS1 issuance and a durable local outbox.

No transport, enrollment, plaintext-key persistence, automatic release, rekey or
device-completion verification is implemented here. Caller supplies trusted keys
and a verified initial floor. Public IDs/paths do not authenticate a device.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import struct

from .files import sync_directory
from .protocol import ProtocolError
from .protocol_v2 import Capture, DurableReceiver, Receipt, FINALIZED, DEFAULT_MAX_PAYLOAD_BYTES

RELEASE_PERMISSION = "release-exact-finalized-capture"
RLS1_DOMAIN = b"AURA-A04-OWNER-RELEASE-v1\0"
_STATE_DOMAIN = b"AURA-A04-RELEASE-OUTBOX-STATE-v1\0"
_REQUEST_DOMAIN = b"AURA-A04-RELEASE-OUTBOX-REQUEST-v1\0"
_HEADER = struct.Struct("<4sBBBB16s16sQQ")
_MAX_U64 = (1 << 64) - 1
_MAX_REQUESTS = 10000
_MAX_BODY = 8192


class ReleaseError(ProtocolError):
    """Release refused; retain the device copy and any pending outbox."""


def _require(condition, message):
    if not condition:
        raise ReleaseError(message)


def _u64(value, name, *, nonzero=False):
    _require(type(value) is int and (1 if nonzero else 0) <= value <= _MAX_U64,
             f"Invalid {name}")


def _identifier(value, name):
    _require(type(value) is bytes and len(value) == 16 and value != bytes(16),
             f"Invalid {name}")


@dataclass(frozen=True)
class TrustedReleaseContext:
    device_id: bytes
    storage_incarnation: bytes
    owner_id: bytes
    owner_generation: int
    key: bytes = field(repr=False)

    def __post_init__(self):
        for name in ("device_id", "storage_incarnation", "owner_id"):
            _identifier(getattr(self, name), name)
        _u64(self.owner_generation, "owner generation", nonzero=True)
        _require(type(self.key) is bytes and len(self.key) == 32 and self.key != bytes(32),
                 "An explicitly enrolled nonzero 32-byte key is required")

    def _public(self):
        return {"device_id": self.device_id.hex(), "storage_incarnation": self.storage_incarnation.hex(),
                "owner_id": self.owner_id.hex(), "owner_generation": self.owner_generation}


@dataclass(frozen=True)
class PendingRelease:
    request_id: str
    sequence: int
    envelope: bytes
    receipt: bytes
    capture_id: bytes
    receiver_db: Path


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _decode(data):
    _require(type(data) is bytes and len(data) <= _MAX_BODY, "Invalid outbox metadata length")
    try:
        result = json.loads(data)
    except (ValueError, UnicodeError) as error:
        raise ReleaseError("Corrupt outbox metadata") from error
    _require(type(result) is dict and _canonical(result) == data, "Noncanonical outbox metadata")
    return result


def _hex(value, bytes_count):
    _require(type(value) is str and len(value) == bytes_count * 2 and
             re.fullmatch(r"[0-9a-f]+", value) is not None, "Invalid outbox binary field")
    return bytes.fromhex(value)


def _mac(context, domain, body):
    return hmac.digest(context.key, domain + body, "sha256")


def _tag_valid(context, domain, body, tag):
    return type(tag) is bytes and len(tag) == 32 and hmac.compare_digest(_mac(context, domain, body), tag)


def _path(value, *, existing):
    _require(str(value) not in ("", ":memory:"), "A persistent local database path is required")
    path = Path(value).expanduser().resolve(strict=existing)
    if existing:
        _require(path.is_file(), "Database path must name an existing file")
    _require(len(str(path)) <= 1024, "Database path is too long")
    return path


def _connect(path, *, readonly):
    # URI mode never silently creates a missing source/authority database.
    db = sqlite3.connect(path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
                         uri=True, timeout=5)
    try:
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA foreign_keys=ON")
        _require(db.execute("PRAGMA journal_mode").fetchone()[0] == "delete",
                 "DELETE rollback journaling is required")
        if not readonly:
            db.execute("PRAGMA synchronous=EXTRA")
            _require(db.execute("PRAGMA synchronous").fetchone()[0] == 3,
                     "Synchronous EXTRA is required")
        _require(db.execute("PRAGMA quick_check").fetchall() == [("ok",)],
                 "SQLite integrity check failed")
        return db
    except BaseException:
        db.close()
        raise


def _commit(db):
    """One commit boundary; failure never permits returning a new envelope."""
    db.commit()


class _ExistingReceiver(DurableReceiver):
    """Read-only connection using the real receiver's prefix/seal validator.

    The ordinary constructor can create/migrate a DB; release must do neither.
    Keep this read transaction open until the outbox commit so a DELETE-journal
    source writer cannot commit changed data during the authorization boundary.
    """
    def __init__(self, path):
        self.max_capture_bytes = DEFAULT_MAX_PAYLOAD_BYTES
        self.db = _connect(path, readonly=True)
        try:
            self.db.execute("BEGIN")
            columns = {row[1] for row in self.db.execute("PRAGMA table_info(captures)")}
            _require({"identity", "manifest", "next_sequence", "encoded_bytes", "sample_count",
                      "chain_sha256", "sealed", "seal_wire"} <= columns,
                     "A current committed receiver database is required")
        except BaseException:
            self.db.close()
            raise

    def terminal(self, device_id, capture_id):
        identity = device_id.hex() + ":" + capture_id.hex()
        row = self.db.execute("SELECT manifest FROM captures WHERE identity=?", (identity,)).fetchone()
        _require(row is not None, "Exact capture is absent from receiver database")
        capture = Capture.parse(row[0])
        _require(capture.device_id == device_id and capture.capture_id == capture_id,
                 "Receiver manifest identity conflicts")
        # Reuse production full packet/chain/seal validation, not caller Receipt.
        prefix, state = self._verified_prefix(capture)
        receipt = self._receipt(prefix, state)
        _require(receipt.status == FINALIZED and state[6] is not None,
                 "Only a committed FINALIZED capture can be released")
        return capture.encode(), receipt.encode()


def _envelope(context, sequence, receipt):
    parsed = Receipt.parse(receipt)
    _require(parsed.status == FINALIZED and parsed.device_id == context.device_id,
             "Release requires this enrolled device's finalized receipt")
    _u64(sequence, "release sequence", nonzero=True)
    body = _HEADER.pack(b"RLS1", 1, 1, 1, 0, context.storage_incarnation,
                        context.owner_id, context.owner_generation, sequence) + receipt
    _require(len(body) == 150, "Invalid RLS1 body length")
    return body + _mac(context, RLS1_DOMAIN, body)


def _request_id(value):
    _require(type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) is not None,
             "Request ID must be 1..128 ASCII letters, digits, underscores or hyphens")


class ReleaseOutbox:
    """One pending request, serialized SQLite transactions, retained history.

    Opening never provisions or resets a floor. No rekey API is provided.
    A valid older whole-database rollback cannot be detected without an external
    protected monotonic anchor; authenticated metadata is not anti-rollback.
    """
    def __init__(self, path, context):
        _require(type(context) is TrustedReleaseContext, "Trusted enrolled context is required")
        self.path = _path(path, existing=True)
        self.context = context
        with self._transaction() as db:
            self._verify(db)

    @classmethod
    def provision(cls, path, context, *, initial_sequence_floor):
        """Explicit local setup from an externally trusted device floor.

        No default floor, discovery, replacement, repair or ownership enrollment.
        A failed/aborted first provision leaves its file for explicit inspection.
        """
        _require(type(context) is TrustedReleaseContext, "Trusted enrolled context is required")
        _u64(initial_sequence_floor, "trusted initial sequence floor")
        target = _path(path, existing=False)
        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        db = _connect(target, readonly=False)
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE authority (id INTEGER PRIMARY KEY CHECK(id=1), body BLOB NOT NULL, tag BLOB NOT NULL)")
            db.execute("CREATE TABLE requests (request_id TEXT PRIMARY KEY, sequence BLOB UNIQUE NOT NULL, body BLOB NOT NULL, tag BLOB NOT NULL)")
            state = {"version": 1, "context": context._public(), "base_floor": initial_sequence_floor,
                     "floor": initial_sequence_floor, "count": 0, "chain": bytes(32).hex()}
            body = _canonical(state)
            db.execute("INSERT INTO authority VALUES(1,?,?)", (body, _mac(context, _STATE_DOMAIN, body)))
            _commit(db)
        finally:
            db.close()
        sync_directory(target.parent)
        return cls(target, context)

    @contextmanager
    def _transaction(self):
        db = _connect(self.path, readonly=False)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            _commit(db)
        finally:
            db.close()  # uncommitted changes roll back; uncertain COMMIT requires reopen/retry

    def _verify(self, db):
        saved = db.execute("SELECT id,body,tag FROM authority").fetchall()
        _require(len(saved) == 1 and saved[0][0] == 1, "Missing or ambiguous outbox authority")
        body, tag = saved[0][1:]
        _require(type(body) is bytes and _tag_valid(self.context, _STATE_DOMAIN, body, tag),
                 "Outbox authority authentication failed; no reset permitted")
        state = _decode(body)
        _require(set(state) == {"version", "context", "base_floor", "floor", "count", "chain"}
                 and type(state["version"]) is int and state["version"] == 1
                 and _canonical(state["context"]) == _canonical(self.context._public()),
                 "Wrong outbox ownership context")
        _u64(state["base_floor"], "base floor"); _u64(state["floor"], "floor")
        _require(type(state["count"]) is int and 0 <= state["count"] <= _MAX_REQUESTS,
                 "Invalid outbox request count")
        chain = bytes(32); sequence = state["base_floor"]; requests = []; pending = 0
        for request_id, seq_wire, raw, request_tag in db.execute(
                "SELECT request_id,sequence,body,tag FROM requests ORDER BY sequence"):
            _require(len(requests) < _MAX_REQUESTS, "Outbox history limit reached")
            _request_id(request_id)
            _require(type(raw) is bytes and _tag_valid(self.context, _REQUEST_DOMAIN, raw, request_tag),
                     "Outbox request authentication failed")
            record = _decode(raw)
            _require(set(record) == {"version", "request_id", "sequence", "receiver_db", "manifest",
                                    "receipt", "envelope", "permission", "completed"},
                     "Invalid outbox request fields")
            _u64(record["sequence"], "saved sequence", nonzero=True)
            _require(sequence < _MAX_U64 and record["sequence"] == sequence + 1 and
                     seq_wire == record["sequence"].to_bytes(8, "big"), "Outbox sequence chain is inconsistent")
            sequence += 1
            _require(type(record["version"]) is int and record["version"] == 1 and
                     record["request_id"] == request_id and record["permission"] == RELEASE_PERMISSION and
                     type(record["completed"]) is bool and type(record["receiver_db"]) is str and
                     0 < len(record["receiver_db"]) <= 1024, "Invalid saved release permission/binding")
            manifest = Capture.parse(_hex(record["manifest"], 68))
            ack = Receipt.parse(_hex(record["receipt"], 94))
            _require(manifest.device_id == self.context.device_id and
                     ack.device_id == manifest.device_id and ack.capture_id == manifest.capture_id,
                     "Saved source identity conflicts")
            _require(hmac.compare_digest(_hex(record["envelope"], 182),
                                         _envelope(self.context, sequence, ack.encode())),
                     "Saved RLS1 does not match its exact receipt/context")
            if not record["completed"]:
                pending += 1
            elif pending:
                raise ReleaseError("Completed request follows an unresolved sequence")
            chain = hashlib.sha256(chain + raw + request_tag).digest()
            requests.append(record)
        _require(pending <= 1 and len(requests) == state["count"] and sequence == state["floor"] and
                 chain == _hex(state["chain"], 32), "Outbox history/floor does not match authority")
        return state, requests

    def _save_state(self, db, state):
        chain = bytes(32); count = 0
        for raw, tag in db.execute("SELECT body,tag FROM requests ORDER BY sequence"):
            chain = hashlib.sha256(chain + raw + tag).digest(); count += 1
        state = {**state, "chain": chain.hex(), "count": count}
        body = _canonical(state)
        db.execute("UPDATE authority SET body=?,tag=? WHERE id=1",
                   (body, _mac(self.context, _STATE_DOMAIN, body)))

    def _put_request(self, db, record, *, update=False):
        body = _canonical(record)
        _require(len(body) <= _MAX_BODY, "Release metadata exceeds bounded outbox size")
        tag = _mac(self.context, _REQUEST_DOMAIN, body)
        if update:
            db.execute("UPDATE requests SET body=?,tag=? WHERE request_id=?", (body, tag, record["request_id"]))
        else:
            db.execute("INSERT INTO requests VALUES(?,?,?,?)", (record["request_id"],
                       record["sequence"].to_bytes(8, "big"), body, tag))

    @staticmethod
    def _match_source(record, manifest, receipt):
        _require(record["manifest"] == manifest.hex() and record["receipt"] == receipt.hex(),
                 "Retained source changed since explicit release request")

    def request_release(self, request_id, receiver_db, capture_id, *, permission):
        """Return exact RLS1 only after source verification and outbox COMMIT.

        Explicit permission is required for this exact capture. No caller Receipt
        can substitute for re-reading the committed receiver DB. Same-ID binding
        conflicts fail; an identical explicit request returns saved exact bytes.
        """
        _request_id(request_id); _identifier(capture_id, "capture ID")
        _require(permission == RELEASE_PERMISSION and type(permission) is str,
                 "Explicit exact-capture release permission is required")
        source = _path(receiver_db, existing=True)
        _require(source != self.path, "Source receiver and outbox must be separate databases")
        with _ExistingReceiver(source) as receiver:
            manifest, receipt = receiver.terminal(self.context.device_id, capture_id)
            with self._transaction() as db:
                state, records = self._verify(db)
                existing = next((r for r in records if r["request_id"] == request_id), None)
                if existing:
                    _require(existing["receiver_db"] == str(source) and existing["permission"] == permission,
                             "Request ID is already bound to another source or permission")
                    self._match_source(existing, manifest, receipt)
                    envelope = _hex(existing["envelope"], 182)
                else:
                    _require(not any(not r["completed"] for r in records),
                             "An earlier release is pending; retry or confirm it first")
                    _require(not any(Capture.parse(_hex(r["manifest"], 68)).capture_id == capture_id
                                     for r in records),
                             "Capture already has a release request; reuse its original request ID")
                    _require(len(records) < _MAX_REQUESTS and state["floor"] < _MAX_U64,
                             "Release sequence/history exhausted; no reset permitted")
                    envelope = _envelope(self.context, state["floor"] + 1, receipt)
                    record = {"version": 1, "request_id": request_id, "sequence": state["floor"] + 1,
                              "receiver_db": str(source), "manifest": manifest.hex(), "receipt": receipt.hex(),
                              "envelope": envelope.hex(), "permission": permission, "completed": False}
                    self._put_request(db, record)
                    self._save_state(db, {**state, "floor": record["sequence"]})
                    self._verify(db)
        return envelope

    def _saved(self, request_id=None):
        with self._transaction() as db:
            _, records = self._verify(db)
            if request_id is None:
                return next((r for r in records if not r["completed"]), None)
            result = next((r for r in records if r["request_id"] == request_id), None)
            _require(result is not None, "Unknown release request")
            return result

    def _revalidate(self, record):
        source = _path(record["receiver_db"], existing=True)
        capture = Capture.parse(_hex(record["manifest"], 68))
        with _ExistingReceiver(source) as receiver:
            manifest, receipt = receiver.terminal(self.context.device_id, capture.capture_id)
            self._match_source(record, manifest, receipt)
        return PendingRelease(record["request_id"], record["sequence"], _hex(record["envelope"], 182),
                              receipt, capture.capture_id, source)

    def pending(self):
        """Return the pending exact envelope after rechecking its retained source."""
        record = self._saved()
        return None if record is None else self._revalidate(record)

    def retry(self, request_id):
        """Revalidate the source and return saved bytes; never allocate a sequence."""
        _request_id(request_id)
        return self._revalidate(self._saved(request_id)).envelope

    def mark_completed(self, request_id, *, envelope, receipt):
        """Idempotent LOCAL bookkeeping for an externally verified device result.

        Requires exact saved envelope and receipt. This does not authenticate a
        device response or infer that sending completed an erase. That external
        protocol/enrollment/confirmation integration is not implemented.
        """
        _request_id(request_id)
        _require(type(envelope) is bytes and len(envelope) == 182 and
                 type(receipt) is bytes and len(receipt) == 94, "Exact completion evidence is required")
        with self._transaction() as db:
            state, records = self._verify(db)
            record = next((r for r in records if r["request_id"] == request_id), None)
            _require(record is not None, "Unknown release request")
            _require(hmac.compare_digest(envelope, _hex(record["envelope"], 182)) and
                     hmac.compare_digest(receipt, _hex(record["receipt"], 94)),
                     "Completion evidence differs from the persisted authorization")
            if not record["completed"]:
                self._put_request(db, {**record, "completed": True}, update=True)
                self._save_state(db, state)
                self._verify(db)
