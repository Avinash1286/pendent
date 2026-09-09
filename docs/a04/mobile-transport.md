# A04 first Android transport proposal

Design review: **2026-09-09**. This specifies the next integration boundary; it is
not an implemented GATT service, enrolled consumer device, tested phone link or
wearable release. Local Android archive import, verification and playback are
the first phone foundation. They do not replace the required pendant-to-phone
capture download, reconnect recovery, ownership enrollment or physical testing.

## Reuse and the implemented storage prerequisite

Reuse the exact [AUR3/AFR3/ASE3/ACK3 bytes](../../firmware/a04/ARCHIVE.md), the
serialized [journal](../../firmware/a04/include/aura_journal.h), capture identities
and [storage owner](../../firmware/a04/STORAGE.md). Reuse A03's physical pairing
window, encrypted characteristics, one outstanding command and immutable reply
principles. Do **not** reuse A03's PCM payload interpretation, integer recording
IDs, DELETE or FORMAT operations. A04 needs a distinct service/version.

The current `aura_journal_export()` first verifies the complete capture, then
replays it again to its synchronous callback and checks the resulting receipt.
Calling it afresh for every BLE chunk would repeatedly scan the whole capture.
The separate [bounded export cursor](../../firmware/a04/JOURNAL-CURSOR.md) now
supplies verification, exact-boundary seek, sequential chunks and final source
revalidation. It shares the legacy validator and adds stricter unreadable and
unassociated-source rejection. Its implemented storage interface provides:

- Open one inactive capture by its full device/capture identity; obtain an exact
  manifest and verified physical ACK3, and bind them to one volatile handle.
- Advance verification and reads in bounded storage-owner steps, with separate
  immutable response storage. Never hold a NAND scratch buffer for a BLE callback.
- Resume at a validated complete-record boundary after a single linear prefix
  replay. Reuse the cursor for subsequent chunks; never rescan per MTU fragment.
- Recheck the completed export against the bound physical receipt before FINISH.
  Any changed, contradictory, unreadable or unassociated source fails the export.
- Cancel only volatile work. Disconnect, expiry, a new capture request or a media
  transition invalidates the handle and cached response; no source is deleted.

The cursor is exercised by portable host checks and the wired bench EXPORT path.
Its operation-count bound does not measure physical NAND/BLE latency or establish
a phone connection. The GATT command owner, enrollment and Android durable
resume coordinator remain to be implemented before phone transport is enabled.

## Proposed A04 BLE v1 surface

Use a separate private service `7f520000-1b15-4f0d-8fe5-3f942170a004`, command
characteristic `7f520001-1b15-4f0d-8fe5-3f942170a004` (write with response), and
response characteristic `7f520002-1b15-4f0d-8fe5-3f942170a004` (notify). These are
project-proposed identifiers, not an existing firmware capability. Both
characteristics require an encrypted link; consumer access additionally needs
the reviewed ownership enrollment described below.

All integers are unsigned little-endian. Commands start with
`version:u8=1, opcode:u8, transaction:u16`. A transaction is nonzero and not
reused within a connection. Each command fits the default 20-byte ATT write
payload. There is one outstanding logical command and one selected export
handle per connection, and one storage operation owner globally.

| Opcode | Command body after the 4-byte header | Required behavior |
| ---: | --- | --- |
| 1 HELLO | Empty | Return device ID[16], storage incarnation[16], catalog revision u32/count u16, and supported response/chunk limits. Status comes from an owner-published snapshot. |
| 2 LIST | Catalog revision u32, index u16 | Return exact manifest[68], verification state and source-fault state. A stale revision fails; an index is never a persistent recording identity. Metadata listing does not issue a receipt. |
| 3 SELECT | Capture ID[16] | Verify the inactive source and create a nonzero connection-scoped export handle. Return handle u32, manifest[68], physical ACK3[94], physical/export byte lengths u64, and whether export adds a derived seal. |
| 4 READ | Handle u32, absolute export offset u64, requested bytes u16 | Return the matching handle/offset, actual byte count, exact bytes and IEEE CRC32 over those bytes. Cap data at 256 bytes and the negotiated advertised limit. A source offset is not an Opus payload offset. |
| 5 FINISH | Handle u32, expected exported bytes u64 | Succeed only after cursor EOF and final source revalidation; return exact physical ACK3[94], export byte length and derived-seal flag. Receipt identity must equal SELECT. |
| 6 CANCEL | Handle u32 | Release volatile transfer state only; preserve journal source and phone's committed prefix. |

Logical responses begin `status:u8, opcode:u8, transaction:u16`. Proposed status
values are 0 OK, 1 BUSY, 2 INVALID, 3 NOT_FOUND, 4 IO_ERROR, 5 FORBIDDEN,
6 END_OF_LIST, 7 STALE and 8 CONFLICT. Error responses have no success payload.
The complete byte layouts, bounds and golden cross-language fixtures must be
locked before implementation is treated as interoperable; this table is the
reviewed behavioral contract, not evidence of an existing parser.

An ATT write completion means command transport acceptance, not operation
completion or saved audio. The device sends the terminal logical response only
after the storage owner finishes the operation. A repeat of the **same last
transaction and exact command bytes** resends the cached immutable response.
An identical retry while that command is still running joins the existing work;
it cannot restart verification or create another cursor. Changing bytes under
the same transaction fails. A new command cannot replace
an in-flight response. Renew the connection before transaction-space exhaustion.
Operation deadlines must account for exposed source length and measured scan
throughput; do not copy A03's fixed 30-second assumption for full-capture checking.
Timeout causes retry/reconciliation, never inferred success or media repair.

### MTU-independent response fragments

Each response notification carries an 8-byte transport header:
`version:u8=1, flags:u8=0, transaction:u16, fragment_offset:u16, total_bytes:u16`,
then bytes from the immutable logical response. Cap each logical response at
512 bytes. A notification value must fit `actual_ATT_MTU - 3`, leaving at most
`actual_ATT_MTU - 11` fragment bytes: 12 at MTU 23. Do not assume a requested MTU
was granted. Android 14 requests 517 on the first MTU request, and subsequent
requests are ignored; the callback result remains the connection's evidence.
[Android BluetoothGatt reference](https://developer.android.com/reference/android/bluetooth/BluetoothGatt#requestMtu(int))

Reassembly has one bounded buffer. Require matching transaction/total, in-range
offsets, contiguous new data and an exact complete response length. An exact
duplicate fragment is harmless; overlapping different bytes, gaps, changed
totals, excess fragments or queue overflow fail the response. A missing fragment
can trigger an exact-command retry of the cached response. No GATT notification,
controller transmit completion or fragment counter is a durable receipt.

The independent Kotlin `BleResponseFragments` component now implements this
fragment subset with a generation token, exact prior-fragment duplicate checks,
512-byte payload bound and 1024-delivery limit. Its JVM tests cover MTUs 23–517,
malformed overlaps/totals, stale generations and defensive copies. It is not
wired to GATT or the logical command protocol, and the earlier published
local-import APK does not contain this new component.

Serialize Android GATT operations, including discovery, MTU request, CCCD writes
and command writes. Wait for successful subscription before accepting the service
as transfer-ready. Associate callbacks with the current `BluetoothGatt` instance
and a local connection generation; drop callbacks from obsolete connections.
Copy callback bytes immediately into bounded owned storage. On API 33+, use the
callbacks that supply `byte[] value`; the characteristic's mutable value may
already have changed. [Android callback reference](https://developer.android.com/reference/android/bluetooth/BluetoothGattCallback)

## Exact resume and receipt provenance

The phone persists device ID, incarnation, exact manifest, selected physical
receipt, transfer revision and **verified committed wire prefix**. On restart it
reopens and verifies retained bytes before claiming any resume position. Merely
remembering a notification count, file length or successful write callback is
insufficient. A partial transport fragment or partial AFR3 record is not a
committed prefix.

For a validated OPEN prefix with ACK3 `next_sequence=N` and `encoded_bytes=B`:

```text
wire_offset = 68 + 26*N + B
```

Every audio/bookmark record contributes its 26-byte framing; bookmarks consume
sequence numbers with zero encoded payload. Add 120 only when the corresponding
ASE3 is actually present in the relevant file/physical stream. Use checked u64
arithmetic and verify the computed position against actual canonical records.
`encoded_bytes` alone is never a download offset.

After reconnect, rediscover the service and subscriptions, check HELLO identity
and incarnation, SELECT by capture ID, and compare the exact manifest and bound
physical receipt. A changed identity or receipt creates a conflict/revision for
review, not an overwrite. Then replay to the retained boundary once and continue.
Cache only the most recent response needed for same-transaction retries; session
handles and RAM progress never survive reconnect as authority.

At completion, independently validate the full archive, seal, EOF and digest,
then commit the actual source to the phone's durable store before producing a
phone ACK3 or presenting it as saved. The existing Python `DurableReceiver`
demonstrates transaction ordering and revalidation; it is not an Android storage
implementation. File-plus-database storage must flush file bytes before advancing
durable metadata and reconcile the two after a crash, or store source records
and receipt state in the same durable transaction. Avoid rescanning the entire
prefix after every small BLE fragment; verify a resumed prefix once and batch
complete records transactionally.

Keep these receipts distinct:

- **Device physical ACK3:** independently verified bytes actually on NAND.
- **Export receipt:** validated received archive, including an export-only
  synthesized interrupted seal when present.
- **Phone durable ACK3:** returned only after exact source commitment succeeds.

An unsealed device prefix may export with a synthesized interrupted ASE3 while
the physical ACK remains OPEN. Show recovery and unknown original duration;
do not silently turn that receipt into FINALIZED, or seal the canonical local
identity in a way that prevents preserving a later genuine finalized revision.
The Python importer already distinguishes revisions by terminal digest. A
finished transfer is never permission to erase the pendant copy.

## Capture, connection and ownership boundaries

The high-priority DMIC reader remains separate from the storage/encoder owner.
BLE callbacks enqueue bounded commands or consume published snapshots; they do
not scan NAND, encode audio, mutate journal/control contexts or block physical
privacy cutoff. Download is inactive-capture work. A local capture gesture must
cancel/preempt a download at a bounded storage step before preparing the next
recording. Cursor cancellation cannot reuse a DMA buffer or skip driver cleanup.
The first phone service preserves A03's local microphone control: no remote
START, no copied bench PROVISION/OPEN secret command, and no DELETE/FORMAT/release.

Keep one foreground recovery coordinator with a single in-flight pass and one
coalesced wake. Reconcile local pending state, rediscover device/catalog, then
resume eligible captures. Preserve explicit user retry intent. Cancel retry
timers on backgrounding and reject stale timer generations; persistent work is
revisited on foreground/startup/device reconnect. Network availability must not
gate local BLE download or playback. A cloud failure remains separate from a
device transfer failure.

This follows useful boundaries in Omi's pinned
[recording-transfer coordinator](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/app/lib/services/wals/recording_transfer_coordinator.dart)
and [native BLE transport](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/app/lib/services/devices/transports/native_ble_transport.dart):
coalesced foreground recovery, cooldown generations, restoring subscription
intent and checking data-path liveness after reconnect. AURA should report
explicit read/subscription errors instead of converting failure to empty data;
GATT-connected is not transfer-ready. These reviewed Dart sources do not prove
Android-native lifecycle behavior.

The first application may stop transfers when no longer foregrounded and resume
durably later. If transfers must continue across app switching, implement the
documented `connectedDevice` foreground-service/companion lifecycle and its
launch restrictions; do not imply a foreground Activity automatically supplies
background execution. [Android BLE background guidance](https://developer.android.com/develop/connectivity/bluetooth/ble/background)

Pairing requires a bounded physical action. Encrypted Just Works pairing does
not authenticate a displayless peer against MITM. The 88-byte A04B bench context
contains the raw owner key and must **not** be copied onto BLE. Consumer enrollment
needs a separately reviewed physical/out-of-band ownership binding, fresh
per-device secrets, nonce/challenge freshness, protected key custody and explicit
owner-change recovery. Public IDs, bonds, CRCs and archive hashes are not a
substitute. Until that exists, any controlled developer BLE fixture must be
identified as such, with no production ownership or secure enrollment claim.

Keep RLS1 disabled in the initial phone/device transport. Its existing MAC and
durable outbox/storage controller can be reused only after enrollment, exact
owner permission, authenticated device completion and the production audio
erase capability are connected and tested. Read/download ACKs remain entirely
separate from release authority. No automatic key reset, media format or
ownership replacement is a recovery action.

## Required integration evidence

Before claiming pendant-to-phone operation: implement and test the bounded
cursor; fragment/MTU 23 and larger transfers; reconnect at each fragment/record/
terminal boundary; stale GATT callbacks; duplicate/conflicting transactions;
process exit before/after source commit; filesystem exhaustion; exact physical
versus synthesized receipts; microphone-priority preemption; and preservation of
unacknowledged NAND data. Then run real nRF52840/PDM/W25N-to-Android capture,
download, independent decode and cold reconnect, with measured RAM/stack,
latency, privacy cutoff and source continuity. The local import/playback
foundation alone closes none of those physical/BLE gates.

## Review source identities

SHA256 values below bind the **initial review inputs**, before cursor integration
changed the journal header/source and bench protocol. They are historical review
identities, not current build/test certificates. Current cursor and bench
verification reports bind their implemented sources. Omi paths below are relative to its
pinned checkout at `f42089f53c8010dd971b3702ece05a231c9c0c66`.

| Source | SHA256 |
| --- | --- |
| `docs/ble-protocol.md` | `3e1f895f0d1624a9ce869935f436020a1a7b94c4b7b0d27894b8f25966837be4` |
| `firmware/a04/ARCHIVE.md` | `e964fb45d89b469859af5fb774159dde047884411f925805f0bf18eadc5b8db4` |
| `firmware/a04/include/aura_journal.h` | `837090ad39cdbe68dcb07b6e6c03915714dced97c0c34c825910324be84123c9` |
| `firmware/a04/src/aura_journal.c` | `775c8226fa909607fc6d4605f52081c9c1f7b08e9f8cf36e9a59634fec0a0b1e` |
| `firmware/a04/STORAGE.md` | `043197283c917ff0a6e22eb67f605288aa5d2b2b236d28af12c26a630ef78035` |
| `firmware/a04/RELEASE-AUTH.md` | `86c909940322160d20d1a11796ac08c1f32e623e11d4989c591ab90d01f82f7d` |
| `firmware/a04/bench/PROTOCOL.md` | `7fcdd0fcf285b7866f881fdc61d6d9b980fe585faed4a5f12ef258deb29731cf` |
| `companion/src/aura_companion/protocol_v2.py` | `7ff7d66d4b03b00bccccedbb5dd3ed4922f56cc6d4857ccf63010128d269b54d` |
| `companion/src/aura_companion/release.py` | `9be977539be073cef123e5170fd09a8c3f911bdd1b1df4d49317cce67ad06fdc` |
| Omi `app/lib/services/wals/recording_transfer_coordinator.dart` | `196c8413123750d6b7b5abe39414dd95bbaf0d66154a9ba7871ed0d227f1b291` |
| Omi `app/lib/services/devices/transports/native_ble_transport.dart` | `855e90cce8ecd4aa316c2dec499154a86e6534b5b4887abacea666936dae8c11` |
