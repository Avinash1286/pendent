# A04 packed NAND journal

Status: **implemented and host-model tested; cross-built for Cortex-M4; not physically tested**. The portable journal connects real Opus 1.6.1 to canonical [AUR3 records](ARCHIVE.md). The W25N01GV command core and Zephyr SPI adapter are compiled alongside it. Existing A03 source and release artifacts remain unchanged.

## Device and ownership contract

The W25N01GV has 1024 blocks, 64 pages per block, 2048 main bytes and 64 spare bytes per page. The adapter uses buffer mode and internal ECC, checks WEL/BUSY/P-FAIL/E-FAIL, verifies full programmed main pages, and reports corrected versus uncorrectable reads. Factory exclusion checks main byte 0 and spare bytes 2048/2049 on **both pages 0 and 1**, with ECC disabled for raw marker inspection, before re-enabling ECC. It reads the A5 bad-block mapping table and reserves both logical and physical endpoints of enabled entries; it does not modify the LUT. See the [manufacturer Rev.R datasheet mirrored by Mouser](https://www.mouser.com/datasheet/2/949/Winbond_Electronics_09072023_W25N01GV_Rev_R_070323-3313374.pdf), sections 7.3, 8.2 and 10.

`aura_w25n01gv_zephyr_init` takes a caller-supplied `spi_dt_spec`. No final board node, chip-select, microphone or GPIO assignment is invented here. One mutex serializes each complete NAND operation, including its cache accesses. Journal/codec/archive calls also require one serialized owner outside an ISR. The owner must establish stable power before cold initialization and bound the SPI transport timeout. Hardware timings and electrical power-cut behavior remain unmeasured.

## Staging and commit boundary

Use the separately named `aura_opus_init_staged` and `aura_archive_begin_staged` initializers with `aura_journal_stage`. Callback success means bounded RAM acceptance. The original durable initializers retain their original callback contract. **A staged archive writer cannot issue a receipt.** The journal replays every accepted canonical record into its own validator; it never copies the outer producer state, which has not yet applied the callback result. This matters when one Opus push emits many records or a capacity flush happens before the current record is appended.

A page becomes committed only after Program Execute completes (or uncertain completion is resolved), a full 2048-byte ECC-readable readback exactly matches, and its expected page CRC is present. The independent replay state at that exact page end then becomes the committed snapshot. A P-FAIL stops the active capture even if bytes happen to match. The page is never reprogrammed. Prior verified pages remain available after reopen and full verification.

Records are packed without crossing pages. Flush triggers are capacity, first audio, explicit flush, the 400 ms service deadline, and a terminal seal. Except for the intentional first-audio page, there is no one-small-Opus-packet-per-page policy. Call `aura_journal_service` once **before** starting a staged producer; an uninitialized service clock is rejected. Continue calling it with monotonic wall milliseconds while recording and paused. The embedding scheduler must guarantee its cadence: this synchronous library cannot force a deadline while its owner is blocked/asleep. A timestamp preceding actual record arrival makes the flush conservative. Input copied into a partial PCM frame, encoder lookahead, pending packets and staged pages may be lost on power failure.

Typical lifecycle:

```c
// Caller-owned bounded objects and correctly aligned encoder arena.
aura_journal_mount(&journal, initialized_nand_io);
// Preparation may be scheduled before a capture; RETRY_PREPARE inspects one
// candidate per call and permits trying another. All return values are checked.
aura_journal_prepare(&journal);
aura_journal_service(&journal, monotonic_ms);
aura_opus_init_staged(&codec, arena, arena_bytes, 20,
                      aura_archive_opus_commit, &writer);
aura_archive_begin_staged(&writer, &new_unique_manifest,
                         aura_journal_stage, &journal);
// Push PCM; preserve consumed/pending semantics. Service while paused too.
aura_opus_finish(&codec, &seal);
aura_archive_finalize(&writer, &seal); // flushes terminal page/checkpoint
// Only the journal can return the physically verified receipt.
aura_journal_receipt(&journal, capture_index, receipt);
```

The snippet omits error branches for readability. Production callers must stop accepting PCM on media-full or an unresolved I/O fault, retain the exact `consumed` count, and use the codec's pending retry route only for retryable staging/preparation failures. An uncertain programmed page is never retried through Program Execute. Reboot always allocates a new ID and block; it does not resume an old Opus encoder or the unused pages of a pre-boot partial block.

## Exact block and page format

All multibyte fields are little-endian; wire bytes never depend on C struct layout. CRC32 is the AUR3 reflected IEEE CRC. Each block belongs to one capture. Page 2 precedes all data writes, and page 63 is last. Each page has at most one program attempt after a successful erase, in increasing order.

| Pages | Role |
|---|---|
| 0–1 | Reserved; never journal-programmed |
| 2 | `A4NH` identity/continuation header |
| 3–62 | Up to 60 `A4ND` packed data pages |
| 63 | `A4NC` checkpoint |

Header/checkpoint metadata occupy the first 256 bytes, with CRC32 at 252; bytes 256–2047 are FF when written. Both start with magic at 0, version 1 at 4, zero at 5, size 256 at 6, and physical block number at 8.

`A4NH`: previous block uint32 at 12 (`FFFFFFFF` for first), part uint32 at 16, starting archive byte offset uint64 at 20, device/capture IDs at 28, exact 68-byte AUR3 manifest at 60, 94-byte preceding committed-state declaration at 128 (all zero for first), zero reserved bytes 222–251. The declaration is metadata, never an old-audio receipt.

`A4NC`: part uint32 at 12, valid data-page count uint16 at 16, zero at 18–19, committed archive byte end uint64 at 20, 94-byte page-end declaration at 28, zero bytes 122–251. It closes either a full block or a terminal short capture.

`A4ND`: magic at 0, version 1 at 4, zero at 5, header size 64 at 6, physical block uint32 at 8, part uint32 at 12, archive byte offset uint64 at 16, IDs at 24, payload length uint16 at 56, record count uint16 at 58, zero uint32 at 60. The payload at 64 holds up to **1980 bytes** of complete manifest/audio/bookmark/seal records. Unused payload bytes are FF; the last four bytes at 2044 are the CRC over bytes 0–2043. Canonical record CRC, sequence, sample offsets, manifest fields and SHA256-chain/seal semantics are independently replayed.

## Mount, recovery and export

Mount validates bounds **1–1024 before indexing** and reads factory/LUT inventory through the initialized backend, plus header/checkpoint prefixes. It never scans all 128 MiB of source audio during startup. A completely factory-good 1024-block portable-model mount performs **2048 reads of 256 bytes = 524288 bytes, zero payload reads, zero programs and zero erases**. These portable counters exclude the adapter's separate raw-marker/LUT command scan. The test with 128 short captures on 129 blocks performs 258 metadata reads/66048 bytes and zero payload reads. Device wall-clock startup is unmeasured.

Existing entries are `UNVERIFIED` after mount. Neither metadata nor a saved checkpoint can authorize their receipt. Full verification checks every data page in each associated block, including every slot after the first blank, unreadable or torn page; it also checks all continuation headers and terminal checkpoints. A single torn final page can terminate an interrupted prefix. Later nonblank/unreadable material, a valid continuation after a gap, a contradictory record, or a valid checkpoint declaring more committed data than the readable prefix is **corruption**. Corrected ECC is usable and counted; uncorrectable bytes cannot establish a commit.

A valid checkpoint can associate a damaged identity header with a known capture; that capture is marked faulty and export fails. Unidentifiable metadata/candidates remain quarantined and increment `unassociated_blocks`. An explicitly interrupted prefix does **not** prove that these unassociated blocks contain no additional source audio. They are preserved for a future forensic/recovery tool; no normal finalized capture or deletion authority is inferred from them. This is a stated recovery limit of the bounded port.

`aura_journal_export` first fully verifies, then streams and verifies again. Its destination must stay temporary until success, because a later corrupt page or I/O failure can invalidate earlier emitted bytes. An unsealed physical prefix receives an export-only `ASE3` interrupted seal with original duration unknown. That synthesized seal never changes the local physical-prefix receipt into a terminal NAND receipt. Export failure invalidates the cached verification state.

A header-blank candidate is eligible for erase only after **all 64 main pages** are fully readable and FF. A successful fresh erase and a second full FF check are mandatory, even if an interrupted all-FF program attempt left no visible data. Lost/partial erase completion quarantines the candidate for the current mount; after reboot it is eligible only if the full blank check and a new erase succeed. The adapter applies its own blank-before-erase guard too. At most one candidate is inspected per `prepare` call. No populated or unidentifiable source block is erased.

## Capacity costs and product gap

The fixed catalog holds **128 captures**. One short capture consumes a 128 KiB block until a future reclamation design exists. A 20 ms one-packet capture uses two data pages (first audio, then terminal), one identity and one checkpoint; the **58 unused data pages = 118784 bytes** are stranded, in addition to reserved and metadata capacity. Across 128 such captures, those short tails alone strand **15204352 bytes (14.5 MiB)**; all 128 blocks consume 16 MiB and exhaust the catalog even if 896 physical blocks remain. This cost is intentional and tested, not the finished product's storage policy.

For a full block, 60 × 1980 = **118800 archive bytes** fit before record-boundary padding, out of 131072 main bytes (90.64%). The 7.553 s real speech fixture packs 378 Opus packets plus manifest/bookmark/seal into **22 data pages, 24 total programs, 37040 archive bytes**. It still owns the rest of its final block. Worst-case legal 1275-byte Opus packets require one 1301-byte record per page; tests use that case to cross block boundaries and fill media.

There is **no populated-block reclamation**, including after host acknowledgement, and no catalog eviction or automatic format. Media-full stops recording and preserves prior audio; verified receipts and export remain available for synchronization. Persistent authenticated host ACK handling, reclamation, capture/catalog rotation, and recovery of unassociated material are full-product requirements still outstanding.

## Tested evidence

Run `scripts/build.ps1 -Mode all` with the existing pinned toolchain and FFmpeg. The host model tracks cells, once-per-page attempts across reset, ordering, all six factory markers, remapped exclusions, corrected/uncorrectable ECC, program and erase failures, partial writes/erases and lost completion. Short-capture cuts cover each identity/audio/tail/checkpoint program at seven byte boundaries. Further tests cover first-audio/service/finish flushes, capacity snapshots before producer callback completion, malformed canonical records/padding, gaps with later material, checkpoint claims, damaged continuation identities, unassociated quarantine, no overwrite, media-full and the 128-capture bound.

[Journal host transcript](verification/journal-host.txt) and [roundtrip evidence](verification/journal-roundtrip.json) bind tested source hashes. The latter runs real Opus through NAND model → power interruption/reopen → AUR3 export → existing Python 3.12 receiver/SQLite restart and replay → independent FFmpeg decode:

| Case | Decoded source samples | Original duration | Local receipt |
|---|---:|---|---|
| Finalized then reboot | 120847 | Exact | Physical terminal |
| Buffered tail lost | 116440 | Unknown | Physical open prefix |
| Partial final-page program | 116440 | Unknown | Physical open prefix |
| Full page, lost completion | 120600 | Unknown | Physical open prefix |

All four have 11.919 dB waveform SNR against the available source prefix. This is a deterministic regression metric, not perceptual/acoustic qualification. The portable host journal context is 35920 bytes; the test-only sparse NAND model is 666712 bytes and is never part of embedded firmware. The final ARM probe uses **194356 bytes flash (18.54%) and 148864 bytes RAM (56.79%)**, including a **35880-byte journal**, **4464-byte Zephyr NAND adapter**, and **16384-byte synthetic RAM NAND**. [Actual ARM ELF resources](verification/arm-resources.json) report these objects, linked flash/RAM and source hashes. The command-level simulator additionally passes **20 groups**, including two combined driver/journal cases; see [its transcript](verification/w25n-command-tests.txt) and [adapter details](W25N-ADAPTER.md). The 48 KiB codec stack reservation has not been measured on silicon.

Physical PDM/SPI integration, electrical NAND power failures, encode/storage deadlines, concurrent BLE, mobile lifecycle, authenticated ownership, signed OTA, current/battery measurements, and the complete live/offline context workflows remain unverified. No host file, sparse RAM model, cross-build or command simulator is described as a physically functioning wearable.
