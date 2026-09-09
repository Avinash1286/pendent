# Explicit A04 release requests and durable outbox

`aura_companion.release` implements local, explicit release issuance for one exact **FINALIZED** capture already committed to a receiver database. It produces the same 182-byte RLS1 envelope as [the portable firmware primitive](../firmware/a04/RELEASE-AUTH.md), using standard-library HMAC-SHA256 with the domain `AURA-A04-OWNER-RELEASE-v1` plus exactly one NUL byte. It does not send messages, connect to a pendant, change the CLI, provision a device, or erase anything.

## API and explicit permission

`TrustedReleaseContext(device_id, storage_incarnation, owner_id, owner_generation, key)` must be supplied by trusted enrollment. IDs are nonzero 16-byte values, generation is a nonzero uint64, and the independently generated secret is exactly 32 bytes. There are no default keys, enrollment discovery or key-file writes. The key is excluded from the context's representation and is never persisted in the outbox; Python does not provide a whole-process secret-erasure guarantee. A nonzero check is an initialization guard, not proof of entropy or secure key storage.

`ReleaseOutbox.provision(path, context, initial_sequence_floor=trusted_floor)` creates a new local outbox exclusively at a previously absent path. The initial floor is mandatory and must be verified externally; it is never guessed as zero or discovered from an archive. Provisioning is local database setup, not ownership enrollment. Existing files are never overwritten, repaired or reset. A failed initial provision may leave a file requiring explicit inspection.

`ReleaseOutbox(path, context)` opens an existing outbox, checks authenticated authority/history, and refuses a missing database or a mismatched context/key. There is no rekey API. Changing ownership requires a future coordinated transition that preserves the sequence floor; opening a database under new ownership does not reset it.

```python
from aura_companion.release import ReleaseOutbox, RELEASE_PERMISSION

# enrolled_context and trusted_floor come from external trusted enrollment/state.
outbox = ReleaseOutbox.provision(
    outbox_path, enrolled_context, initial_sequence_floor=trusted_floor)
wire = outbox.request_release(
    "explicit_request_uuid", receiver_database, exact_capture_id,
    permission=RELEASE_PERMISSION)
```

The permission keyword is required and accepts only `release-exact-finalized-capture`. A caller must invoke this after explicit owner consent for that capture. Request IDs contain 1–128 ASCII letters, digits, underscores or hyphens. Paths and request IDs are bookkeeping identities, not device authentication.

There is one pending request at a time per outbox. Keep one active outbox for the enrolled device/ownership context; independently provisioned database files do not coordinate their sequence floors, and this module does not implement multiple-phone ownership or migration. `request_release` returns its envelope only after the exact request and sequence have committed. Repeating the same ID with the same source binding returns identical saved bytes, without allocating another sequence. Rebinding an ID to another database/capture/receipt conflicts. A capture already requested under another ID also conflicts, including after completion; use the original request ID. Only after locally marking the pending request completed can a different capture allocate the next sequence.

`pending()` returns a `PendingRelease` containing the request ID, sequence, exact envelope/receipt, capture ID and receiver database, or `None`. `retry(request_id)` returns the exact saved envelope. Both reopen and revalidate the retained source before returning bytes. Missing or changed source data blocks retries; it does not remove the pending request or reset its sequence.

`mark_completed(request_id, envelope=exact_saved_wire, receipt=exact_saved_ack)` is idempotent **local bookkeeping**. Both arguments must match persisted bytes. The caller must first verify the device's exact completion result through a future authenticated protocol. This method does not authenticate a response, infer completion from a send, or prove that anything was erased. Supplying the saved envelope alone is insufficient to call it, but the matching receipt is also public evidence—not an authentication credential.

## Source and commit ordering

The source is an existing on-disk receiver database with DELETE rollback journaling and the current capture/seal schema. It is opened read-only without creating or migrating tables. A small adapter reuses `DurableReceiver`'s actual full packet-prefix and seal validation. It retrieves the manifest for the enrolled device and exact capture ID, rechecks every saved packet, sequence, count, chain and terminal seal, and derives the receipt itself. The public issuer accepts no caller-created `Receipt` as durability proof.

This first policy accepts only FINALIZED status. Open receipts, physically committed interrupted receipts, and interrupted seals synthesized by export/recovery are all refused. It does not infer physical device provenance from a database or seal. Firmware must independently verify its own immutable terminal capture and match the exact ACK3 before committing any release grant.

The order is:

1. Audio/manifest/seal are already committed by the receiver.
2. The issuer reopens and validates that committed source inside a read transaction.
3. While retaining the source read lock, a serialized outbox transaction verifies authority/history, allocates exactly the next uint64 sequence, and inserts the canonical explicit request, exact manifest/ACK3/RLS1, source path and permission.
4. The same outbox transaction updates its authenticated floor/history root and commits with `synchronous=EXTRA`.
5. The source transaction closes and only then are authorization bytes returned.

The source lock prevents a conforming DELETE-journal writer from committing changed source data across this boundary. Uncommitted source changes are not treated as a receipt. These are ordered commits in two databases, not a cross-database atomic transaction. A failure before outbox commit preserves the source and allocates nothing; a successful commit followed by a lost result is recovered by reopening and retrying the original ID. Process-exit tests exercise both sides of that boundary.

Outbox metadata is canonical JSON stored as SQLite blobs. Every request has a distinct-domain HMAC covering its permission, source binding, envelope, sequence and completion state. A separately authenticated authority record covers the public ownership context, base floor, allocated floor, count and the ordered request-history digest. Altered fields, deleted records and broken sequence/history links fail closed. Sequence columns use fixed 8-byte big-endian blobs so the full unsigned range sorts without SQLite signed-integer overflow; RLS1 integers remain little-endian. Secret keys are never written to SQLite.

Completed history is retained; there is no deletion, compaction or floor-reset API. The initial implementation bounds retained history to 10,000 requests and rejects sequence overflow/history exhaustion. Future authenticated compaction must preserve the replay floor and retry evidence rather than recreating an empty outbox. A valid rollback of the entire old database cannot be detected by its own HMACs; a protected external monotonic anchor is still required for adversarial rollback resistance.

## Verification and limits

From `companion/`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_release.py -v
.\.venv\Scripts\python.exe scripts/verify_release.py --report verification/release.json
```

The 36 release tests exercise actual receiver and outbox SQLite transactions, the fixed production-C RLS1 golden vector, full standard-library HMAC/CRC/encoding agreement, explicit permission, exact retries, one-pending ordering, identity/context mismatch, corrupt/missing/open/synthesized sources, read-only source support, refusal of nonwritable outbox issuance, authenticated metadata/history tampering, full uint64 exhaustion, and no plaintext-key persistence. They inject mutation/commit failures, lost commit replies and real subprocess exits immediately before/after SQLite commit. A competing source writer test verifies that its commit is blocked until the outbox commit boundary. Concurrent issuers with both source snapshots held verify that the same request commits one sequence and different requests cannot create two pending releases. Completion mutation failures and lost replies preserve replay history; WAL source and outbox databases are refused without silently changing their journal mode.

[The reproducible verification report](verification/release.json) records the targeted release tests, the 33 receiver tests, and all 131 companion tests, with command results, runtime versions and exact/line-ending-normalized hashes of the tested source and fixtures. The runner uses this checkout on `PYTHONPATH`, requires no failures, errors or skips, and refuses to publish success if an input changes while tests run. The full suite count includes the targeted tests once; the three command counts should not be added together. The C golden-vector reference is recorded separately from executed Python code and does not imply controller or radio execution.

No transport, UI consent flow, enrollment, device challenge/response, authenticated device-completion handling, OS keychain integration, physical secure storage, or firmware-controller interoperability run is implemented here. The byte-level C golden-vector check is not a physical link test. An enrolled shared key authenticates possession by trusted peers; it cannot prove remote media honored `fsync` or prevent a malicious authorized owner from requesting deletion.

SQLite durability depends on the OS, filesystem and device honoring flushes. Keep the receiver and outbox on local storage outside cloud-sync/network folders. Provisioning also syncs the containing directory on POSIX; the existing helper has no equivalent portable directory-persistence guarantee on Windows. Tests on this Windows host cover process interruption, not physical power loss, filesystem rollback or hostile raw-file replacement.
