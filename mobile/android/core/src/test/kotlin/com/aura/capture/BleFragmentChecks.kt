package com.aura.capture

internal data class BleFragmentCheckSummary(val groups: Int, val checks: Int)

/** Dependency-free checks called by the existing executable :core:verifyCore. */
internal fun verifyBleFragments(): BleFragmentCheckSummary {
    var checks = 0
    var groups = 0
    fun expect(ok: Boolean, message: String) {
        checks++
        check(ok) { message }
    }
    fun rejects(action: () -> Unit) {
        checks++
        try { action() } catch (_: BleFragmentException) { return }
        error("Invalid response fragment was accepted")
    }
    fun badArgument(action: () -> Unit) {
        checks++
        try { action() } catch (_: IllegalArgumentException) { return }
        error("Invalid reassembler configuration was accepted")
    }
    fun fragment(transaction: Int, offset: Int, total: Int, payload: ByteArray): ByteArray {
        val wire = ByteArray(8 + payload.size)
        wire[0] = 1
        for ((at, value) in listOf(2 to transaction, 4 to offset, 6 to total)) {
            wire[at] = value.toByte(); wire[at + 1] = (value ushr 8).toByte()
        }
        payload.copyInto(wire, 8)
        return wire
    }
    fun complete(result: BleFragmentResult): BleFragmentResult.Complete {
        expect(result is BleFragmentResult.Complete, "Reply did not complete")
        return result as BleFragmentResult.Complete
    }
    val r = BleResponseFragments()

    // Literal wire example does not use the test encoder: u16 fields are LE.
    val first = byteArrayOf(1, 0, 0x34, 0x12, 0, 0, 13, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
    val last = byteArrayOf(1, 0, 0x34, 0x12, 12, 0, 13, 0, 12)
    var token = r.begin(0x1234)
    expect(r.accept(token, first) == BleFragmentResult.Pending(12, 13), "Default MTU payload should be 12")
    val done = complete(r.accept(token, last))
    expect(done.transaction == 0x1234 && done.bytes().contentEquals(ByteArray(13) { it.toByte() }), "Golden logical bytes differ")
    expect(done.size == 13, "Complete result size differs")
    groups++

    // Every legal logical length, at the default and maximum ATT MTU. Completion
    // must occur exactly at total length, independent of fragmentation boundaries.
    for (mtu in listOf(23, 24, 185, 247, 517)) {
        for (length in 1..512) {
            val source = ByteArray(length) { ((it * 61 + length) and 255).toByte() }
            token = r.begin(65535, mtu)
            var offset = 0
            var result: BleFragmentResult = BleFragmentResult.Stale
            while (offset < length) {
                val end = minOf(length, offset + mtu - 11)
                result = r.accept(token, fragment(65535, offset, length, source.copyOfRange(offset, end)))
                expect((result is BleFragmentResult.Complete) == (end == length), "Completion boundary differs")
                offset = end
            }
            expect(complete(result).bytes().contentEquals(source), "MTU-independent bytes differ")
        }
    }
    groups++

    // Short, empty, oversized, version, flags, identity, u16 and total bounds.
    val invalid = (0..8).map { ByteArray(it) }.toMutableList()
    invalid += fragment(1, 0, 13, ByteArray(13)) // exceeds default MTU
    invalid += fragment(1, 0, 1, byteArrayOf(1)).also { it[0] = 2 }
    invalid += fragment(1, 0, 1, byteArrayOf(1)).also { it[1] = 1 }
    invalid += fragment(0, 0, 1, byteArrayOf(1))
    invalid += fragment(2, 0, 1, byteArrayOf(1))
    invalid += fragment(1, 0, 0, byteArrayOf(1))
    invalid += fragment(1, 0, 513, byteArrayOf(1))
    invalid += fragment(1, 0, 65535, byteArrayOf(1))
    invalid += fragment(1, 65535, 512, byteArrayOf(1))
    invalid += fragment(1, 512, 512, byteArrayOf(1))
    invalid += fragment(1, 0, 1, byteArrayOf(1, 2))
    for (wire in invalid) {
        token = r.begin(1)
        rejects { r.accept(token, wire) }
        expect(r.accept(token, fragment(1, 0, 1, byteArrayOf(1))) === BleFragmentResult.Stale, "Fault did not invalidate generation")
    }
    token = r.begin(1, 517)
    rejects { r.accept(token, fragment(1, 0, 512, ByteArray(507))) }
    for (id in listOf(-1, 0, 65536, Int.MAX_VALUE)) badArgument { r.begin(id) }
    for (mtu in listOf(-1, 0, 22, 518, Int.MAX_VALUE)) badArgument { r.begin(1, mtu) }
    groups++

    // An exact early or late retry is harmless, even after completion, but must
    // never emit Complete twice or retain the caller's mutable callback array.
    token = r.begin(7)
    val a = fragment(7, 0, 5, byteArrayOf(10, 11))
    val aCopy = a.copyOf()
    val b = fragment(7, 2, 5, byteArrayOf(12, 13))
    expect(r.accept(token, a) == BleFragmentResult.Pending(2, 5), "Initial fragment did not append")
    a.fill(99)
    expect(r.accept(token, aCopy) == BleFragmentResult.Duplicate(2, 5), "Input mutation changed retained bytes")
    expect(r.accept(token, b) == BleFragmentResult.Pending(4, 5), "Second fragment did not append")
    expect(r.accept(token, aCopy) == BleFragmentResult.Duplicate(4, 5), "Early exact duplicate rejected")
    val response = complete(r.accept(token, fragment(7, 4, 5, byteArrayOf(14))))
    val exported = response.bytes(); exported.fill(99)
    expect(response.bytes().contentEquals(byteArrayOf(10, 11, 12, 13, 14)), "Completion exposes mutable storage")
    expect(r.accept(token, b) == BleFragmentResult.Duplicate(5, 5), "Completed duplicate must not redeliver result")
    r.reset()
    expect(response.bytes().contentEquals(byteArrayOf(10, 11, 12, 13, 14)), "Reset changed an emitted response")
    groups++

    // All nonexact overlaps fail, including same-byte subranges or a fragment
    // that repeats a prefix and attempts to introduce additional bytes.
    val overlaps = listOf(
        fragment(7, 0, 5, byteArrayOf(99, 11)),
        fragment(7, 1, 5, byteArrayOf(11)),
        fragment(7, 0, 5, byteArrayOf(10)),
        fragment(7, 0, 5, byteArrayOf(10, 11, 12)),
        fragment(7, 1, 5, byteArrayOf(11, 12)),
        fragment(7, 3, 5, byteArrayOf(13)), // gap
        fragment(7, 2, 4, byteArrayOf(12, 13)), // changed total on append
        fragment(7, 0, 4, byteArrayOf(10, 11)), // changed total on duplicate
        fragment(8, 2, 5, byteArrayOf(12)), // different expected transaction
    )
    for (wire in overlaps) {
        token = r.begin(7)
        r.accept(token, aCopy)
        rejects { r.accept(token, wire) }
        expect(r.accept(token, b) === BleFragmentResult.Stale, "Failed reply still accepts fragments")
    }
    token = r.begin(7)
    rejects { r.accept(token, b) } // first fragment also cannot leave a gap
    groups++

    // A full worst-case response plus its exact replay fits the explicit budget.
    // An additional delivery fails even after completion; duplicate floods while
    // incomplete are equally bounded and cannot be promoted to completion.
    token = r.begin(12)
    for (i in 0 until 512) {
        val result = r.accept(token, fragment(12, i, 512, byteArrayOf(i.toByte())))
        expect((result is BleFragmentResult.Complete) == (i == 511), "One-byte completion differs")
    }
    for (i in 0 until 512) {
        expect(r.accept(token, fragment(12, i, 512, byteArrayOf(i.toByte()))) is BleFragmentResult.Duplicate, "Exact worst-case replay exceeds budget")
    }
    rejects { r.accept(token, fragment(12, 0, 512, byteArrayOf(0))) }
    token = r.begin(12)
    val repeated = fragment(12, 0, 2, byteArrayOf(1))
    r.accept(token, repeated)
    repeat(BleResponseFragments.MAX_FRAGMENT_DELIVERIES - 1) {
        expect(r.accept(token, repeated) is BleFragmentResult.Duplicate, "Duplicate changed progress")
    }
    rejects { r.accept(token, fragment(12, 1, 2, byteArrayOf(2))) }
    groups++

    // Tokens bind local generations, not just reused wire transaction numbers.
    // Obsolete callbacks (including malformed arrays) cannot poison new state.
    val old = r.begin(21)
    r.accept(old, fragment(21, 0, 2, byteArrayOf(1)))
    r.reset()
    expect(r.accept(old, fragment(21, 1, 2, byteArrayOf(2))) === BleFragmentResult.Stale, "Reset left old token active")
    token = r.begin(21)
    expect(token !== old, "Generation identity was reused")
    expect(r.accept(old, ByteArray(2048)) === BleFragmentResult.Stale, "Stale callback affected current generation")
    expect(complete(r.accept(token, fragment(21, 0, 1, byteArrayOf(42)))).bytes().contentEquals(byteArrayOf(42)), "Current generation was damaged by stale callback")
    repeat(1024) {
        val previous = token
        token = r.begin(21)
        expect(previous !== token && r.accept(previous, byteArrayOf()) === BleFragmentResult.Stale, "Begin reused or accepted obsolete generation")
    }
    r.reset()
    groups++

    return BleFragmentCheckSummary(groups, checks)
}
