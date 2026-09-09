package com.aura.notes

import android.content.Context
import android.content.ContextWrapper
import com.aura.capture.ReceiptStatus
import com.aura.capture.TransferCommand
import com.aura.capture.TransferResponse
import com.aura.capture.TransferSelection
import com.aura.capture.TransferSession
import com.aura.capture.TransferWire
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.zip.CRC32

/** Real Android SQLite/library/decoder with a deliberately scripted logical
 * transport. This does not test GATT, radio timing, ownership or a power cut. */
internal fun runCaptureRecoveryChecks(testContext: Context, targetContext: Context,
    runCase: (String, () -> Unit) -> Unit, expect: (Boolean, String) -> Unit): JSONObject =
    RecoveryChecks(testContext, targetContext, runCase, expect).run()

private class RecoveryChecks(private val testContext: Context, private val targetContext: Context,
    private val runCase: (String, () -> Unit) -> Unit, private val expect: (Boolean, String) -> Unit) {
    private lateinit var trusted: TransferSession
    private lateinit var fixtures: List<Fixture>

    fun run(): JSONObject {
        load()
        runCase("recovery real C finalized and OPEN sources reach independently decoded library") { roundtrip() }
        runCase("recovery transaction rollover reselects exact source and resumes committed boundary") { rollover() }
        runCase("recovery background cancellation rejects late replies and foreground replay resumes") { lifecycle() }
        runCase("recovery repeated wakes coalesce into one serialized follow-up") { coalescing() }
        runCase("recovery mismatched identity and FINISH cannot mark source saved") { rejectedReplies() }
        runCase("recovery connection retry and stale catalog refresh have finite budgets") { retryBudgets() }
        runCase("recovery unavailable catalog entries and busy selections never become saved") { unavailable() }
        runCase("recovery source pin survives reconnect and revoked access stops the pass") { reconnectIdentity() }
        runCase("recovery repeated failed source is counted once and later success resolves it") { reconciledFailures() }
        runCase("recovery tiny READ rollover without record progress fails within a fixed bound") { stalledRollover() }
        return JSONObject().put("transport", "scripted TransferConnection logical replies from exact owned C archives")
            .put("storage", "actual Android DownloadStore and CaptureStore")
            .put("rollover_transaction_limit", 256).put("scripted_read_bytes", 128)
            .put("gatt_tested", false).put("physical_recording_tested", false)
            .put("enrollment_tested", false).put("scripted_timing_is_performance_evidence", false)
    }

    private data class Fixture(val name: String, val bytes: ByteArray, val ack: ByteArray,
        val select: ByteArray, val finish: ByteArray) {
        val captureId: ByteArray get() = bytes.copyOfRange(24, 40)
    }

    private fun load() {
        val index = JSONObject(String(testContext.assets.open("downloads/index.json").use { it.readBytes() }, Charsets.UTF_8))
        val contexts = index.getJSONObject("contexts")
        trusted = TransferSession(hex(contexts.getString("device_id")), hex(contexts.getString("incarnation")))
        val rows = index.getJSONArray("fixtures")
        fixtures = (0 until rows.length()).map { at ->
            val row = rows.getJSONObject(at)
            fun asset(field: String): ByteArray {
                val entry = row.getJSONObject(field)
                val bytes = testContext.assets.open("downloads/${entry.getString("asset")}").use { it.readBytes() }
                expect(bytes.size == entry.getInt("bytes") && sha(bytes) == entry.getString("sha256"), "Recovery C fixture changed")
                return bytes
            }
            Fixture(row.getString("name"), asset("archive"), asset("physical"),
                hex(row.getString("select_response")), hex(row.getString("finish_response")))
        }
        expect(fixtures.map { it.name }.toSet() == setOf("finalized", "open"), "Missing recovery C fixture states")
    }

    private class Events {
        val states = CopyOnWriteArrayList<RecoveryStatus>()
        private val changed = Object()
        fun record(state: RecoveryStatus) { synchronized(changed) { states += state; changed.notifyAll() } }
        fun until(predicate: (List<RecoveryStatus>) -> Boolean): List<RecoveryStatus> = synchronized(changed) {
            val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(45)
            while (!predicate(states)) {
                val remaining = deadline - System.nanoTime()
                check(remaining > 0) { "Recovery event wait exceeded bound; last phase=${states.lastOrNull()?.phase}" }
                changed.wait(maxOf(1, TimeUnit.NANOSECONDS.toMillis(remaining)))
            }
            states.toList()
        }
        fun terminal() = until { values -> values.lastOrNull()?.phase in setOf(RecoveryPhase.COMPLETE, RecoveryPhase.ATTENTION) }.last()
    }

    private fun coordinator(context: Context, script: Script, events: Events,
        transactionLimit: Int = 65535, retries: List<Long> = listOf(1, 2, 3)) =
        CaptureRecovery(context, trusted, script::connect, events::record,
            RecoveryPolicy(transactionLimit = transactionLimit, retryDelaysMillis = retries))

    private fun roundtrip() {
        val context = fresh("roundtrip")
        val script = Script(fixtures); val events = Events()
        coordinator(context, script, events).use { recovery ->
            expect(script.connections.isEmpty(), "Constructor connected without foreground authorization")
            recovery.retry()
            expect(script.connections.isEmpty(), "Background retry connected")
            recovery.start()
            val done = events.terminal()
            expect(done.phase == RecoveryPhase.COMPLETE && done.sourcesPreserved == 2 && done.sourcesReady == 2,
                "Recovery did not preserve and decode both C sources")
            val library = CaptureStore(context).list()
            expect(library.size == 2 && library.all { it.playbackReady }, "Actual decoder/library handoff failed")
            for (fixture in fixtures) {
                val item = library.single { it.fileSha256 == sha(fixture.bytes) }
                expect(File(item.bundle, "source.aura").readBytes().contentEquals(fixture.bytes), "Recovery rewrote original C source")
                expect(File(item.bundle, "physical.ack").readBytes().contentEquals(fixture.ack), "Recovery rewrote physical provenance")
                if (fixture.name == "open") expect(item.physicalStatus == ReceiptStatus.OPEN && item.status == ReceiptStatus.INTERRUPTED,
                    "Physical OPEN was promoted to device finalization")
            }
            val firstPreserved = events.states.indexOfFirst { it.phase == RecoveryPhase.SOURCE_PRESERVED }
            val firstProcessing = events.states.indexOfFirst { it.phase == RecoveryPhase.PROCESSING }
            val firstReady = events.states.indexOfFirst { it.phase == RecoveryPhase.READY }
            expect(firstPreserved >= 0 && firstPreserved < firstProcessing && firstProcessing < firstReady,
                "Preserved source and playable media were conflated")
            expect(script.finishes.get() == 2 && script.eofReads.get() == 2, "FINISH did not follow an actual EOF READ")
        }
    }

    private fun rollover() {
        val fixture = fixtures.first(); val context = fresh("rollover")
        val script = Script(listOf(fixture)); val events = Events()
        coordinator(context, script, events, transactionLimit = 256).use { recovery ->
            recovery.start(); val done = events.terminal()
            expect(done.phase == RecoveryPhase.COMPLETE && done.sourcesReady == 1, "Rollover did not complete source")
            expect(script.connections.size >= 2 && script.connections.all { it.maxTransaction <= 256 },
                "Rollover reused or exceeded transaction ceiling")
            val offsets = script.firstReadOffsets.toList()
            expect(offsets.first() == 0L && offsets.drop(1).all { it > 0 && it < fixture.bytes.size && boundary(fixture.bytes, it) },
                "Rollover resumed a partial record or failed to preserve progress")
            expect(CaptureStore(context).list().single().fileSha256 == sha(fixture.bytes), "Rollover changed source identity")
        }
        // A complete local source must still perform EOF READ in a new handle
        // before FINISH; direct FINISH is rejected by the scripted C gate.
        val again = Script(listOf(fixture)); val repeated = Events()
        coordinator(context, again, repeated).use { recovery ->
            recovery.start(); expect(repeated.terminal().sourcesReady == 1, "Completed-source retry failed")
            expect(again.firstReadOffsets.single() == fixture.bytes.size.toLong() && again.eofReads.get() == 1,
                "Reopened complete source skipped the real C seek/EOF gate")
            expect(CaptureStore(context).list().size == 1, "Repeated source created another library revision")
        }
    }

    private fun lifecycle() {
        val fixture = fixtures.first(); val context = fresh("lifecycle")
        val script = Script(listOf(fixture), blockRead = true, lateReply = true)
        val events = Events()
        coordinator(context, script, events).use { recovery ->
            recovery.start()
            await(script.blocked, "READ never reached cancellation barrier")
            val oldGeneration = recovery.snapshot().generation
            recovery.setForeground(false)
            expect(script.connections.first().closed.get(), "Background did not promptly close exchange")
            expect(recovery.snapshot().phase == RecoveryPhase.BACKGROUND, "Background phase was not authoritative")
            recovery.setForeground(true)
            val done = events.terminal()
            expect(done.phase == RecoveryPhase.COMPLETE && done.generation > oldGeneration, "Foreground did not resume new generation")
            val committedAtCancel = (0L..128L).last { boundary(fixture.bytes, it) }
            expect(script.firstReadOffsets.size == 2 && script.firstReadOffsets[1] == committedAtCancel,
                "Cancelled partial record was treated as committed")
            val background = events.states.indexOfFirst { it.phase == RecoveryPhase.BACKGROUND }
            expect(events.states.drop(background + 1).none { it.generation == oldGeneration && it.phase == RecoveryPhase.READY },
                "Late obsolete callback marked the cancelled generation ready")
            recovery.cancel()
            expect(recovery.snapshot().phase == RecoveryPhase.CANCELLED, "Explicit cancellation did not invalidate status")
            recovery.start()
            expect(events.terminal().phase == RecoveryPhase.COMPLETE, "Explicit start after cancel did not queue a new pass")
        }
    }

    private fun coalescing() {
        val context = fresh("coalescing")
        val script = Script(emptyList(), blockHello = true); val events = Events()
        coordinator(context, script, events).use { recovery ->
            recovery.start(); await(script.blocked, "HELLO never reached coalescing barrier")
            repeat(50) { recovery.retry() }
            expect(script.connections.size == 1, "Repeated wakes started parallel connections")
            script.release.countDown()
            events.until { it.count { state -> state.phase == RecoveryPhase.COMPLETE } == 2 }
            expect(script.connections.size == 2 && script.maximumExchanges.get() == 1, "Wakes did not coalesce to one serialized follow-up")
            recovery.close(); recovery.start(); recovery.retry()
            expect(recovery.snapshot().phase == RecoveryPhase.CLOSED && script.connections.size == 2,
                "Closed owner restarted hidden work")
        }
    }

    private fun rejectedReplies() {
        val fixture = fixtures.first()
        for (fault in listOf("identity", "finish")) {
            val context = fresh(fault); val script = Script(listOf(fixture), fault = fault); val events = Events()
            coordinator(context, script, events).use { recovery ->
                recovery.start(); val done = events.terminal()
                expect(done.phase == RecoveryPhase.ATTENTION && done.sourcesPreserved == 0 && done.sourcesReady == 0,
                    "Invalid identity/FINISH marked a source saved")
                expect(CaptureStore(context).list().isEmpty(), "Invalid logical reply published playback")
                if (fault == "identity") expect(script.connections.size == 1 && script.reads.get() == 0 &&
                    done.reason == RecoveryReason.SESSION_REJECTED, "Mismatched HELLO fell back or read source")
                else DownloadStore(context).open(selection(fixture)).use {
                    expect(!it.progress().complete && it.progress().committedBytes == fixture.bytes.size.toLong(),
                        "Rejected FINISH lost exact retained source or completed it")
                }
            }
        }
    }

    private fun retryBudgets() {
        for (fault in listOf("connection", "stale")) {
            val context = fresh(fault); val script = Script(fixtures.take(1), fault = fault); val events = Events()
            coordinator(context, script, events).use { recovery ->
                recovery.start(); val done = events.terminal()
                expect(done.phase == RecoveryPhase.ATTENTION && done.sourcesPreserved == 0, "Retry budget claimed completion")
                val expectedConnections = if (fault == "connection") 4 else 3
                expect(script.connections.size == expectedConnections && script.reads.get() == 0,
                    "Automatic retry/catalog refresh was unbounded")
            }
        }
    }

    private fun unavailable() {
        for (fault in listOf("busy", "flag", "invalid")) {
            val script = Script(fixtures.take(1), fault = fault); val events = Events()
            coordinator(fresh(fault), script, events).use { recovery ->
                recovery.start(); val done = events.terminal()
                expect(done.phase == RecoveryPhase.ATTENTION && done.sourcesSkipped == 1 &&
                    done.sourcesPreserved == 0 && script.reads.get() == 0, "Unavailable source was presented as saved")
                expect(script.selects.get() == if (fault == "busy") 1 else 0,
                    "Flagged/invalid catalog item reached SELECT")
            }
        }
    }

    private fun reconnectIdentity() {
        for (fault in listOf("changed", "revoked")) {
            val context = fresh(fault); val script = Script(fixtures, fault = fault); val events = Events()
            coordinator(context, script, events).use { recovery ->
                recovery.start(); val done = events.terminal()
                if (fault == "changed") {
                    expect(events.states.any { it.phase == RecoveryPhase.SOURCE_SKIPPED && it.reason == RecoveryReason.SOURCE_CHANGED },
                        "Transient reconnect silently changed the pinned physical receipt")
                    expect(done.sourcesSkipped == 1 && done.sourcesReady == 1, "Changed source did not stay separate from healthy catalog entry")
                } else expect(done.reason == RecoveryReason.SESSION_REJECTED && script.selects.get() == 1 && done.sourcesPreserved == 0,
                    "Revoked READ authorization continued catalog recovery")
                expect(CaptureStore(context).list().none { it.fileSha256 == sha(fixtures.first().bytes) },
                    "Changed/revoked source was published")
            }
        }
    }

    private fun reconciledFailures() {
        for (fault in listOf("repeat-busy", "resolve-busy")) {
            val script = Script(fixtures, fault = fault); val events = Events()
            coordinator(fresh(fault), script, events).use { recovery ->
                recovery.start(); val done = events.terminal()
                val resolved = fault == "resolve-busy"
                expect(done.sourcesSkipped == if (resolved) 0 else 1, "Repeated source failure inflated or failed to clear unresolved count")
                expect(done.phase == if (resolved) RecoveryPhase.COMPLETE else RecoveryPhase.ATTENTION,
                    "Resolved source left stale attention state")
                expect(done.sourcesReady == if (resolved) 2 else 1, "Healthy sources were lost during failure reconciliation")
            }
        }
    }

    private fun stalledRollover() {
        // A legal maximum-sized framed packet cannot finish inside the lowered
        // test transaction budget when a hostile peer returns only one byte.
        // Keep actual C manifest/selection, but deliberately corrupt the source
        // into a maximum-record prefix: this fault must never reach publication.
        val original = fixtures.first()
        val packet = ByteArray(1301)
        original.bytes.copyInto(packet, 0, 68, 90)
        put(packet, 20, 1275, 2)
        original.bytes.copyInto(packet, 22, 90, 93)
        put(packet, 1297, CRC32().apply { update(packet, 0, 1297) }.value, 4)
        val changed = original.bytes.copyOf()
        packet.copyInto(changed, 68)
        val script = Script(listOf(original.copy(bytes = changed)), fault = "tiny"); val events = Events()
        coordinator(fresh("tiny"), script, events, transactionLimit = 256).use { recovery ->
            recovery.start(); val done = events.terminal()
            expect(done.phase == RecoveryPhase.ATTENTION && done.sourcesPreserved == 0 && done.sourcesSkipped == 1,
                "Repeated partial-record rollover claimed saved source")
            expect(script.connections.size <= 4 && script.reads.get() <= 1024 &&
                events.states.any { it.reason == RecoveryReason.SOURCE_STALLED }, "No-progress rollover was not bounded")
        }
    }

    private inner class Script(private val entries: List<Fixture>, private val fault: String = "",
        private val blockRead: Boolean = false, private val blockHello: Boolean = false,
        private val lateReply: Boolean = false) {
        val connections = CopyOnWriteArrayList<Link>()
        val firstReadOffsets = CopyOnWriteArrayList<Long>()
        val blocked = CountDownLatch(1); val release = CountDownLatch(1)
        private val barrierUsed = AtomicBoolean(false)
        val reads = AtomicInteger(); val selects = AtomicInteger(); val finishes = AtomicInteger(); val eofReads = AtomicInteger()
        private val activeExchanges = AtomicInteger(); val maximumExchanges = AtomicInteger()
        private val transientFailure = AtomicBoolean(false)
        fun connect(): TransferConnection = Link(connections.size + 1).also { connections += it }

        inner class Link(private val number: Int) : TransferConnection {
            val closed = AtomicBoolean(false)
            var maxTransaction = 0
            private var selected: Fixture? = null
            private var handle = 0L
            private var nextOffset = 0L
            private var seeked = false
            private var eof = false
            override fun exchange(command: TransferCommand, timeoutMillis: Long): ByteArray {
                check(timeoutMillis >= 1_000 && !closed.get())
                val active = activeExchanges.incrementAndGet()
                maximumExchanges.updateAndGet { maxOf(it, active) }
                try {
                    check(command.transaction > maxTransaction) { "Coordinator repeated/decreased transaction outside link retry owner" }
                    maxTransaction = command.transaction
                    val wire = command.encode(); val opcode = wire[1].toInt()
                    val offset = if (opcode == 4) u64(wire, 8) else 0
                    if (((blockHello && opcode == 1) || (blockRead && opcode == 4 && offset >= 128)) &&
                        barrierUsed.compareAndSet(false, true)) {
                        blocked.countDown()
                        try { await(release, "Scripted exchange never cancelled or released") }
                        catch (_: InterruptedException) {
                            // Model a late callback even when close/cancellation wins.
                            if (!lateReply) throw TransferConnectionException("Scripted exchange interrupted")
                        }
                        if (closed.get() && !lateReply) throw TransferConnectionException("Scripted exchange closed")
                    }
                    if (fault == "connection") throw TransferConnectionException("Scripted transport failure")
                    return when (opcode) {
                        1 -> response(command, 46).also {
                            trusted.deviceIdBytes().copyInto(it, 4); trusted.incarnationBytes().copyInto(it, 20)
                            if (fault == "identity") it[4] = (it[4].toInt() xor 1).toByte()
                            put(it, 36, 1, 4); put(it, 40, entries.size.toLong(), 2); put(it, 42, 512, 2); put(it, 44, 256, 2)
                        }
                        2 -> if (fault == "stale") error(command, 7) else {
                            check(u64(wire, 4, 4) == 1L)
                            val fixture = entries[u64(wire, 8, 2).toInt()]
                            response(command, 80).also {
                                put(it, 4, 1, 4); put(it, 8, u64(wire, 8, 2), 2)
                                fixture.bytes.copyInto(it, 10, 0, 68)
                                it[78] = if (fault == "invalid") 4 else 0 // UNVERIFIED is eligible.
                                it[79] = if (fault == "flag") 1 else 0
                            }
                        }
                        3 -> {
                            selects.incrementAndGet()
                            val fixture = entries.single { it.captureId.contentEquals(wire.copyOfRange(4, 20)) }
                            val first = fixture === entries.first()
                            if (fault == "busy" || (first && fault == "repeat-busy") ||
                                (first && fault == "resolve-busy" && !transientFailure.get())) error(command, 1) else {
                                selected = fixture; handle++; nextOffset = 0; seeked = false; eof = false
                                fixture.select.copyOf().also {
                                    put(it, 2, command.transaction.toLong(), 2)
                                    put(it, 4, handle, 4)
                                    if (fault == "changed" && number > 1 && first) {
                                        it[76 + 58] = (it[76 + 58].toInt() xor 1).toByte()
                                        val ack = it.copyOfRange(76, 170)
                                        put(ack, 90, CRC32().apply { update(ack, 0, 90) }.value, 4); ack.copyInto(it, 76)
                                    }
                                }
                            }
                        }
                        4 -> {
                            reads.incrementAndGet()
                            val fixture = checkNotNull(selected)
                            if (fault == "revoked") return error(command, 5)
                            if ((fault == "changed" && fixture === entries.first() && offset >= 128 && number == 1) ||
                                (fault in setOf("repeat-busy", "resolve-busy") && fixture === entries.last() &&
                                    transientFailure.compareAndSet(false, true))) {
                                throw TransferConnectionException("Scripted transient connection failure")
                            }
                            check(u64(wire, 4, 4) == handle)
                            if (!seeked) {
                                check(boundary(fixture.bytes, offset)) { "First READ did not seek complete-record boundary" }
                                firstReadOffsets += offset; nextOffset = offset; seeked = true
                            }
                            check(offset == nextOffset)
                            val count = minOf(if (fault == "tiny") 1 else 128, u64(wire, 16, 2).toInt(), fixture.bytes.size - offset.toInt())
                            check(count >= 0)
                            val data = fixture.bytes.copyOfRange(offset.toInt(), offset.toInt() + count)
                            nextOffset += count; eof = count == 0
                            if (eof) eofReads.incrementAndGet()
                            response(command, 22 + count).also {
                                put(it, 4, handle, 4); put(it, 8, offset, 8); put(it, 16, count.toLong(), 2)
                                data.copyInto(it, 18); put(it, 18 + count, CRC32().apply { update(data) }.value, 4)
                            }
                        }
                        5 -> {
                            val fixture = checkNotNull(selected)
                            check(u64(wire, 4, 4) == handle && seeked && eof && nextOffset == fixture.bytes.size.toLong() &&
                                u64(wire, 8) == nextOffset) { "FINISH bypassed real C seek/EOF gate" }
                            finishes.incrementAndGet()
                            fixture.finish.copyOf().also {
                                put(it, 2, command.transaction.toLong(), 2)
                                put(it, 4, handle, 4)
                                if (fault == "finish") {
                                    it[8 + 58] = (it[8 + 58].toInt() xor 1).toByte()
                                    val ack = it.copyOfRange(8, 102)
                                    put(ack, 90, CRC32().apply { update(ack, 0, 90) }.value, 4); ack.copyInto(it, 8)
                                }
                            }
                        }
                        else -> throw IllegalStateException("Recovery sent unexpected command")
                    }
                } finally { activeExchanges.decrementAndGet() }
            }
            override fun close() { if (closed.compareAndSet(false, true)) release.countDown() }
        }
    }

    private fun selection(fixture: Fixture): TransferSelection {
        val command = TransferWire.select(3, fixture.captureId)
        return (TransferWire.decode(command, fixture.select, trusted) as TransferResponse.Selected).selection
    }
    private fun response(command: TransferCommand, size: Int) = ByteArray(size).also {
        it[1] = command.opcode.wireValue.toByte(); put(it, 2, command.transaction.toLong(), 2)
    }
    private fun error(command: TransferCommand, status: Int) = response(command, 4).also { it[0] = status.toByte() }
    private fun boundary(bytes: ByteArray, offset: Long): Boolean {
        if (offset == 0L || offset == bytes.size.toLong()) return true
        var at = 68
        while (at < bytes.size) {
            if (at.toLong() == offset) return true
            at += if (String(bytes, at, 4, Charsets.US_ASCII) == "ASE3") 120 else 26 + u64(bytes, at + 20, 2).toInt()
        }
        return false
    }
    private fun fresh(name: String): Context {
        val root = File(targetContext.cacheDir, "recovery-$name-${UUID.randomUUID()}")
        check(root.mkdir())
        return object : ContextWrapper(targetContext) {
            override fun getApplicationContext(): Context = this
            override fun getNoBackupFilesDir(): File = File(root, "private").also { check(it.isDirectory || it.mkdir()) }
            override fun getCacheDir(): File = File(root, "cache").also { check(it.isDirectory || it.mkdir()) }
        }
    }
    private fun await(latch: CountDownLatch, message: String) { check(latch.await(45, TimeUnit.SECONDS)) { message } }
    private fun hex(text: String) = ByteArray(text.length / 2) { text.substring(2 * it, 2 * it + 2).toInt(16).toByte() }
    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it.toInt() and 255) }
    private fun u64(bytes: ByteArray, at: Int, size: Int = 8): Long {
        var value = 0L
        for (i in 0 until size) value = value or ((bytes[at + i].toLong() and 255) shl (8 * i))
        return value
    }
    private fun put(bytes: ByteArray, at: Int, value: Long, size: Int) {
        for (i in 0 until size) bytes[at + i] = (value ushr (8 * i)).toByte()
    }
}
