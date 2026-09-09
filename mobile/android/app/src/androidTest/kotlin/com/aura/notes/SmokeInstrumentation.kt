package com.aura.notes

import android.app.Activity
import android.app.Instrumentation
import android.content.Context
import android.content.ContextWrapper
import android.database.DatabaseErrorHandler
import android.database.sqlite.SQLiteDatabase
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import com.aura.capture.AuraArchive
import com.aura.capture.AuraOgg
import com.aura.capture.ReceiptStatus
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Real Android instrumentation; no fake codec, database, shadow or test framework.
 * Test source files are the public synthetic C fixtures, never user recordings.
 */
class SmokeInstrumentation : Instrumentation() {
    private val finished = AtomicBoolean(false)
    private val watchdog = Executors.newSingleThreadScheduledExecutor { action ->
        Thread(action, "aura-smoke-watchdog").apply { isDaemon = true }
    }
    private val cases = JSONArray()
    private val decodeResults = JSONArray()
    private var assertions = 0
    private var started = 0L
    private var suiteArguments = Bundle()
    private lateinit var isolated: IsolatedContext
    private lateinit var fixtures: Map<String, Fixture>
    private lateinit var indexHash: String
    private var downloadEvidence: JSONObject? = null
    private var recoveryEvidence: JSONObject? = null

    override fun onCreate(arguments: Bundle?) {
        super.onCreate(arguments)
        suiteArguments = arguments?.let(::Bundle) ?: Bundle()
        start()
    }

    override fun onStart() {
        if (suiteArguments.getString("suite") == "virtualBle") {
            watchdog.shutdownNow()
            BleInstrumentation(this, suiteArguments).run()
            return
        }
        started = SystemClock.elapsedRealtime()
        watchdog.schedule({
            complete(false, JSONObject().put("failure", "Instrumentation exceeded its 240-second bound"))
        }, 240, TimeUnit.SECONDS)
        try {
            val root = File(targetContext.cacheDir, "aura-instrumentation-${UUID.randomUUID()}")
            check(root.mkdir()) { "Could not create isolated instrumentation directory" }
            isolated = IsolatedContext(targetContext, root)
            case("immutable C fixture assets") { fixtures = copyFixtures() }
            case("real platform Opus decode, EOS and exact WAV durations") { decoderChecks() }
            case("decoder destination preservation and incomplete input refusal") { decoderFailureChecks() }
            storeChecks()
            downloadEvidence = runDownloadStoreChecks(context, isolated, ::case, ::expect)
            recoveryEvidence = runCaptureRecoveryChecks(context, isolated, ::case, ::expect)
            complete(true)
        } catch (error: Throwable) {
            complete(false, JSONObject().put("failure_type", error.javaClass.simpleName)
                .put("failure", error.message?.take(400) ?: "No detail"))
        } finally {
            watchdog.shutdownNow()
        }
    }

    private fun complete(passed: Boolean, extra: JSONObject = JSONObject()) {
        if (!finished.compareAndSet(false, true)) return
        extra.put("schema", "aura-android-smoke-v1")
            .put("passed", passed).put("cases", cases).put("assertions", assertions)
            .put("elapsed_ms", SystemClock.elapsedRealtime() - started)
            .put("android_sdk", Build.VERSION.SDK_INT).put("android_fingerprint", Build.FINGERPRINT)
            .put("decoder_results", decodeResults).put("physical_hardware_verified", false)
        if (::indexHash.isInitialized) extra.put("fixture_index_sha256", indexHash)
        downloadEvidence?.let { extra.put("download_store", it) }
        recoveryEvidence?.let { extra.put("capture_recovery", it) }
        val result = Bundle().apply {
            putString("resultdetailJSON", extra.toString())
            putString("stream", "AURA_SMOKE_${if (passed) "PASS" else "FAIL"} ${extra}\n")
        }
        finish(if (passed) Activity.RESULT_OK else Activity.RESULT_CANCELED, result)
    }

    private fun case(name: String, operation: () -> Unit) {
        check(!finished.get()) { "Instrumentation already timed out" }
        val beginning = SystemClock.elapsedRealtime()
        try {
            operation()
            cases.put(JSONObject().put("name", name).put("passed", true)
                .put("elapsed_ms", SystemClock.elapsedRealtime() - beginning))
            sendStatus(0, Bundle().apply { putString("stream", "PASS $name\n") })
        } catch (error: Throwable) {
            cases.put(JSONObject().put("name", name).put("passed", false)
                .put("elapsed_ms", SystemClock.elapsedRealtime() - beginning))
            throw error
        }
    }

    private fun expect(value: Boolean, message: String) {
        assertions++
        check(value) { message }
    }

    private fun rejects(operation: () -> Unit) {
        assertions++
        try { operation() } catch (_: Exception) { return }
        error("An operation that must be rejected succeeded")
    }

    private fun copyFixtures(): Map<String, Fixture> {
        val indexBytes = context.assets.open("fixtures/index.json").use { it.readBytes() }
        indexHash = sha(indexBytes)
        val index = JSONObject(String(indexBytes, Charsets.UTF_8))
        expect(!index.getBoolean("physical_hardware_recordings"), "Fixture must not claim physical capture")
        val result = LinkedHashMap<String, Fixture>()
        val entries = index.getJSONArray("fixtures")
        for (i in 0 until entries.length()) {
            val entry = entries.getJSONObject(i)
            val name = entry.getString("name")
            val bytes = context.assets.open("fixtures/${entry.getString("asset")}").use { it.readBytes() }
            expect(bytes.size == entry.getInt("bytes") && sha(bytes) == entry.getString("sha256"),
                "Bundled C archive identity differs")
            val file = File(isolated.cacheDir, "$name.aura")
            writeNew(file, bytes)
            var proof: File? = null
            if (entry.has("physical_asset")) {
                val ack = context.assets.open("fixtures/${entry.getString("physical_asset")}").use { it.readBytes() }
                expect(ack.size == 94 && sha(ack) == entry.getString("physical_sha256"),
                    "Bundled C receipt identity differs")
                proof = File(isolated.cacheDir, "$name.physical.ack3")
                writeNew(proof, ack)
            }
            result[name] = Fixture(name, file, proof, entry)
        }
        expect(result.size == 4, "Expected four source fixtures")
        return result
    }

    private fun decoderChecks() {
        for (name in listOf("journal-0", "journal-2", "recorder-1")) {
            val fixture = fixtures.getValue(name)
            val before = sha(fixture.file)
            val archive = AuraArchive.verify(fixture.file, fixture.proof!!.readBytes())
            expect(archive.receipt.hex() == fixture.metadata.getString("archive_receipt"),
                "Android core receipt differs from C/Python fixture")
            val ogg = File(isolated.cacheDir, "$name-platform.ogg")
            FileOutputStream(ogg).use { output -> AuraOgg.write(archive, output); output.fd.sync() }
            val wav = File(isolated.cacheDir, "$name-platform.wav")
            val result = AudioDecoder.decode(ogg, wav, archive)
            expect(result.sampleRate == 16000 || result.sampleRate == 48000, "Unexpected platform sample rate")
            val expectedFrames = fixture.metadata.getLong("source_samples") * (result.sampleRate / 16000)
            expect(result.frames == expectedFrames, "Platform WAV duration differs from exact source")
            val untrimmed = (archive.seal.encodedSamples - archive.seal.preSkip) * (result.sampleRate / 16000)
            expect(result.rawFrames == result.frames || result.rawFrames == untrimmed,
                "Platform decoder returned an unrecognized trim endpoint")
            expect(result.decoderName.isNotBlank(), "Actual MediaCodec identity was not reported")
            verifyWav(wav, result.sampleRate, expectedFrames)
            expect(sha(fixture.file) == before, "Decoder altered the source archive")
            if (name == "journal-2") {
                expect(archive.physicalReceipt!!.status == ReceiptStatus.OPEN && archive.derivedExportSeal,
                    "Physical OPEN provenance was promoted to a terminal device receipt")
                expect(archive.originalSourceSamples == null && archive.status == ReceiptStatus.INTERRUPTED,
                    "Recovered prefix invented an exact original duration")
            }
            decodeResults.put(JSONObject().put("fixture", name).put("decoder", result.decoderName)
                .put("sample_rate", result.sampleRate).put("frames", result.frames).put("raw_frames", result.rawFrames)
                .put("end_trim_applied", result.endTrimApplied).put("wav_sha256", sha(wav))
                .put("source_sha256", before).put("physical_status", archive.physicalReceipt!!.status.name))
        }
    }

    private fun decoderFailureChecks() {
        val fixture = fixtures.getValue("journal-0")
        val archive = AuraArchive.verify(fixture.file, fixture.proof!!.readBytes())
        val ogg = File(isolated.cacheDir, "journal-0-platform.ogg")
        val protectedOutput = File(isolated.cacheDir, "protected-existing.wav")
        val sentinel = "retain this previous output".toByteArray()
        writeNew(protectedOutput, sentinel)
        rejects { AudioDecoder.decode(ogg, protectedOutput, archive) }
        expect(protectedOutput.readBytes().contentEquals(sentinel), "Decoder overwrote an existing output")
        val sourceHash = sha(fixture.file)
        rejects { AudioDecoder.decode(ogg, fixture.file, archive) }
        expect(sha(fixture.file) == sourceHash, "Decoder overwrote its source archive")
        val truncated = File(isolated.cacheDir, "truncated.ogg")
        val data = ogg.readBytes()
        writeNew(truncated, data.copyOf(data.size / 2))
        val failed = File(isolated.cacheDir, "incomplete-output.wav")
        rejects { AudioDecoder.decode(truncated, failed, archive) }
        expect(!failed.exists(), "Decoder published an incomplete output")
    }

    private fun verifyWav(file: File, sampleRate: Int, frames: Long) {
        expect(file.length() == 44 + frames * 2, "WAV length differs from retained PCM frames")
        file.inputStream().buffered().use { stream ->
            val header = ByteArray(44)
            expect(stream.read(header) == 44, "Incomplete WAV header")
            val bytes = ByteBuffer.wrap(header).order(ByteOrder.LITTLE_ENDIAN)
            expect(String(header, 0, 4, Charsets.US_ASCII) == "RIFF" &&
                String(header, 8, 8, Charsets.US_ASCII) == "WAVEfmt " &&
                String(header, 36, 4, Charsets.US_ASCII) == "data", "Invalid WAV chunk identifiers")
            expect((bytes.getInt(4).toLong() and 0xffff_ffffL) == file.length() - 8 &&
                bytes.getInt(16) == 16 && bytes.getShort(20).toInt() == 1 && bytes.getShort(22).toInt() == 1,
                "Invalid WAV PCM header")
            expect(bytes.getInt(24) == sampleRate && bytes.getInt(28) == sampleRate * 2 &&
                bytes.getShort(32).toInt() == 2 && bytes.getShort(34).toInt() == 16 &&
                (bytes.getInt(40).toLong() and 0xffff_ffffL) == frames * 2, "WAV format/duration fields differ")
            val buffer = ByteArray(32768)
            var seenFrames = 0L
            var peak = 0
            while (true) {
                val count = stream.read(buffer)
                if (count < 0) break
                expect(count % 2 == 0, "WAV PCM is not sample aligned")
                for (i in 0 until count step 2) {
                    val value = ((buffer[i].toInt() and 255) or (buffer[i + 1].toInt() shl 8)).toShort().toInt()
                    peak = maxOf(peak, kotlin.math.abs(value))
                }
                seenFrames += count / 2
            }
            expect(seenFrames == frames && peak > 100, "C fixture did not decode to nonempty audible PCM")
        }
    }

    private fun storeChecks() {
        val store = CaptureStore(isolated)
        lateinit var saved: LocalCapture
        case("real content provider and SQLite source import") {
            expect(store.list().isEmpty(), "Isolated library should start empty")
            rejects { store.importSources(listOf(Uri.fromFile(fixtures.getValue("journal-0").file))) }
            saved = store.importSources(listOf(uri("journal-0.aura"), uri("journal-0.physical.ack3")))
            expect(saved.status == ReceiptStatus.FINALIZED && saved.physicalStatus == ReceiptStatus.FINALIZED,
                "Imported final source lost physical provenance")
            expect(saved.playbackReady && !saved.decoderName.isNullOrBlank() && saved.decodeRate != null,
                "Capture was published without a real platform decode")
            expect(saved.fileSha256 == fixtures.getValue("journal-0").metadata.getString("sha256") &&
                sha(store.fileForExport(saved.key)) == saved.fileSha256, "Store altered exact source bytes")
            verifyWav(saved.playbackFile, saved.decodeRate!!, saved.sourceSamples * (saved.decodeRate!! / 16000))
        }
        case("idempotent import and fresh store instance reopen") {
            val priorHash = sha(store.fileForExport(saved.key))
            val priorPlayback = sha(saved.playbackFile)
            val retry = store.importSources(listOf(uri("journal-0.physical.ack3"), uri("journal-0.aura")))
            expect(retry.key == saved.key && retry.importedAtMs == saved.importedAtMs,
                "Idempotent import created a new source revision")
            val reopened = CaptureStore(isolated)
            expect(reopened.list().size == 1 && reopened.find(saved.key)?.fileSha256 == priorHash,
                "Fresh store instance failed to reopen actual inventory")
            expect(sha(reopened.fileForExport(saved.key)) == priorHash && sha(retry.playbackFile) == priorPlayback,
                "Reopen or retry changed saved source/playback")
        }
        case("manual context survives reopen without changing source evidence") {
            val source = store.fileForExport(saved.key)
            val sourceHash = sha(source)
            val metadata = File(saved.bundle, "bundle.json")
            val metadataHash = sha(metadata)
            store.update(saved.key, "A moment worth remembering", "Manual context for the fixture.\nNo transcript is invented.")
            val edited = CaptureStore(isolated).find(saved.key)!!
            expect(edited.title == "A moment worth remembering" && edited.contextText.contains("No transcript is invented."),
                "Manual context did not survive SQLite reopen")
            expect(sha(source) == sourceHash && sha(metadata) == metadataHash &&
                edited.receiptDigest == saved.receiptDigest, "Editing notes altered immutable source metadata")
            rejects { store.update(saved.key, "", "") }
            expect(CaptureStore(isolated).find(saved.key)!!.title == edited.title,
                "Rejected edit changed existing notes")
        }
        lateinit var recovered: LocalCapture
        case("late physical OPEN proof remains distinct from the derived export seal") {
            val unknown = store.importSources(listOf(uri("journal-2.aura")))
            expect(unknown.status == ReceiptStatus.INTERRUPTED && unknown.physicalStatus == null,
                "Unproven interrupted archive gained physical provenance")
            val sourceHash = sha(store.fileForExport(unknown.key))
            val metadataHash = sha(File(unknown.bundle, "bundle.json"))
            recovered = store.importSources(listOf(uri("journal-2.aura"), uri("journal-2.physical.ack3")))
            val verified = store.readVerified(recovered.key)
            expect(recovered.key == unknown.key && recovered.physicalStatus == ReceiptStatus.OPEN &&
                verified.derivedExportSeal && verified.originalSourceSamples == null,
                "Late proof promoted OPEN to a finalized physical recording")
            expect(sha(store.fileForExport(recovered.key)) == sourceHash &&
                sha(File(recovered.bundle, "bundle.json")) == metadataHash,
                "Late proof rewrote source or completed decode metadata")
            expect(store.list().size == 2, "Late proof duplicated the capture")
        }
        case("corrupt source and conflicting proof are retained without publication") {
            val count = store.list().size
            val stable = sha(store.fileForExport(saved.key))
            val pending = File(isolated.noBackupFilesDir, "captures/.pending")
            val before = pending.listFiles()?.map { it.name }?.toSet() ?: emptySet()
            rejects { store.importSources(listOf(uri("corrupt-journal-0.aura"))) }
            rejects { store.importSources(listOf(uri("capture-20ms-open.aura"))) }
            rejects { store.importSources(listOf(uri("journal-2.aura"), uri("journal-0.physical.ack3"))) }
            expect(store.list().size == count && sha(store.fileForExport(saved.key)) == stable,
                "Failed import changed the visible library or original")
            val newDirectories = pending.listFiles()!!.filter { it.name !in before }
            expect(newDirectories.size == 3,
                "Failed source copies were discarded instead of retained")
            val retainedHashes = newDirectories.flatMap { it.walkTopDown().filter { file -> file.isFile }.toList() }
                .map { sha(it) }.toSet()
            val corrupted = fixtures.getValue("journal-0").file.readBytes()
            corrupted[90] = (corrupted[90].toInt() xor 1).toByte()
            expect(sha(corrupted) in retainedHashes && sha(fixtures.getValue("capture-20ms-open").file) in retainedHashes &&
                sha(fixtures.getValue("journal-2").file) in retainedHashes &&
                sha(fixtures.getValue("journal-0").proof!!) in retainedHashes,
                "A failed import's exact source or conflicting receipt bytes are missing")
            expect(CaptureStore(isolated).find(recovered.key)?.physicalStatus == ReceiptStatus.OPEN,
                "Conflicting proof changed previously saved provenance")
        }
        case("cold inventory rebuild from a complete real decoded bundle") {
            val recoveryRoot = File(isolated.root, "cold-rebuild").apply { mkdir() }
            val recoveryContext = IsolatedContext(targetContext, recoveryRoot)
            val destination = File(recoveryContext.noBackupFilesDir, "captures/complete/${saved.key}").apply { mkdirs() }
            for (file in saved.bundle.listFiles()!!.filter { it.isFile }) {
                writeNew(File(destination, file.name), file.readBytes())
            }
            // No inventory row exists: this is the on-disk state after complete
            // bundle publication but before its first inventory transaction.
            val rebuilt = CaptureStore(recoveryContext)
            val found = rebuilt.list().single()
            expect(found.key == saved.key && found.playbackReady && found.physicalStatus == ReceiptStatus.FINALIZED,
                "Complete published source was not recovered into actual SQLite")
            expect(sha(rebuilt.fileForExport(found.key)) == saved.fileSha256,
                "Rebuilt inventory changed the preserved original")
            val proof = File(destination, "physical.ack")
            val retainedProof = File(destination, "physical.ack.retained-test")
            expect(proof.renameTo(retainedProof), "Could not inject missing-proof state")
            val missingProof = CaptureStore(recoveryContext)
            expect(missingProof.list().isEmpty() && missingProof.recoveryWarnings.isNotEmpty(),
                "Cold recovery silently downgraded known physical provenance")
            expect(retainedProof.exists() && sha(File(destination, "source.aura")) == saved.fileSha256,
                "Cold recovery deleted source or retained proof")
            expect(retainedProof.renameTo(proof), "Could not restore exact test proof")
            expect(CaptureStore(recoveryContext).list().single().physicalStatus == ReceiptStatus.FINALIZED,
                "Restored identical provenance did not recover")
            val source = File(destination, "source.aura")
            val changed = source.readBytes(); changed[90] = (changed[90].toInt() xor 1).toByte()
            FileOutputStream(source).use { it.write(changed); it.fd.sync() }
            val corruptHash = sha(source)
            val corrupt = CaptureStore(recoveryContext)
            expect(corrupt.list().isEmpty() && corrupt.recoveryWarnings.isNotEmpty(),
                "Changed source was promoted during cold rebuild")
            expect(sha(source) == corruptHash, "Cold rebuild overwrote or removed changed source evidence")
        }
    }

    private fun uri(name: String): Uri = Uri.parse("content://com.aura.notes.tests.fixtures/$name")

    private data class Fixture(val name: String, val file: File, val proof: File?, val metadata: JSONObject)

    /** Namespace isolation only; content resolution, filesystem and SQLite are real. */
    private class IsolatedContext(base: Context, val root: File) : ContextWrapper(base) {
        private fun directory(name: String): File = File(root, name).apply { mkdirs() }
        override fun getApplicationContext(): Context = this
        override fun getFilesDir(): File = directory("files")
        override fun getCacheDir(): File = directory("cache")
        override fun getNoBackupFilesDir(): File = directory("no-backup")
        override fun getDataDir(): File = root
        override fun getDatabasePath(name: String): File {
            require(name.matches(Regex("[a-zA-Z0-9._-]+")))
            return File(directory("databases"), name)
        }
        override fun openOrCreateDatabase(name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?): SQLiteDatabase =
            SQLiteDatabase.openOrCreateDatabase(getDatabasePath(name), factory)
        override fun openOrCreateDatabase(name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?,
                                         errorHandler: DatabaseErrorHandler?): SQLiteDatabase =
            SQLiteDatabase.openOrCreateDatabase(getDatabasePath(name).path, factory, errorHandler)
    }

    private fun writeNew(file: File, bytes: ByteArray) {
        check(file.createNewFile()) { "Test file unexpectedly exists" }
        FileOutputStream(file).use { it.write(bytes); it.fd.sync() }
    }
    private fun sha(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { stream ->
            val buffer = ByteArray(65536)
            while (true) { val count = stream.read(buffer); if (count < 0) break; digest.update(buffer, 0, count) }
        }
        return hex(digest.digest())
    }
    private fun sha(bytes: ByteArray): String = hex(MessageDigest.getInstance("SHA-256").digest(bytes))
    private fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it.toInt() and 255) }
}
