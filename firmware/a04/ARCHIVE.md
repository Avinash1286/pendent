# AURA A04 capture archive — experimental wire revision 3

This is the authoritative byte contract for the portable C writer in `src/aura_archive.c` and Python reader/receiver in `companion/src/aura_companion/protocol_v2.py`. The C writer is attached to the real libopus encoder. Host fixtures exercise file flush/retry, cross-language receipts, durable SQLite import and independent audio decoding. The Zephyr build links the same writer through the [packed journal](NAND-JOURNAL.md) and volatile synthetic NAND. A separate W25N01GV SPI adapter is compiled but not physically initialized. BLE, ownership and physical device qualification remain outside this archive layer.

Revision 3 deliberately rejects the previously published experimental revision-2 records and the `AOC1` codec-debug container. Keeping the Python module name `protocol_v2` does not imply wire compatibility. No converter is provided. An existing receiver database may receive the additional `seal_wire` column, but old manifests/identities are never relabeled or rebound; importing revision 3 over an old identity fails. Preserve old databases and use a separate revision-3 database. A03 firmware and its published binaries are unchanged.

## Serialization and identity

One `.aura` file holds exactly one immutable manifest, contiguous audio/bookmark records, and one terminal seal followed immediately by EOF. An explicitly requested recovery can instead preserve a complete prefix from an unsealed/torn file. All integers are unsigned little-endian, with no C alignment or struct padding. Every record has a 4-byte trailing CRC32: reflected polynomial `0xEDB88320`, initial value `0xFFFFFFFF`, final XOR `0xFFFFFFFF`, over every preceding byte in that record. This is the same result as Python `zlib.crc32`.

The device ID and capture ID are opaque, nonzero 16-byte values. Their combination identifies a capture. Reusing that combination with changed metadata or packet bytes is a conflict. The test harness uses fixed synthetic IDs. Secure provisioning, persistent capture-ID generation and authenticated device ownership remain integration work; CRC and SHA256 detect inconsistency, and do not establish authenticity against an attacker who can rewrite the archive.

Manifest `AUR3`: **68 bytes**, Python body `<4sBBBB16s16sIHHIBBBBQ>` plus CRC.

| Offset | Bytes | Field | Accepted values |
|---:|---:|---|---|
| 0 | 4 | Magic | `AUR3` |
| 4 | 1 | Wire revision | 3 |
| 5 | 1 | Codec | 1 PCM16, 2 Opus; C writer currently emits Opus |
| 6 | 1 | Channels | 1 |
| 7 | 1 | Flags | 0 |
| 8 | 16 | Device ID | Nonzero |
| 24 | 16 | Capture ID | Nonzero |
| 40 | 4 | Sample rate | 16000 Hz |
| 44 | 2 | Samples per frame | 160 or 320 |
| 46 | 2 | Encoder pre-skip | 40 for Opus profile 1; 0 PCM |
| 48 | 4 | Configured bitrate | 32000 for Opus; 0 PCM |
| 52 | 1 | Codec profile | 1 for Opus; 0 PCM |
| 53 | 1 | Complexity | 3 for Opus; 0 PCM |
| 54 | 1 | Time source | 0 unknown, 1 synchronized |
| 55 | 1 | Reserved | 0 |
| 56 | 8 | Start epoch milliseconds | 0 iff time source is 0; otherwise 1–4102444800000 |
| 64 | 4 | CRC32 | Manifest bytes 0–63 |

Profile 1 uses upstream libopus 1.6.1, fixed-point, mono 16 kHz, restricted low-delay application, wideband maximum, 32 kbps constrained VBR, complexity 3, DTX disabled and in-band FEC disabled. The encoder queries its lookahead; this profile requires the measured value 40. Codec changes require an explicit new profile/contract, not a silent control change. Configured bitrate is not a constant packet size or measured bitrate promise.

## Audio and bookmarks

Packet `AFR3`: **26 + payload bytes**, Python header `<4sBBIQHH>` plus payload and CRC.

| Offset | Bytes | Field | Meaning |
|---:|---:|---|---|
| 0 | 4 | Magic | `AFR3` |
| 4 | 1 | Revision | 3 |
| 5 | 1 | Kind | 1 audio, 2 bookmark |
| 6 | 4 | Sequence | Starts at 0; increments for both kinds |
| 10 | 8 | Sample offset | Encoded timeline for audio; source timeline for bookmark |
| 18 | 2 | Sample count | Manifest frame samples for audio; 0 bookmark |
| 20 | 2 | Payload byte count | 1–1275 audio, 0 bookmark; Opus profile additionally requires at least 2 |
| 22 | variable | Payload | Encoded audio, or empty bookmark |
| 22 + payload size | 4 | CRC32 | Complete header and payload |

Audio offsets must equal the sum of all previous audio sample counts. Bookmark records consume sequence numbers but no encoded samples or bytes. A bookmark offset may be at the source end; it cannot exceed the encoded samples already committed when the bookmark is stored. During finalization it must also be at or before the final source end. No wall-clock inference is made when capture time is unknown.

All sample offsets, pre-skip, end-trim and durations in this archive use **16 kHz source units**, including Opus. Source sample 8000 is 0.5 seconds. Audio frame 0 starts on the encoded decoder timeline and includes the initial encoder lookahead. The decoded source timeline begins after pre-skip.

For Opus profile 1, framing checks require mono CELT narrowband/wideband TOC configurations 16–23, packet code 0 (one frame), and matching 10/20 ms duration. The full entropy/audio decode must still succeed before derived media is published; a CRC-valid packet is not automatically valid audio. PCM payload length is exactly `sample_count * 2`.

## Terminal seal and exact duration

Seal `ASE3`: **120 bytes**, Python body `<4sBBH16s16sIIQQQQHH32s>` plus CRC.

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 4 | Magic `ASE3` |
| 4 | 1 | Revision 3 |
| 5 | 1 | Status: 1 finalized, 2 interrupted |
| 6 | 2 | Reserved 0 |
| 8 | 16 | Device ID |
| 24 | 16 | Capture ID |
| 40 | 4 | Next sequence / total audio and bookmark records |
| 44 | 4 | Audio packet count |
| 48 | 8 | Total encoded payload bytes |
| 56 | 8 | Total encoded samples |
| 64 | 8 | Retained source samples |
| 72 | 8 | Original source samples; `UINT64_MAX` means unknown |
| 80 | 2 | Effective pre-skip |
| 82 | 2 | End-trim |
| 84 | 32 | Packet-prefix SHA256 chain |
| 116 | 4 | CRC32 |

Every count, identity and prefix digest must match the records actually read. For both statuses, `source_samples + pre_skip + end_trim == encoded_samples`. Nonempty captures use the manifest's pre-skip; empty captures use 0. End-trim is less than one configured frame.

**Finalized** means the encoder flushed its lookahead and partial frame, the terminal metadata committed, and the exact original source sample count is known. `original_source_samples == source_samples`. All source bookmarks must fit within that length. The fixture's original 120847 samples become 120960 encoded samples, then remove 40 initial and 73 final samples to recover exactly 120847.

**Interrupted** means only the complete committed prefix is retained. End-trim is 0; original source duration is unknown. The retained decodable duration is `encoded_samples - pre_skip`. The unencoded partial input and encoder lookahead are unavailable. If audio flush completed but its terminal seal was lost, padded tail and actual source cannot be distinguished; retained length must not be presented as the exact original recording length. A preserved bookmark within the unavailable final lookahead is retained as evidence and marked unavailable when its offset exceeds retained source length.

The reader defaults to strict complete finalization. `allow_interrupted=True` is required for an interrupted seal or recovery without a complete seal. A complete CRC-bad record, unsupported profile, impossible header, sequence gap, wrong identity/digest or any data after a complete seal is an error even in recovery mode. A recognizable incomplete final record is discarded whole. Recovery synthesizes a deterministic interrupted seal in memory; it does not modify the input file. `discarded_tail_bytes` reports discarded bytes, and the file SHA256 includes those bytes. There is no resynchronization past corruption.

## Chain and receipts

Let `M` be the exact manifest including its CRC, `P_i` each exact packet including CRC, and `S` the exact seal including CRC:

```text
H_0 = SHA256(M)
H_(i+1) = SHA256(H_i || P_i)
S.packet_prefix_sha256 = H_N
terminal_digest = SHA256(H_N || S)
```

An open receipt uses `H_N`. A terminal receipt uses `terminal_digest`, binding status, exact source duration, pre-skip, end-trim and unknown-original-length semantics. The terminal digest is the immutable source `archiveDigest` used by the importer. The SHA256 of actual file bytes is separate evidence: a recovered file's synthesized terminal seal is not in those original bytes.

Receipt `ACK3`: **94 bytes**, Python body `<4sBB16s16sIQQ32s>` plus CRC.

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 4 | Magic `ACK3` |
| 4 | 1 | Revision 3 |
| 5 | 1 | Status: 0 open, 1 finalized, 2 interrupted |
| 6 | 16 | Device ID |
| 22 | 16 | Capture ID |
| 38 | 4 | Next sequence |
| 42 | 8 | Committed encoded payload bytes |
| 50 | 8 | Committed encoded samples |
| 58 | 32 | Open prefix or terminal digest |
| 90 | 4 | CRC32 |

A reader's receipt describes validated expected bytes; it is **not** a durable ACK. `DurableReceiver.import_archive()` returns its receipt only after a single SQLite transaction has verified EOF and the immutable file digest and successfully committed all packets and the seal. It checks an existing saved prefix once, then streams the import in linear time. Per-packet `accept()` validates the whole saved prefix before either a fresh or replayed ACK; that more expensive interface is not used for a long file import.

SQLite uses an on-disk database, DELETE rollback journaling and synchronous EXTRA. Empty and in-memory paths are refused. One serialized local owner is assumed. Actual persistence requires the OS, filesystem and storage device to honor flushes; keep database and rollback journal together outside cloud-sync/network folders. Neither an ACK nor this hash provides permission to delete the device's only copy. Durable host-ACK storage and device reclamation are future integration work.

Both terminal statuses freeze the identity within one database. A later finalized archive cannot replace a previously sealed interrupted prefix there. The local importer can preserve them as separate explicit revisions by naming the database and derived files with device ID, capture ID and terminal digest. Revision promotion/reconciliation is not implemented; do not quietly overwrite a recovered recording.

## C integration and retry ownership

Initialize `aura_opus_capture` with `aura_archive_opus_commit` and the writer pointer; use the encoder's queried lookahead in `aura_archive_begin`. Begin must commit before pushing input. The callback receives an absolute file offset and exact record bytes. It returns zero only when those bytes are durable at that offset. After an uncertain/partial write it must accept exactly the same offset/bytes idempotently; appending again is incorrect. The portable host callback writes at that offset, flushes C stdio, and calls `_commit`/`fsync`.

Audio failures are retried through `aura_opus_retry` (or repeated finish while closing). This lets both codec and archive observe the same single committed packet. Calling `aura_archive_retry` directly for pending audio is refused. Manifest, bookmark and terminal failures use `aura_archive_retry`. Counters, chain, receipt and offset advance only after callback success; no receipt is available while a record is pending. A differing retry conflicts. New input waits while encoded output is pending. Preserve the codec's `consumed` value to avoid resubmitting PCM that was already copied.

Normal close calls `aura_opus_finish`, then `aura_archive_finalize` with the returned seal. `aura_archive_interrupt` seals an existing preserved unflushed prefix and records unknown original length. This function does not reconstruct C writer state from NAND after reboot. Reinitialization invalidates the old in-memory writer; never use it as a capture rollover until the previous capture is safely closed or retained for recovery. All calls have one serialized owner; no ISR or thread-safety guarantee is provided.

## Python reader integration

```python
archive = read_archive(path, allow_interrupted=False)
with DurableReceiver(database_path) as receiver:
    committed_receipt = receiver.import_archive(archive)
for packet in archive.iter_packets():
    # Stream into a temporary decoder/container; do not publish yet.
    ...
# Iterator exhaustion rechecks the input hash and termination.
# Publish derived media atomically only after full decode and exact duration checks.
```

`VerifiedArchive` exposes `capture`, actual `seal` or `None`, always-present `termination`, `status`, `source_samples`, `original_source_samples`, `end_trim`, `duration_seconds`, `receipt`, `sha256_hex`, `file_bytes`, `discarded_tail_bytes` and `iter_packets()`. Reading and iteration use bounded per-record memory, not a full-file packet list. The importer copies input into its own bounded temporary file to establish a stable snapshot before publication.

When exporting Ogg Opus, pre-skip and granule positions use 48 kHz units: multiply these archive sample counts by 3. Use the terminal source length to set the last granule, so final padding is removed. [RFC 7845 sections 4.2–4.4](https://www.rfc-editor.org/rfc/rfc7845.html#section-4.2) define those container timing rules. [RFC 6716 section 3.1](https://www.rfc-editor.org/rfc/rfc6716.html#section-3.1) specifies the Opus TOC/frame representation. The [official encoder API](https://opus-codec.org/docs/opus_api-1.6/group__opus__encoder.html) supplies the actual encoder and sizing contract; no codec source was copied from Omi.

## Bounds, evidence and remaining work

The C writer uses no heap and keeps at most a 1301-byte pending record. Its object is 1504 bytes on the tested 64-bit host and 1496 bytes on ARM. The current DK integration probe includes 16 KiB of synthetic RAM NAND; [arm-resources.json](verification/arm-resources.json) records actual ELF symbols and hashes. SHA256 scratch is bounded, and compiler stack reports are lower bounds, not a runtime high-water measurement. The same ARM probe reserves a 32 KiB encoder arena and a 48 KiB usable codec thread stack, with guard/alignment overhead. This probe does not establish the complete wearable memory budget or physical PDM/NAND/BLE/OTA operation.

Default encoded-payload quota is 256 MiB in C and Python. Audio plus bookmark records are limited to 1000000; packet sequences 0–999999 are accepted, terminal next sequence may be 1000000. A 20 ms capture therefore needs rotation before about 5.56 hours (about 2.78 hours for 10 ms), earlier if bookmarks consume records or storage fills. Segmented continuous-capture rollover is required future work. Python permits a caller-specified positive payload limit up to 1 TiB; individual payloads remain at most 1275 bytes and record-count limits still apply. The local CLI imposes its separate total-file bound. A file over quota fails without advancing the durable receipt.

`scripts/build.ps1 -Mode host` runs the real C codec/archive harness, Python framing/receiver/archive tests, and independent FFmpeg roundtrip. [archive-roundtrip.json](verification/archive-roundtrip.json) and [archive-host.txt](verification/archive-host.txt) bind fixture results. C fixtures inject partial/uncertain writes at manifest, audio, bookmark and seal and verify exact retry offsets/bytes. Tests cover malformed profiles/seals, CRC errors, torn tails, conflict after terminal seal, replay after restart, file changes before publication, process exit before COMMIT and refusal of temporary databases. Ten- and twenty-millisecond finalized recordings decode to exactly 120847 source samples; the interrupted fixture retains 120600 samples with original duration unknown.

This is a working experimental archive port, not a deployed A04 capture stack. Still required: actual PDM input/queue and overflow policy, physical qualification of the implemented NAND journal/ECC/recovery and media-full behavior, persistent device ACK/reclamation, BLE fragmentation/flow control and mobile background lifecycle, secure identity/ownership, signed OTA and power-failure integration. Device execution, encode deadlines, concurrent storage/radio behavior, stack high-water, current draw and acoustic/transcription quality remain unmeasured. Live/offline capture, controlled continuous capture, memory, tasks, search, context export, speech and phone/earbud interactions remain the full product objective.

The separate staged initializers and journal receipt contract are documented in [NAND-JOURNAL.md](NAND-JOURNAL.md). Existing durable initializer semantics above are unchanged. Staged callback acceptance never authorizes a receipt; only the independently replayed and fully read-verified NAND page end does. An export-only interrupted seal remains distinct from a physical local terminal receipt.
