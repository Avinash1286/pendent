# A04 capture identity and authorized storage release

The serialized [storage owner](include/aura_storage.h) combines the existing journal, authenticated owner commands and two-block control ledger. It durably reserves capture identities and releases one explicitly authorized, finalized capture while preserving other recordings. This implementation is exercised on the host NAND model and linked into the unprovisioned DK resource probe. **No production populated-audio erase adapter, key enrollment or complete wearable application is connected.**

The [Python release outbox](../../companion/RELEASE.md) rereads the committed receiver database and requires exact-capture permission before durably storing an RLS1 command. A receipt alone, radio transmit completion or successful upload cannot authorize this controller to erase a recording.

## Integration contract

One owner serializes all journal/control/media operations. The caller provides trusted device ID, storage incarnation, owner ID/generation, a 32-byte secret, two fixed control blocks, private journal/control contexts and a **45408-byte** caller snapshot. No default enrollment, key generation/storage, discovery, formatting-on-error, ownership transfer or floor reset exists. The driver configuration and contexts must remain private; this is an API ownership rule, not a memory protection boundary.

On real W25N integration, configure its immutable control pair immediately after cold initialization and before any ordinary callback. Use the separate restricted control view for the ledger and ordinary data view for the journal. [W25N-ADAPTER.md](W25N-ADAPTER.md) defines those checks. The ordinary driver's erase remains blank-only. The separate `erase_released` callback is currently supplied only by host tests; leaving it null rejects a new release without reserving a sequence. A future real callback must independently exclude control/factory/LUT blocks, check fresh successful erase/status/full readback, preserve program-order guards and run under the same complete-operation serialization.

`aura_storage_provision` requires every readable, nonbad data/control main page to be blank. It cannot reset an existing layout or repair uncertain authority. The authority is copied before scratch reads. `aura_storage_open` loads and validates the control state before mounting the journal; pending release extents are excluded before catalog discovery. Any observed owned allocation generation above the persisted reservation floor stops opening.

## Capture and release sequence

1. `prepare_capture` copies and validates settings, rejects output buffers overlapping private contexts, increments the durable reservation floor, derives the capture ID and binds the exact manifest to the next journal start. IDs supplied in settings are replaced with trusted IDs. The generation is reserved **before** any journal header is programmed. Cancellation, a failed start and reboot burn that reservation rather than reuse it.
2. Record through the existing recorder/journal using the returned manifest. Version-2 `A4NH` headers and `A4NC` checkpoints carry the storage incarnation and uint64 allocation generation. Version-1 journal reading remains available; legacy captures do not qualify for this release path.
3. The receiving app commits the exact finalized archive. Its explicit owner-approved release outbox verifies the stored source and produces the authenticated RLS1 envelope, with a sequence exactly one greater than its trusted floor.
4. `request_release` authenticates that envelope, independently replays the complete local source and checks the exact terminal ACK, owned generation and derived capture ID. It persists the exact envelope, manifest and original block extents/header hashes in a **GRANTED** snapshot before any audio erase callback. Every target remains excluded from allocation and catalog visibility.
5. `release_step` handles at most one target block. It scans all main pages, including beyond torn/blank gaps, and rejects intact contradictory header/checkpoint/data identities or material in reserved areas. Then it invokes the privileged callback and requires every main page to read ECC-clean FF. On reboot the still-fenced targets may be erased again; no earlier grant can identify a coherent newer capture as its own.
6. Only after all targets have passed does a durable **IDLE** snapshot remove their fences. A successful remount makes their space reusable. The exact last RLS1 and replay floor remain persisted, making an identical pending/completed retry idempotent. Different replayed, skipped, interrupted or open-capture commands are refused.

`capture_id = SHA256("AURA-A04-CAPTURE-v1\0" || device_id[16] || incarnation[16] || generation_u64_le)[0:16]`. A nonzero, independently trusted incarnation separates storage lifetimes. This is deterministic collision-resistant naming; it is not authentication by itself.

## AST1 snapshot bytes

Integers are little-endian. The enclosing control ledger supplies its page CRCs and linked commit hashes.

| Offset | Bytes | Meaning |
|---|---:|---|
| 0 | 4 | `AST1` magic |
| 4 | 1 | Version 1 |
| 5 | 1 | Phase: 0 IDLE, 1 GRANTED |
| 6 | 2 | Zero |
| 8 / 24 / 40 | 16 each | Device / storage incarnation / owner IDs |
| 56 / 64 / 72 | 8 each | Owner generation / capture reservation floor / release sequence floor |
| 80 | 182 | Exact last RLS1; all zero only at floor zero |
| 262 | 2 | Number of fenced extents |
| 264 | 68 | Exact capture manifest; zero in IDLE |
| 332 | 20 | Zero |
| 352 onward | 44 each | Physical block u16, contiguous part u16, original full-page header SHA256[32], allocation generation u64 |

IDLE is exactly 352 bytes. GRANTED is exactly `352 + count*44`, with unique in-range non-control targets, matching owner/device namespace and one generation. The caller reserves the 1024-entry upper bound (45408 bytes); the actual grant is bounded by the usable data-block count. The last command MAC is checked again on state load. The public ledger integrity hashes do not authenticate arbitrary raw NAND rewrites or prevent whole-device rollback.

## Verification and limits

Run `./firmware/a04/scripts/build.ps1 -Mode all`. [storage-roundtrip.json](verification/storage-roundtrip.json) binds the actual tested code, executable hashes and results; [storage-host.txt](verification/storage-host.txt) records the fault cases. The integration harness encodes real speech through the C recorder/Opus/journal, hands the archive to a reopened Python SQLite receiver and persisted release outbox, then sends those exact command bytes back to C. It checks recovery, completed retry, reuse with a fresh generation, another capture's byte identity before/after reuse, and independent FFmpeg decoding. Public deterministic fixture keys are used only by tests.

Fault cases cover grant/erase/completion interruption, invalid commands, reservation cancellation, more than 128 successive release cycles with an unacknowledged recording retained, wrapped extents, changed allocations, surviving foreign identities and caller-buffer aliasing. They model operations and power cuts; no physical microphone, NAND, radio or phone lifecycle was exercised by this harness.

An ambiguous newer control write can deliberately block further work even while older bytes survive. No trusted recovery protocol, control-block wear rotation or replacement of failed control blocks is implemented. Full raw-media rollback or an entirely unidentifiable replacement is outside the guarantees of the serialized operation model. Secure enrollment, key custody, encryption, authenticated device completion, BLE/mobile integration and measured latency/endurance remain required. The 128-live-capture catalog limit remains; modeled authorized release now permits successive reuse beyond that many lifetime captures. Unacknowledged recordings are preserved and full storage stops new capture.
