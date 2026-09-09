# AURA archive core for the Android companion

This pure Kotlin/JVM module validates the existing experimental A04 **AUR3** archive and **ACK3** byte contract, response fragments, and the locked transfer command/response format. It uses Kotlin and the Java standard library, with no Android, networking, database, or decoder dependency. The native app owns private source copying, publication, playback, and lifecycle. No Omi source code is copied here.

The authoritative definitions remain [ARCHIVE.md](../../../firmware/a04/ARCHIVE.md), the portable C writer, and the companion Python reader. Complete-file verification accepts finalized and interrupted archives, including a complete bench export with a derived interrupted seal. It rejects raw unsealed prefixes, recognizable truncated records, malformed complete records, and trailing bytes. Incremental validation can retain a strict complete-record prefix for later resume; it cannot mark that prefix complete. Neither API repairs or rewrites an input file.

## Application API

```kotlin
import com.aura.capture.AuraArchive
import com.aura.capture.AuraOgg

// privateSource must already be a bounded, complete private copy of the user file.
val source = AuraArchive.verify(privateSource, optionalPhysicalAckBytes)
val sourceIdentity = source.capture.identity
val retainedSamples = source.sourceSamples
val originalSamples: Long? = source.originalSourceSamples

// The caller owns a private temporary stream. Keep it unpublished on any error.
privateTemporaryOutput.use { output ->
    AuraOgg.write(source, output)
}
// Still required: flush, actual platform decode and duration checks, then publication.
```

`VerifiedArchive` exposes the immutable manifest, seal, expected archive receipt, optional physical receipt, file SHA-256, byte length, bookmark counts, retained source duration, and original source duration when known. IDs and digests are lowercase hex strings. `encode()` methods return independent byte copies, so a caller cannot alter validated metadata by mutating an exposed array.

`AuraArchive.visitPackets(source) { packet -> ... }` streams each audio/bookmark record and then verifies the complete current file against the original result. Visitor output is provisional until iteration returns successfully. A callback failure or a changed source invalidates derived output; no API publishes a partial result.

The parser bounds each record to 1301 bytes. Default file and encoded-payload limits are 320 MiB and 256 MiB, respectively, with at most 1,000,000 combined audio/bookmark records. `ArchiveLimits` can lower these limits. Values are validated before allocation or conversion. Unsigned 64-bit wire fields with their high bit set are rejected before conversion to signed `Long`, except the exact `UINT64_MAX` sentinel for unknown original duration. Duration validation uses checked subtraction instead of potentially overflowing addition. Sequence, identity, codec profile, time source, Opus TOC, CRC, chain hash, source trim, bookmarks, and terminal counts are checked against actual records.

Bookmark locations are streamed rather than accumulated into an unbounded list. `unavailableBookmarkCount` preserves interrupted bookmarks inside the unavailable final lookahead: those offsets remain source evidence, but must not be shown as seekable retained audio. A later complete audio frame makes earlier lookahead bookmarks available. Finalized archives require every bookmark to lie within the exact final source duration.

## Incremental validation and strict prefix replay

`ArchiveStream` is the canonical validator behind both `AuraArchive.verify()` and
`visitPackets()`. It accepts arbitrary chunks of 0–256 bytes through `feed()`,
retains at most one incomplete 1301-byte record, and accumulates no packet list.
An optional exact expected manifest binds every selected field, including its
timestamp/profile. An optional physical ACK retains its independent scope.

```kotlin
val stream = ArchiveStream(
    expectedManifest = selected.manifest.encode(),
    physicalAck = selected.physicalReceipt.encode(),
    recordVisitor = { recordStart, independentWireBytes ->
        // Stage this exact validated record in the caller's transaction.
        // The callback does not make that transaction durable.
    },
)
val progress = stream.feed(nextChunkOfAtMost256Bytes)
// progress.validatedOffset excludes progress.bufferedBytes.
// receivedBytes = validatedOffset + bufferedBytes.
// Declare exact EOF only after the caller has checked the selected source end:
val finished = stream.finish()
```

`ArchiveProgress` exposes immutable manifest, current OPEN or terminal receipt,
seal, physical receipt, bookmark counts, byte accounting and completion. Its
`seal` becomes non-null after a valid terminal record, while `complete` and the
whole-file `sha256` are available only after successful explicit `finish()`.
The receipt and `validatedOffset` describe the same exact complete-record prefix.
They do not imply an fsync, device acknowledgement, or committed database row.

`recordVisitor` runs after validation for every manifest, packet and seal, with
the exact start offset and independent bytes. The optional packet visitor follows
it for audio/bookmarks. Snapshots may be read inside callbacks. A callback error,
reentrant mutation, or validation failure poisons the instance; every later
snapshot/feed/finish fails. The caller must handle its failed transaction and
create a fresh parser from independently retained records. Earlier callback
success cannot authorize publication after a later error.

`ArchiveStream.replayPrefix(file, ...)` reads the stored prefix once and requires
an actual manifest plus an exact complete-record boundary at EOF. It rejects an
empty file or any partial tail, never discards bytes, and never synthesizes a seal.
A sealed prefix returns complete; an OPEN prefix remains resumable. Replaying
database records through `feed()` provides the same canonical checks. No serialized
SHA state or receipt alone can substitute for revalidating the exact saved bytes.

`finish()` requires a complete seal and checks the exact physical receipt. A
physical OPEN receipt must match the computed pre-seal prefix of an interrupted
export; it remains OPEN in the result. Successful finish is idempotent, but any
nonempty bytes after a seal or declared EOF invalidate the stream.

## Physical provenance and receipt scope

Passing no physical ACK leaves device-side termination provenance **unknown**. An archive that declares finalized is not by itself proof that a physical device durably finalized it. Both CRC and SHA-256 check consistency; neither authenticates the source against a writer who can change the bytes and recompute them.

When supplied, a physical ACK must be exactly 94 bytes. Finalized and physically interrupted ACKs must equal the full verified archive receipt. A physical OPEN ACK is accepted only for an interrupted exported archive and must equal the independently computed prefix immediately before its derived seal. `derivedExportSeal` and `physicalProvenanceKnown` make these cases explicit. Original duration remains unknown for every interrupted capture.

The result's receipt describes expected validated bytes. This module does not implement a durable receiver transaction, acknowledge a connected device, authenticate ownership, authorize release, delete recordings, or send any BLE/UART command. Publication and persistence are separate caller responsibilities.

## Ogg Opus mapping

`AuraOgg.write` preserves each exact Opus payload, emits one packet per Ogg page, calculates the Ogg CRC, and converts archive timing from 16 kHz to 48 kHz granule units. The last page trims padding using the terminal retained source duration. The source is revalidated while streaming, so mutation after the first verification causes failure before the caller can consider the output ready.

This is a container muxer, not an entropy/audio decoder. A packet can satisfy profile/CRC checks and still fail decoding. `audioDecoded` therefore remains false. The Android app must validate with an actual supported platform decoder before marking derived media ready; JVM tests use independent FFmpeg decoding only for their test fixtures. PCM source archives validate, but this Opus muxer refuses them. Empty captures also validate but have no playable Opus packets; no synthetic audio is invented for them.

## Response-fragment foundation

`BleResponseFragments` implements only the 8-byte response-fragment header in
[the A04 transport proposal](../../../docs/a04/mobile-transport.md). It is not
connected to Android GATT, an enrollment flow or an application download
coordinator. The published local-import APK does not integrate this component.

Begin with a nonzero u16 transaction and the actual negotiated ATT MTU (23 by
default). Keep the returned generation token with callbacks. `accept()` copies
bounded input and returns pending, exact duplicate, complete or stale. A complete
result owns an independent byte copy; its logical contents still need validation.
Reset/begin invalidate older tokens. A current-generation framing error clears
the response; stale callbacks cannot poison the current one. The caller remains
responsible for GATT identity, subscriptions, transaction reuse, deadlines and
copying platform callback bytes before queuing them.

One logical response is at most 512 bytes. A fragment carries at most `MTU - 11`
data bytes (12 at MTU 23). Only a previously accepted fragment with the exact
offset, length, total and bytes may repeat; gaps and other overlaps fail. Storage
is bounded to a 512-byte payload buffer and 512 u16 boundary entries, plus bounded
input/result copies. A 1024-delivery budget bounds duplicate floods. This parser
provides neither authentication nor a durable acknowledgement.

## Transfer command and logical-response codec

`TransferWire` implements the exact [transfer wire v1](../../../docs/a04/transfer-wire-v1.md)
layouts for HELLO, LIST, SELECT, READ, FINISH and CANCEL. Command factories return
immutable `TransferCommand` values with defensive `encode()` copies. Each command
fits the default 20-byte ATT payload; this module never sends one itself.

```kotlin
// These public IDs must come from a separately authenticated session.
val session = TransferSession(trustedDeviceIdBytes, trustedIncarnationBytes)
val request = TransferWire.select(transaction, captureIdBytes)
val commandBytes = request.encode()

// logicalReplyBytes comes from a completed, current-generation fragment chain.
val result = TransferWire.decode(request, logicalReplyBytes, session)
if (result is TransferResponse.Selected) {
    val selected = result.selection
    val readRequest = TransferWire.read(nextTransaction, selected.handle, 0, 256)
    // Keep selected for decode(readRequest, replyBytes, session, selected).
}
// TransferResponse.Failure contains an exact four-byte logical error status.
```

The codec checks exact lengths, unsigned fields, enums/flags, the outstanding
request's opcode and transaction, and success echoes. HELLO must match the
supplied trusted IDs and the specified catalog/chunk limits. LIST preserves
unavailable or explicitly flagged foreign entries without treating the catalog
as allocation authority. Canonical manifests use `AuraArchive.parseManifest()`;
physical receipts reuse its existing strict ACK3 parser.

SELECT binds the handle to the manifest, physical ACK3, exact physical/export
lengths and allocation generation. `captureId()` uses the C storage algorithm:
SHA256 over the domain including its terminating NUL, device ID, incarnation and
little-endian generation, then the first 16 digest bytes. Generation is `ULong`,
including valid values above `Long.MAX_VALUE`; bounded file lengths use `Long`.
Physical length must equal `68 + 26*nextSequence + encodedBytes`, plus 120 only
for a terminal physical receipt. An OPEN receipt requires an export-only derived
seal and an additional 120 exported bytes.

READ needs the selected context, checks the handle/offset/count/CRC, and permits
zero bytes only at the selected export EOF. FINISH must repeat the exact SELECT
physical receipt, generation, length and derived-seal flag. These consistency
checks do not independently verify audio bytes that have not been downloaded.
A full archive must still pass AUR3 verification and durable source publication;
neither READ nor FINISH is a phone acknowledgement or permission to erase data.

The caller owns monotonically increasing transactions, the connection and GATT
generation, exact retries, deadlines, sequential download progress, independently
verified resume boundaries, and cancellation. `TransferSession` contains public
IDs only; constructing it does not authenticate or enroll an owner. No GATT,
secret provisioning, microphone command, deletion or release is implemented here.

## Reproduce verification

The `verifyCore` task is a dependency-free JVM executable, and `check` depends on it. It requires an explicit fixture index and result directory; a plain compile does not silently count as protocol verification. The default JUnit task explicitly allows empty discovery because this module's checks run through that executable, rather than a JUnit dependency. The Python runner prepares expectations using the existing C-generated fixture files and independent Python parser, executes Kotlin, compares exact ACK3 and Ogg bytes, then runs FFmpeg and checks the decoded PCM sample count. The same JVM executable requires the actual C engine's transfer command/response/fragment vectors; it cannot silently skip those tests when the TSV is missing.

The committed `firmware/a04/verification/transfer-wire-golden.tsv` is emitted by
the real C engine harness, using public deterministic owned identities and the
existing Opus fixtures. Regenerate it with the configured firmware host build
when its C inputs change: `./firmware/a04/scripts/build.ps1 -Mode host` also runs
`verify_transfer.py`. Kotlin tests consume its exact bytes; they do not fabricate
replacement C output. Avoid regenerating it concurrently with core verification.

After configuring the repository's Android JDK/Gradle environment:

```powershell
uv run --project companion --locked python mobile/android/core/scripts/verify_core.py --gradle .tools/android/gradle/gradle-9.4.1/bin/gradle.bat
```

For separate build orchestration, run `--prepare-only`, invoke `:core:check` with `-PauraFixtureIndex=...` and `-PauraResultDirectory=...`, then run `--finish-only`. The script writes its generated index, JVM output, exact receipt/Ogg files, and source-bound report under the ignored `core/build/verification` directory, and publishes the compact report and JVM transcript in `core/verification`. It never accesses a serial device or personal recording.

Preparation records the exact C archive/paired-receipt fixtures, golden TSV,
canonical Kotlin/Python inputs, wire specification, command-engine and
generation-algorithm source hashes. They are checked after the JVM run and
again while finalizing the report. A change fails verification instead of binding
a new fixture to an old run; the split prepare/finish flow retains the same
baseline. Final evidence includes the golden TSV hash and all Kotlin source hashes.

The JVM harness includes semantic mutations with recomputed CRCs, truncation and trailing-byte rejection, unsigned boundary rejection, payload/record quotas, empty and PCM sources, bookmark availability, physical receipt mismatches, immutable metadata access, and source changes before derived publication. Passing these tests is not a claim of Android runtime execution, hardware recording, entropy validation for arbitrary future input, battery safety, or a launch-ready device.

Fragment checks cover each logical length 1–512 at MTUs 23, 24, 185, 247 and 517,
a literal little-endian wire example, malformed headers/ranges, exact retries,
conflicting overlaps, changed totals, buffer ownership, delivery limits and stale
generations. These are JVM parser checks; no radio or Android GATT is exercised.

Transfer checks cover literal command layouts, canonical metadata, unsigned
generation boundaries, invalid headers/counts/echoes/flags, READ CRC and EOF,
physical OPEN versus derived seals, FINISH identity conflicts, and defensive
copies. The current C vectors supply 14 command/response pairs for finalized and
OPEN captures, plus four complete fragment chains at MTUs 23 and 517. The actual
JVM transcript records 338 transfer checks. Incremental checks add strict prefix
replay/resume, exact callback bytes and boundary offsets, all chunk widths 1–256
for a maximum-size record, seal-before-EOF state, explicit failure poisoning,
callback failures/reentrancy, quotas, immutable copies and bookmark availability.
The owned finalized/OPEN C transfer archives and their paired physical ACKs also
run through the independent Python/JVM/Ogg/FFmpeg path. The current full core run
records 82,213 checks across 30 groups, including 49,471 incremental checks,
19 complete C archive fixtures and one rejected raw prefix. These are host
verification results; Android SQLite durability, GATT and physical recording are
separate verification scopes.
