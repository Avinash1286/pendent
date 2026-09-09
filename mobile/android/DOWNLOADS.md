# A04 durable download owner

`DownloadStore` is the Android storage boundary between validated transfer replies
and the existing local recording library. It uses actual Android SQLite, private
app storage and filesystem synchronization. It does not connect to Bluetooth,
authenticate a device, run a background service or authorize erasure. The current
Activity still exposes file import; a GATT recovery coordinator must call this
owner before pendant-to-phone download becomes a user-facing capability.

## One canonical source validator

The Kotlin `ArchiveStream` validates AUR3 manifests, AFR3 audio/bookmark records
and ASE3 seals incrementally. `AuraArchive.verify` and packet visitation use that
same engine. Each input chunk is at most 256 bytes and a partial record occupies
at most 1,301 bytes. Complete records are emitted with their exact wire offsets;
the validator does not retain the entire recording or synthesize a missing seal.

A snapshot distinguishes received bytes from the last validated complete-record
boundary. It exposes a seal before explicit EOF, but marks completion and returns
the whole-file digest only after `finish()`. A validation or callback error
poisons that parser instance. A retained prefix is replayed once; hash counters
from unverified metadata are never accepted as a replacement for source bytes.

## Source and resume state commit together

The private `noBackupFilesDir/a04-downloads/downloads.sqlite` database stores:

- `downloads`: immutable selected-source descriptor, committed byte offset,
  record count, exact derived receipt and completion marker.
- `records`: one exact manifest, packet or seal per row, with a separate ordinal
  and absolute wire offset. A seal is not confused with an AFR sequence number.

A process reservation is acquired before opening `.owner.lock`, and the
filesystem lock is held for the session lifetime. A rejected second owner never
opens and closes another channel for the same lock. This follows Android's
[FileLock platform guidance](https://developer.android.com/reference/java/nio/channels/FileLock),
which warns that closing a different channel can release a process's existing
locks. Identity tokens prevent stale cleanup from releasing a newer owner.
SQLite uses a rollback journal and `synchronous=EXTRA`, with
FULL-or-stronger behavior checked. Complete records and their updated resume
metadata enter the same transaction. The public committed offset advances only
after `endTransaction()` succeeds. No separate audio-file/checkpoint rename race
exists in this staging store.

The stream may receive the start of the next record in the same READ. Those
partial bytes stay in RAM. Closing or losing the process discards that partial
record, while retaining every committed database row. A failed or uncertain
transaction faults the session; it cannot continue using a parser that has
advanced beyond the database. Reopening replays the authoritative rows and checks
exact ordinals, offsets, one-record row boundaries, receipt and metadata count.
Contradictory or corrupt data is retained and rejected, never truncated, reset,
repaired or silently treated as an earlier prefix. The corruption handler does
not delete the database.

## Stable source identity

The local revision key is SHA-256 of a fixed 211-byte `ADS1` descriptor:

| Offset | Bytes | Field |
| ---: | ---: | --- |
| 0 | 8 | `ADS1`, version 1, three zero reserved bytes |
| 8 | 16 | Storage incarnation |
| 24 | 68 | Exact selected manifest |
| 92 | 94 | Exact physical ACK3 |
| 186 | 8 | Physical byte length, unsigned little-endian |
| 194 | 8 | Export byte length, unsigned little-endian |
| 202 | 1 | Derived-seal flag |
| 203 | 8 | Allocation generation, unsigned little-endian |

Device/capture identities are inside the manifest and physical receipt. The
validated selection already checks generation-derived identity and framing.
Handles, transactions and connection generations are volatile and are excluded
from this key. A changed source descriptor creates a separate retained revision;
it does not overwrite the earlier recording. This hash names local data and
does not authenticate a sender or enroll an owner.

## Caller sequence

All calls perform blocking work and belong on the single application worker.
The caller obtains `TransferSelection`, `ReadData` and `Finished` through the
strict `TransferWire` decoder under its already authenticated connection.

```kotlin
DownloadStore(context).open(selection).use { download ->
    // First READ after open resumes at progress().committedBytes.
    // Later READs use progress().receivedBytes, including the RAM partial record.
    download.append(decodedRead)
    // Repeat READ until the selected byte length has arrived, then obtain FINISH.
    download.finish(decodedFinish)
    val recording = CaptureStore(context).importDownload(download)
}
```

An exact retry of the last READ is idempotent. Changed bytes, wrong handles,
unexpected offsets, callback/storage failures and stale closed sessions cannot
advance progress. After reconnect, re-SELECT and compare the exact source; open
the matching revision and request a new handle at the recovered complete-record
boundary. The future coordinator must close the session on cancellation and
reject callbacks belonging to an obsolete Bluetooth connection.

`finish()` requires all selected bytes to have been committed, a matching device
FINISH, the exact physical receipt and an independently valid full archive.
Physical OPEN remains OPEN; its complete interrupted export has a derived seal.
No transport completion becomes an automatic delete or release command.

## Handoff to the library

`DownloadSession.export(newPrivateFile)` replays and validates the stored source,
writes an exclusive file, synchronizes it and independently verifies its full
archive. It preserves failed copies and refuses an existing destination.
`CaptureStore.importDownload` uses this path, writes the physical receipt and
reuses the existing archive/decode/bundle publication checks. Duplicate imports
reuse the existing library revision. SQLite retains the original download when
copying, decoding or library publication fails.

Download completion means preserved source bytes, not verified audio playback.
The library still validates actual Opus decoding before marking playback ready.
The source transport permits 320 MiB, while the current playback import path
has a separate 128 MiB limit. Larger sources remain retained and can be exported;
they cannot be presented as playable by this library version.

## Verification boundary

The checks use real C-generated owned finalized and physical-OPEN exports,
actual C SELECT/FINISH metadata, the shared incremental validator and Android's
actual SQLite/codec APIs. The Android harness constructs chunked READ replies
from those complete C exports and passes them through the strict wire decoder;
it does not execute the C firmware over a live radio. See the
[current verification record](VERIFICATION.md) for
the exact observed runs and source hashes. Modeled failures and emulator tests
do not establish physical phone power-loss durability, NAND timing, a working
Bluetooth link or wear readiness. Durable guarantees still depend on the
platform and storage honoring SQLite and filesystem synchronization.
