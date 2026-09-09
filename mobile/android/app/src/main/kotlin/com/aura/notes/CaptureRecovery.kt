package com.aura.notes

import android.content.Context
import com.aura.capture.ArchiveException
import com.aura.capture.CaptureManifest
import com.aura.capture.TransferCommand
import com.aura.capture.TransferResponse
import com.aura.capture.TransferSelection
import com.aura.capture.TransferSession
import com.aura.capture.TransferStatus
import com.aura.capture.TransferVerification
import com.aura.capture.TransferWire
import com.aura.capture.TransferWireException
import java.io.Closeable

enum class RecoveryPhase {
    BACKGROUND, SCHEDULED, CONNECTING, CATALOG, DOWNLOADING,
    SOURCE_PRESERVED, PROCESSING, READY, SOURCE_SKIPPED, RETRY_WAIT,
    COMPLETE, ATTENTION, CANCELLED, CLOSED,
}

/** Fixed reasons only: transport exceptions, identities and source contents are never displayed. */
enum class RecoveryReason { NONE, CONNECTION, SESSION_REJECTED, PROTOCOL, SOURCE_UNAVAILABLE,
    SOURCE_CHANGED, SOURCE_INVALID, SOURCE_STALLED, STORAGE, PLAYBACK, CATALOG_CHANGED, RETRY_LIMIT }

/** All counters describe this recovery pass. Preserved bytes do not imply playable audio. */
data class RecoveryStatus(
    val generation: Long,
    val phase: RecoveryPhase,
    val reason: RecoveryReason = RecoveryReason.NONE,
    val catalogCount: Int = 0,
    val sourcesPreserved: Int = 0,
    val sourcesReady: Int = 0,
    val sourcesSkipped: Int = 0,
    val sourceKey: String? = null,
    val committedBytes: Long = 0,
    val receivedBytes: Long = 0,
    val exportBytes: Long = 0,
    val libraryKey: String? = null,
)

/** Configurable budgets, not measured NAND/phone performance. Full source
 * verification and first-seek/EOF replay may scan a large source at low SPI rate. */
data class RecoveryTimeouts(
    val commandMillis: Long = 30_000,
    val sourceVerificationMillis: Long = 3_600_000,
) {
    init {
        require(commandMillis in 1_000..300_000)
        require(sourceVerificationMillis in commandMillis..7_200_000)
    }
}

/** Internal knobs let instrumentation force rollover with the actual small C
 * archives. A 256 minimum still fits HELLO plus the entire 128-entry catalog. */
internal class RecoveryPolicy(
    val timeouts: RecoveryTimeouts = RecoveryTimeouts(),
    val transactionLimit: Int = 65_535,
    retryDelaysMillis: List<Long> = listOf(1_000, 3_000, 10_000),
    val catalogRefreshLimit: Int = 2,
) {
    val retryDelaysMillis = retryDelaysMillis.toList()
    init {
        require(transactionLimit in 256..65_535)
        require(this.retryDelaysMillis.size <= 3 && this.retryDelaysMillis.all { it in 1..30_000 })
        require(catalogRefreshLimit in 0..2)
    }
}

/**
 * One foreground recovery worker over a separately authenticated connection.
 * This class is intentionally not wired into Activity/consumer access: public
 * device IDs and a Bluetooth bond cannot substitute for ownership enrollment.
 * The factory must be nonblocking; exchange lazily connects on this worker.
 *
 * start()/foreground entry queues one scan. retry() coalesces repeated wakes,
 * including one follow-up while a scan runs. Background/cancel/close invalidate
 * generations, promptly close the connection and interrupt processing. No
 * background service, periodic timer, source deletion or release exists here.
 *
 * The immutable observer runs serialized under the lifecycle monitor; it must
 * return promptly (e.g. post to a UI dispatcher). It must retain the generation
 * when dispatching asynchronously. Its exceptions do not alter saved sources.
 * close is nonblocking; the worker unwinds its storage owner independently.
 */
class CaptureRecovery internal constructor(
    context: Context,
    private val trusted: TransferSession,
    private val connectionFactory: () -> TransferConnection,
    private val observer: (RecoveryStatus) -> Unit,
    private val policy: RecoveryPolicy,
) : Closeable {
    constructor(context: Context, trusted: TransferSession, connectionFactory: () -> TransferConnection,
        observer: (RecoveryStatus) -> Unit, timeouts: RecoveryTimeouts = RecoveryTimeouts()) :
        this(context, trusted, connectionFactory, observer, RecoveryPolicy(timeouts))

    private val appContext = context.applicationContext
    private val monitor = Object()
    private var foreground = false
    private var closed = false
    private var pending = false
    private var running = false
    private var generation = 0L
    private var activeConnection: TransferConnection? = null
    private var state = RecoveryStatus(0, RecoveryPhase.BACKGROUND)
    private val worker = Thread({ workLoop() }, "aura-foreground-recovery").apply {
        isDaemon = true
        start()
    }

    fun snapshot(): RecoveryStatus = synchronized(monitor) { state }

    fun start() {
        if (synchronized(monitor) { foreground && !closed }) retry() else setForeground(true)
    }

    fun setForeground(value: Boolean) {
        val toClose = synchronized(monitor) {
            if (closed || foreground == value) return
            foreground = value; pending = value; generation++
            val connection = activeConnection
            activeConnection = null
            // Interrupt under the monitor so this cancellation cannot land on
            // a later generation after the worker has resumed.
            worker.interrupt()
            emitLocked(RecoveryStatus(generation, if (value) RecoveryPhase.SCHEDULED else RecoveryPhase.BACKGROUND))
            monitor.notifyAll()
            connection
        }
        closeQuietly(toClose)
    }

    /** Only one pending wake is retained; retries while background do no work. */
    fun retry() = synchronized(monitor) {
        if (!closed && foreground) {
            pending = true
            if (!running) emitLocked(state.copy(phase = RecoveryPhase.SCHEDULED, reason = RecoveryReason.NONE))
            monitor.notifyAll()
        }
    }

    fun cancel() = stop(false)

    override fun close() = stop(true)

    private fun stop(permanent: Boolean) {
        val toClose = synchronized(monitor) {
            if (closed) return
            closed = permanent; pending = false; generation++
            if (permanent) foreground = false
            val connection = activeConnection; activeConnection = null
            worker.interrupt()
            emitLocked(RecoveryStatus(generation, if (permanent) RecoveryPhase.CLOSED else RecoveryPhase.CANCELLED))
            monitor.notifyAll()
            connection
        }
        closeQuietly(toClose)
    }

    private fun workLoop() {
        while (true) {
            val token = synchronized(monitor) {
                while (!closed && (!foreground || !pending)) {
                    try { monitor.wait() } catch (_: InterruptedException) { /* own lifecycle wake */ }
                }
                if (closed) return
                pending = false; running = true; generation++
                // A cancelled previous pass must not poison the new one.
                Thread.interrupted()
                generation
            }
            val run = Run(token)
            try {
                run.execute()
            } catch (_: Cancelled) {
                // A newer lifecycle state already owns the observer.
            } catch (_: Exception) {
                run.report(RecoveryPhase.ATTENTION, RecoveryReason.STORAGE, failIfStale = false)
            } finally {
                run.disconnect()
                synchronized(monitor) { running = false; monitor.notifyAll() }
            }
        }
    }

    private inner class Run(private val token: Long) {
        private var wire: Wire? = null
        private var catalogCount = 0
        private val preserved = HashSet<String>()
        private val ready = HashSet<String>()
        private val failures = LinkedHashMap<String, RecoveryReason>()
        private val pins = HashMap<String, TransferSelection>()
        private var source: DownloadProgress? = null
        private var libraryKey: String? = null

        fun report(phase: RecoveryPhase, reason: RecoveryReason = RecoveryReason.NONE, failIfStale: Boolean = true) {
            synchronized(monitor) {
                if (!active(token)) {
                    if (failIfStale) throw Cancelled()
                    return
                }
                emitLocked(RecoveryStatus(token, phase, reason, catalogCount, preserved.size, ready.size, failures.size,
                    source?.key, source?.committedBytes ?: 0, source?.receivedBytes ?: 0,
                    source?.exportBytes ?: 0, libraryKey))
            }
        }

        fun execute() {
            var connectionFailures = 0
            var catalogRefreshes = 0
            while (true) {
                checkActive(token)
                try {
                    val entries = catalog()
                    for (entry in entries) {
                        checkActive(token)
                        source = null; libraryKey = null
                        if (entry.sourceFlags != 0 || entry.verification == TransferVerification.INVALID) {
                            skip(entry.manifest.identity, RecoveryReason.SOURCE_UNAVAILABLE); continue
                        }
                        try { recover(entry.manifest) }
                        catch (failure: SourceFailure) {
                            checkActive(token)
                            disconnect()
                            skip(entry.manifest.identity, failure.reason)
                        }
                    }
                    report(if (failures.isEmpty()) RecoveryPhase.COMPLETE else RecoveryPhase.ATTENTION,
                        if (failures.isEmpty()) RecoveryReason.NONE else RecoveryReason.SOURCE_UNAVAILABLE)
                    return
                } catch (_: RefreshCatalog) {
                    disconnect()
                    if (catalogRefreshes++ >= policy.catalogRefreshLimit) {
                        report(RecoveryPhase.ATTENTION, RecoveryReason.CATALOG_CHANGED); return
                    }
                    report(RecoveryPhase.RETRY_WAIT, RecoveryReason.CATALOG_CHANGED)
                    pause(token, policy.retryDelaysMillis.firstOrNull() ?: 1_000)
                } catch (_: ConnectionFailure) {
                    disconnect()
                    if (connectionFailures >= policy.retryDelaysMillis.size) {
                        report(RecoveryPhase.ATTENTION, RecoveryReason.RETRY_LIMIT); return
                    }
                    report(RecoveryPhase.RETRY_WAIT, RecoveryReason.CONNECTION)
                    pause(token, policy.retryDelaysMillis[connectionFailures++])
                } catch (_: SessionFailure) {
                    report(RecoveryPhase.ATTENTION, RecoveryReason.SESSION_REJECTED); return
                } catch (_: ProtocolFailure) {
                    report(RecoveryPhase.ATTENTION, RecoveryReason.PROTOCOL); return
                }
            }
        }

        private fun skip(key: String, reason: RecoveryReason) {
            failures[key] = reason
            report(RecoveryPhase.SOURCE_SKIPPED, reason)
        }

        private fun catalog(): List<TransferResponse.Listing> {
            // Each refresh/connection retry obtains a new bounded catalog.
            disconnect()
            source = null; libraryKey = null
            val owner = connection()
            catalogCount = owner.hello.catalogCount
            failures.keys.removeAll { it.startsWith("catalog:") }
            report(RecoveryPhase.CATALOG)
            val entries = ArrayList<TransferResponse.Listing>(catalogCount)
            for (index in 0 until catalogCount) {
                when (val reply = owner.exchange({ TransferWire.list(it, owner.hello.revision, index) })) {
                    is TransferResponse.Listing -> entries += reply
                    is TransferResponse.Failure -> when (reply.status) {
                        TransferStatus.STALE, TransferStatus.END_OF_LIST -> throw RefreshCatalog()
                        TransferStatus.FORBIDDEN -> throw SessionFailure()
                        else -> skip("catalog:$index", RecoveryReason.SOURCE_UNAVAILABLE)
                    }
                    else -> throw ProtocolFailure()
                }
            }
            val currentSources = entries.map { it.manifest.identity }.toSet()
            failures.keys.removeAll { !it.startsWith("catalog:") && it !in currentSources }
            return entries
        }

        private fun recover(manifest: CaptureManifest) {
            var lastRolloverOffset: Long? = null
            var stalledRollovers = 0
            while (true) {
                checkActive(token)
                try {
                    val owner = connection()
                    val selected = when (val reply = owner.exchange({
                        TransferWire.select(it, decodeId(manifest.captureId))
                    }, verification = true)) {
                        is TransferResponse.Selected -> reply.selection
                        is TransferResponse.Failure -> sourceError(reply)
                        else -> throw ProtocolFailure()
                    }
                    if (!selected.manifest.encode().contentEquals(manifest.encode()) ||
                        (pins[manifest.identity]?.let { !sameSource(it, selected) } == true)) {
                        throw SourceFailure(RecoveryReason.SOURCE_CHANGED)
                    }
                    pins[manifest.identity] = selected
                    val download = try { DownloadStore(appContext).open(selected) }
                    catch (_: ArchiveException) { throw SourceFailure(RecoveryReason.SOURCE_INVALID) }
                    catch (_: Exception) { checkActive(token); throw SourceFailure(RecoveryReason.STORAGE) }
                    download.use {
                        source = it.progress()
                        if (ready.contains(checkNotNull(source).key)) {
                            failures.remove(manifest.identity)
                            return
                        }
                        report(RecoveryPhase.DOWNLOADING)
                        var first = true
                        while (checkNotNull(source).receivedBytes < selected.exportBytes) {
                            val offset = checkNotNull(source).receivedBytes
                            val data = read(owner, selected, offset, first)
                            first = false
                            try { source = it.append(data) }
                            catch (_: ArchiveException) { throw SourceFailure(RecoveryReason.SOURCE_INVALID) }
                            catch (_: Exception) { checkActive(token); throw SourceFailure(RecoveryReason.STORAGE) }
                            report(RecoveryPhase.DOWNLOADING)
                        }
                        // Real C FINISH requires seeked && next_offset == EOF.
                        // A reopened fully saved archive still performs this READ;
                        // otherwise a scripted transport could conceal a wire bug.
                        val eof = read(owner, selected, selected.exportBytes, verification = true)
                        if (eof.count != 0) throw ProtocolFailure()
                        if (!checkNotNull(source).complete) source = it.append(eof)
                        val finished = when (val reply = owner.exchange({
                            TransferWire.finish(it, selected.handle, selected.exportBytes)
                        }, selected, verification = true)) {
                            is TransferResponse.Finished -> reply
                            is TransferResponse.Failure -> sourceError(reply, ownershipRequired = true)
                            else -> throw ProtocolFailure()
                        }
                        try { source = it.finish(finished) }
                        catch (_: ArchiveException) { throw SourceFailure(RecoveryReason.SOURCE_INVALID) }
                        catch (_: Exception) { checkActive(token); throw SourceFailure(RecoveryReason.STORAGE) }
                        checkActive(token)
                        preserved += checkNotNull(source).key
                        report(RecoveryPhase.SOURCE_PRESERVED)
                        report(RecoveryPhase.PROCESSING)
                        checkActive(token)
                        val capture = try { CaptureStore(appContext).importDownload(it) }
                        catch (_: Exception) { checkActive(token); throw SourceFailure(RecoveryReason.PLAYBACK) }
                        checkActive(token)
                        libraryKey = capture.key
                        failures.remove(manifest.identity)
                        // Empty captures remain useful preserved evidence but do
                        // not become playable just because library import succeeds.
                        if (capture.playbackReady) {
                            ready += checkNotNull(source).key
                            report(RecoveryPhase.READY)
                        } else report(RecoveryPhase.SOURCE_PRESERVED)
                    }
                    return
                } catch (_: Rollover) {
                    // use{} closes the database before its parser is replaced.
                    // Re-SELECT exact pinned metadata and resume committed bytes,
                    // never the discarded partial record or a previous handle.
                    disconnect()
                    val committed = source?.committedBytes ?: 0L
                    stalledRollovers = if (lastRolloverOffset == committed) stalledRollovers + 1 else 0
                    lastRolloverOffset = committed
                    if (stalledRollovers >= 2) throw SourceFailure(RecoveryReason.SOURCE_STALLED)
                } catch (_: ProtocolFailure) {
                    throw SourceFailure(RecoveryReason.SOURCE_INVALID)
                }
            }
        }

        private fun read(owner: Wire, selected: TransferSelection, offset: Long, verification: Boolean): TransferResponse.ReadData =
            when (val reply = owner.exchange({ TransferWire.read(it, selected.handle, offset, 256) }, selected, verification)) {
                is TransferResponse.ReadData -> reply
                is TransferResponse.Failure -> sourceError(reply, ownershipRequired = true)
                else -> throw ProtocolFailure()
            }

        private fun sourceError(reply: TransferResponse.Failure, ownershipRequired: Boolean = false): Nothing {
            if (reply.status == TransferStatus.STALE) throw RefreshCatalog()
            if (ownershipRequired && reply.status == TransferStatus.FORBIDDEN) throw SessionFailure()
            throw SourceFailure(RecoveryReason.SOURCE_UNAVAILABLE)
        }

        private fun connection(): Wire {
            wire?.let { return it }
            checkActive(token)
            report(RecoveryPhase.CONNECTING)
            val connected = try { connectionFactory() } catch (_: Exception) {
                checkActive(token); throw ConnectionFailure()
            }
            try {
                synchronized(monitor) {
                    if (!active(token)) throw Cancelled()
                    check(activeConnection == null)
                    activeConnection = connected
                }
                val owner = Wire(connected)
                wire = owner
                owner.hello = when (val reply = owner.exchange({ TransferWire.hello(it) })) {
                    is TransferResponse.Hello -> reply
                    is TransferResponse.Failure -> if (reply.status == TransferStatus.BUSY || reply.status == TransferStatus.IO_ERROR)
                        throw ConnectionFailure() else throw SessionFailure()
                    else -> throw SessionFailure()
                }
                return owner
            } catch (_: ProtocolFailure) {
                closeQuietly(connected)
                throw SessionFailure()
            } catch (error: Exception) {
                closeQuietly(connected)
                throw error
            }
        }

        fun disconnect() {
            val current = wire?.connection
            wire = null
            synchronized(monitor) { if (activeConnection === current) activeConnection = null }
            closeQuietly(current)
        }

        private inner class Wire(val connection: TransferConnection) {
            lateinit var hello: TransferResponse.Hello
            private var next = 1
            fun exchange(command: (Int) -> TransferCommand, selected: TransferSelection? = null,
                verification: Boolean = false): TransferResponse {
                checkActive(token)
                if (next > policy.transactionLimit) throw Rollover()
                val request = command(next++)
                val bytes = try {
                    connection.exchange(request, if (verification) policy.timeouts.sourceVerificationMillis else policy.timeouts.commandMillis)
                } catch (_: Exception) { checkActive(token); throw ConnectionFailure() }
                checkActive(token)
                return try { TransferWire.decode(request, bytes, trusted, selected) }
                catch (_: TransferWireException) { throw ProtocolFailure() }
            }
        }
    }

    private fun active(token: Long) = !closed && foreground && generation == token && !worker.isInterrupted
    private fun checkActive(token: Long) = synchronized(monitor) { if (!active(token)) throw Cancelled() }
    private fun pause(token: Long, millis: Long) = synchronized(monitor) {
        val deadline = System.nanoTime() + millis * 1_000_000
        while (true) {
            if (!active(token)) throw Cancelled()
            val remaining = deadline - System.nanoTime()
            if (remaining <= 0) break
            try { monitor.wait(maxOf(1, remaining / 1_000_000)) }
            catch (_: InterruptedException) { throw Cancelled() }
        }
    }
    private fun emitLocked(next: RecoveryStatus) {
        state = next
        try { observer(next) } catch (_: Exception) { /* observer cannot publish or undo source bytes */ }
    }
    private fun closeQuietly(connection: TransferConnection?) {
        try { connection?.close() } catch (_: Exception) { /* connection is already invalidated */ }
    }
    private fun decodeId(hex: String) = ByteArray(16) { hex.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
    private fun sameSource(a: TransferSelection, b: TransferSelection) =
        a.manifest.encode().contentEquals(b.manifest.encode()) &&
            a.physicalReceipt.encode().contentEquals(b.physicalReceipt.encode()) &&
            a.physicalBytes == b.physicalBytes && a.exportBytes == b.exportBytes && a.derivedSeal == b.derivedSeal &&
            a.allocationGeneration == b.allocationGeneration && a.storageIncarnation == b.storageIncarnation

    private class Cancelled : Exception()
    private class Rollover : Exception()
    private class RefreshCatalog : Exception()
    private class ConnectionFailure : Exception()
    private class SessionFailure : Exception()
    private class ProtocolFailure : Exception()
    private class SourceFailure(val reason: RecoveryReason) : Exception()
}
