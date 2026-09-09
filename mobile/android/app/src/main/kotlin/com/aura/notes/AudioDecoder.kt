package com.aura.notes

import android.media.AudioFormat
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.os.SystemClock
import com.aura.capture.CaptureCodec
import com.aura.capture.VerifiedArchive
import java.io.BufferedOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder

data class DecodeResult(
    val sampleRate: Int,
    /** Mono PCM frames retained in the WAV, after any remaining terminal trim. */
    val frames: Long,
    /** Frames actually returned by MediaCodec, which already applies Opus pre-skip. */
    val rawFrames: Long,
    val decoderName: String,
    val endTrimApplied: Boolean,
)

/** Offline validation of a private AuraOgg-derived file, not a device provenance check.
 * The caller owns both original inputs and publication of the completed WAV. This
 * method never overwrites a destination and removes its incomplete output on error.
 */
object AudioDecoder {
    private const val OPUS_MIME = "audio/opus"
    private const val SOURCE_RATE = 16_000
    private const val MAX_PACKET_BYTES = 1_275
    private const val MAX_OGG_BYTES = 160L * 1024 * 1024
    private const val MAX_WAV_DATA_BYTES = 2L * 1024 * 1024 * 1024 - 44
    private const val STALL_TIMEOUT_MS = 10_000L
    private const val MAX_TOTAL_MS = 10L * 60 * 1000
    private const val CODEC_WAIT_US = 10_000L

    @Throws(IOException::class)
    fun decode(ogg: File, outputWav: File, archive: VerifiedArchive): DecodeResult {
        demand(archive.capture.codec == CaptureCodec.OPUS, "Playback conversion requires Opus")
        demand(archive.capture.sampleRate == SOURCE_RATE, "Unsupported capture sample rate")
        demand(archive.seal.audioPackets > 0 && archive.sourceSamples > 0,
            "Empty capture has no playable audio")
        demand(archive.seal.encodedSamples >= archive.seal.preSkip.toLong(),
            "Invalid effective pre-skip")
        val untrimmedSourceFrames = archive.seal.encodedSamples - archive.seal.preSkip
        demand(untrimmedSourceFrames - archive.sourceSamples == archive.seal.endTrim.toLong(),
            "Capture duration and end trim disagree")
        demand(archive.sourceSamples <= MAX_WAV_DATA_BYTES / 6 &&
            untrimmedSourceFrames <= MAX_WAV_DATA_BYTES / 6,
            "Decoded capture exceeds the WAV resource limit")

        val inputPath = ogg.canonicalFile
        val outputPath = outputWav.canonicalFile
        demand(inputPath != outputPath && archive.file.canonicalFile != outputPath,
            "Playback output must be separate from the original inputs")
        val oggLimit = minOf(MAX_OGG_BYTES,
            archive.limits.maxPayloadBytes + archive.limits.maxRecords.toLong() * 33 + 1024)
        val inputBytes = inputPath.length()
        demand(inputPath.isFile && inputBytes in 1..oggLimit, "Ogg input exceeds its bounded size")
        demand(!outputPath.exists(), "Playback output already exists")

        val startedAt = SystemClock.elapsedRealtime()
        // Short files still get codec startup time; long files cannot occupy a
        // worker forever, even when a platform codec continues making progress.
        val totalBudgetMs = minOf(MAX_TOTAL_MS,
            maxOf(30_000L, archive.sourceSamples * 1000 / SOURCE_RATE / 2 + 10_000L))
        var lastProgressAt = startedAt
        var codec: MediaCodec? = null
        var codecStarted = false
        var outputCreated = false
        var succeeded = false
        val extractor = MediaExtractor()
        try {
            extractor.setDataSource(inputPath.absolutePath)
            demand(extractor.trackCount == 1, "Expected exactly one Opus audio track")
            val track = extractor.getTrackFormat(0)
            demand(track.getString(MediaFormat.KEY_MIME) == OPUS_MIME,
                "Ogg track is not Opus")
            demand(track.getInteger(MediaFormat.KEY_CHANNEL_COUNT) == 1,
                "Only mono capture playback is supported")
            verifyCodecHeaders(track, archive)
            extractor.selectTrack(0)
            track.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, MAX_PACKET_BYTES)
            track.setInteger(MediaFormat.KEY_PCM_ENCODING, AudioFormat.ENCODING_PCM_16BIT)
            val activeCodec = MediaCodec.createDecoderByType(OPUS_MIME)
            codec = activeCodec
            val decoderName = activeCodec.name
            activeCodec.configure(track, null, null, 0)
            activeCodec.start()
            codecStarted = true

            demand(outputPath.createNewFile(), "Could not create a new private playback output")
            outputCreated = true
            var outputRate = 0
            var targetFrames = 0L
            var maximumRawFrames = 0L
            var rawFrames = 0L
            var writtenFrames = 0L
            var inputPackets = 0
            var lastInputTimeUs = -1L
            var inputEos = false
            var outputEos = false
            var events = 0L
            val maximumEvents = archive.seal.audioPackets.toLong() * 8 + 1024
            val info = MediaCodec.BufferInfo()
            val scratch = ByteArray(32 * 1024)

            fun acceptOutputFormat(format: MediaFormat) {
                demand(format.getString(MediaFormat.KEY_MIME) == "audio/raw",
                    "Decoder returned a non-PCM output format")
                val rate = format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
                demand(rate == SOURCE_RATE || rate == 48_000, "Unsupported decoded sample rate")
                demand(format.getInteger(MediaFormat.KEY_CHANNEL_COUNT) == 1,
                    "Decoder returned non-mono PCM")
                // PCM16 is the documented default when the optional key is absent.
                val encoding = if (format.containsKey(MediaFormat.KEY_PCM_ENCODING))
                    format.getInteger(MediaFormat.KEY_PCM_ENCODING)
                else AudioFormat.ENCODING_PCM_16BIT
                demand(encoding == AudioFormat.ENCODING_PCM_16BIT,
                    "Decoder did not return signed PCM16")
                demand(outputRate == 0 || outputRate == rate,
                    "Decoder changed sample rate within one capture")
                outputRate = rate
                val ratio = rate / SOURCE_RATE
                targetFrames = archive.sourceSamples * ratio
                maximumRawFrames = untrimmedSourceFrames * ratio
                demand(targetFrames * 2 <= MAX_WAV_DATA_BYTES && maximumRawFrames * 2 <= MAX_WAV_DATA_BYTES,
                    "Decoder output exceeds the WAV resource limit")
            }

            FileOutputStream(outputPath).use { fileOutput ->
                BufferedOutputStream(fileOutput, 64 * 1024).use { wav ->
                    wav.write(ByteArray(44)) // Header is committed only after full output EOS validation.
                    while (!outputEos) {
                        if (Thread.currentThread().isInterrupted) throw IOException("Audio decoding cancelled")
                        val now = SystemClock.elapsedRealtime()
                        demand(now - startedAt < totalBudgetMs, "Audio decoding exceeded its time budget")
                        demand(now - lastProgressAt < STALL_TIMEOUT_MS, "Audio decoder stopped making progress")

                        if (!inputEos) {
                            val index = activeCodec.dequeueInputBuffer(CODEC_WAIT_US)
                            if (index >= 0) {
                                val input = activeCodec.getInputBuffer(index)
                                    ?: throw IOException("Decoder input buffer is unavailable")
                                input.clear()
                                val sampleTimeUs = extractor.sampleTime
                                if (sampleTimeUs < 0) {
                                    demand(inputPackets == archive.seal.audioPackets,
                                        "Ogg ended before all verified audio packets")
                                    activeCodec.queueInputBuffer(index, 0, 0, 0,
                                        MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                                    inputEos = true
                                } else {
                                    demand(inputPackets < archive.seal.audioPackets,
                                        "Ogg contains extra audio packets")
                                    demand(sampleTimeUs >= lastInputTimeUs,
                                        "Ogg packet timestamps move backwards")
                                    demand(extractor.sampleTrackIndex == 0 &&
                                        extractor.sampleFlags and MediaExtractor.SAMPLE_FLAG_ENCRYPTED == 0 &&
                                        extractor.sampleFlags and MediaExtractor.SAMPLE_FLAG_PARTIAL_FRAME == 0,
                                        "Unsupported encrypted, partial, or foreign-track packet")
                                    val packetBytes = extractor.sampleSize
                                    demand(packetBytes in 1..MAX_PACKET_BYTES.toLong() && packetBytes <= input.capacity(),
                                        "Opus packet exceeds the decoder input buffer")
                                    val read = extractor.readSampleData(input, 0)
                                    demand(read.toLong() == packetBytes, "Ogg packet read was incomplete")
                                    activeCodec.queueInputBuffer(index, 0, read, sampleTimeUs, 0)
                                    lastInputTimeUs = sampleTimeUs
                                    inputPackets++
                                    extractor.advance()
                                }
                                events++
                                lastProgressAt = SystemClock.elapsedRealtime()
                            }
                        }

                        when (val index = activeCodec.dequeueOutputBuffer(info, CODEC_WAIT_US)) {
                            MediaCodec.INFO_TRY_AGAIN_LATER -> Unit
                            MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                                acceptOutputFormat(activeCodec.outputFormat)
                                events++
                                lastProgressAt = SystemClock.elapsedRealtime()
                            }
                            MediaCodec.INFO_OUTPUT_BUFFERS_CHANGED -> {
                                events++ // Buffer arrays are never cached by this implementation.
                            }
                            else -> {
                                demand(index >= 0, "Unexpected decoder output status")
                                try {
                                    acceptOutputFormat(activeCodec.getOutputFormat(index))
                                    demand(info.offset >= 0 && info.size >= 0 && info.size % 2 == 0,
                                        "Decoder returned a misaligned PCM buffer")
                                    demand(info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG == 0,
                                        "Unexpected codec configuration in decoded PCM")
                                    if (info.size > 0) {
                                        val output = activeCodec.getOutputBuffer(index)
                                            ?: throw IOException("Decoder output buffer is unavailable")
                                        demand(info.offset <= output.capacity() &&
                                            info.size <= output.capacity() - info.offset,
                                            "Decoded PCM buffer bounds are invalid")
                                        val frames = info.size.toLong() / 2
                                        demand(frames <= maximumRawFrames - rawFrames,
                                            "Decoder returned extra PCM beyond verified duration")
                                        rawFrames += frames
                                        val retain = minOf(frames, targetFrames - writtenFrames)
                                        val retainedBytes = (retain * 2).toInt()
                                        val readable = output.duplicate()
                                        readable.clear()
                                        readable.position(info.offset)
                                        readable.limit(info.offset + retainedBytes)
                                        while (readable.hasRemaining()) {
                                            val count = minOf(readable.remaining(), scratch.size)
                                            readable.get(scratch, 0, count)
                                            if (ByteOrder.nativeOrder() == ByteOrder.BIG_ENDIAN) {
                                                for (i in 0 until count step 2) {
                                                    val first = scratch[i]
                                                    scratch[i] = scratch[i + 1]
                                                    scratch[i + 1] = first
                                                }
                                            }
                                            wav.write(scratch, 0, count)
                                        }
                                        writtenFrames += retain
                                    }
                                    if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) {
                                        demand(inputEos, "Decoder signalled output EOS before complete input")
                                        outputEos = true
                                    }
                                    events++
                                    lastProgressAt = SystemClock.elapsedRealtime()
                                } finally {
                                    activeCodec.releaseOutputBuffer(index, false)
                                }
                            }
                        }
                        demand(events <= maximumEvents, "Decoder exceeded its bounded event count")
                    }
                    demand(outputRate != 0 && writtenFrames == targetFrames,
                        "Decoded audio is shorter than the exact source duration")
                    // Platform paths differ in terminal Ogg padding handling. Only
                    // these two exact counts are acceptable; a partial tail is not.
                    demand(rawFrames == targetFrames || rawFrames == maximumRawFrames,
                        "Decoded sample count differs from both valid trim endpoints")
                    demand(inputPackets == archive.seal.audioPackets && inputPath.length() == inputBytes,
                        "Ogg input changed or was not completely consumed")
                    wav.flush()
                    fileOutput.fd.sync()
                }
            }

            val pcmBytes = writtenFrames * 2
            demand(outputPath.length() == pcmBytes + 44, "WAV output length is inconsistent")
            RandomAccessFile(outputPath, "rw").use { wav ->
                wav.seek(0)
                wav.write(wavHeader(outputRate, pcmBytes))
                wav.fd.sync()
            }
            succeeded = true
            return DecodeResult(outputRate, writtenFrames, rawFrames, decoderName,
                endTrimApplied = rawFrames > writtenFrames)
        } catch (error: IOException) {
            throw error
        } catch (error: Exception) {
            throw IOException("Platform Opus validation failed: ${error.message ?: error.javaClass.simpleName}", error)
        } finally {
            if (codecStarted) runCatching { codec?.stop() }
            runCatching { codec?.release() }
            runCatching { extractor.release() }
            if (outputCreated && !succeeded) outputPath.delete()
        }
    }

    private fun verifyCodecHeaders(format: MediaFormat, archive: VerifiedArchive) {
        val header = format.getByteBuffer("csd-0")?.duplicate()
            ?: throw IOException("Missing Opus identification header")
        demand(header.remaining() == 19, "Unsupported Opus identification header")
        val bytes = ByteArray(19)
        header.get(bytes)
        demand(String(bytes, 0, 8, Charsets.US_ASCII) == "OpusHead" &&
            bytes[8].toInt() == 1 && bytes[9].toInt() == 1 && bytes[18].toInt() == 0,
            "Unsupported Opus version, channel count, or mapping")
        val fields = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        val preSkip48k = fields.getShort(10).toInt() and 0xffff
        demand(preSkip48k == archive.seal.preSkip * 3 && fields.getInt(12) == SOURCE_RATE &&
            fields.getShort(16).toInt() == 0, "Opus header differs from verified capture")
        val delay = format.getByteBuffer("csd-1")?.duplicate()?.order(ByteOrder.nativeOrder())
            ?: throw IOException("Missing Opus codec delay")
        demand(delay.remaining() == 8 && delay.getLong() == preSkip48k.toLong() * 1_000_000_000 / 48_000,
            "Opus decoder pre-skip differs from verified capture")
        // The decoder consumes this delay. No manual leading trim is performed.
    }

    private fun wavHeader(sampleRate: Int, dataBytes: Long): ByteArray {
        demand(dataBytes in 0..MAX_WAV_DATA_BYTES && dataBytes + 36 <= 0xffff_ffffL,
            "WAV exceeds the RIFF size limit")
        return ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN).apply {
            put("RIFF".toByteArray(Charsets.US_ASCII))
            putInt((dataBytes + 36).toInt())
            put("WAVEfmt ".toByteArray(Charsets.US_ASCII))
            putInt(16)
            putShort(1.toShort()) // PCM
            putShort(1.toShort()) // Mono
            putInt(sampleRate)
            putInt(sampleRate * 2)
            putShort(2.toShort())
            putShort(16.toShort())
            put("data".toByteArray(Charsets.US_ASCII))
            putInt(dataBytes.toInt())
        }.array()
    }

    private fun demand(condition: Boolean, message: String) {
        if (!condition) throw IOException(message)
    }
}
