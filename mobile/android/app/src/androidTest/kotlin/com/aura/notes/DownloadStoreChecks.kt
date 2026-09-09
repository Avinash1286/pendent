package com.aura.notes

import android.content.ContentValues
import android.content.Context
import android.content.ContextWrapper
import android.database.DatabaseErrorHandler
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteException
import com.aura.capture.AuraArchive
import com.aura.capture.ReceiptStatus
import com.aura.capture.TransferResponse
import com.aura.capture.TransferSelection
import com.aura.capture.TransferSession
import com.aura.capture.TransferWire
import com.aura.capture.VerifiedArchive
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.FileNotFoundException
import java.io.RandomAccessFile
import java.security.MessageDigest
import java.util.UUID
import java.util.zip.CRC32

/** Actual Android SQLite/filesystem checks using public owned C archives. The
 * response builder exercises the real Kotlin logical codec; it is not BLE, a
 * simulated power cut, physical recording, enrollment or a deletion receipt.
 */
internal fun runDownloadStoreChecks(
    testContext: Context,
    targetContext: Context,
    runCase: (String, () -> Unit) -> Unit,
    expect: (Boolean, String) -> Unit,
): JSONObject = DownloadChecks(testContext, targetContext, runCase, expect).run()

private class DownloadChecks(
    private val testContext: Context,
    private val targetContext: Context,
    private val runCase: (String, () -> Unit) -> Unit,
    private val expect: (Boolean, String) -> Unit,
) {
    private lateinit var index: JSONObject
    private lateinit var indexHash: String
    private lateinit var trusted: TransferSession
    private lateinit var fixtures: List<Fixture>
    private val bridgeEvidence = JSONArray()
    private var nextTransaction = 100

    fun run(): JSONObject {
        runCase("download owned C source and logical SELECT/FINISH identity") { loadFixtures() }
        runCase("download complete-record durability, reconnect and exact source export") { resumeChecks() }
        runCase("download exact READ retry and poisoned conflicting input") { retryChecks() }
        runCase("download real SQLite record/metadata/FINISH transaction rollback") { rollbackChecks() }
        runCase("download retained corrupt metadata and source rows refuse recovery") { corruptionChecks() }
        runCase("download split or concatenated saved records refuse recovery") { rowFramingChecks() }
        runCase("download lifetime owner lock, closed sessions and failed-open cleanup") { lockChecks() }
        runCase("download immutable revisions retain conflicting selected receipts") { revisionChecks() }
        runCase("download incomplete and conflicting FINISH cannot publish") { finishChecks() }
        runCase("download finalized and OPEN source bridge into real decoded library") { bridgeChecks() }
        return JSONObject().put("fixture_index_sha256", indexHash)
            .put("golden_origin", index.getString("golden_origin"))
            .put("golden_sha256", index.getString("golden_sha256"))
            .put("fixtures", index.getJSONArray("fixtures"))
            .put("bridge_results", bridgeEvidence).put("sqlite_implementation", "Android SQLiteDatabase")
            .put("fault_injection", "SQLite ABORT triggers and explicit retained-row corruption")
            .put("cross_process_tested", false).put("process_kill_or_power_cut_tested", false)
            .put("gatt_tested", false).put("physical_hardware_recordings", false)
    }

    private data class Fixture(val name: String, val bytes: ByteArray, val ack: ByteArray,
        val metadata: JSONObject, val selection: TransferSelection, val verified: VerifiedArchive)

    private fun loadFixtures() {
        val indexBytes = testContext.assets.open("downloads/index.json").use { it.readBytes() }
        indexHash = sha(indexBytes)
        index = JSONObject(String(indexBytes, Charsets.UTF_8))
        expect(!index.getBoolean("physical_hardware_recordings"), "Download fixtures falsely claim hardware")
        val identities = index.getJSONObject("contexts")
        trusted = TransferSession(unhex(identities.getString("device_id")), unhex(identities.getString("incarnation")))
        val destination = fresh("fixtures")
        val entries = index.getJSONArray("fixtures")
        fixtures = (0 until entries.length()).map { position ->
            val entry = entries.getJSONObject(position)
            fun asset(field: String): ByteArray {
                val item = entry.getJSONObject(field)
                val bytes = testContext.assets.open("downloads/${item.getString("asset")}").use { it.readBytes() }
                expect(bytes.size == item.getInt("bytes") && sha(bytes) == item.getString("sha256"),
                    "Owned C download asset changed: $field")
                return bytes
            }
            val source = asset("archive"); val proof = asset("physical")
            val file = File(destination.cacheDir, "${entry.getString("name")}.aura")
            writeNew(file, source)
            val verified = AuraArchive.verify(file, proof)
            val selected = selection(entry)
            expect(selected.manifest.encode().contentEquals(source.copyOfRange(0, 68)) &&
                selected.exportBytes == source.size.toLong() && selected.physicalReceipt.encode().contentEquals(proof),
                "C SELECT does not bind exact bundled source and physical receipt")
            val fixture = Fixture(entry.getString("name"), source, proof, entry, selected, verified)
            val finished = finish(fixture, selected)
            expect(finished.selection.physicalReceipt.encode().contentEquals(proof), "C FINISH receipt changed")
            fixture
        }
        expect(fixtures.map { it.name }.toSet() == setOf("finalized", "open"), "Required C fixture pair missing")
        expect(fixtures.single { it.name == "open" }.verified.derivedExportSeal, "OPEN fixture lost derived-seal distinction")
    }

    private fun selection(metadata: JSONObject, handle: Long? = null, changedReceipt: Boolean = false): TransferSelection {
        val command = unhex(metadata.getString("select_command"))
        val response = unhex(metadata.getString("select_response"))
        if (handle != null) put(response, 4, handle, 4)
        if (changedReceipt) {
            response[76 + 60] = (response[76 + 60].toInt() xor 1).toByte()
            val ack = response.copyOfRange(76, 170)
            repairCrc(ack); ack.copyInto(response, 76)
        }
        val request = TransferWire.select(u16(command, 2), command.copyOfRange(4, 20))
        expect(request.encode().contentEquals(command), "C SELECT command canonical encoding changed")
        return (TransferWire.decode(request, response, trusted) as TransferResponse.Selected).selection
    }

    private fun finish(fixture: Fixture, selected: TransferSelection): TransferResponse.Finished {
        val response = unhex(fixture.metadata.getString("finish_response"))
        val command = unhex(fixture.metadata.getString("finish_command"))
        put(response, 4, selected.handle, 4)
        val request = TransferWire.finish(u16(command, 2), selected.handle, selected.exportBytes)
        return TransferWire.decode(request, response, trusted, selected) as TransferResponse.Finished
    }

    private fun read(selected: TransferSelection, offset: Int, bytes: ByteArray): TransferResponse.ReadData {
        val tx = nextTransaction++
        check(tx < 65536)
        val request = TransferWire.read(tx, selected.handle, offset.toLong(), maxOf(1, bytes.size))
        val response = ByteArray(22 + bytes.size)
        response[1] = 4; put(response, 2, tx.toLong(), 2); put(response, 4, selected.handle, 4)
        put(response, 8, offset.toLong(), 8); put(response, 16, bytes.size.toLong(), 2)
        bytes.copyInto(response, 18)
        put(response, 18 + bytes.size, CRC32().apply { update(bytes) }.value, 4)
        return TransferWire.decode(request, response, trusted, selected) as TransferResponse.ReadData
    }

    private fun appendTo(session: DownloadSession, fixture: Fixture, selected: TransferSelection,
                         end: Int = fixture.bytes.size, chunk: Int = 256) {
        var offset = session.progress().receivedBytes.toInt()
        while (offset < end) {
            val stop = minOf(offset + chunk, end)
            session.append(read(selected, offset, fixture.bytes.copyOfRange(offset, stop)))
            offset = stop
        }
    }

    private fun resumeChecks() {
        for (fixture in fixtures) {
            val context = fresh("resume-${fixture.name}")
            val store = DownloadStore(context)
            val first = store.open(fixture.selection)
            val key = first.key
            expect(first.progress().committedBytes == 0L, "New download starts with phantom bytes")
            appendTo(first, fixture, fixture.selection, 85, 43)
            val partial = first.progress()
            expect(partial.committedBytes == 68L && partial.receivedBytes == 85L && !partial.complete,
                "Incomplete AFR was committed or complete manifest was not")
            first.close()
            reject { first.progress() }
            val selected = selection(fixture.metadata, 77)
            store.open(selected).use { resumed ->
                expect(resumed.key == key && resumed.progress().committedBytes == 68L &&
                    resumed.progress().receivedBytes == 68L, "Reconnect did not discard only RAM partial")
                appendTo(resumed, fixture, selected)
                expect(resumed.progress().committedBytes == fixture.bytes.size.toLong() && !resumed.progress().complete,
                    "EOF claimed durable FINISH before its transaction")
            }
            // The last committed record can be a seal even when FINISH was lost.
            store.open(selected).use { resumed ->
                expect(!resumed.progress().complete && resumed.progress().receivedBytes == selected.exportBytes,
                    "Sealed unfinished source could not replay")
                val done = resumed.finish(finish(fixture, selected))
                expect(done.complete && done.receiptHex == fixture.verified.receipt.hex(), "Final committed receipt differs")
                expect(resumed.finish(finish(fixture, selected)) == done, "Exact FINISH retry changed progress")
                val exported = File(context.cacheDir, "source.aura")
                val verified = resumed.export(exported)
                expect(exported.readBytes().contentEquals(fixture.bytes) && verified.sha256 == fixture.verified.sha256,
                    "Resumed export changed original C bytes")
                expect(verified.physicalReceipt?.encode()?.contentEquals(fixture.ack) == true,
                    "Export replaced physical receipt with derived receipt")
                if (fixture.name == "open") expect(verified.physicalReceipt?.status == ReceiptStatus.OPEN &&
                    verified.status == ReceiptStatus.INTERRUPTED && verified.originalSourceSamples == null,
                    "OPEN export invented physical termination or original duration")
                val saved = exported.readBytes()
                reject { resumed.export(exported) }
                expect(exported.readBytes().contentEquals(saved), "Exclusive export overwrote existing destination")
            }
            store.open(selected).use { expect(it.progress().complete, "Durable FINISH was lost on reopen") }
        }
    }

    private fun retryChecks() {
        val fixture = fixtures.first()
        for (kind in listOf("offset", "handle", "retry-bytes", "record-crc")) {
            val context = fresh("retry-$kind")
            val store = DownloadStore(context)
            store.open(fixture.selection).use { session ->
                val request = read(fixture.selection, 0, fixture.bytes.copyOfRange(0, 68))
                val progress = session.append(request)
                val saved = logical(context)
                expect(session.append(request) == progress && logical(context) == saved, "Exact last READ retry is not idempotent")
                when (kind) {
                    "offset" -> reject { session.append(TransferResponse.ReadData(4, fixture.selection.handle, 69, byteArrayOf(1))) }
                    "handle" -> reject { session.append(TransferResponse.ReadData(4, fixture.selection.handle + 1, 68, byteArrayOf(1))) }
                    "retry-bytes" -> {
                        val changed = request.bytes(); changed[0] = 0
                        reject { session.append(TransferResponse.ReadData(4, fixture.selection.handle, 0, changed)) }
                    }
                    else -> {
                        val end = firstRecordEnd(fixture)
                        val changed = fixture.bytes.copyOfRange(68, end)
                        changed[changed.lastIndex] = (changed.last().toInt() xor 1).toByte()
                        // The transport CRC is repaired, but the archive record CRC is wrong.
                        reject { session.append(read(fixture.selection, 68, changed)) }
                    }
                }
                reject { session.progress() }
                expect(logical(context) == saved, "Rejected READ changed durable rows or checkpoint")
            }
            store.open(fixture.selection).use { expect(it.progress().committedBytes == 68L, "Rejected READ destroyed retained prefix") }
        }
    }

    private fun rollbackChecks() {
        val fixture = fixtures.first()
        for (kind in listOf("record-insert", "metadata-update", "finish-update")) {
            val context = fresh("rollback-$kind")
            val store = DownloadStore(context)
            store.open(fixture.selection).use { session ->
                appendTo(session, fixture, fixture.selection, if (kind == "finish-update") fixture.bytes.size else 68)
                val baseline = logical(context)
                sql(context) { db ->
                    val event = if (kind == "record-insert") "INSERT ON records" else "UPDATE ON downloads"
                    db.execSQL("CREATE TRIGGER injected_abort BEFORE $event BEGIN SELECT RAISE(ABORT, 'test rollback'); END")
                }
                val failure = if (kind == "finish-update") rejected { session.finish(finish(fixture, fixture.selection)) }
                    else rejected { appendTo(session, fixture, fixture.selection, firstRecordEnd(fixture)) }
                expect(failure is SQLiteException && failure.message?.contains("test rollback") == true,
                    "Injected SQLite ABORT was not the transaction failure")
                reject { session.progress() }
                expect(logical(context) == baseline, "Aborted transaction published records, receipt or completion")
            }
            sql(context) { it.execSQL("DROP TRIGGER injected_abort") }
            store.open(fixture.selection).use { recovered ->
                val expected = if (kind == "finish-update") fixture.bytes.size.toLong() else 68L
                expect(recovered.progress().committedBytes == expected && !recovered.progress().complete,
                    "Rollback reopen did not recover exact committed source")
                if (kind != "finish-update") appendTo(recovered, fixture, fixture.selection, firstRecordEnd(fixture))
                else expect(recovered.finish(finish(fixture, fixture.selection)).complete, "Rolled-back FINISH could not retry")
                if (kind != "finish-update") expect(recovered.progress().committedBytes == firstRecordEnd(fixture).toLong(),
                    "Poisoned validator state survived rollback/reopen")
            }
        }
    }

    private fun corruptionChecks() {
        val fixture = fixtures.first()
        for (kind in listOf("committed", "count", "receipt", "start", "wire", "missing", "finished")) {
            val context = fresh("corrupt-$kind")
            seed(context, fixture, secondRecordEnd(fixture))
            sql(context) { db ->
                when (kind) {
                    "committed" -> db.execSQL("UPDATE downloads SET committed = committed + 1")
                    "count" -> db.execSQL("UPDATE downloads SET record_count = record_count + 1")
                    "receipt" -> db.execSQL("UPDATE downloads SET receipt = zeroblob(94)")
                    "start" -> db.execSQL("UPDATE records SET start = start + 1 WHERE ordinal = 1")
                    "missing" -> db.execSQL("DELETE FROM records WHERE ordinal = 1")
                    "finished" -> db.execSQL("UPDATE downloads SET finished = 1")
                    else -> {
                        val changed = fixture.bytes.copyOfRange(68, firstRecordEnd(fixture))
                        changed[24] = (changed[24].toInt() xor 1).toByte(); repairCrc(changed)
                        db.update("records", ContentValues().apply { put("wire", changed) }, "ordinal = 1", null)
                    }
                }
            }
            assertRetainedRejection(context, fixture.selection, "Corrupt $kind")
        }
    }

    private fun rowFramingChecks() {
        val fixture = fixtures.first()
        for (kind in listOf("split", "concatenate")) {
            val context = fresh("framing-$kind")
            seed(context, fixture, firstRecordEnd(fixture))
            sql(context) { db ->
                val key = db.rawQuery("SELECT revision FROM downloads", null).use { it.moveToFirst(); it.getString(0) }
                val record = fixture.bytes.copyOfRange(68, firstRecordEnd(fixture))
                db.beginTransaction()
                try {
                    db.delete("records", null, null)
                    fun insert(ordinal: Int, start: Int, wire: ByteArray) {
                        db.insertOrThrow("records", null, ContentValues().apply {
                            put("revision", key); put("ordinal", ordinal); put("start", start); put("wire", wire)
                        })
                    }
                    if (kind == "split") {
                        insert(0, 0, fixture.bytes.copyOfRange(0, 34))
                        insert(1, 34, fixture.bytes.copyOfRange(34, 68))
                        insert(2, 68, record)
                        db.execSQL("UPDATE downloads SET record_count = 3")
                    } else {
                        insert(0, 0, fixture.bytes.copyOfRange(0, firstRecordEnd(fixture)))
                        db.execSQL("UPDATE downloads SET record_count = 1")
                    }
                    db.setTransactionSuccessful()
                } finally { db.endTransaction() }
            }
            assertRetainedRejection(context, fixture.selection, "Saved $kind record")
        }
    }

    private fun lockChecks() {
        val fixture = fixtures.first()
        val context = fresh("locking")
        val first = DownloadStore(context).open(fixture.selection)
        val denied = rejected { DownloadStore(context).open(fixture.selection).close() }
        expect(denied is DownloadStoreException && denied.message?.contains("in this process") == true,
            "Second owner did not fail at the process reservation before opening a channel")
        expect(first.progress().committedBytes == 0L, "Rejected second owner invalidated first session")
        appendTo(first, fixture, fixture.selection, 68)
        expect(first.progress().committedBytes == 68L, "Active owner could not commit after rejected second open")
        first.close()
        DownloadStore(context).open(fixture.selection).use { second ->
            first.close()
            reject { first.progress() }
            reject { first.append(read(fixture.selection, 0, fixture.bytes.copyOfRange(0, 68))) }
            reject { first.finish(finish(fixture, fixture.selection)) }
            reject { first.export(File(context.cacheDir, "closed.aura")) }
            reject { DownloadStore(context).open(fixture.selection).close() }
            expect(second.progress().committedBytes == 68L, "Closing stale owner invalidated live owner")
            expect(!File(context.cacheDir, "closed.aura").exists(), "Closed session created destination")
        }
        DownloadStore(context).open(fixture.selection).use { expect(it.progress().committedBytes == 68L, "Owner lock leaked") }

        // Both obstructions are test-created empty directories, retained by
        // renaming within this unique private namespace; no source is removed.
        for (kind in listOf("lock-file-construction", "database-open")) {
            val failedContext = fresh("owner-failure-$kind")
            val downloadRoot = File(failedContext.noBackupFilesDir, "a04-downloads")
            expect(downloadRoot.mkdir(), "Could not create isolated owner-failure namespace")
            val obstruction = File(downloadRoot, if (kind == "lock-file-construction") ".owner.lock" else "downloads.sqlite")
            expect(obstruction.mkdir(), "Could not create isolated open obstruction")
            val failure = rejected { DownloadStore(failedContext).open(fixture.selection).close() }
            expect(if (kind == "lock-file-construction") failure is FileNotFoundException else failure is SQLiteException,
                "Owner failure did not reach the intended file/database open boundary")
            val retained = File(downloadRoot, "$kind.retained-test-directory")
            expect(obstruction.isDirectory && obstruction.renameTo(retained) && retained.isDirectory,
                "Test-created open obstruction was removed or could not be retained")
            DownloadStore(failedContext).open(fixture.selection).use {
                expect(it.progress().committedBytes == 0L, "Failed open leaked process reservation or OS resources")
                appendTo(it, fixture, fixture.selection, 68)
                expect(it.progress().committedBytes == 68L, "Recovered owner could not commit source")
            }
        }
    }

    private fun revisionChecks() {
        val fixture = fixtures.first()
        val context = fresh("revisions")
        val store = DownloadStore(context)
        val originalKey = store.open(fixture.selection).use {
            appendTo(it, fixture, fixture.selection, 68); it.key
        }
        val different = selection(fixture.metadata, 88, changedReceipt = true)
        store.open(different).use {
            expect(it.key != originalKey && it.progress().committedBytes == 0L,
                "Changed physical receipt was merged into prior immutable revision")
        }
        store.open(selection(fixture.metadata, 99)).use {
            expect(it.key == originalKey && it.progress().committedBytes == 68L,
                "Ephemeral handle change forked or lost stable revision")
        }
        sql(context) { db ->
            db.rawQuery("SELECT count(*) FROM downloads", null).use {
                expect(it.moveToFirst() && it.getInt(0) == 2, "Conflicting revision was removed")
            }
        }
    }

    private fun finishChecks() {
        val fixture = fixtures.first()
        for (kind in listOf("premature", "wrong-handle", "wrong-receipt")) {
            val context = fresh("finish-$kind")
            val store = DownloadStore(context)
            store.open(fixture.selection).use {
                appendTo(it, fixture, fixture.selection, 68)
                val saved = logical(context)
                val selected = when (kind) {
                    "wrong-handle" -> selection(fixture.metadata, 91)
                    "wrong-receipt" -> selection(fixture.metadata, changedReceipt = true)
                    else -> fixture.selection
                }
                reject { it.finish(TransferResponse.Finished(71, selected)) }
                expect(logical(context) == saved, "Rejected FINISH changed saved state")
            }
            store.open(fixture.selection).use {
                val destination = File(context.cacheDir, "premature.aura")
                reject { it.export(destination) }
                expect(!destination.exists(), "Incomplete download created publishable source")
            }
        }
    }

    private fun bridgeChecks() {
        for (fixture in fixtures) {
            val context = fresh("bridge-${fixture.name}")
            val store = DownloadStore(context)
            store.open(fixture.selection).use { session ->
                appendTo(session, fixture, fixture.selection)
                session.finish(finish(fixture, fixture.selection))
                val original = logical(context)
                val captures = CaptureStore(context)
                val capture = captures.importDownload(session)
                expect(capture.playbackReady && capture.playbackFile.isFile && capture.decoderName != null,
                    "Completed download did not pass real platform decode before Ready")
                expect(capture.fileSha256 == fixture.verified.sha256 &&
                    capture.physicalStatus == fixture.selection.physicalReceipt.status &&
                    captures.fileForExport(capture.key).readBytes().contentEquals(fixture.bytes),
                    "Playback bridge changed source bytes or physical provenance")
                val verified = captures.readVerified(capture.key)
                expect(verified.receipt.encode().contentEquals(fixture.verified.receipt.encode()) &&
                    verified.physicalReceipt?.encode()?.contentEquals(fixture.ack) == true,
                    "Playback bridge promoted derived receipt to physical proof")
                val again = captures.importDownload(session)
                expect(again.key == capture.key && captures.list().size == 1, "Duplicate bridge created duplicate library entry")
                val exported = File(context.cacheDir, "after-bridge.aura")
                session.export(exported)
                expect(exported.readBytes().contentEquals(fixture.bytes) && logical(context) == original,
                    "Playback bridge altered or consumed download source")
                bridgeEvidence.put(JSONObject().put("fixture", fixture.name).put("sha256", capture.fileSha256)
                    .put("physical_status", capture.physicalStatus?.name).put("export_status", capture.status.name)
                    .put("decoder", capture.decoderName).put("sample_rate", capture.decodeRate)
                    .put("source_samples", capture.sourceSamples).put("playback_ready", capture.playbackReady))
            }
        }
    }

    private fun seed(context: Context, fixture: Fixture, end: Int) {
        DownloadStore(context).open(fixture.selection).use { appendTo(it, fixture, fixture.selection, end) }
    }

    private fun assertRetainedRejection(context: Context, selection: TransferSelection, label: String) {
        val before = logical(context)
        val initial = rejected { DownloadStore(context).open(selection).close() }
        expect(initial.message?.contains("in this process") != true, "$label failed before actual replay")
        expect(databaseFile(context).isFile && logical(context) == before, "$label was deleted or repaired on reopen")
        RandomAccessFile(File(context.noBackupFilesDir, "a04-downloads/.owner.lock"), "rw").use { owner ->
            val lock = owner.channel.tryLock()
            expect(lock != null, "$label leaked owner lock after failed replay")
            lock?.release()
        }
        // Repeated failure must release ownership, preserving the same evidence.
        val repeated = rejected { DownloadStore(context).open(selection).close() }
        expect(repeated.message?.contains("in this process") != true, "$label leaked process reservation after refused replay")
        expect(logical(context) == before, "$label changed after second refused reopen")
    }

    private fun firstRecordEnd(fixture: Fixture): Int = 68 + 26 + u16(fixture.bytes, 88)
    private fun secondRecordEnd(fixture: Fixture): Int {
        val start = firstRecordEnd(fixture)
        return start + 26 + u16(fixture.bytes, start + 20)
    }

    private fun logical(context: Context): String = sql(context) { db ->
        val result = StringBuilder()
        for (table in listOf("downloads", "records")) {
            db.rawQuery("SELECT * FROM $table ORDER BY ${if (table == "downloads") "revision" else "revision, ordinal"}", null).use { cursor ->
                while (cursor.moveToNext()) {
                    result.append(table).append(':')
                    for (column in 0 until cursor.columnCount) {
                        result.append(when (cursor.getType(column)) {
                            android.database.Cursor.FIELD_TYPE_NULL -> "NULL"
                            android.database.Cursor.FIELD_TYPE_BLOB -> hex(cursor.getBlob(column))
                            else -> cursor.getString(column)
                        }).append('|')
                    }
                    result.append('\n')
                }
            }
        }
        result.toString()
    }

    private fun <T> sql(context: Context, action: (SQLiteDatabase) -> T): T =
        SQLiteDatabase.openDatabase(databaseFile(context).absolutePath, null, SQLiteDatabase.OPEN_READWRITE).use(action)
    private fun databaseFile(context: Context) = File(context.noBackupFilesDir, "a04-downloads/downloads.sqlite")

    private fun fresh(name: String): Context {
        val root = File(targetContext.cacheDir, "download-$name-${UUID.randomUUID()}")
        check(root.mkdir())
        return DownloadTestContext(targetContext, root)
    }

    private fun reject(action: () -> Unit) {
        rejected(action)
    }

    private fun rejected(action: () -> Unit): Exception {
        var failure: Exception? = null
        try { action() } catch (error: Exception) { failure = error }
        expect(failure != null, "Operation required to fail unexpectedly succeeded")
        return checkNotNull(failure)
    }

    private fun writeNew(file: File, bytes: ByteArray) {
        check(file.createNewFile())
        FileOutputStream(file).use { it.write(bytes); it.fd.sync() }
    }
    private fun sha(bytes: ByteArray) = hex(MessageDigest.getInstance("SHA-256").digest(bytes))
    private fun hex(bytes: ByteArray) = bytes.joinToString("") { "%02x".format(it.toInt() and 255) }
    private fun unhex(value: String) = value.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
    private fun u16(bytes: ByteArray, at: Int) = (bytes[at].toInt() and 255) or ((bytes[at + 1].toInt() and 255) shl 8)
    private fun put(bytes: ByteArray, at: Int, value: Long, size: Int) {
        for (i in 0 until size) bytes[at + i] = (value ushr (8 * i)).toByte()
    }
    private fun repairCrc(bytes: ByteArray) {
        val crc = CRC32().apply { update(bytes, 0, bytes.size - 4) }.value
        put(bytes, bytes.size - 4, crc, 4)
    }
}

/** Namespace wrapper only: real platform Context services, SQLite and files. */
private class DownloadTestContext(base: Context, private val root: File) : ContextWrapper(base) {
    private fun directory(name: String) = File(root, name).apply { mkdirs() }
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
