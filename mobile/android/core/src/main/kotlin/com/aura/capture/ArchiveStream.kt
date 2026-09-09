package com.aura.capture

import java.io.BufferedInputStream
import java.io.File
import java.io.FileInputStream
import java.security.MessageDigest

/** Complete-record validation state. No field claims a file flush or durable commit. */
class ArchiveProgress internal constructor(
    val validatedOffset: Long,
    val receivedBytes: Long,
    val bufferedBytes: Int,
    val manifest: CaptureManifest?,
    val receipt: ArchiveReceipt?,
    val seal: ArchiveSeal?,
    val physicalReceipt: ArchiveReceipt?,
    val bookmarkCount: Int,
    val unavailableBookmarkCount: Int,
    val complete: Boolean,
    /** Whole-file SHA256 is available only after successful explicit EOF. */
    val sha256: String?,
)

/**
 * One canonical AUR3 validation engine for file scans and incremental input.
 * Input is copied in chunks of at most 256 bytes. Only an incomplete record is
 * retained (at most 1301 bytes); complete records are not accumulated. Callback
 * bytes and snapshot models are independent copies or immutable values.
 *
 * A recordVisitor sees manifest, packet and seal bytes only after validation,
 * with the exact record start offset. It may place them in a caller-owned
 * transaction, but must not infer durable completion from this callback. Caller
 * callback failure or any validation error poisons this instance. Recreate and
 * replay an independently retained prefix after the failed transaction is handled.
 *
 * A validated seal is visible before explicit EOF, while complete stays false.
 * finish() declares actual end of input; it never synthesizes a recovery seal.
 */
class ArchiveStream(
    expectedManifest: ByteArray? = null,
    physicalAck: ByteArray? = null,
    val limits: ArchiveLimits = ArchiveLimits(),
    private val visitor: ((ArchivePacket) -> Unit)? = null,
    private val recordVisitor: ((Long, ByteArray) -> Unit)? = null,
) {
    companion object {
        const val MAX_CHUNK_BYTES = 256
        const val MAX_RECORD_BYTES = 1301

        /**
         * Replay one exact stored prefix once. Requires a manifest and a complete
         * record boundary at file EOF; no torn tail is skipped or repaired. A
         * sealed prefix returns complete, otherwise it can accept later chunks.
         * This does not authenticate the file, restore a hash checkpoint, or fsync.
         */
        fun replayPrefix(
            file: File,
            expectedManifest: ByteArray? = null,
            physicalAck: ByteArray? = null,
            limits: ArchiveLimits = ArchiveLimits(),
            visitor: ((ArchivePacket) -> Unit)? = null,
            recordVisitor: ((Long, ByteArray) -> Unit)? = null,
        ): ArchiveStream {
            checkArchive(file.isFile, "Archive prefix must be a regular file")
            checkArchive(file.length() <= limits.maxFileBytes, "Archive exceeds file limit")
            val validator = ArchiveStream(expectedManifest, physicalAck, limits, visitor, recordVisitor)
            BufferedInputStream(FileInputStream(file), 65536).use { input ->
                val chunk = ByteArray(MAX_CHUNK_BYTES)
                while (true) {
                    val count = input.read(chunk)
                    if (count < 0) break
                    checkArchive(count > 0, "Archive prefix read stalled")
                    validator.feed(if (count == chunk.size) chunk else chunk.copyOf(count))
                }
            }
            val state = validator.snapshot()
            checkArchive(state.manifest != null && state.bufferedBytes == 0,
                "Stored prefix does not end at a complete record boundary")
            if (state.seal != null) validator.finish()
            return validator
        }
    }

    private val expected = expectedManifest?.let { AuraArchive.parseManifest(it).encode() }
    private val physical = physicalAck?.copyOf()?.let(AuraArchive::parseReceipt)
    private val partial = ByteArray(MAX_RECORD_BYTES)
    private val fileDigest = MessageDigest.getInstance("SHA-256")
    private var buffered = 0
    private var needed = 68
    private var received = 0L
    private var validated = 0L
    private var capture: CaptureManifest? = null
    private var latestReceipt: ArchiveReceipt? = null
    private var terminalSeal: ArchiveSeal? = null
    private var chain = ByteArray(32)
    private var sequence = 0
    private var audioPackets = 0
    private var encodedBytes = 0L
    private var samples = 0L
    private var bookmarkCount = 0
    private var maxBookmark = 0L
    private var unavailableTailBookmarks = 0
    private var ended = false
    private var digestHex: String? = null
    private var failed = false
    private var mutating = false

    /** The snapshot offset excludes all buffered partial bytes. */
    @Synchronized
    fun snapshot(): ArchiveProgress {
        healthy()
        return ArchiveProgress(validated, received, buffered, capture, latestReceipt, terminalSeal, physical,
            bookmarkCount, if (terminalSeal?.status == ReceiptStatus.FINALIZED) 0 else unavailableTailBookmarks,
            ended, digestHex)
    }

    @Synchronized
    fun feed(bytes: ByteArray): ArchiveProgress = mutate {
        checkArchive(bytes.size <= MAX_CHUNK_BYTES, "Archive feed exceeds 256-byte chunk limit")
        checkArchive(bytes.size.toLong() <= limits.maxFileBytes - received, "Archive exceeds file limit")
        checkArchive(bytes.isEmpty() || !ended, "Unexpected bytes after declared EOF")
        val input = bytes.copyOf()
        var at = 0
        while (at < input.size) {
            checkArchive(terminalSeal == null, "Unexpected bytes after terminal seal")
            val take = minOf(input.size - at, needed - buffered)
            input.copyInto(partial, buffered, at, at + take)
            buffered += take; received += take; at += take
            if (buffered != needed) continue
            if (capture != null && needed == 4) {
                needed = when {
                    magic(partial, "AFR3") -> 22
                    magic(partial, "ASE3") -> 120
                    else -> throw ArchiveException("Unknown archive record; no resynchronization is permitted")
                }
                continue
            }
            if (capture != null && needed == 22 && magic(partial, "AFR3")) {
                checkArchive(u8(partial, 4) == 3 && u8(partial, 5) in 1..2, "Unsupported packet header")
                val payloadSize = u16(partial, 20)
                checkArchive(payloadSize <= 1275, "Packet exceeds payload bound")
                checkArchive(sequence < limits.maxRecords, "Archive exceeds record limit")
                needed = 26 + payloadSize
                continue
            }
            val wire = partial.copyOf(needed)
            val packet = validateRecord(wire)
            val start = validated
            validated += wire.size
            fileDigest.update(wire)
            partial.fill(0, 0, buffered)
            buffered = 0; needed = 4
            recordVisitor?.invoke(start, wire.copyOf())
            healthy() // A callback cannot hide a failed reentrant mutation.
            if (packet != null) visitor?.invoke(packet)
            healthy()
        }
        snapshot()
    }

    /** Idempotent explicit EOF. An OPEN prefix or partial tail is not complete. */
    @Synchronized
    fun finish(): ArchiveProgress = mutate {
        if (!ended) {
            checkArchive(capture != null && buffered == 0 && terminalSeal != null,
                "Incomplete archive: complete terminal seal and exact EOF required")
            matchPhysical(checkNotNull(terminalSeal), checkNotNull(latestReceipt))
            digestHex = fileDigest.digest().hexString()
            ended = true
        }
        snapshot()
    }

    private fun validateRecord(wire: ByteArray): ArchivePacket? {
        val manifest = capture
        if (manifest == null) {
            val parsed = AuraArchive.parseManifest(wire)
            checkArchive(expected == null || expected.contentEquals(wire), "Archive manifest differs from selected exact manifest")
            checkArchive(physical == null || (physical.deviceId == parsed.deviceId && physical.captureId == parsed.captureId),
                "Physical receipt identity differs from archive manifest")
            capture = parsed; chain = sha(wire)
            latestReceipt = openReceipt()
            return null
        }
        if (magic(wire, "AFR3")) {
            crc(wire)
            val packetSequence = u32Bound(wire, 6, 999_999).toInt()
            val offset = u64Bound(wire, 10, Long.MAX_VALUE)
            val count = u16(wire, 18)
            val payloadSize = u16(wire, 20)
            checkArchive(packetSequence == sequence, "Packet sequence gap or replay")
            val kind = if (u8(wire, 5) == 1) PacketKind.AUDIO else PacketKind.BOOKMARK
            val payload = wire.copyOfRange(22, 22 + payloadSize)
            checkArchive(payloadSize.toLong() <= limits.maxPayloadBytes - encodedBytes, "Archive exceeds encoded payload limit")
            if (kind == PacketKind.AUDIO) {
                checkArchive(offset == samples && count == manifest.frameSamples, "Noncontiguous audio timeline or frame duration")
                AuraArchive.validateAudio(manifest, payload, count)
                audioPackets++
                // <= 1,000,000 bounded records * 320 samples cannot overflow Long.
                samples += count
                unavailableTailBookmarks = 0
            } else {
                checkArchive(count == 0 && payloadSize == 0 && offset <= samples, "Invalid bookmark timeline or payload")
                bookmarkCount++
                maxBookmark = maxOf(maxBookmark, offset)
                val retainedEnd = samples - if (samples == 0L) 0 else manifest.preSkip
                if (offset > retainedEnd) unavailableTailBookmarks++
            }
            encodedBytes += payloadSize
            chain = sha(chain, wire); sequence++
            latestReceipt = openReceipt()
            return ArchivePacket(kind, packetSequence, offset, count, payload, wire)
        }
        checkArchive(magic(wire, "ASE3"), "Unknown archive record")
        val seal = AuraArchive.parseSeal(wire)
        checkArchive(seal.deviceId == manifest.deviceId && seal.captureId == manifest.captureId &&
            seal.nextSequence == sequence && seal.audioPackets == audioPackets &&
            seal.encodedBytes == encodedBytes && seal.encodedSamples == samples && seal.prefixSha256 == chain.hexString(),
            "Seal differs from verified packet prefix")
        val skip = if (samples == 0L) 0 else manifest.preSkip
        checkArchive(seal.preSkip == skip && seal.endTrim < manifest.frameSamples, "Invalid seal pre-skip or end trim")
        checkArchive(samples >= skip + seal.endTrim && seal.sourceSamples == samples - skip - seal.endTrim,
            "Seal does not preserve exact retained source duration")
        if (seal.status == ReceiptStatus.FINALIZED) {
            checkArchive(seal.originalSourceSamples == seal.sourceSamples && maxBookmark <= seal.sourceSamples,
                "Invalid final source length or bookmark")
        } else checkArchive(seal.originalSourceSamples == null && seal.endTrim == 0,
            "Interrupted capture invents an original duration or final trim")
        val terminal = AuraArchive.buildReceipt(manifest, sequence, encodedBytes, samples, sha(chain, wire), seal.status)
        matchPhysical(seal, terminal)
        terminalSeal = seal; latestReceipt = terminal
        return null
    }

    private fun openReceipt(): ArchiveReceipt = AuraArchive.buildReceipt(checkNotNull(capture), sequence,
        encodedBytes, samples, chain, ReceiptStatus.OPEN)

    private fun matchPhysical(seal: ArchiveSeal, terminal: ArchiveReceipt) {
        val supplied = physical ?: return
        if (supplied.status == ReceiptStatus.OPEN) {
            checkArchive(seal.status == ReceiptStatus.INTERRUPTED && supplied.encode().contentEquals(openReceipt().encode()),
                "Physical OPEN receipt differs from exported pre-seal prefix")
        } else checkArchive(supplied.encode().contentEquals(terminal.encode()), "Physical terminal receipt differs from verified archive")
    }

    private fun healthy() = checkArchive(!failed, "Archive stream is poisoned; replay an independently retained prefix")

    private fun <T> mutate(action: () -> T): T {
        healthy()
        if (mutating) {
            failed = true
            throw ArchiveException("Reentrant archive mutation is forbidden")
        }
        mutating = true
        try {
            return action()
        } catch (error: Throwable) {
            failed = true
            throw error
        } finally {
            mutating = false
        }
    }
}
