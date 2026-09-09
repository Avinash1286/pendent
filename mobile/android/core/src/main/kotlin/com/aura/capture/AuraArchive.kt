package com.aura.capture

import java.io.BufferedInputStream
import java.io.File
import java.io.FileInputStream
import java.io.InputStream
import java.security.MessageDigest
import java.util.zip.CRC32

/** A source consistency error. CRC and SHA-256 do not authenticate the device. */
class ArchiveException(message: String) : Exception(message)

data class ArchiveLimits(
    val maxFileBytes: Long = 320L * 1024 * 1024,
    val maxPayloadBytes: Long = 256L * 1024 * 1024,
    val maxRecords: Int = 1_000_000,
) {
    init {
        checkArchive(maxFileBytes in 188..(1L shl 40), "Invalid archive file limit")
        checkArchive(maxPayloadBytes in 1..(1L shl 40), "Invalid archive payload limit")
        checkArchive(maxRecords in 1..1_000_000, "Invalid archive record limit")
    }
}

enum class CaptureCodec { PCM16, OPUS }
enum class ReceiptStatus(val wireValue: Int) { OPEN(0), FINALIZED(1), INTERRUPTED(2) }
enum class PacketKind { AUDIO, BOOKMARK }

class CaptureManifest internal constructor(
    val deviceId: String,
    val captureId: String,
    val codec: CaptureCodec,
    val sampleRate: Int,
    val frameSamples: Int,
    val preSkip: Int,
    val bitrate: Int,
    val codecProfile: Int,
    val complexity: Int,
    val timeSource: Int,
    val startedAtMs: Long,
    wire: ByteArray,
) {
    private val bytes = wire.copyOf()
    val identity: String get() = "$deviceId:$captureId"
    fun encode(): ByteArray = bytes.copyOf()
}

class ArchivePacket internal constructor(
    val kind: PacketKind,
    val sequence: Int,
    val sampleOffset: Long,
    val sampleCount: Int,
    payload: ByteArray,
    wire: ByteArray,
) {
    private val payloadBytes = payload.copyOf()
    private val wireBytes = wire.copyOf()
    val payloadSize: Int get() = payloadBytes.size
    fun payload(): ByteArray = payloadBytes.copyOf()
    fun encode(): ByteArray = wireBytes.copyOf()
}

class ArchiveReceipt internal constructor(
    val deviceId: String,
    val captureId: String,
    val nextSequence: Int,
    val encodedBytes: Long,
    val encodedSamples: Long,
    val chainSha256: String,
    val status: ReceiptStatus,
    wire: ByteArray,
) {
    private val bytes = wire.copyOf()
    fun encode(): ByteArray = bytes.copyOf()
    fun hex(): String = bytes.hexString()
}

class ArchiveSeal internal constructor(
    val deviceId: String,
    val captureId: String,
    val nextSequence: Int,
    val audioPackets: Int,
    val encodedBytes: Long,
    val encodedSamples: Long,
    val sourceSamples: Long,
    val originalSourceSamples: Long?,
    val preSkip: Int,
    val endTrim: Int,
    val prefixSha256: String,
    val status: ReceiptStatus,
    wire: ByteArray,
) {
    private val bytes = wire.copyOf()
    fun encode(): ByteArray = bytes.copyOf()
}

/** Complete validated file, not a durable receiver ACK and not proof of audio decoding.
 * A missing physicalReceipt means device-side termination provenance is unknown.
 * A physical OPEN receipt plus interrupted archive means the export seal is derived.
 */
class VerifiedArchive internal constructor(
    val file: File,
    val capture: CaptureManifest,
    val seal: ArchiveSeal,
    val receipt: ArchiveReceipt,
    val physicalReceipt: ArchiveReceipt?,
    val sha256: String,
    val fileBytes: Long,
    val bookmarkCount: Int,
    val unavailableBookmarkCount: Int,
    val limits: ArchiveLimits,
) {
    val status: ReceiptStatus get() = seal.status
    val sourceSamples: Long get() = seal.sourceSamples
    val originalSourceSamples: Long? get() = seal.originalSourceSamples
    val durationSeconds: Double get() = sourceSamples.toDouble() / capture.sampleRate
    val derivedExportSeal: Boolean get() = physicalReceipt?.status == ReceiptStatus.OPEN
    val physicalProvenanceKnown: Boolean get() = physicalReceipt != null
    val audioDecoded: Boolean get() = false
}

/** Strict AUR3 complete-archive reader. It never repairs or rewrites input. */
object AuraArchive {
    fun verify(
        file: File,
        physicalAck: ByteArray? = null,
        limits: ArchiveLimits = ArchiveLimits(),
    ): VerifiedArchive = scan(file, physicalAck?.copyOf(), limits, null)

    /** Stream packets, then recheck EOF, identities, receipts and the complete file hash.
     * Visitor output must remain temporary until this method returns successfully.
     * Callback failure aborts verification; do not publish partial derived output.
     */
    fun visitPackets(archive: VerifiedArchive, visitor: (ArchivePacket) -> Unit) {
        val current = scan(archive.file, archive.physicalReceipt?.encode(), archive.limits, visitor)
        checkArchive(
            current.sha256 == archive.sha256 && current.fileBytes == archive.fileBytes &&
                current.capture.encode().contentEquals(archive.capture.encode()) &&
                current.seal.encode().contentEquals(archive.seal.encode()) &&
                current.receipt.encode().contentEquals(archive.receipt.encode()),
            "Archive changed after validation; discard derived output",
        )
    }

    fun parseReceipt(wire: ByteArray): ArchiveReceipt {
        checkArchive(wire.size == 94, "Invalid ACK3 length")
        crc(wire)
        checkArchive(magic(wire, "ACK3") && u8(wire, 4) == 3, "Unsupported ACK3 header")
        val status = status(u8(wire, 5), allowOpen = true)
        val device = identity(wire, 6)
        val capture = identity(wire, 22)
        return ArchiveReceipt(device, capture, u32Bound(wire, 38, 1_000_000).toInt(),
            u64Bound(wire, 42, 1L shl 40), u64Bound(wire, 50, Long.MAX_VALUE),
            wire.copyOfRange(58, 90).hexString(), status, wire)
    }

    private fun scan(
        file: File,
        physicalAck: ByteArray?,
        limits: ArchiveLimits,
        visitor: ((ArchivePacket) -> Unit)?,
    ): VerifiedArchive {
        checkArchive(file.isFile, "Archive must be a regular file")
        checkArchive(file.length() <= limits.maxFileBytes, "Archive exceeds file limit")
        val physical = physicalAck?.let(::parseReceipt)
        BufferedInputStream(FileInputStream(file), 65536).use { stream ->
            val reader = Reader(stream, limits.maxFileBytes)
            val capture = manifest(reader.exact(68))
            var digest = sha(capture.encode())
            var sequence = 0
            var audioPackets = 0
            var encodedBytes = 0L
            var samples = 0L
            var bookmarkCount = 0
            var maxBookmark = 0L
            var unavailableTailBookmarks = 0
            while (true) {
                val prefix = reader.exact(4)
                when {
                    magic(prefix, "AFR3") -> {
                        val header = prefix + reader.exact(18)
                        checkArchive(u8(header, 4) == 3 && u8(header, 5) in 1..2,
                            "Unsupported packet header")
                        val payloadSize = u16(header, 20)
                        checkArchive(payloadSize <= 1275, "Packet exceeds payload bound")
                        checkArchive(sequence < limits.maxRecords, "Archive exceeds record limit")
                        val wire = header + reader.exact(payloadSize + 4)
                        crc(wire)
                        val packetSequence = u32Bound(header, 6, 999_999).toInt()
                        val offset = u64Bound(header, 10, Long.MAX_VALUE)
                        val count = u16(header, 18)
                        checkArchive(packetSequence == sequence, "Packet sequence gap or replay")
                        val kind = if (u8(header, 5) == 1) PacketKind.AUDIO else PacketKind.BOOKMARK
                        val payload = wire.copyOfRange(22, 22 + payloadSize)
                        if (kind == PacketKind.AUDIO) {
                            checkArchive(offset == samples && count == capture.frameSamples,
                                "Noncontiguous audio timeline or frame duration")
                            validateAudio(capture, payload, count)
                            audioPackets++
                            // At most 1,000,000 records * 320 samples, so this cannot overflow Long.
                            samples += count
                            unavailableTailBookmarks = 0
                        } else {
                            checkArchive(count == 0 && payloadSize == 0 && offset <= samples,
                                "Invalid bookmark timeline or payload")
                            bookmarkCount++
                            maxBookmark = maxOf(maxBookmark, offset)
                            val retainedEnd = samples - if (samples == 0L) 0 else capture.preSkip
                            if (offset > retainedEnd) unavailableTailBookmarks++
                        }
                        checkArchive(payloadSize.toLong() <= limits.maxPayloadBytes - encodedBytes,
                            "Archive exceeds encoded payload limit")
                        encodedBytes += payloadSize
                        digest = sha(digest, wire)
                        sequence++
                        visitor?.invoke(ArchivePacket(kind, packetSequence, offset, count, payload, wire))
                    }
                    magic(prefix, "ASE3") -> {
                        val wire = prefix + reader.exact(116)
                        val seal = seal(wire)
                        checkArchive(seal.deviceId == capture.deviceId && seal.captureId == capture.captureId &&
                            seal.nextSequence == sequence && seal.audioPackets == audioPackets &&
                            seal.encodedBytes == encodedBytes && seal.encodedSamples == samples &&
                            seal.prefixSha256 == digest.hexString(), "Seal differs from verified packet prefix")
                        val skip = if (samples == 0L) 0 else capture.preSkip
                        checkArchive(seal.preSkip == skip && seal.endTrim < capture.frameSamples,
                            "Invalid seal pre-skip or end trim")
                        checkArchive(samples >= skip + seal.endTrim &&
                            seal.sourceSamples == samples - skip - seal.endTrim,
                            "Seal does not preserve exact retained source duration")
                        if (seal.status == ReceiptStatus.FINALIZED) {
                            checkArchive(seal.originalSourceSamples == seal.sourceSamples &&
                                maxBookmark <= seal.sourceSamples, "Invalid final source length or bookmark")
                        } else {
                            checkArchive(seal.originalSourceSamples == null && seal.endTrim == 0,
                                "Interrupted capture invents an original duration or final trim")
                        }
                        reader.eof()
                        val open = receipt(capture, sequence, encodedBytes, samples, digest, ReceiptStatus.OPEN)
                        val terminal = receipt(capture, sequence, encodedBytes, samples, sha(digest, wire), seal.status)
                        if (physical != null) {
                            if (physical.status == ReceiptStatus.OPEN) {
                                checkArchive(seal.status == ReceiptStatus.INTERRUPTED &&
                                    physical.encode().contentEquals(open.encode()),
                                    "Physical OPEN receipt differs from exported pre-seal prefix")
                            } else checkArchive(physical.encode().contentEquals(terminal.encode()),
                                "Physical terminal receipt differs from verified archive")
                        }
                        return VerifiedArchive(file, capture, seal, terminal, physical, reader.digestHex(),
                            reader.count, bookmarkCount,
                            if (seal.status == ReceiptStatus.INTERRUPTED) unavailableTailBookmarks else 0, limits)
                    }
                    else -> throw ArchiveException("Unknown archive record; no resynchronization is permitted")
                }
            }
        }
    }

    private fun manifest(wire: ByteArray): CaptureManifest {
        crc(wire)
        checkArchive(magic(wire, "AUR3") && u8(wire, 4) == 3 && u8(wire, 6) == 1 &&
            u8(wire, 7) == 0 && u8(wire, 55) == 0, "Unsupported AUR3 manifest header")
        val codec = when (u8(wire, 5)) {
            1 -> CaptureCodec.PCM16
            2 -> CaptureCodec.OPUS
            else -> throw ArchiveException("Unsupported capture codec")
        }
        val rate = u32Bound(wire, 40, 16000).toInt()
        val frameSamples = u16(wire, 44)
        val skip = u16(wire, 46)
        val bitrate = u32Bound(wire, 48, 32000).toInt()
        val profile = u8(wire, 52)
        val complexity = u8(wire, 53)
        val timeSource = u8(wire, 54)
        val startedAt = u64Bound(wire, 56, 4_102_444_800_000)
        checkArchive(rate == 16000 && frameSamples in setOf(160, 320), "Unsupported sample rate or frame size")
        checkArchive(timeSource in 0..1 && ((startedAt == 0L) == (timeSource == 0)), "Invalid capture time source")
        if (codec == CaptureCodec.OPUS) {
            checkArchive(skip == 40 && bitrate == 32000 && profile == 1 && complexity == 3,
                "Unsupported Opus low-delay profile")
        } else checkArchive(skip == 0 && bitrate == 0 && profile == 0 && complexity == 0,
            "PCM profile requires zero codec controls")
        return CaptureManifest(identity(wire, 8), identity(wire, 24), codec, rate, frameSamples,
            skip, bitrate, profile, complexity, timeSource, startedAt, wire)
    }

    private fun validateAudio(capture: CaptureManifest, payload: ByteArray, samples: Int) {
        checkArchive(payload.isNotEmpty(), "Audio packet has no payload")
        if (capture.codec == CaptureCodec.PCM16) {
            checkArchive(payload.size == samples * 2, "PCM payload length differs from sample count")
        } else {
            val toc = u8(payload, 0)
            val config = toc ushr 3
            checkArchive(payload.size >= 2 && toc and 7 == 0 && config in 16..23 &&
                (40 shl (config and 3)) == samples, "Opus packet violates negotiated framing profile")
        }
    }

    private fun seal(wire: ByteArray): ArchiveSeal {
        crc(wire)
        checkArchive(magic(wire, "ASE3") && u8(wire, 4) == 3 && u16(wire, 6) == 0,
            "Unsupported ASE3 seal header")
        val original = if ((72..79).all { u8(wire, it) == 255 }) null else u64Bound(wire, 72, Long.MAX_VALUE)
        return ArchiveSeal(identity(wire, 8), identity(wire, 24),
            u32Bound(wire, 40, 1_000_000).toInt(), u32Bound(wire, 44, 1_000_000).toInt(),
            u64Bound(wire, 48, 1L shl 40), u64Bound(wire, 56, Long.MAX_VALUE),
            u64Bound(wire, 64, Long.MAX_VALUE), original,
            u16(wire, 80).also { checkArchive(it <= 320, "Invalid seal pre-skip") },
            u16(wire, 82).also { checkArchive(it <= 319, "Invalid seal end trim") },
            wire.copyOfRange(84, 116).hexString(), status(u8(wire, 5), allowOpen = false), wire)
    }

    private fun receipt(capture: CaptureManifest, sequence: Int, encoded: Long, samples: Long,
                        digest: ByteArray, status: ReceiptStatus): ArchiveReceipt {
        val wire = ByteArray(94)
        "ACK3".toByteArray(Charsets.US_ASCII).copyInto(wire)
        wire[4] = 3; wire[5] = status.wireValue.toByte()
        capture.encode().copyInto(wire, 6, 8, 24)
        capture.encode().copyInto(wire, 22, 24, 40)
        putLe(wire, 38, sequence.toLong(), 4)
        putLe(wire, 42, encoded, 8); putLe(wire, 50, samples, 8)
        digest.copyInto(wire, 58)
        putLe(wire, 90, CRC32().apply { update(wire, 0, 90) }.value, 4)
        return parseReceipt(wire)
    }

    private class Reader(private val input: InputStream, private val maximum: Long) {
        var count: Long = 0
            private set
        private val digest = MessageDigest.getInstance("SHA-256")
        fun exact(size: Int): ByteArray {
            checkArchive(size in 1..1301 && size.toLong() <= maximum - count, "Archive exceeds file limit")
            val bytes = ByteArray(size)
            var used = 0
            while (used < size) {
                val read = input.read(bytes, used, size - used)
                checkArchive(read > 0, "Incomplete archive: complete terminal seal required")
                used += read
            }
            count += size
            digest.update(bytes)
            return bytes
        }
        fun eof() { checkArchive(input.read() == -1, "Unexpected bytes after terminal seal") }
        fun digestHex(): String = digest.digest().hexString()
    }
}

internal fun checkArchive(condition: Boolean, message: String) {
    if (!condition) throw ArchiveException(message)
}
internal fun ByteArray.hexString(): String {
    val digits = "0123456789abcdef"
    val result = CharArray(size * 2)
    for (i in indices) { val n = this[i].toInt() and 255; result[i * 2] = digits[n ushr 4]; result[i * 2 + 1] = digits[n and 15] }
    return String(result)
}
internal fun u8(bytes: ByteArray, offset: Int): Int = bytes[offset].toInt() and 255
internal fun u16(bytes: ByteArray, offset: Int): Int = u8(bytes, offset) or (u8(bytes, offset + 1) shl 8)
internal fun u32Bound(bytes: ByteArray, offset: Int, maximum: Long): Long {
    var value = 0L
    for (i in 0..3) value = value or (u8(bytes, offset + i).toLong() shl (i * 8))
    checkArchive(value <= maximum, "Unsigned 32-bit field exceeds contract bound")
    return value
}
internal fun u64Bound(bytes: ByteArray, offset: Int, maximum: Long): Long {
    // All numeric AUR3 fields are <= Long.MAX_VALUE. UINT64_MAX is accepted only
    // by the explicit original-duration sentinel branch, never a signed -1 count.
    checkArchive(u8(bytes, offset + 7) and 128 == 0, "Unsigned 64-bit field exceeds signed storage range")
    var value = 0L
    for (i in 0..7) value = value or (u8(bytes, offset + i).toLong() shl (i * 8))
    checkArchive(value <= maximum, "Unsigned 64-bit field exceeds contract bound")
    return value
}
internal fun putLe(bytes: ByteArray, offset: Int, value: Long, count: Int) {
    for (i in 0 until count) bytes[offset + i] = (value ushr (i * 8)).toByte()
}
internal fun sha(vararg parts: ByteArray): ByteArray = MessageDigest.getInstance("SHA-256").run {
    parts.forEach { update(it) }; digest()
}
private fun magic(bytes: ByteArray, text: String): Boolean = bytes.size >= 4 &&
    (0..3).all { u8(bytes, it) == text[it].code }
private fun crc(wire: ByteArray) {
    checkArchive(wire.size >= 4, "Record is too short for a checksum")
    val actual = CRC32().apply { update(wire, 0, wire.size - 4) }.value
    checkArchive(actual == u32Bound(wire, wire.size - 4, 0xffff_ffffL), "Record checksum mismatch")
}
private fun identity(bytes: ByteArray, offset: Int): String {
    val raw = bytes.copyOfRange(offset, offset + 16)
    checkArchive(raw.any { it != 0.toByte() }, "Device and capture IDs must be nonzero")
    return raw.hexString()
}
private fun status(value: Int, allowOpen: Boolean): ReceiptStatus = when (value) {
    0 -> if (allowOpen) ReceiptStatus.OPEN else throw ArchiveException("A complete archive cannot have an OPEN seal")
    1 -> ReceiptStatus.FINALIZED
    2 -> ReceiptStatus.INTERRUPTED
    else -> throw ArchiveException("Unsupported termination status")
}
