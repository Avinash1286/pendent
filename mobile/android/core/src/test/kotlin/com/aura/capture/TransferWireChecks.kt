package com.aura.capture

import java.io.File
import java.util.zip.CRC32

internal data class TransferWireCheckSummary(val groups: Int, val checks: Int, val goldenResponses: Int)

/** Synthetic faults plus exact command/response bytes emitted by the actual C engine. */
internal fun verifyTransferWire(fixtureIndex: File): TransferWireCheckSummary {
    var checks = 0
    var groups = 0
    fun expect(ok: Boolean, message: String) { checks++; check(ok) { message } }
    fun rejects(action: () -> Unit) {
        checks++
        try { action() } catch (_: TransferWireException) { return }
        error("Invalid transfer wire input was accepted")
    }
    fun hex(text: String): ByteArray {
        check(text.length % 2 == 0 && text.all { it in "0123456789abcdef" })
        return ByteArray(text.length / 2) { text.substring(2 * it, 2 * it + 2).toInt(16).toByte() }
    }
    fun crc(bytes: ByteArray): ByteArray = bytes.copyOf().also {
        putLe(it, it.size - 4, CRC32().apply { update(it, 0, it.size - 4) }.value, 4)
    }
    fun response(request: TransferCommand, size: Int): ByteArray = ByteArray(size).also {
        it[1] = request.opcode.wireValue.toByte(); putLe(it, 2, request.transaction.toLong(), 2)
    }
    val device = ByteArray(16) { 0x11 }
    val incarnation = byteArrayOf(0xa4.toByte()) + ByteArray(15) { (it + 2).toByte() }
    val session = TransferSession(device, incarnation)
    fun manifest(generation: ULong, owner: TransferSession = session): ByteArray {
        val wire = ByteArray(68)
        "AUR3".toByteArray().copyInto(wire); wire[4] = 3; wire[5] = 2; wire[6] = 1
        owner.deviceIdBytes().copyInto(wire, 8); TransferWire.captureId(owner, generation).copyInto(wire, 24)
        putLe(wire, 40, 16000, 4); putLe(wire, 44, 320, 2); putLe(wire, 46, 40, 2)
        putLe(wire, 48, 32000, 4); wire[52] = 1; wire[53] = 3
        return crc(wire)
    }
    fun receipt(m: ByteArray, status: Int): ByteArray {
        val wire = ByteArray(94)
        "ACK3".toByteArray().copyInto(wire); wire[4] = 3; wire[5] = status.toByte()
        m.copyInto(wire, 6, 8, 40); putLe(wire, 38, 1, 4); putLe(wire, 42, 3, 8)
        putLe(wire, 50, 320, 8); wire.fill(0x51, 58, 90)
        return crc(wire)
    }
    fun selectedPair(status: Int = 1, generation: ULong = 17uL): Pair<TransferCommand, ByteArray> {
        val m = manifest(generation)
        val request = TransferWire.select(3, m.copyOfRange(24, 40))
        val wire = response(request, 195)
        putLe(wire, 4, 0xffff_ffffL, 4); m.copyInto(wire, 8); receipt(m, status).copyInto(wire, 76)
        putLe(wire, 170, if (status == 0) 97 else 217, 8); putLe(wire, 178, 217, 8)
        wire[186] = if (status == 0) 1 else 0; putLe(wire, 187, generation.toLong(), 8)
        return request to wire
    }
    fun decodeSelection(pair: Pair<TransferCommand, ByteArray>): TransferSelection =
        (TransferWire.decode(pair.first, pair.second, session) as TransferResponse.Selected).selection
    fun readPair(selected: TransferSelection, offset: Long, data: ByteArray, requested: Int = 256): Pair<TransferCommand, ByteArray> {
        val request = TransferWire.read(4, selected.handle, offset, requested)
        val wire = response(request, 22 + data.size)
        putLe(wire, 4, selected.handle, 4); putLe(wire, 8, offset, 8); putLe(wire, 16, data.size.toLong(), 2)
        data.copyInto(wire, 18); putLe(wire, 18 + data.size, CRC32().apply { update(data) }.value, 4)
        return request to wire
    }
    fun finishPair(selected: TransferSelection): Pair<TransferCommand, ByteArray> {
        val request = TransferWire.finish(5, selected.handle, selected.exportBytes)
        val wire = response(request, 119)
        putLe(wire, 4, selected.handle, 4); selected.physicalReceipt.encode().copyInto(wire, 8)
        putLe(wire, 102, selected.exportBytes, 8); wire[110] = if (selected.derivedSeal) 1 else 0
        putLe(wire, 111, selected.allocationGeneration.toLong(), 8)
        return request to wire
    }

    val commands = listOf(
        TransferWire.hello(1) to "01010100",
        TransferWire.list(2, 0x89abcdefL, 65535) to "01020200efcdab89ffff",
        TransferWire.select(3, ByteArray(16) { (it + 1).toByte() }) to "010303000102030405060708090a0b0c0d0e0f10",
        TransferWire.read(4, 0x87654321L, TransferWire.MAX_FILE_BYTES, 256) to "010404002143658700000014000000000001",
        TransferWire.finish(5, 0xffff_ffffL, 0) to "01050500ffffffff0000000000000000",
        TransferWire.cancel(6, 0xffff_ffffL) to "01060600ffffffff",
    )
    for ((command, literal) in commands) {
        expect(command.encode().contentEquals(hex(literal)), "Literal command layout differs")
        val mutable = command.encode(); mutable.fill(0)
        expect(command.encode().contentEquals(hex(literal)), "Command leaked mutable bytes")
    }
    for (id in listOf(-1, 0, 65536)) rejects { TransferWire.hello(id) }
    for (value in listOf(-1L, 0L, 0x1_0000_0000L)) {
        rejects { TransferWire.list(1, value, 0) }; rejects { TransferWire.cancel(1, value) }
    }
    for (index in listOf(-1, 65536)) rejects { TransferWire.list(1, 1, index) }
    for (offset in listOf(-1L, TransferWire.MAX_FILE_BYTES + 1, Long.MAX_VALUE)) {
        rejects { TransferWire.read(1, 1, offset, 1) }; rejects { TransferWire.finish(1, 1, offset) }
    }
    for (count in listOf(0, 257, Int.MAX_VALUE)) rejects { TransferWire.read(1, 1, 0, count) }
    for (bytes in listOf(ByteArray(15), ByteArray(16), ByteArray(17))) {
        rejects { TransferWire.select(1, bytes) }; rejects { TransferSession(bytes, incarnation) }
    }
    rejects { TransferSession(device, ByteArray(16)) }
    rejects { TransferWire.captureId(session, 0uL) }
    val mutableDevice = device.copyOf(); val mutableIncarnation = incarnation.copyOf()
    val ownedSession = TransferSession(mutableDevice, mutableIncarnation)
    mutableDevice.fill(0); mutableIncarnation.fill(0); ownedSession.deviceIdBytes().fill(0)
    expect(ownedSession.deviceId == session.deviceId && ownedSession.storageIncarnation == session.storageIncarnation, "Session IDs were mutable")
    groups++

    val hello = TransferWire.hello(1)
    val helloWire = response(hello, 46).also {
        device.copyInto(it, 4); incarnation.copyInto(it, 20); putLe(it, 36, 0xffff_ffffL, 4)
        putLe(it, 40, 128, 2); putLe(it, 42, 512, 2); putLe(it, 44, 256, 2)
    }
    expect((TransferWire.decode(hello, helloWire, session) as TransferResponse.Hello).catalogCount == 128, "HELLO catalog bound differs")
    for (length in 0 until helloWire.size) rejects { TransferWire.decode(hello, helloWire.copyOf(length), session) }
    rejects { TransferWire.decode(hello, helloWire + byteArrayOf(0), session) }
    for ((at, value) in listOf(0 to 9, 1 to 2, 2 to 0, 3 to 1, 40 to 129, 42 to 1, 44 to 1)) {
        rejects { TransferWire.decode(hello, helloWire.copyOf().also { it[at] = value.toByte() }, session) }
    }
    for (at in listOf(4, 20, 36)) {
        val wire = helloWire.copyOf(); wire.fill(0, at, at + if (at == 36) 4 else 16)
        rejects { TransferWire.decode(hello, wire, session) }
    }
    rejects { TransferWire.decode(hello, helloWire.copyOf().also { it[4] = 0x12 }, session) }
    for ((request, _) in commands) for (status in 1..8) {
        val error = response(request, 4).also { it[0] = status.toByte() }
        expect((TransferWire.decode(request, error, session) as TransferResponse.Failure).status.ordinal == status, "Exact error status differs")
        rejects { TransferWire.decode(request, error + byteArrayOf(0), session) }
    }
    groups++

    val list = TransferWire.list(2, 17, 0)
    val listWire = response(list, 80).also { putLe(it, 4, 17, 4); manifest(17uL).copyInto(it, 10) }
    for (state in 0..4) {
        val wire = listWire.copyOf(); wire[78] = state.toByte(); wire[79] = 7
        val listing = TransferWire.decode(list, wire, session) as TransferResponse.Listing
        expect(listing.verification.ordinal == state && listing.sourceFlags == 7, "LIST unavailable-entry state differs")
    }
    for ((at, value) in listOf(4 to 18, 8 to 1, 78 to 5, 79 to 16, 79 to 8, 10 to 0)) {
        rejects { TransferWire.decode(list, listWire.copyOf().also { it[at] = value.toByte() }, session) }
    }
    val foreign = TransferSession(ByteArray(16) { 0x22 }, incarnation)
    val foreignWire = listWire.copyOf(); manifest(17uL, foreign).copyInto(foreignWire, 10); foreignWire[79] = 8
    expect((TransferWire.decode(list, foreignWire, session) as TransferResponse.Listing).manifest.deviceId == foreign.deviceId,
        "LIST must preserve a flagged foreign catalog entry")
    foreignWire[79] = 0; rejects { TransferWire.decode(list, foreignWire, session) }
    val outsideCatalog = listWire.copyOf(); putLe(outsideCatalog, 8, 128, 2)
    rejects { TransferWire.decode(TransferWire.list(2, 17, 128), outsideCatalog, session) }
    groups++

    for (status in 0..2) for (generation in listOf(1uL, 17uL, 1uL shl 63, ULong.MAX_VALUE)) {
        val selected = decodeSelection(selectedPair(status, generation))
        expect(selected.allocationGeneration == generation && selected.physicalReceipt.status.wireValue == status &&
            selected.derivedSeal == (status == 0) && selected.exportBytes == 217L, "SELECT unsigned generation or receipt distinction differs")
    }
    val pair = selectedPair()
    val selected = decodeSelection(pair)
    for (length in listOf(4, 76, 170, 194, 196)) rejects { TransferWire.decode(pair.first, pair.second.copyOf(length), session) }
    for ((at, value) in listOf(4 to 0, 8 to 0, 76 to 0, 170 to 0, 178 to 0, 186 to 1, 186 to 2, 187 to 18)) {
        val wire = pair.second.copyOf(); wire[at] = value.toByte()
        if (at == 4) wire.fill(0, 4, 8)
        rejects { TransferWire.decode(pair.first, wire, session) }
    }
    for (at in listOf(170, 178, 187)) {
        val wire = pair.second.copyOf(); wire.fill(0, at, at + 8)
        rejects { TransferWire.decode(pair.first, wire, session) }
    }
    for (at in listOf(170, 178)) {
        val wire = pair.second.copyOf(); putLe(wire, at, Long.MIN_VALUE, 8)
        rejects { TransferWire.decode(pair.first, wire, session) }
    }
    // Repaired CRC isolates identity/count semantics from checksum detection.
    for (at in listOf(6, 22, 38, 42, 50)) {
        val wire = pair.second.copyOf(); val ack = wire.copyOfRange(76, 170); ack[at] = (ack[at].toInt() xor 1).toByte()
        crc(ack).copyInto(wire, 76)
        rejects { TransferWire.decode(pair.first, wire, session) }
    }
    rejects { TransferWire.decode(TransferWire.select(3, ByteArray(16) { 1 }), pair.second, session) }
    rejects { TransferWire.decode(pair.first, pair.second, foreign) }
    val openPair = selectedPair(0)
    for (at in listOf(170, 178, 186)) {
        val wire = openPair.second.copyOf(); wire[at] = 0
        rejects { TransferWire.decode(openPair.first, wire, session) }
    }
    groups++

    val read = readPair(selected, 10, ByteArray(13) { it.toByte() })
    val decoded = TransferWire.decode(read.first, read.second, session, selected) as TransferResponse.ReadData
    expect(decoded.offset == 10L && decoded.count == 13 && decoded.bytes().contentEquals(ByteArray(13) { it.toByte() }), "Short READ differs")
    decoded.bytes().fill(99); read.second[18] = 99
    expect(decoded.bytes()[0] == 0.toByte(), "READ exposed callback/output mutation")
    rejects { TransferWire.decode(read.first, read.second, session, selected) } // bad CRC
    val goodRead = readPair(selected, 10, ByteArray(13) { it.toByte() })
    for (at in listOf(4, 8, 16, goodRead.second.lastIndex)) {
        val wire = goodRead.second.copyOf(); wire[at] = (wire[at].toInt() xor 1).toByte()
        rejects { TransferWire.decode(goodRead.first, wire, session, selected) }
    }
    rejects { TransferWire.decode(goodRead.first, goodRead.second + byteArrayOf(0), session, selected) }
    rejects { TransferWire.decode(goodRead.first, goodRead.second, session) }
    rejects { TransferWire.decode(goodRead.first, goodRead.second, foreign, selected) }
    rejects { TransferWire.decode(TransferWire.read(4, selected.handle, 10, 12), goodRead.second, session, selected) }
    val eof = readPair(selected, selected.exportBytes, byteArrayOf())
    expect((TransferWire.decode(eof.first, eof.second, session, selected) as TransferResponse.ReadData).count == 0, "EOF zero READ rejected")
    for ((offset, data) in listOf(0L to byteArrayOf(), selected.exportBytes to byteArrayOf(1),
            (selected.exportBytes - 1) to byteArrayOf(1, 2), (selected.exportBytes + 1) to byteArrayOf())) {
        val invalid = readPair(selected, offset, data)
        rejects { TransferWire.decode(invalid.first, invalid.second, session, selected) }
    }
    val last = readPair(selected, selected.exportBytes - 1, byteArrayOf(1))
    expect((TransferWire.decode(last.first, last.second, session, selected) as TransferResponse.ReadData).count == 1, "Exact final byte rejected")
    groups++

    for (status in 0..2) {
        val context = decodeSelection(selectedPair(status))
        val finish = finishPair(context)
        val finished = TransferWire.decode(finish.first, finish.second, session, context) as TransferResponse.Finished
        expect(finished.selection.physicalReceipt.encode().contentEquals(context.physicalReceipt.encode()), "FINISH changed physical proof")
        for (at in listOf(4, 13, 66, 102, 110, 111)) {
            val wire = finish.second.copyOf(); wire[at] = (wire[at].toInt() xor 1).toByte()
            rejects { TransferWire.decode(finish.first, wire, session, context) }
        }
        rejects { TransferWire.decode(TransferWire.finish(5, context.handle, 0), finish.second, session, context) }
        rejects { TransferWire.decode(finish.first, finish.second.copyOf(118), session, context) }
        rejects { TransferWire.decode(finish.first, finish.second + byteArrayOf(0), session, context) }
    }
    val cancel = TransferWire.cancel(6, selected.handle)
    val cancelWire = response(cancel, 8).also { putLe(it, 4, selected.handle, 4) }
    expect((TransferWire.decode(cancel, cancelWire, session, selected) as TransferResponse.Cancelled).handle == selected.handle, "CANCEL echo differs")
    rejects { TransferWire.decode(cancel, cancelWire.copyOf().also { it[4] = 0 }, session, selected) }
    rejects { TransferWire.decode(cancel, cancelWire + byteArrayOf(0), session, selected) }
    groups++

    // The C harness owns these golden bytes. This test cannot generate a missing
    // file itself, and encoding is compared against its actual command records.
    val source = File(fixtureIndex.readLines().first { it.isNotBlank() && !it.startsWith("#") }.split('\t')[1])
    val golden = File(source.parentFile.parentFile, "verification/transfer-wire-golden.tsv")
    check(golden.isFile && golden.length() in 1..(1024 * 1024)) { "Actual bounded C transfer golden TSV required" }
    val lines = golden.readLines().filter { it.isNotBlank() && !it.startsWith("#") }
    val records = if (lines.firstOrNull() == "name\tkind\thex") lines.drop(1) else lines
    val rows = records.map { it.split('\t') }
    check(rows.all { it.size == 3 }) { "Invalid C transfer golden row" }
    val contexts = rows.filter { it[1] == "context" }.associate { it[0] to hex(it[2]) }
    val goldenSession = TransferSession(checkNotNull(contexts["device_id"]), checkNotNull(contexts["incarnation"]))
    val requests = mutableMapOf<String, TransferCommand>()
    val responses = mutableMapOf<String, ByteArray>()
    val selections = mutableMapOf<Long, TransferSelection>()
    val fragmentReceivers = mutableMapOf<Pair<String, String>, Pair<BleResponseFragments, BleResponseFragments.Generation>>()
    val completedFragments = mutableSetOf<Pair<String, String>>()
    var goldenResponses = 0
    val covered = mutableSetOf<TransferOpcode>()
    for ((name, kind, text) in rows) {
        val wire = hex(text)
        if (kind == "command") {
            check(wire.size in 4..20 && wire[0] == 1.toByte())
            val txn = u16(wire, 2)
            val request = when (u8(wire, 1)) {
                1 -> TransferWire.hello(txn)
                2 -> TransferWire.list(txn, u32Bound(wire, 4, 0xffff_ffffL), u16(wire, 8))
                3 -> TransferWire.select(txn, wire.copyOfRange(4, 20))
                4 -> TransferWire.read(txn, u32Bound(wire, 4, 0xffff_ffffL), u64Bound(wire, 8, TransferWire.MAX_FILE_BYTES), u16(wire, 16))
                5 -> TransferWire.finish(txn, u32Bound(wire, 4, 0xffff_ffffL), u64Bound(wire, 8, TransferWire.MAX_FILE_BYTES))
                6 -> TransferWire.cancel(txn, u32Bound(wire, 4, 0xffff_ffffL))
                else -> error("Unsupported C golden opcode")
            }
            expect(request.encode().contentEquals(wire), "C command encoding differs: $name")
            check(requests.put(name, request) == null) { "Duplicate C command name" }
        } else if (kind == "response") {
            val request = checkNotNull(requests[name]) { "C response has no preceding command: $name" }
            val command = request.encode()
            val context = if (request.opcode in setOf(TransferOpcode.READ, TransferOpcode.FINISH, TransferOpcode.CANCEL))
                selections[u32Bound(command, 4, 0xffff_ffffL)] else null
            val result = TransferWire.decode(request, wire, goldenSession, context)
            if (result is TransferResponse.Selected) selections[result.selection.handle] = result.selection
            if (result !is TransferResponse.Failure) covered += request.opcode
            expect(result.transaction == request.transaction, "C response transaction differs: $name")
            check(responses.put(name, wire.copyOf()) == null) { "Duplicate C response name" }
            goldenResponses++
        } else if (kind in setOf("fragment23", "fragment517")) {
            val key = name to kind
            val (receiver, token) = fragmentReceivers.getOrPut(key) {
                val receiver = BleResponseFragments()
                receiver to receiver.begin(checkNotNull(requests[name]).transaction, if (kind == "fragment23") 23 else 517)
            }
            val result = receiver.accept(token, wire)
            if (result is BleFragmentResult.Complete) {
                expect(completedFragments.add(key), "C fragment sequence completed twice")
                expect(result.bytes().contentEquals(checkNotNull(responses[name])), "C fragments differ from exact logical reply: $name/$kind")
            }
        } else check(kind == "context") { "Unknown C golden row kind" }
    }
    expect(covered == TransferOpcode.entries.toSet() && goldenResponses >= 8, "C golden responses do not cover all commands and capture states")
    expect(completedFragments.size >= 4 && completedFragments == fragmentReceivers.keys,
        "C fragment fixture sequences are missing or incomplete")
    groups++
    return TransferWireCheckSummary(groups, checks, goldenResponses)
}
