package com.aura.notes

import com.aura.capture.TransferCommand
import java.io.Closeable

/** Transport boundary, not ownership enrollment. A connection factory must be
 * nonblocking; connect/discovery/subscription happens on the first exchange.
 * The recovery owner supplies separately authenticated TransferSession IDs.
 *
 * One worker calls exchange. close may be called from another thread, must
 * wake an in-flight exchange, and permanently invalidates this connection.
 * Returned logical bytes are untrusted until TransferWire.decode succeeds.
 */
interface TransferConnection : Closeable {
    fun exchange(command: TransferCommand, timeoutMillis: Long): ByteArray
    override fun close()
}

/** Fixed transport failures must not contain peer identifiers or source data. */
class TransferConnectionException(message: String) : Exception(message)
