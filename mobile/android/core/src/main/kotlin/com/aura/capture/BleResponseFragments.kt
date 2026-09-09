package com.aura.capture

/** Invalid response framing. This is not an archive, receipt, or GATT error. */
class BleFragmentException(message: String) : Exception(message)

sealed class BleFragmentResult {
    /** An obsolete callback was ignored without inspecting or retaining its bytes. */
    data object Stale : BleFragmentResult()
    data class Pending(val receivedBytes: Int, val totalBytes: Int) : BleFragmentResult()
    data class Duplicate(val receivedBytes: Int, val totalBytes: Int) : BleFragmentResult()

    /** Framing is complete; the logical response contents remain unvalidated. */
    class Complete internal constructor(val transaction: Int, bytes: ByteArray) : BleFragmentResult() {
        private val ownedBytes = bytes.copyOf()
        val size: Int get() = ownedBytes.size
        fun bytes(): ByteArray = ownedBytes.copyOf()
    }
}

/**
 * The response-fragment subset of docs/a04/mobile-transport.md, not a BLE client.
 *
 * One response owns at most 512 payload bytes plus 512 u16 boundary entries.
 * Each nonempty fragment must fit the actual negotiated ATT MTU. Only an exact
 * prior fragment (same offset, length, total and bytes) is a duplicate; a retry
 * cannot append new bytes through an overlapping fragment. The delivery budget
 * allows the worst-case 512 one-byte fragments and one entire exact retry.
 *
 * Keep the returned token with each callback. reset/begin invalidate old tokens,
 * including when a transaction number is reused on a new connection. The caller
 * still owns GATT identity, subscription, transaction allocation and deadlines,
 * and must copy callback bytes before queuing them elsewhere. These methods
 * serialize state changes and copy accepted input before parsing it.
 */
class BleResponseFragments {
    companion object {
        const val MAX_LOGICAL_BYTES = 512
        const val MAX_FRAGMENT_DELIVERIES = 1024
        const val DEFAULT_ATT_MTU = 23
    }

    /** Identity token avoids numeric generation wraparound; no wire authority. */
    class Generation internal constructor()

    private val buffer = ByteArray(MAX_LOGICAL_BYTES)
    private val fragmentLengths = ShortArray(MAX_LOGICAL_BYTES)
    private var active: Generation? = null
    private var transaction = 0
    private var maxPayload = 0
    private var total = 0
    private var received = 0
    private var deliveries = 0

    /** Begin only after obtaining the actual MTU; the safe default is 23. */
    @Synchronized
    fun begin(transaction: Int, actualAttMtu: Int = DEFAULT_ATT_MTU): Generation {
        require(transaction in 1..65535) { "Expected a nonzero u16 transaction" }
        require(actualAttMtu in 23..517) { "Invalid negotiated ATT MTU" }
        clear()
        this.transaction = transaction
        maxPayload = actualAttMtu - 11
        return Generation().also { active = it }
    }

    /** Cancel this partial/complete response, without a wire command or side effect. */
    @Synchronized
    fun reset() = clear()

    /**
     * Complete is emitted once. Exact retransmissions after completion return
     * Duplicate. A current-generation error clears state and throws; only a new
     * begin can accept further input. Stale input cannot cancel an active reply.
     */
    @Synchronized
    fun accept(generation: Generation, notification: ByteArray): BleFragmentResult {
        if (generation !== active) return BleFragmentResult.Stale
        if (notification.size !in 9..(8 + maxPayload)) fail("Fragment length exceeds ATT bounds")
        val wire = notification.copyOf()
        if (wire[0].toInt() != 1 || wire[1].toInt() != 0) fail("Unsupported fragment version or flags")
        if (readU16(wire, 2) != transaction) fail("Fragment transaction does not match")
        val offset = readU16(wire, 4)
        val declaredTotal = readU16(wire, 6)
        val length = wire.size - 8
        if (declaredTotal !in 1..MAX_LOGICAL_BYTES || offset >= declaredTotal || length > declaredTotal - offset) {
            fail("Fragment range is outside the logical response")
        }
        if (total != 0 && total != declaredTotal) fail("Fragment total changed")
        if (deliveries == MAX_FRAGMENT_DELIVERIES) fail("Fragment delivery budget exceeded")
        deliveries++

        if (offset < received) {
            if (fragmentLengths[offset].toInt() != length || offset + length > received) {
                fail("Overlap is not an exact prior fragment")
            }
            for (i in 0 until length) {
                if (wire[8 + i] != buffer[offset + i]) fail("Duplicate fragment bytes conflict")
            }
            return BleFragmentResult.Duplicate(received, total)
        }
        if (offset != received) fail("Fragment leaves a gap")
        total = declaredTotal
        wire.copyInto(buffer, offset, 8, wire.size)
        fragmentLengths[offset] = length.toShort()
        received += length
        return if (received == total) {
            BleFragmentResult.Complete(transaction, buffer.copyOf(total))
        } else {
            BleFragmentResult.Pending(received, total)
        }
    }

    private fun readU16(bytes: ByteArray, offset: Int): Int =
        (bytes[offset].toInt() and 255) or ((bytes[offset + 1].toInt() and 255) shl 8)

    private fun fail(message: String): Nothing {
        clear()
        throw BleFragmentException(message)
    }

    private fun clear() {
        active = null
        transaction = 0
        maxPayload = 0
        total = 0
        received = 0
        deliveries = 0
        buffer.fill(0)
        fragmentLengths.fill(0)
    }
}
