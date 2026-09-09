package com.aura.capture

import java.io.ByteArrayOutputStream
import java.io.File
import java.util.zip.CRC32

private var groups = 0
private var checks = 0
private fun expect(value: Boolean, message: String = "Check failed") {
    checks++
    if (!value) throw IllegalStateException(message)
}
private fun rejects(action: () -> Unit) {
    checks++
    try { action() } catch (_: ArchiveException) { return }
    throw IllegalStateException("Invalid input was accepted")
}
private fun checked(wire: ByteArray): ByteArray {
    val result = wire.copyOf()
    putLe(result, result.size - 4, CRC32().apply { update(result, 0, result.size - 4) }.value, 4)
    return result
}
private fun decodeHex(text: String): ByteArray {
    require(text.length % 2 == 0 && text.all { it in "0123456789abcdef" })
    return ByteArray(text.length / 2) { text.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
}
private fun manifest(pcm: Boolean = false): ByteArray {
    val wire = ByteArray(68)
    "AUR3".toByteArray().copyInto(wire)
    wire[4] = 3; wire[5] = if (pcm) 1 else 2; wire[6] = 1
    ByteArray(16) { 1 }.copyInto(wire, 8); ByteArray(16) { 2 }.copyInto(wire, 24)
    putLe(wire, 40, 16000, 4); putLe(wire, 44, 320, 2)
    if (!pcm) { putLe(wire, 46, 40, 2); putLe(wire, 48, 32000, 4); wire[52] = 1; wire[53] = 3 }
    return checked(wire)
}
private fun packet(sequence: Int, offset: Long, payload: ByteArray = byteArrayOf(0xb8.toByte(), 0xff.toByte(), 0xfe.toByte()),
                   count: Int = 320, bookmark: Boolean = false): ByteArray {
    val wire = ByteArray(26 + payload.size)
    "AFR3".toByteArray().copyInto(wire); wire[4] = 3; wire[5] = if (bookmark) 2 else 1
    putLe(wire, 6, sequence.toLong(), 4); putLe(wire, 10, offset, 8)
    putLe(wire, 18, count.toLong(), 2); putLe(wire, 20, payload.size.toLong(), 2)
    payload.copyInto(wire, 22)
    return checked(wire)
}
private fun archive(m: ByteArray = manifest(), packets: List<ByteArray> = listOf(packet(0, 0)),
                    interrupted: Boolean = false, sourceOverride: Long? = null): ByteArray {
    var digest = sha(m)
    var samples = 0L
    var payloadBytes = 0L
    var audio = 0
    for (p in packets) {
        digest = sha(digest, p)
        samples += u16(p, 18); payloadBytes += u16(p, 20)
        if (u8(p, 5) == 1) audio++
    }
    val skip = if (samples == 0L) 0 else u16(m, 46)
    val source = sourceOverride ?: (samples - skip)
    val seal = ByteArray(120)
    "ASE3".toByteArray().copyInto(seal); seal[4] = 3; seal[5] = if (interrupted) 2 else 1
    m.copyInto(seal, 8, 8, 40)
    putLe(seal, 40, packets.size.toLong(), 4); putLe(seal, 44, audio.toLong(), 4)
    putLe(seal, 48, payloadBytes, 8); putLe(seal, 56, samples, 8)
    putLe(seal, 64, source, 8); putLe(seal, 72, if (interrupted) -1 else source, 8)
    putLe(seal, 80, skip.toLong(), 2); putLe(seal, 82, samples - skip - source, 2)
    digest.copyInto(seal, 84)
    val out = ByteArrayOutputStream(); out.write(m); packets.forEach { out.write(it) }; out.write(checked(seal))
    return out.toByteArray()
}
private fun withFile(directory: File, bytes: ByteArray, action: (File) -> Unit) {
    val file = File.createTempFile("archive-", ".aura", directory)
    try { file.writeBytes(bytes); action(file) } finally { file.delete() }
}

private fun synthetic(directory: File) {
    val valid = archive()
    withFile(directory, valid) { file ->
        val verified = AuraArchive.verify(file)
        expect(verified.sourceSamples == 280L && !verified.physicalProvenanceKnown)
        expect(!verified.audioDecoded && verified.bookmarkCount == 0)
        val mutatedReceipt = verified.receipt.encode(); mutatedReceipt[0] = 0
        expect(verified.receipt.encode()[0] == 'A'.code.toByte(), "Receipt exposed mutable internal state")
        val mutatedManifest = verified.capture.encode(); mutatedManifest[8] = 0
        expect(verified.capture.encode()[8] == 1.toByte(), "Manifest exposed mutable internal state")
        AuraArchive.visitPackets(verified) { packet ->
            val bytes = packet.payload(); bytes[0] = 0
            expect(packet.payload()[0] == 0xb8.toByte(), "Packet exposed mutable payload")
        }
        rejects { AuraArchive.verify(file, limits = ArchiveLimits(maxFileBytes = 188)) }
        rejects { AuraArchive.verify(file, limits = ArchiveLimits(maxPayloadBytes = 2)) }
    }
    groups++

    // CRC failures and recognizable incomplete records are rejected even if a
    // general recovery tool could derive an interrupted prefix from them.
    for (offset in listOf(0, 4, 8, 64, 68, 72, 90, valid.size - 1)) {
        val wire = valid.copyOf(); wire[offset] = (wire[offset].toInt() xor 1).toByte()
        withFile(directory, wire) { rejects { AuraArchive.verify(it) } }
    }
    for (size in listOf(0, 4, 67, 68, 70, 90, valid.size - 1)) {
        withFile(directory, valid.copyOf(size)) { rejects { AuraArchive.verify(it) } }
    }
    withFile(directory, valid + byteArrayOf(0)) { rejects { AuraArchive.verify(it) } }
    groups++

    // Recomputed CRC ensures these exercise semantic bounds, not checksum only.
    for ((offset, value) in listOf(4 to 2, 5 to 3, 6 to 2, 7 to 1, 40 to 0,
            44 to 80, 46 to 41, 48 to 1, 52 to 2, 53 to 4, 54 to 1, 55 to 1)) {
        val m = manifest(); m[offset] = value.toByte()
        withFile(directory, archive(checked(m))) { rejects { AuraArchive.verify(it) } }
    }
    for (offset in listOf(8, 24)) {
        val m = manifest(); m.fill(0, offset, offset + 16)
        withFile(directory, archive(checked(m))) { rejects { AuraArchive.verify(it) } }
    }
    for (value in listOf(Long.MIN_VALUE, -2L, Long.MAX_VALUE)) {
        val m = manifest(); m[54] = 1; putLe(m, 56, value, 8)
        withFile(directory, archive(checked(m))) { rejects { AuraArchive.verify(it) } }
    }
    val synchronized = manifest(); synchronized[54] = 1; putLe(synchronized, 56, 4_102_444_800_000, 8)
    withFile(directory, archive(checked(synchronized))) {
        expect(AuraArchive.verify(it).capture.startedAtMs == 4_102_444_800_000L)
    }
    groups++

    for (p in listOf(packet(1, 0), packet(0, 1), packet(0, Long.MIN_VALUE), packet(0, -1),
            packet(0, 0, count = 160), packet(0, 0, payload = byteArrayOf()),
            packet(0, 0, payload = byteArrayOf(0xb8.toByte())),
            packet(0, 0, payload = byteArrayOf(0xb9.toByte(), 0, 0)),
            packet(0, 0, payload = byteArrayOf(0xb0.toByte(), 0, 0)),
            packet(0, 0, payload = ByteArray(1276)))) {
        withFile(directory, archive(packets = listOf(p))) { rejects { AuraArchive.verify(it) } }
    }
    withFile(directory, archive(packets = listOf(packet(0, 0), packet(0, 320)))) { rejects { AuraArchive.verify(it) } }
    withFile(directory, archive(packets = listOf(packet(0, 0), packet(1, 320)))) {
        rejects { AuraArchive.verify(it, limits = ArchiveLimits(maxRecords = 1)) }
    }
    groups++

    for (offset in listOf(4, 5, 6, 8, 24, 40, 44, 48, 56, 64, 72, 80, 82, 84)) {
        val wire = valid.copyOf()
        val start = wire.size - 120
        wire[start + offset] = (wire[start + offset].toInt() xor 1).toByte()
        checked(wire.copyOfRange(start, wire.size)).copyInto(wire, start)
        withFile(directory, wire) { rejects { AuraArchive.verify(it) } }
    }
    for (offset in listOf(48, 56, 64, 72)) {
        for (value in listOf(Long.MIN_VALUE, -2L, Long.MAX_VALUE)) {
            val wire = valid.copyOf(); val start = wire.size - 120
            putLe(wire, start + offset, value, 8)
            checked(wire.copyOfRange(start, wire.size)).copyInto(wire, start)
            withFile(directory, wire) { rejects { AuraArchive.verify(it) } }
        }
    }
    groups++

    // Empty archives and PCM are valid source formats without fabricated Opus.
    for (pcm in listOf(false, true)) {
        withFile(directory, archive(manifest(pcm), emptyList())) { file ->
            val result = AuraArchive.verify(file)
            expect(result.sourceSamples == 0L && result.seal.preSkip == 0)
            rejects { AuraOgg.write(result, ByteArrayOutputStream()) }
        }
    }
    withFile(directory, archive(manifest(true), listOf(packet(0, 0, ByteArray(640))))) { file ->
        expect(AuraArchive.verify(file).sourceSamples == 320L)
        rejects { AuraOgg.write(AuraArchive.verify(file), ByteArrayOutputStream()) }
    }
    withFile(directory, archive(manifest(true), listOf(packet(0, 0, ByteArray(638))))) { rejects { AuraArchive.verify(it) } }
    withFile(directory, archive(packets = listOf(packet(0, 0, byteArrayOf(), 0, true)))) {
        val result = AuraArchive.verify(it)
        expect(result.sourceSamples == 0L && result.bookmarkCount == 1 && result.unavailableBookmarkCount == 0)
    }
    groups++

    val bookmark = packet(1, 320, byteArrayOf(), 0, bookmark = true)
    withFile(directory, archive(packets = listOf(packet(0, 0), bookmark), interrupted = true)) { file ->
        val result = AuraArchive.verify(file)
        expect(result.originalSourceSamples == null && result.unavailableBookmarkCount == 1)
        expect(result.bookmarkCount == 1 && result.sourceSamples == 280L)
    }
    withFile(directory, archive(packets = listOf(packet(0, 0), bookmark))) { rejects { AuraArchive.verify(it) } }
    withFile(directory, archive(packets = listOf(packet(0, 0), bookmark, packet(2, 320)), interrupted = true)) {
        expect(AuraArchive.verify(it).unavailableBookmarkCount == 0)
    }
    withFile(directory, archive(packets = listOf(packet(0, 0), packet(1, 280, byteArrayOf(), 0, true)))) {
        expect(AuraArchive.verify(it).bookmarkCount == 1)
    }
    withFile(directory, archive(packets = listOf(packet(0, 0), packet(1, 321, byteArrayOf(), 0, true)), interrupted = true)) {
        rejects { AuraArchive.verify(it) }
    }
    withFile(directory, archive(interrupted = true, sourceOverride = 279)) { rejects { AuraArchive.verify(it) } }
    groups++

    withFile(directory, valid) { file ->
        val result = AuraArchive.verify(file)
        for (offset in listOf(0, 4, 5, 6, 22, 38, 42, 50, 58)) {
            val wire = result.receipt.encode(); wire[offset] = (wire[offset].toInt() xor 1).toByte()
            rejects { AuraArchive.verify(file, checked(wire)) }
        }
        for (offset in listOf(42, 50)) {
            val wire = result.receipt.encode(); putLe(wire, offset, Long.MIN_VALUE, 8)
            rejects { AuraArchive.parseReceipt(checked(wire)) }
        }
        rejects { AuraArchive.parseReceipt(result.receipt.encode().copyOf(93)) }
        rejects { AuraArchive.parseReceipt(result.receipt.encode() + byteArrayOf(0)) }
        val open = result.receipt.encode(); open[5] = 0
        rejects { AuraArchive.verify(file, checked(open)) }
    }
    groups++

    withFile(directory, valid) { file ->
        val result = AuraArchive.verify(file)
        val changed = archive(sourceOverride = 279)
        file.writeBytes(changed)
        rejects { AuraArchive.visitPackets(result) { } }
        rejects { AuraOgg.write(result, ByteArrayOutputStream()) }
        file.writeBytes(valid)
        val failure = IllegalStateException("visitor failed")
        try { AuraArchive.visitPackets(result) { throw failure }; error("Visitor failure swallowed") }
        catch (error: IllegalStateException) { expect(error === failure) }
    }
    groups++
}

/** Args: Python-generated tab-separated fixture index, private/generated result directory. */
fun main(args: Array<String>) {
    require(args.size == 2) { "Expected fixture index and result directory" }
    val index = File(args[0]); val output = File(args[1]); output.mkdirs()
    val results = StringBuilder("name\tsha256\treceipt\tphysical\tsourceSamples\toggBytes\n")
    var fixtures = 0
    var rejected = 0
    for (row in index.readLines().filter { it.isNotBlank() && !it.startsWith("#") }) {
        val fields = row.split('\t')
        require(fields.size == 9) { "Invalid fixture index" }
        val name = fields[0]; val path = fields[1]; val expectedHash = fields[2]
        val expectedReceipt = fields[3]; val physicalHex = fields[4]; val expectedSource = fields[5]
        val expectedStatus = fields[6]; val expectedOriginal = fields[7]; val disposition = fields[8]
        val file = File(path)
        if (disposition == "reject") {
            rejects { AuraArchive.verify(file) }; rejected++; continue
        }
        val physical = if (physicalHex == "-") null else decodeHex(physicalHex)
        val result = AuraArchive.verify(file, physical)
        expect(result.sha256 == expectedHash, "File SHA differs for $name")
        expect(result.receipt.hex() == expectedReceipt, "ACK3 differs for $name")
        expect(result.sourceSamples == expectedSource.toLong(), "Source length differs for $name")
        expect(result.status.wireValue == expectedStatus.toInt(), "Termination differs for $name")
        expect((result.originalSourceSamples?.toString() ?: "-") == expectedOriginal, "Original duration differs for $name")
        expect(result.physicalProvenanceKnown == (physical != null))
        var packetCount = 0
        AuraArchive.visitPackets(result) { packetCount++ }
        expect(packetCount == result.seal.nextSequence)
        var oggBytes = 0L
        if (result.capture.codec == CaptureCodec.OPUS && result.seal.audioPackets > 0) {
            File(output, "$name.ogg").outputStream().use { stream -> oggBytes = AuraOgg.write(result, stream).bytesWritten }
        }
        File(output, "$name.ack3").writeBytes(result.receipt.encode())
        results.append(listOf(name, result.sha256, result.receipt.hex(),
            result.physicalReceipt?.status?.wireValue?.toString() ?: "-", result.sourceSamples, oggBytes).joinToString("\t")).append('\n')
        fixtures++
    }
    groups++
    synthetic(output)
    val fragments = verifyBleFragments()
    groups += fragments.groups
    checks += fragments.checks
    val transfer = verifyTransferWire(index)
    groups += transfer.groups
    checks += transfer.checks
    val streaming = verifyArchiveStream(index, output)
    groups += streaming.groups
    checks += streaming.checks
    File(output, "results.tsv").writeText(results.toString())
    println("PASS Kotlin core groups=$groups checks=$checks C_fixtures=$fixtures raw_prefix_rejected=$rejected audio_decode_claim=false")
    println("PASS BLE response fragments groups=${fragments.groups} checks=${fragments.checks} gatt_tested=false")
    println("PASS transfer wire groups=${transfer.groups} checks=${transfer.checks} C_golden_responses=${transfer.goldenResponses} gatt_tested=false")
    println("PASS incremental archive groups=${streaming.groups} checks=${streaming.checks} C_fixtures=${streaming.fixtures} durable_storage_tested=false")
}
