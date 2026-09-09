package com.aura.capture

import java.io.OutputStream

data class OggExport(val bytesWritten: Long, val audioPackets: Int, val sourceSamples: Long) {
    /** This muxer does not contain an entropy decoder or validate decoded PCM. */
    val audioDecoded: Boolean get() = false
}

/** RFC 7845 Opus mapping, one exact packet per page; no re-encoding. */
object AuraOgg {
    /** Caller owns a private temporary output and must not publish it on failure.
     * This verifies structure, source identity and exact duration metadata; the
     * platform decoder still has to validate the actual Opus audio. No output
     * flush/fsync/publication is performed here, and the stream is not closed.
     */
    fun write(archive: VerifiedArchive, output: OutputStream): OggExport {
        checkArchive(archive.capture.codec == CaptureCodec.OPUS, "Ogg export requires Opus audio")
        checkArchive(archive.seal.audioPackets > 0, "Empty capture has no playable Opus packets")
        val manifest = archive.capture.encode()
        val serial = u32Bound(manifest, 24, 0xffff_ffffL)
        var bytesWritten = 0L
        var pageSequence = 0L
        fun emit(payload: ByteArray, granule: Long, flags: Int) {
            val page = page(payload, serial, pageSequence++, granule, flags)
            // A packet adds at most 33 bytes of page overhead. The record bound
            // also bounds this output independently of caller stream behavior.
            val maximum = archive.limits.maxPayloadBytes + archive.limits.maxRecords.toLong() * 33 + 1024
            checkArchive(page.size <= maximum - bytesWritten, "Ogg output exceeds bounded size")
            output.write(page)
            bytesWritten += page.size
        }
        val head = ByteArray(19)
        "OpusHead".toByteArray(Charsets.US_ASCII).copyInto(head)
        head[8] = 1; head[9] = 1
        putLe(head, 10, archive.capture.preSkip.toLong() * 3, 2)
        putLe(head, 12, archive.capture.sampleRate.toLong(), 4)
        emit(head, 0, 2)
        val vendor = "AURA verified local capture export".toByteArray(Charsets.US_ASCII)
        val tags = ByteArray(16 + vendor.size)
        "OpusTags".toByteArray(Charsets.US_ASCII).copyInto(tags)
        putLe(tags, 8, vendor.size.toLong(), 4); vendor.copyInto(tags, 12)
        emit(tags, 0, 0)
        var pending: ByteArray? = null
        var encodedSamples = 0L
        var audioPackets = 0
        AuraArchive.visitPackets(archive) { packet ->
            if (packet.kind == PacketKind.AUDIO) {
                pending?.let { emit(it, encodedSamples * 3, 0) }
                encodedSamples += packet.sampleCount
                audioPackets++
                pending = packet.payload()
            }
        }
        // visitPackets has now rechecked complete source identity and EOF. The
        // final granule trims padding in 48 kHz units, preserving source length.
        checkArchive(audioPackets == archive.seal.audioPackets && pending != null,
            "Verified capture lost its audio packets")
        emit(pending!!, (archive.sourceSamples + archive.seal.preSkip) * 3, 4)
        return OggExport(bytesWritten, audioPackets, archive.sourceSamples)
    }

    private fun page(payload: ByteArray, serial: Long, sequence: Long, granule: Long, flags: Int): ByteArray {
        checkArchive(payload.size <= 1275 && granule >= 0 && sequence <= 0xffff_ffffL,
            "Ogg page exceeds mapping limits")
        val segments = payload.size / 255 + 1
        val result = ByteArray(27 + segments + payload.size)
        "OggS".toByteArray(Charsets.US_ASCII).copyInto(result)
        result[5] = flags.toByte()
        putLe(result, 6, granule, 8); putLe(result, 14, serial, 4); putLe(result, 18, sequence, 4)
        result[26] = segments.toByte()
        for (i in 0 until segments - 1) result[27 + i] = 255.toByte()
        result[27 + segments - 1] = (payload.size % 255).toByte()
        payload.copyInto(result, 27 + segments)
        var crc = 0
        for (byte in result) {
            crc = crc xor ((byte.toInt() and 255) shl 24)
            repeat(8) { crc = if (crc < 0) (crc shl 1) xor 0x04c11db7 else crc shl 1 }
        }
        putLe(result, 22, crc.toLong() and 0xffff_ffffL, 4)
        return result
    }
}
