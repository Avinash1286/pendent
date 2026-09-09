package com.aura.capture

import java.io.ByteArrayOutputStream
import java.io.File
import java.util.zip.CRC32

internal data class ArchiveStreamCheckSummary(val groups: Int, val checks: Int, val fixtures: Int)

/** Real C bytes plus framing/transaction-boundary faults; no entropy or fsync claim. */
internal fun verifyArchiveStream(index: File, output: File): ArchiveStreamCheckSummary {
    var groups = 0
    var checks = 0
    var fixtures = 0
    fun expect(value: Boolean, message: String) { checks++; check(value) { message } }
    fun rejects(action: () -> Unit) {
        checks++
        try { action() } catch (_: ArchiveException) { return }
        error("Invalid incremental archive was accepted")
    }
    fun hex(text: String) = ByteArray(text.length / 2) { text.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
    fun checked(bytes: ByteArray): ByteArray = bytes.copyOf().also {
        putLe(it, it.size - 4, CRC32().apply { update(it, 0, it.size - 4) }.value, 4)
    }
    fun feed(stream: ArchiveStream, bytes: ByteArray, width: Int = 256) {
        var at = 0
        while (at < bytes.size) {
            val end = minOf(at + width, bytes.size)
            stream.feed(bytes.copyOfRange(at, end)); at = end
        }
    }
    fun poisoned(stream: ArchiveStream) {
        rejects { stream.snapshot() }; rejects { stream.feed(byteArrayOf()) }; rejects { stream.finish() }
    }
    fun temporary(bytes: ByteArray, action: (File) -> Unit) {
        val file = File.createTempFile("stream-prefix-", ".aura", output)
        try { file.writeBytes(bytes); action(file) } finally { check(file.delete()) }
    }
    fun records(bytes: ByteArray): List<ByteArray> {
        val result = ArrayList<ByteArray>()
        var at = 0
        while (at < bytes.size) {
            val size = when {
                at == 0 -> 68
                magic(bytes.copyOfRange(at, at + 4), "ASE3") -> 120
                else -> 26 + u16(bytes, at + 20)
            }
            result += bytes.copyOfRange(at, at + size); at += size
        }
        return result
    }

    // These expected hashes, exact terminal ACK3s and physical receipts were
    // prepared independently by Python from actual C-generated archives.
    for (line in index.readLines().filter { it.isNotBlank() && !it.startsWith("#") }) {
        val fields = line.split('\t'); check(fields.size == 9)
        val file = File(fields[1]); val bytes = file.readBytes()
        val physical = fields[4].takeUnless { it == "-" }?.let(::hex)
        if (fields[8] == "reject") {
            val prefix = ArchiveStream.replayPrefix(file, physicalAck = physical)
            expect(prefix.snapshot().receipt?.status == ReceiptStatus.OPEN && !prefix.snapshot().complete,
                "Actual raw C prefix was silently finalized")
            expect(prefix.snapshot().validatedOffset == bytes.size.toLong() && prefix.snapshot().bufferedBytes == 0,
                "Raw C prefix was repaired or skipped")
            expect(prefix.snapshot().receipt?.encode()?.contentEquals(checkNotNull(physical)) == true,
                "Actual raw C OPEN prefix ACK differs")
            rejects { prefix.finish() }; poisoned(prefix)
            continue
        }
        val wires = records(bytes)
        var ordinal = 0
        var callbackOffset = 0L
        var packets = 0
        val expectedManifest = bytes.copyOf(68)
        val physicalInput = physical?.copyOf()
        lateinit var stream: ArchiveStream
        stream = ArchiveStream(expectedManifest, physicalInput, visitor = {
            packets++
            val copy = it.encode(); copy.fill(0)
            expect(magic(it.encode(), "AFR3"), "Packet visitor leaked mutable bytes")
        }, recordVisitor = { offset, wire ->
            expect(offset == callbackOffset && wire.contentEquals(wires[ordinal]), "C record callback bytes/offset differ")
            callbackOffset += wire.size; ordinal++
            val state = stream.snapshot()
            expect(state.validatedOffset == callbackOffset && state.bufferedBytes == 0,
                "Callback snapshot is not the validated record boundary")
            expect(state.receipt != null && !state.complete && state.sha256 == null,
                "Record callback claimed EOF before finish")
            wire.fill(0) // Every consumer receives independent source bytes.
        })
        expectedManifest.fill(0); physicalInput?.fill(0)
        var at = 0; var turn = 0
        while (at < bytes.size) {
            val end = minOf(at + 1 + (turn * 73 % 256), bytes.size)
            val input = bytes.copyOfRange(at, end)
            val state = stream.feed(input); input.fill(0)
            expect(state.receivedBytes == end.toLong() && state.validatedOffset + state.bufferedBytes == state.receivedBytes,
                "Byte accounting differs at arbitrary C chunk boundary")
            expect(state.bufferedBytes < ArchiveStream.MAX_RECORD_BYTES, "Unbounded incomplete record")
            at = end; turn++
        }
        expect(stream.snapshot().seal != null && !stream.snapshot().complete, "Seal and EOF were conflated")
        val done = stream.finish()
        expect(done.complete && done.sha256 == fields[2] && done.receipt?.hex() == fields[3], "C complete hash or ACK differs")
        expect(done.seal?.sourceSamples == fields[5].toLong() && done.seal.status.wireValue == fields[6].toInt(),
            "C sample count/status differs")
        expect((done.seal?.originalSourceSamples?.toString() ?: "-") == fields[7], "C interruption provenance differs")
        expect(ordinal == wires.size && packets == wires.size - 2, "Not every C record was visited exactly once")
        expect(done.physicalReceipt?.hex() == physical?.hexString(), "Physical receipt was rewritten")
        expect(stream.finish().sha256 == done.sha256 && stream.feed(byteArrayOf()).complete, "EOF was not idempotent")
        val sealCopy = checkNotNull(done.seal).encode(); sealCopy.fill(0)
        expect(magic(checkNotNull(stream.snapshot().seal).encode(), "ASE3"), "Seal snapshot leaked mutable bytes")

        // Reopen once at representative complete-record boundaries, then consume
        // the remaining source. No hash-state deserialization or tail repair.
        val boundaries = listOf(68, wires.take(wires.size / 2).sumOf { it.size }, bytes.size - 120, bytes.size).distinct()
        for (boundary in boundaries) temporary(bytes.copyOf(boundary)) { prefixFile ->
            val resumed = ArchiveStream.replayPrefix(prefixFile, bytes.copyOf(68), physical)
            expect(resumed.snapshot().validatedOffset == boundary.toLong() && resumed.snapshot().bufferedBytes == 0,
                "Stored prefix replay changed its exact boundary")
            expect(resumed.snapshot().complete == (boundary == bytes.size), "Prefix replay completion differs")
            feed(resumed, bytes.copyOfRange(boundary, bytes.size), 127)
            expect(resumed.finish().receipt?.hex() == fields[3] && resumed.snapshot().sha256 == fields[2],
                "Resumed C source differs from uninterrupted validation")
        }
        fixtures++
    }
    expect(fixtures >= 19, "Owned C transfer fixture coverage is missing")
    groups++

    fun manifest(): ByteArray = checked(ByteArray(68).also {
        "AUR3".toByteArray().copyInto(it); it[4] = 3; it[5] = 2; it[6] = 1
        it.fill(1, 8, 24); it.fill(2, 24, 40)
        putLe(it, 40, 16000, 4); putLe(it, 44, 320, 2); putLe(it, 46, 40, 2)
        putLe(it, 48, 32000, 4); it[52] = 1; it[53] = 3
    })
    fun packet(sequence: Int, offset: Long, payload: ByteArray?, bookmark: Boolean = false): ByteArray {
        val audio = payload ?: byteArrayOf()
        return checked(ByteArray(26 + audio.size).also {
            "AFR3".toByteArray().copyInto(it); it[4] = 3; it[5] = if (bookmark) 2 else 1
            putLe(it, 6, sequence.toLong(), 4); putLe(it, 10, offset, 8)
            putLe(it, 18, if (bookmark) 0 else 320, 2); putLe(it, 20, audio.size.toLong(), 2)
            audio.copyInto(it, 22)
        })
    }
    fun archive(m: ByteArray, packets: List<ByteArray>, interrupted: Boolean = false): ByteArray {
        var chain = sha(m)
        var samples = 0L; var encoded = 0L; var audio = 0L
        for (p in packets) { chain = sha(chain, p); samples += u16(p, 18); encoded += u16(p, 20); if (u8(p, 5) == 1) audio++ }
        val skip = if (samples == 0L) 0 else 40
        val seal = checked(ByteArray(120).also {
            "ASE3".toByteArray().copyInto(it); it[4] = 3; it[5] = if (interrupted) 2 else 1
            m.copyInto(it, 8, 8, 40); putLe(it, 40, packets.size.toLong(), 4); putLe(it, 44, audio, 4)
            putLe(it, 48, encoded, 8); putLe(it, 56, samples, 8); putLe(it, 64, samples - skip, 8)
            putLe(it, 72, if (interrupted) -1 else samples - skip, 8); putLe(it, 80, skip.toLong(), 2)
            chain.copyInto(it, 84)
        })
        return ByteArrayOutputStream().apply { write(m); packets.forEach { write(it) }; write(seal) }.toByteArray()
    }
    val m = manifest()
    val p = packet(0, 0, ByteArray(1275).also { it[0] = 0xb8.toByte() })
    val valid = archive(m, listOf(p))
    val expected = sha(valid).hexString()
    for (width in 1..256) {
        val stream = ArchiveStream()
        feed(stream, valid, width)
        expect(stream.finish().sha256 == expected && stream.snapshot().bufferedBytes == 0,
            "Maximum record failed chunk width $width")
    }
    val split = ArchiveStream()
    split.feed(m.copyOf(67))
    expect(split.snapshot().manifest == null && split.snapshot().receipt == null && split.snapshot().validatedOffset == 0L,
        "Incomplete manifest exposed a receipt")
    split.feed(m.copyOfRange(67, 68))
    expect(split.snapshot().receipt?.status == ReceiptStatus.OPEN && split.snapshot().validatedOffset == 68L,
        "Manifest boundary is not OPEN")
    feed(split, p.copyOf(p.size - 1))
    expect(split.snapshot().bufferedBytes == 1300 && split.snapshot().validatedOffset == 68L,
        "Maximum incomplete record accounting differs")
    split.feed(p.copyOfRange(p.size - 1, p.size))
    expect(split.snapshot().validatedOffset == 1369L && split.snapshot().receipt?.nextSequence == 1,
        "Maximum record boundary not committed after final CRC byte")
    feed(split, valid.takeLast(120).toByteArray()); expect(split.finish().sha256 == expected, "Maximum split hash differs")
    groups++

    for (size in listOf(0, 1, 67, 69, 71, 89, 90, 1368, valid.size - 1)) {
        temporary(valid.copyOf(size)) { file -> rejects { ArchiveStream.replayPrefix(file) } }
    }
    for (size in listOf(0, 67, 68, 69, 1369, valid.size - 1)) {
        val stream = ArchiveStream(); feed(stream, valid.copyOf(size))
        rejects { stream.finish() }; poisoned(stream)
    }
    for (trailingTogether in listOf(false, true)) {
        val stream = ArchiveStream()
        if (trailingTogether) rejects { feed(stream, valid + byteArrayOf(0), 256) }
        else { feed(stream, valid); rejects { stream.feed(byteArrayOf(0)) } }
        poisoned(stream)
    }
    val ended = ArchiveStream(); feed(ended, valid); ended.finish()
    rejects { ended.feed(byteArrayOf(0)) }; poisoned(ended)
    val oversized = ArchiveStream(); rejects { oversized.feed(ByteArray(257)) }; poisoned(oversized)
    val fileLimited = ArchiveStream(limits = ArchiveLimits(maxFileBytes = 188))
    rejects { feed(fileLimited, valid) }; poisoned(fileLimited)
    val payloadLimited = ArchiveStream(limits = ArchiveLimits(maxPayloadBytes = 1274))
    rejects { feed(payloadLimited, valid) }; poisoned(payloadLimited)
    val two = archive(m, listOf(p, packet(1, 320, byteArrayOf(0xb8.toByte(), 0))))
    val recordLimited = ArchiveStream(limits = ArchiveLimits(maxRecords = 1))
    rejects { feed(recordLimited, two) }; poisoned(recordLimited)
    groups++

    // An exact selected manifest includes its profile and timestamp, beyond IDs.
    val changedManifest = checked(m.copyOf().also { it[54] = 1; putLe(it, 56, 1, 8) })
    val mismatch = ArchiveStream(expectedManifest = changedManifest)
    rejects { feed(mismatch, valid) }; poisoned(mismatch)
    val terminal = ArchiveStream(); feed(terminal, valid)
    val terminalAck = checkNotNull(terminal.finish().receipt).encode()
    val open = ArchiveStream(); feed(open, m + p)
    val openAck = checkNotNull(open.snapshot().receipt).encode()
    val recovered = archive(m, listOf(p), interrupted = true)
    val openProof = ArchiveStream(physicalAck = openAck); feed(openProof, recovered)
    expect(openProof.finish().physicalReceipt?.status == ReceiptStatus.OPEN &&
        openProof.snapshot().receipt?.status == ReceiptStatus.INTERRUPTED, "OPEN physical provenance was promoted")
    for ((source, receipt) in listOf(valid to openAck, recovered to terminalAck,
            recovered to checked(openAck.copyOf().also { it[58] = (it[58].toInt() xor 1).toByte() }))) {
        val stream = ArchiveStream(physicalAck = receipt)
        rejects { feed(stream, source); stream.finish() }; poisoned(stream)
    }
    groups++

    // Transaction callbacks may fail at any complete record; success before a
    // failure is not a durability guarantee and the parser cannot be reused.
    for (failureRecord in 0..2) {
        var callbacks = 0
        val failure = IllegalStateException("transaction callback failed")
        val stream = ArchiveStream(recordVisitor = { _, _ -> if (callbacks++ == failureRecord) throw failure })
        checks++
        try { feed(stream, valid); error("Callback failure swallowed") }
        catch (error: IllegalStateException) { expect(error === failure, "Callback failure identity was lost") }
        expect(callbacks == failureRecord + 1, "Callback continued after failure")
        poisoned(stream)
    }
    val visitorFailure = IllegalStateException("packet callback failed")
    val visitorStream = ArchiveStream(visitor = { throw visitorFailure })
    checks++
    try { feed(visitorStream, valid); error("Packet callback failure swallowed") }
    catch (error: IllegalStateException) { expect(error === visitorFailure, "Packet callback failure identity was lost") }
    poisoned(visitorStream)
    lateinit var reentrant: ArchiveStream
    reentrant = ArchiveStream(recordVisitor = { _, _ -> rejects { reentrant.feed(byteArrayOf()) } })
    rejects { reentrant.feed(m) }; poisoned(reentrant)
    groups++

    val bookmark = packet(1, 320, null, bookmark = true)
    val bookmarked = ArchiveStream()
    feed(bookmarked, m + p + bookmark)
    expect(bookmarked.snapshot().bookmarkCount == 1 && bookmarked.snapshot().unavailableBookmarkCount == 1,
        "OPEN bookmark availability lost")
    val next = packet(2, 320, byteArrayOf(0xb8.toByte(), 0))
    feed(bookmarked, next)
    expect(bookmarked.snapshot().unavailableBookmarkCount == 0, "Later retained audio did not resolve bookmark")
    feed(bookmarked, archive(m, listOf(p, bookmark, next), true).takeLast(120).toByteArray())
    expect(bookmarked.finish().seal?.originalSourceSamples == null, "Interrupted duration was invented")
    val empty = ArchiveStream(); feed(empty, archive(m, emptyList()))
    expect(empty.finish().seal?.sourceSamples == 0L && empty.snapshot().receipt?.nextSequence == 0,
        "Empty capture became an incomplete prefix")
    groups++
    return ArchiveStreamCheckSummary(groups, checks, fixtures)
}
