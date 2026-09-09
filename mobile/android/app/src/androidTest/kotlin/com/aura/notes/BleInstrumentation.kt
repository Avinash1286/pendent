package com.aura.notes

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.Instrumentation
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.content.Context
import android.content.ContextWrapper
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import com.aura.capture.AuraArchive
import com.aura.capture.ReceiptStatus
import com.aura.capture.TransferCommand
import com.aura.capture.TransferSession
import com.aura.capture.VerifiedArchive
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import java.util.EnumMap
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/** Opt-in real Android GATT suite for the public AURA-test-only virtual peripheral.
 * The registered SmokeInstrumentation invokes this helper with suite=virtualBle;
 * additional arguments: address=F0:F1:F2:F3:F4:F5, timeoutMillis=180000,
 * fixtureOnly=true. No scan, arbitrary peer selection, pairing or enrollment.
 * A non-emulator is refused unless separately authorized by the operator using
 * physicalFixtureAuthorized=true for this exact synthetic fixture; that flag
 * does not itself establish authorization or qualify a physical wearable.
 */
@SuppressLint("MissingPermission") // Adopted shell identity is test-only and dropped in finally.
internal class BleInstrumentation(private val owner: Instrumentation, arguments: Bundle) {
    private val parameters = Bundle(arguments)
    private val context: Context get() = owner.context
    private val targetContext: Context get() = owner.targetContext
    private val uiAutomation get() = owner.uiAutomation
    private val finished = AtomicBoolean(false)
    private val watchdog = Executors.newSingleThreadScheduledExecutor { action ->
        Thread(action, "aura-ble-test-watchdog").apply { isDaemon = true }
    }
    private val cases = JSONArray()
    private val events = Events()
    private val connections = AtomicInteger()
    private val exchanges = AtomicInteger()
    private val transportErrors = ArrayList<String>()
    private var assertions = 0
    private var started = 0L
    private var emulator = false
    private var fixtureIndexHash: String? = null
    private var libraryEvidence = JSONArray()
    @Volatile private var recovery: CaptureRecovery? = null

    fun run() {
        started = SystemClock.elapsedRealtime()
        var adopted = false
        try {
            if (Build.VERSION.SDK_INT < 33) throw IllegalStateException("Virtual GATT runner requires Android API 33 or newer")
            emulator = Build.HARDWARE == "ranchu" || Build.HARDWARE == "goldfish"
            check(emulator || parameters.getString("physicalFixtureAuthorized") == "true") {
                "Non-emulator target requires separate explicit physical-fixture authorization"
            }
            check(parameters.getString("fixtureOnly") == "true") { "Explicit synthetic-fixture scope is required" }
            val address = parameters.getString("address") ?: error("An explicit fixture address is required")
            check(address == "F0:F1:F2:F3:F4:F5") { "Only the configured AURA-test-only fixture address is allowed" }
            val timeout = parameters.getString("timeoutMillis")?.toLongOrNull()
                ?: error("An explicit timeoutMillis argument is required")
            check(timeout in 30_000..600_000) { "Fixture timeout must be 30000 through 600000 milliseconds" }
            watchdog.schedule({
                recovery?.close()
                complete(false, "Virtual GATT instrumentation exceeded its bounded duration")
            }, timeout * 2 + 30_000, TimeUnit.MILLISECONDS)
            uiAutomation.adoptShellPermissionIdentity(Manifest.permission.BLUETOOTH_CONNECT)
            adopted = true
            val adapter = targetContext.getSystemService(BluetoothManager::class.java)?.adapter
                ?: error("Android Bluetooth adapter is unavailable")
            check(adapter.isEnabled) { "The test-owned emulator Bluetooth adapter must already be enabled" }
            // getRemoteDevice(String) loses random-address typing. API33's exact
            // LE constructor selects the fixture's configured random static peer.
            val peer = adapter.getRemoteLeDevice(address, BluetoothDevice.ADDRESS_TYPE_RANDOM)
            val isolated = isolatedContext()
            lateinit var fixture: FixtureSet
            case("immutable public C fixtures and explicit virtual-peer scope") { fixture = fixtures(isolated) }
            case("nonblocking GATT construction and permanent pre-connect close") {
                val connection = AndroidGattConnection(isolated, peer)
                connection.close(); connection.close()
                var rejected = false
                try { connection.exchange(com.aura.capture.TransferWire.hello(1), 30_000) }
                catch (_: TransferConnectionException) { rejected = true }
                expect(rejected, "Closed transport accepted an exchange")
            }
            val owner = CaptureRecovery(isolated, fixture.session, {
                connections.incrementAndGet()
                val actual = AndroidGattConnection(isolated, peer)
                object : TransferConnection {
                    override fun exchange(command: TransferCommand, timeoutMillis: Long): ByteArray {
                        exchanges.incrementAndGet()
                        return try { actual.exchange(command, timeoutMillis) } catch (failure: TransferConnectionException) {
                            synchronized(transportErrors) {
                                if (transportErrors.size < 16) transportErrors += failure.message?.take(160) ?: "Transport failed"
                            }
                            throw failure
                        }
                    }
                    override fun close() = actual.close()
                }
            }, events::record, RecoveryTimeouts(commandMillis = 30_000, sourceVerificationMillis = timeout))
            recovery = owner
            var first: RecoveryStatus? = null
            var firstKeys: Set<String> = emptySet()
            case("real Android GATT downloads finalized and OPEN C sources into decoded library") {
                expect(connections.get() == 0, "Coordinator connected before foreground start")
                owner.start()
                val done = events.terminal(afterGeneration = -1, timeoutMillis = timeout)
                first = done
                expect(done.phase == RecoveryPhase.COMPLETE && done.sourcesPreserved == 2 && done.sourcesReady == 2 &&
                    done.sourcesSkipped == 0, "Virtual GATT recovery did not complete both preserved and playable sources")
                firstKeys = checkLibrary(isolated, fixture)
                expect(events.firstIndex(RecoveryPhase.SOURCE_PRESERVED) < events.firstIndex(RecoveryPhase.PROCESSING) &&
                    events.firstIndex(RecoveryPhase.PROCESSING) < events.firstIndex(RecoveryPhase.READY),
                    "Preserved source and decoded playback publication were conflated")
            }
            case("new GATT pass revalidates completed sources without duplicate library entries") {
                val firstConnectionCount = connections.get()
                owner.retry()
                val done = events.terminal(checkNotNull(first).generation, timeout)
                expect(done.phase == RecoveryPhase.COMPLETE && done.sourcesPreserved == 2 && done.sourcesReady == 2,
                    "Second virtual GATT recovery did not complete")
                expect(checkLibrary(isolated, fixture) == firstKeys, "Revalidation forked or duplicated library entries")
                expect(connections.get() > firstConnectionCount, "Second pass reused an old GATT lineage")
                expect(CaptureStore(isolated).list().size == 2, "Exact duplicate recovery created extra library records")
            }
            owner.close()
            expect(owner.snapshot().phase == RecoveryPhase.CLOSED, "Recovery owner did not close")
            awaitGattShutdown()
            complete(true)
        } catch (failure: Exception) {
            complete(false, failure.message?.take(240) ?: failure.javaClass.simpleName)
        } finally {
            recovery?.close()
            try { awaitGattShutdown() } catch (_: Exception) { /* Still drop the test permission identity below. */ }
            watchdog.shutdownNow()
            if (adopted) uiAutomation.dropShellPermissionIdentity()
        }
    }

    private data class Fixture(val name: String, val bytes: ByteArray, val ack: ByteArray, val verified: VerifiedArchive)
    private data class FixtureSet(val session: TransferSession, val sources: List<Fixture>)

    private fun fixtures(context: Context): FixtureSet {
        val bytes = this.context.assets.open("downloads/index.json").use { it.readBytes() }
        fixtureIndexHash = sha(bytes)
        val index = JSONObject(String(bytes, Charsets.UTF_8))
        expect(!index.getBoolean("physical_hardware_recordings"), "Fixture must not claim physical recordings")
        val identities = index.getJSONObject("contexts")
        val session = TransferSession(unhex(identities.getString("device_id")), unhex(identities.getString("incarnation")))
        val rows = index.getJSONArray("fixtures")
        val sources = (0 until rows.length()).map { position ->
            val row = rows.getJSONObject(position)
            fun asset(field: String): ByteArray {
                val entry = row.getJSONObject(field)
                val data = this.context.assets.open("downloads/${entry.getString("asset")}").use { it.readBytes() }
                expect(data.size == entry.getInt("bytes") && sha(data) == entry.getString("sha256"), "Bundled owned C fixture changed")
                return data
            }
            val source = asset("archive"); val proof = asset("physical")
            val destination = File(context.cacheDir, "fixture-${row.getString("name")}.aura")
            check(destination.createNewFile())
            FileOutputStream(destination).use { it.write(source); it.fd.sync() }
            Fixture(row.getString("name"), source, proof, AuraArchive.verify(destination, proof))
        }
        expect(sources.map { it.name }.toSet() == setOf("finalized", "open"), "Required fixture pair missing")
        return FixtureSet(session, sources)
    }

    private fun checkLibrary(context: Context, fixture: FixtureSet): Set<String> {
        val store = CaptureStore(context)
        val items = store.list()
        expect(items.size == 2, "Library must contain exactly two synthetic sources")
        val evidence = JSONArray()
        for (source in fixture.sources) {
            val item = items.single { it.fileSha256 == source.verified.sha256 }
            val verified = store.readVerified(item.key)
            expect(item.playbackReady && item.playbackFile.isFile && item.decoderName != null,
                "Source was published without complete platform decoding")
            expect(store.fileForExport(item.key).readBytes().contentEquals(source.bytes) &&
                File(item.bundle, "physical.ack").readBytes().contentEquals(source.ack), "Original source or physical receipt changed")
            expect(verified.capture.encode().contentEquals(source.verified.capture.encode()) &&
                verified.receipt.encode().contentEquals(source.verified.receipt.encode()) &&
                verified.physicalReceipt?.encode()?.contentEquals(source.ack) == true &&
                item.receiptDigest == source.verified.receipt.chainSha256 && item.sourceSamples == source.verified.sourceSamples,
                "Library metadata differs from the complete C source and exact receipt")
            if (source.name == "open") expect(item.physicalStatus == ReceiptStatus.OPEN && item.status == ReceiptStatus.INTERRUPTED &&
                verified.derivedExportSeal && verified.originalSourceSamples == null,
                "Physical OPEN became a device terminal receipt or invented original duration")
            else expect(item.physicalStatus == ReceiptStatus.FINALIZED && item.status == ReceiptStatus.FINALIZED,
                "Finalized physical provenance changed")
            evidence.put(JSONObject().put("fixture", source.name).put("sha256", item.fileSha256)
                .put("receipt_digest", item.receiptDigest).put("physical_status", item.physicalStatus?.name)
                .put("export_status", item.status.name).put("source_samples", item.sourceSamples)
                .put("decoder", item.decoderName).put("sample_rate", item.decodeRate).put("playback_ready", item.playbackReady))
        }
        libraryEvidence = evidence
        return items.map { it.key }.toSet()
    }

    /** Bounded observer evidence; no per-fragment application event queue. */
    private class Events {
        private val gate = Object()
        private var latest: RecoveryStatus? = null
        private val counts = EnumMap<RecoveryPhase, Int>(RecoveryPhase::class.java)
        private val transitions = ArrayList<RecoveryPhase>()
        fun record(value: RecoveryStatus) = synchronized(gate) {
            if (latest?.phase != value.phase && transitions.size < 256) transitions += value.phase
            counts[value.phase] = minOf(1_000_000, (counts[value.phase] ?: 0) + 1)
            latest = value
            gate.notifyAll()
        }
        fun terminal(afterGeneration: Long, timeoutMillis: Long): RecoveryStatus = synchronized(gate) {
            val deadline = SystemClock.elapsedRealtime() + timeoutMillis
            while (true) {
                val value = latest
                if (value != null && value.generation > afterGeneration &&
                    value.phase in setOf(RecoveryPhase.COMPLETE, RecoveryPhase.ATTENTION)) return@synchronized value
                val left = deadline - SystemClock.elapsedRealtime()
                check(left > 0) { "Virtual GATT recovery timeout; last phase=${latest?.phase}, reason=${latest?.reason}" }
                gate.wait(left)
            }
            @Suppress("UNREACHABLE_CODE") error("Unreachable")
        }
        fun firstIndex(phase: RecoveryPhase): Int = synchronized(gate) { transitions.indexOf(phase).also { check(it >= 0) } }
        fun evidence(): JSONObject = synchronized(gate) {
            JSONObject().put("phase_counts", JSONObject().also { json -> counts.forEach { (phase, count) -> json.put(phase.name, count) } })
                .put("transitions", JSONArray(transitions.map { it.name })).put("last_phase", latest?.phase?.name)
                .put("last_reason", latest?.reason?.name)
        }
    }

    private fun isolatedContext(): Context {
        val root = File(targetContext.cacheDir, "aura-virtual-gatt-${UUID.randomUUID()}")
        check(root.mkdir())
        return object : ContextWrapper(targetContext) {
            override fun getApplicationContext(): Context = this
            override fun getNoBackupFilesDir(): File = File(root, "private").apply { check(isDirectory || mkdir()) }
            override fun getCacheDir(): File = File(root, "cache").apply { check(isDirectory || mkdir()) }
        }
    }

    private fun case(name: String, action: () -> Unit) {
        val time = SystemClock.elapsedRealtime()
        try {
            action()
            cases.put(JSONObject().put("name", name).put("passed", true).put("elapsed_ms", SystemClock.elapsedRealtime() - time))
            owner.sendStatus(0, Bundle().apply { putString("stream", "PASS $name\n") })
        } catch (error: Exception) {
            cases.put(JSONObject().put("name", name).put("passed", false).put("elapsed_ms", SystemClock.elapsedRealtime() - time))
            throw error
        }
    }
    private fun expect(value: Boolean, message: String) { assertions++; check(value) { message } }
    private fun awaitGattShutdown() {
        val deadline = SystemClock.elapsedRealtime() + 5_000
        while (Thread.getAllStackTraces().keys.any { it.isAlive && it.name in setOf("aura-gatt-owner", "aura-gatt-cleanup") }) {
            check(SystemClock.elapsedRealtime() < deadline) { "GATT callback owner did not finish bounded cleanup" }
            Thread.sleep(20)
        }
    }
    private fun complete(passed: Boolean, error: String? = null) {
        if (!finished.compareAndSet(false, true)) return
        val result = JSONObject().put("schema", "aura-android-virtual-gatt-v1").put("passed", passed)
            .put("cases", cases).put("assertions", assertions).put("elapsed_ms", SystemClock.elapsedRealtime() - started)
            .put("android_sdk", Build.VERSION.SDK_INT).put("android_fingerprint", Build.FINGERPRINT).put("emulator", emulator)
            .put("fixture_index_sha256", fixtureIndexHash).put("peer_address", parameters.getString("address"))
            .put("peer_address_type", "random-static").put("timeout_ms", parameters.getString("timeoutMillis"))
            .put("logical_exchange_calls", exchanges.get()).put("connections_created", connections.get())
            .put("transport_errors", synchronized(transportErrors) { JSONArray(transportErrors.toList()) })
            .put("recovery", events.evidence()).put("library", libraryEvidence)
            .put("transport", "actual AndroidGattConnection and Android GATT callbacks")
            .put("server", "test-only Bumble virtual peripheral replaying public owned C archives")
            .put("authentication_tested", false).put("physical_recording_tested", false)
            .put("physical_wearable_qualified", false).put("complete_gatt_download_verified", passed)
            .put("physical_radio_tested", passed && !emulator)
        if (error != null) result.put("failure", error)
        owner.finish(if (passed) Activity.RESULT_OK else Activity.RESULT_CANCELED, Bundle().apply {
            putString("resultdetailJSON", result.toString())
            putString("stream", "AURA_VIRTUAL_GATT_${if (passed) "PASS" else "FAIL"} $result\n")
        })
    }
    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it.toInt() and 255) }
    private fun unhex(text: String) = text.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
}
