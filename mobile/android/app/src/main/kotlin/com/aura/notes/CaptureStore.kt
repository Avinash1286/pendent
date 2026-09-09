package com.aura.notes

import android.content.ContentValues
import android.content.Context
import android.database.DatabaseErrorHandler
import android.database.sqlite.SQLiteDatabase
import android.net.Uri
import android.system.Os
import android.system.OsConstants
import com.aura.capture.ArchiveLimits
import com.aura.capture.AuraArchive
import com.aura.capture.AuraOgg
import com.aura.capture.CaptureCodec
import com.aura.capture.ReceiptStatus
import com.aura.capture.VerifiedArchive
import org.json.JSONObject
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.IOException
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.file.Files
import java.security.MessageDigest
import java.util.UUID

data class LocalCapture(
    val key: String,
    val title: String,
    val contextText: String,
    val sourceSamples: Long,
    val startedAtMs: Long,
    val importedAtMs: Long,
    val status: ReceiptStatus,
    val physicalStatus: ReceiptStatus?,
    val fileSha256: String,
    val receiptDigest: String,
    val playbackReady: Boolean,
    val decoderName: String?,
    val decodeRate: Int?,
    val bundle: File,
) {
    val playbackFile: File get() = File(bundle, "playback.wav")
}

class CaptureStoreException(message: String) : IOException(message)

/** Private, offline publication of selected A04 sources. All methods do blocking
 * IO and belong on the application's single worker, never the UI thread.
 *
 * A file lock serializes publishers across store instances/processes. Complete
 * files and both rename parents reach fsync before a FULL-or-stronger SQLite
 * transaction exposes an inventory row. SQLite holds editable notes; it never
 * replaces the original archive. A crash may leave an unindexed complete bundle
 * or a retained pending import, but cannot intentionally publish partial audio.
 *
 * Receipt checks prove byte consistency, not device identity/authentication.
 * This importer does not issue a device durable-ACK or authorize NAND erasure.
 */
class CaptureStore(context: Context) {
    private val appContext = context.applicationContext
    private val root = File(appContext.noBackupFilesDir, "captures")
    private val pending = File(root, ".pending")
    private val complete = File(root, "complete")
    private var reconciled = false

    @Volatile var recoveryWarnings: List<String> = emptyList()
        private set

    fun importSources(uris: List<Uri>): LocalCapture = locked { db ->
        requireStore(uris.size in 1..2 && uris.all { it.scheme == "content" },
            "Select one AURA archive and, optionally, its physical receipt")
        val staging = File(pending, UUID.randomUUID().toString())
        requireStore(staging.mkdir(), "Could not create a private import directory")
        syncDirectory(pending)

        // Copy and sync every selected source before inspecting any untrusted
        // header. A failed or conflicting import remains here for recovery.
        var totalBytes = 0L
        val copied = uris.mapIndexed { index, uri ->
            val output = File(staging, "incoming-$index")
            val input = appContext.contentResolver.openInputStream(uri)
                ?: throw CaptureStoreException("The selected source could not be opened")
            input.use { source ->
                requireStore(output.createNewFile(), "Import output already exists")
                FileOutputStream(output).use { target ->
                    val buffer = ByteArray(64 * 1024)
                    var bytes = 0L
                    var emptyReads = 0
                    while (true) {
                        checkCancelled()
                        val count = source.read(buffer)
                        if (count < 0) break
                        if (count == 0) {
                            requireStore(++emptyReads <= 16, "The source stopped making progress")
                            continue
                        }
                        emptyReads = 0
                        requireStore(count <= MAX_SOURCE_BYTES - bytes &&
                            count <= MAX_SOURCE_BYTES + ACK_BYTES - totalBytes,
                            "Selected sources exceed the 128 MiB import limit")
                        target.write(buffer, 0, count)
                        bytes += count
                        totalBytes += count
                    }
                    target.flush()
                    target.fd.sync()
                }
            }
            output
        }
        syncDirectory(staging)

        var archiveInput: File? = null
        var ackInput: File? = null
        copied.forEach { file ->
            when (magic(file)) {
                "AUR3" -> {
                    requireStore(archiveInput == null, "Select exactly one AURA archive")
                    archiveInput = file
                }
                "ACK3" -> {
                    requireStore(ackInput == null && file.length() == ACK_BYTES,
                        "A physical receipt must be exactly 94 bytes")
                    ackInput = file
                }
                else -> throw CaptureStoreException("The selected file is not an AURA archive or receipt")
            }
        }
        val source = File(staging, SOURCE_NAME)
        renameNew(archiveInput ?: throw CaptureStoreException("No AURA archive was selected"), source)
        ackInput?.let { renameNew(it, File(staging, ACK_NAME)) }
        syncDirectory(staging)
        publishStaging(db, staging)
    }

    /** Publish an already committed local download through the same independent
     * archive/decode/bundle validation as a selected file. SQLite retains the
     * original download even if copying, decoding or publication fails.
     */
    fun importDownload(session: DownloadSession): LocalCapture = locked { db ->
        val progress = session.progress()
        requireStore(progress.complete && progress.exportBytes <= MAX_SOURCE_BYTES,
            "A completed download within the 128 MiB playback import limit is required")
        val staging = File(pending, UUID.randomUUID().toString())
        requireStore(staging.mkdir(), "Could not create a private download import directory")
        syncDirectory(pending)
        val source = session.export(File(staging, SOURCE_NAME))
        val physical = source.physicalReceipt
            ?: throw CaptureStoreException("Downloaded source is missing physical provenance")
        writeNew(File(staging, ACK_NAME), physical.encode())
        syncDirectory(staging)
        publishStaging(db, staging)
    }

    private fun publishStaging(db: SQLiteDatabase, staging: File): LocalCapture {
        val source = File(staging, SOURCE_NAME)
        val ack = optionalAck(staging)
        val verified = AuraArchive.verify(source, ack, LIMITS)
        requireStore(verified.capture.codec == CaptureCodec.OPUS,
            "This version supports A04 Opus captures; the PCM source has been retained")
        val key = keyFor(verified)
        val destination = File(complete, key)

        if (destination.exists()) {
            val existing = loadBundle(destination)
            requireStore(existing.archive.sha256 == verified.sha256 &&
                existing.archive.receipt.hex() == verified.receipt.hex(),
                "This capture revision conflicts with an existing original")
            val existingAck = optionalAck(destination)
            if (ack != null) {
                if (existingAck != null) {
                    requireStore(existingAck.contentEquals(ack),
                        "This physical receipt conflicts with the saved provenance")
                } else {
                    // Validate against the saved original, then add a new
                    // immutable sidecar. Never rewrite the source or metadata.
                    AuraArchive.verify(existing.archive.file, ack, LIMITS)
                    val proof = File(destination, ".proof-${UUID.randomUUID()}.pending")
                    writeNew(proof, ack)
                    renameNew(proof, File(destination, ACK_NAME))
                    syncDirectory(destination)
                }
            }
            val finalBundle = loadBundle(destination)
            index(db, finalBundle)
            return row(db, key)!!
        }

        val metadata = JSONObject()
            .put("schema", 1)
            .put("key", key)
            .put("source_sha256", verified.sha256)
            .put("source_bytes", verified.fileBytes)
            .put("receipt_hex", verified.receipt.hex())
            .put("imported_at_ms", System.currentTimeMillis())

        if (verified.sourceSamples > 0) {
            requireStore(verified.seal.audioPackets > 0, "Nonempty capture has no audio packets")
            val ogg = File(staging, OGG_NAME)
            requireStore(ogg.createNewFile(), "A derived audio file already exists")
            FileOutputStream(ogg).use { output ->
                AuraOgg.write(verified, output)
                output.flush()
                output.fd.sync()
            }
            val wav = File(staging, WAV_NAME)
            val decoded = AudioDecoder.decode(ogg, wav, verified)
            validateDecode(verified, decoded.sampleRate, decoded.frames,
                decoded.rawFrames, decoded.decoderName, decoded.endTrimApplied)
            metadata.put("decode_state", "decoded")
                .put("ogg_sha256", hash(ogg, MAX_OGG_BYTES))
                .put("wav_sha256", hash(wav, MAX_WAV_BYTES))
                .put("decode_rate", decoded.sampleRate)
                .put("frames", decoded.frames)
                .put("raw_frames", decoded.rawFrames)
                .put("decoder_name", decoded.decoderName)
                .put("end_trim_applied", decoded.endTrimApplied)
        } else {
            // A valid zero-duration capture is useful evidence, with no playable
            // audio and no claim that its optional zero-duration packets decoded.
            metadata.put("decode_state", "empty")
        }

        writeNew(File(staging, META_NAME), metadata.toString().toByteArray(Charsets.UTF_8))
        syncDirectory(staging)
        // Re-open the completed private bundle before publication. The decoder
        // has already consumed full EOS; this checks its persisted files/metadata.
        loadBundle(staging, expectedKey = key)
        renameNew(staging, destination)
        syncDirectory(pending)
        syncDirectory(complete)
        val published = loadBundle(destination)
        index(db, published)
        return row(db, key)!!
    }

    fun list(): List<LocalCapture> = locked { db ->
        val captures = mutableListOf<LocalCapture>()
        db.query("captures", COLUMNS, "valid = 1", null, null, null,
            "imported_at_ms DESC, key ASC").use { cursor ->
            while (cursor.moveToNext()) captures += fromCursor(cursor)
        }
        captures
    }

    fun find(key: String): LocalCapture? = locked { db ->
        validateKey(key)
        val item = row(db, key) ?: return@locked null
        validateIndexed(db, item)
        row(db, key)
    }

    fun update(key: String, title: String, contextText: String) = locked { db ->
        validateKey(key)
        val cleanTitle = title.trim()
        requireStore(cleanTitle.isNotEmpty() && cleanTitle.length <= 120 &&
            contextText.length <= 20_000 && '\u0000' !in cleanTitle && '\u0000' !in contextText,
            "Use a title up to 120 characters and context up to 20,000 characters")
        val item = row(db, key) ?: throw CaptureStoreException("Capture is unavailable")
        validateIndexed(db, item)
        transaction(db) {
            val values = ContentValues().apply {
                put("title", cleanTitle)
                put("context_text", contextText)
            }
            requireStore(db.update("captures", values, "key = ? AND valid = 1", arrayOf(key)) == 1,
                "Capture is unavailable")
        }
    }

    fun readVerified(key: String): VerifiedArchive = locked { db ->
        validateKey(key)
        val item = row(db, key) ?: throw CaptureStoreException("Capture is unavailable")
        validateIndexed(db, item).archive
    }

    /** The private immutable original, for a user-initiated SAF export. */
    fun fileForExport(key: String): File = readVerified(key).file

    private data class Bundle(
        val key: String,
        val directory: File,
        val archive: VerifiedArchive,
        val importedAtMs: Long,
        val decoded: Boolean,
        val decoderName: String?,
        val decodeRate: Int?,
    )

    private fun loadBundle(directory: File, expectedKey: String = directory.name): Bundle {
        requireStore(directory.isDirectory && !Files.isSymbolicLink(directory.toPath()),
            "Capture bundle is not a private directory")
        validateKey(expectedKey)
        val metadataFile = regularFile(directory, META_NAME, MAX_METADATA_BYTES)
        val metadata = JSONObject(metadataFile.readText(Charsets.UTF_8))
        requireStore(metadata.getInt("schema") == 1 && metadata.getString("key") == expectedKey,
            "Unsupported capture bundle metadata")
        val source = regularFile(directory, SOURCE_NAME, MAX_SOURCE_BYTES)
        val archive = AuraArchive.verify(source, optionalAck(directory), LIMITS)
        requireStore(archive.capture.codec == CaptureCodec.OPUS && keyFor(archive) == expectedKey &&
            metadata.getString("source_sha256") == archive.sha256 &&
            metadata.getLong("source_bytes") == archive.fileBytes &&
            metadata.getString("receipt_hex") == archive.receipt.hex(),
            "Saved source does not match its capture metadata")
        val imported = metadata.getLong("imported_at_ms")
        requireStore(imported >= 0, "Invalid import timestamp")
        var decoderName: String? = null
        var decodeRate: Int? = null
        val decoded = when (metadata.getString("decode_state")) {
            "empty" -> {
                requireStore(archive.sourceSamples == 0L,
                    "A nonempty capture is missing validated playback")
                false
            }
            "decoded" -> {
                val rate = metadata.getInt("decode_rate")
                val frames = metadata.getLong("frames")
                val rawFrames = metadata.getLong("raw_frames")
                val name = metadata.getString("decoder_name")
                validateDecode(archive, rate, frames, rawFrames, name,
                    metadata.getBoolean("end_trim_applied"))
                val ogg = regularFile(directory, OGG_NAME, MAX_OGG_BYTES)
                val wav = regularFile(directory, WAV_NAME, MAX_WAV_BYTES)
                requireStore(metadata.getString("ogg_sha256") == hash(ogg, MAX_OGG_BYTES) &&
                    metadata.getString("wav_sha256") == hash(wav, MAX_WAV_BYTES),
                    "Saved playback bytes differ from the completed decode")
                validateWav(wav, rate, frames)
                decoderName = name
                decodeRate = rate
                true
            }
            else -> throw CaptureStoreException("Unsupported playback validation state")
        }
        return Bundle(expectedKey, directory, archive, imported, decoded, decoderName, decodeRate)
    }

    private fun validateDecode(archive: VerifiedArchive, rate: Int, frames: Long,
        rawFrames: Long, decoderName: String, endTrimApplied: Boolean) {
        requireStore(archive.sourceSamples > 0 && archive.seal.audioPackets > 0 &&
            (rate == 16_000 || rate == 48_000) && archive.capture.sampleRate == 16_000,
            "Unsupported decoded capture")
        val target = Math.multiplyExact(archive.sourceSamples, (rate / 16_000).toLong())
        val raw = Math.multiplyExact(archive.seal.encodedSamples - archive.seal.preSkip,
            (rate / 16_000).toLong())
        requireStore(frames == target && (rawFrames == target || rawFrames == raw) &&
            rawFrames >= frames && frames <= (MAX_WAV_BYTES - 44) / 2 &&
            endTrimApplied == (rawFrames > frames) &&
            decoderName.isNotBlank() && decoderName.length <= 256,
            "Playback validation does not match the exact source duration")
    }

    private fun validateWav(file: File, rate: Int, frames: Long) {
        val header = ByteArray(44)
        FileInputStream(file).use { input ->
            requireStore(input.read(header) == header.size, "Incomplete WAV header")
        }
        val bytes = ByteBuffer.wrap(header).order(ByteOrder.LITTLE_ENDIAN)
        fun ascii(offset: Int, length: Int) = String(header, offset, length, Charsets.US_ASCII)
        val dataBytes = Math.multiplyExact(frames, 2L)
        requireStore(ascii(0, 4) == "RIFF" && ascii(8, 8) == "WAVEfmt " &&
            ascii(36, 4) == "data" && bytes.getInt(16) == 16 && bytes.getShort(20).toInt() == 1 &&
            bytes.getShort(22).toInt() == 1 && bytes.getInt(24) == rate &&
            bytes.getInt(28) == rate * 2 && bytes.getShort(32).toInt() == 2 &&
            bytes.getShort(34).toInt() == 16 &&
            (bytes.getInt(4).toLong() and 0xffff_ffffL) == dataBytes + 36 &&
            (bytes.getInt(40).toLong() and 0xffff_ffffL) == dataBytes &&
            file.length() == dataBytes + 44,
            "Saved WAV header or duration is inconsistent")
    }

    private fun validateIndexed(db: SQLiteDatabase, item: LocalCapture): Bundle {
        try {
            val bundle = loadBundle(item.bundle)
            requireStore(bundle.archive.sha256 == item.fileSha256 &&
                bundle.archive.receipt.chainSha256 == item.receiptDigest,
                "Inventory does not match the original source")
            index(db, bundle)
            return bundle
        } catch (error: Exception) {
            transaction(db) {
                db.update("captures", ContentValues().apply { put("valid", 0) },
                    "key = ?", arrayOf(item.key))
            }
            recoveryWarnings = recoveryWarnings + "One changed or incomplete capture was retained for recovery."
            throw error
        }
    }

    /** Only atomically published complete bundles can rebuild inventory. Pending
     * sources stay untouched; a parser success alone is never a ready row. */
    private fun reconcile(db: SQLiteDatabase) {
        val warnings = mutableListOf<String>()
        val directories = complete.listFiles()
            ?: throw CaptureStoreException("Could not inspect the private capture directory")
        transaction(db) {
            db.update("captures", ContentValues().apply { put("valid", 0) }, null, null)
            for (directory in directories) {
                checkCancelled()
                if (!KEY_PATTERN.matches(directory.name)) {
                    warnings += "An unrecognized published entry was retained for recovery."
                    continue
                }
                val bundle = try {
                    loadBundle(directory)
                } catch (_: Exception) {
                    checkCancelled()
                    warnings += "An incomplete or changed capture bundle was retained for recovery."
                    continue
                }
                if (!inventoryMatches(db, bundle)) {
                    warnings += "A capture conflicting with its saved inventory was retained for recovery."
                    continue
                }
                // Database errors must abort reconciliation, not become a
                // misleading success that hides an otherwise valid source.
                upsert(db, bundle)
            }
        }
        recoveryWarnings = warnings
        reconciled = true
    }

    private fun index(db: SQLiteDatabase, bundle: Bundle) = transaction(db) { upsert(db, bundle) }

    private fun upsert(db: SQLiteDatabase, bundle: Bundle) {
        requireStore(inventoryMatches(db, bundle),
            "Capture files conflict with the saved original or physical provenance")
        val archive = bundle.archive
        val values = ContentValues().apply {
            put("key", bundle.key)
            put("source_samples", archive.sourceSamples)
            put("started_at_ms", archive.capture.startedAtMs)
            put("imported_at_ms", bundle.importedAtMs)
            put("status", archive.status.name)
            put("physical_status", archive.physicalReceipt?.status?.name)
            put("file_sha256", archive.sha256)
            put("receipt_digest", archive.receipt.chainSha256)
            put("playback_ready", if (bundle.decoded) 1 else 0)
            put("decoder_name", bundle.decoderName)
            put("decode_rate", bundle.decodeRate)
            put("bundle_name", bundle.key)
            put("valid", 1)
        }
        val edited = db.update("captures", values, "key = ?", arrayOf(bundle.key))
        if (edited == 0) {
            values.put("title", "Untitled capture")
            values.put("context_text", "")
            db.insertOrThrow("captures", null, values)
        }
    }

    private fun inventoryMatches(db: SQLiteDatabase, bundle: Bundle): Boolean =
        db.query("captures", arrayOf("file_sha256", "receipt_digest", "physical_status"),
            "key = ?", arrayOf(bundle.key), null, null, null).use { cursor ->
            if (!cursor.moveToFirst()) return@use true
            val physical = if (cursor.isNull(2)) null else cursor.getString(2)
            cursor.getString(0) == bundle.archive.sha256 &&
                cursor.getString(1) == bundle.archive.receipt.chainSha256 &&
                (physical == null || physical == bundle.archive.physicalReceipt?.status?.name)
        }

    private fun row(db: SQLiteDatabase, key: String): LocalCapture? =
        db.query("captures", COLUMNS, "key = ? AND valid = 1", arrayOf(key),
            null, null, null).use { cursor -> if (cursor.moveToFirst()) fromCursor(cursor) else null }

    private fun fromCursor(cursor: android.database.Cursor): LocalCapture {
        fun string(name: String) = cursor.getString(cursor.getColumnIndexOrThrow(name))
        fun long(name: String) = cursor.getLong(cursor.getColumnIndexOrThrow(name))
        fun nullableString(name: String): String? {
            val column = cursor.getColumnIndexOrThrow(name)
            return if (cursor.isNull(column)) null else cursor.getString(column)
        }
        val key = string("key")
        validateKey(key)
        requireStore(string("bundle_name") == key, "Invalid inventory bundle path")
        val rateColumn = cursor.getColumnIndexOrThrow("decode_rate")
        return LocalCapture(key, string("title"), string("context_text"), long("source_samples"),
            long("started_at_ms"), long("imported_at_ms"), ReceiptStatus.valueOf(string("status")),
            nullableString("physical_status")?.let { ReceiptStatus.valueOf(it) },
            string("file_sha256"), string("receipt_digest"), long("playback_ready") == 1L,
            nullableString("decoder_name"),
            if (cursor.isNull(rateColumn)) null else cursor.getInt(rateColumn), File(complete, key))
    }

    private fun <T> locked(action: (SQLiteDatabase) -> T): T = synchronized(PROCESS_LOCK) {
        ensureDirectory(root)
        ensureDirectory(pending)
        ensureDirectory(complete)
        val lockFile = File(root, "store.lock")
        requireStore(!Files.isSymbolicLink(lockFile.toPath()), "Invalid library lock")
        RandomAccessFile(lockFile, "rw").use { lock ->
            lock.channel.lock().use {
                val dbFile = File(root, "inventory.sqlite")
                requireStore(!Files.isSymbolicLink(dbFile.toPath()), "Invalid inventory path")
                // Android's default corruption handler may delete the database.
                // Preserve both editable notes and sources for explicit recovery.
                val corruptionHandler = DatabaseErrorHandler {
                    throw CaptureStoreException("Inventory is damaged and has been retained for recovery")
                }
                SQLiteDatabase.openDatabase(dbFile.absolutePath, null,
                    SQLiteDatabase.OPEN_READWRITE or SQLiteDatabase.CREATE_IF_NECESSARY or
                        SQLiteDatabase.NO_LOCALIZED_COLLATORS, corruptionHandler).use { db ->
                    configureDatabase(db)
                    if (!reconciled) reconcile(db)
                    action(db)
                }
            }
        }
    }

    private fun configureDatabase(db: SQLiteDatabase) {
        db.rawQuery("PRAGMA journal_mode = DELETE", null).use { cursor ->
            requireStore(cursor.moveToFirst() && cursor.getString(0).equals("delete", true),
                "Could not enable durable inventory journaling")
        }
        // EXTRA includes FULL synchronization plus rollback-journal directory
        // sync on deletion. Android SQLite supports this on the minimum API 29.
        db.execSQL("PRAGMA synchronous = EXTRA")
        db.rawQuery("PRAGMA synchronous", null).use { cursor ->
            requireStore(cursor.moveToFirst() && cursor.getInt(0) >= 2,
                "Durable inventory synchronization is unavailable")
        }
        val version = db.version
        requireStore(version == 0 || version == 1, "Unsupported inventory schema; source files are retained")
        if (version == 0) {
            db.rawQuery("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'", null)
                .use { cursor ->
                    // Android may create its locale metadata table on opening.
                    while (cursor.moveToNext()) requireStore(cursor.getString(0) == "android_metadata",
                        "Unversioned inventory is retained for recovery")
                }
            transaction(db) {
                db.execSQL("""CREATE TABLE captures (
                    key TEXT PRIMARY KEY NOT NULL, title TEXT NOT NULL, context_text TEXT NOT NULL,
                    source_samples INTEGER NOT NULL, started_at_ms INTEGER NOT NULL,
                    imported_at_ms INTEGER NOT NULL, status TEXT NOT NULL, physical_status TEXT,
                    file_sha256 TEXT NOT NULL, receipt_digest TEXT NOT NULL,
                    playback_ready INTEGER NOT NULL, decoder_name TEXT, decode_rate INTEGER,
                    bundle_name TEXT NOT NULL, valid INTEGER NOT NULL DEFAULT 1
                )""")
                db.version = 1
            }
        }
        val names = mutableSetOf<String>()
        db.rawQuery("PRAGMA table_info(captures)", null).use { cursor ->
            while (cursor.moveToNext()) names += cursor.getString(cursor.getColumnIndexOrThrow("name"))
        }
        requireStore(names == COLUMNS.toSet() + "valid", "Inventory schema is inconsistent")
    }

    private fun transaction(db: SQLiteDatabase, action: () -> Unit) {
        db.beginTransaction()
        try {
            action()
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        syncDirectory(root)
    }

    private fun optionalAck(directory: File): ByteArray? {
        val file = File(directory, ACK_NAME)
        if (!file.exists() && !Files.isSymbolicLink(file.toPath())) return null
        return regularFile(directory, ACK_NAME, ACK_BYTES).also {
            requireStore(it.length() == ACK_BYTES, "Invalid physical receipt size")
        }.readBytes()
    }

    private fun regularFile(directory: File, name: String, maximum: Long): File {
        val file = File(directory, name)
        requireStore(file.isFile && !Files.isSymbolicLink(file.toPath()) &&
            file.canonicalFile.parentFile == directory.canonicalFile && file.length() in 1..maximum,
            "A required private capture file is missing or exceeds its limit")
        return file
    }

    private fun ensureDirectory(directory: File) {
        requireStore(!Files.isSymbolicLink(directory.toPath()), "Invalid private library directory")
        if (!directory.exists()) {
            requireStore(directory.mkdir(), "Could not create the private library")
            syncDirectory(directory)
            syncDirectory(directory.parentFile!!)
        }
        requireStore(directory.isDirectory, "Private library path is not a directory")
    }

    private fun renameNew(from: File, to: File) {
        requireStore(!to.exists() && !Files.isSymbolicLink(to.toPath()), "Publication destination already exists")
        Os.rename(from.absolutePath, to.absolutePath)
    }

    private fun writeNew(file: File, bytes: ByteArray) {
        requireStore(file.createNewFile(), "Private output already exists")
        FileOutputStream(file).use { output ->
            output.write(bytes)
            output.flush()
            output.fd.sync()
        }
    }

    private fun syncDirectory(directory: File) {
        requireStore(directory.isDirectory && !Files.isSymbolicLink(directory.toPath()),
            "Library synchronization requires a private directory")
        // O_DIRECTORY is not part of Android's public OsConstants API. Reject
        // symlinks at open, then validate the actual descriptor before syncing.
        val descriptor = Os.open(directory.absolutePath,
            OsConstants.O_RDONLY or OsConstants.O_NOFOLLOW or OsConstants.O_CLOEXEC, 0)
        try {
            requireStore(OsConstants.S_ISDIR(Os.fstat(descriptor).st_mode),
                "Opened library path is not a directory")
            Os.fsync(descriptor)
        } finally {
            Os.close(descriptor)
        }
    }

    private fun magic(file: File): String {
        val bytes = ByteArray(4)
        FileInputStream(file).use { input ->
            requireStore(input.read(bytes) == bytes.size, "Selected source is shorter than its header")
        }
        return String(bytes, Charsets.US_ASCII)
    }

    private fun hash(file: File, maximum: Long): String {
        requireStore(file.length() in 1..maximum, "Private file exceeds its verification limit")
        val expectedBytes = file.length()
        val digest = MessageDigest.getInstance("SHA-256")
        var bytes = 0L
        FileInputStream(file).use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                checkCancelled()
                val count = input.read(buffer)
                if (count < 0) break
                requireStore(count > 0 && count <= maximum - bytes, "Private file changed during verification")
                digest.update(buffer, 0, count)
                bytes += count
            }
        }
        requireStore(bytes == expectedBytes && file.length() == expectedBytes,
            "Private file changed during verification")
        return digest.digest().joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    private fun keyFor(archive: VerifiedArchive): String =
        "${archive.capture.deviceId}_${archive.capture.captureId}_${archive.receipt.chainSha256}"

    private fun validateKey(key: String) = requireStore(KEY_PATTERN.matches(key), "Invalid capture key")

    private fun checkCancelled() {
        if (Thread.currentThread().isInterrupted) throw CaptureStoreException("Capture operation cancelled")
    }

    private fun requireStore(condition: Boolean, message: String) {
        if (!condition) throw CaptureStoreException(message)
    }

    private companion object {
        val PROCESS_LOCK = Any()
        val KEY_PATTERN = Regex("[0-9a-f]{32}_[0-9a-f]{32}_[0-9a-f]{64}")
        const val MAX_SOURCE_BYTES = 128L * 1024 * 1024
        const val MAX_OGG_BYTES = 160L * 1024 * 1024
        const val MAX_WAV_BYTES = 2L * 1024 * 1024 * 1024
        const val MAX_METADATA_BYTES = 16L * 1024
        const val ACK_BYTES = 94L
        const val SOURCE_NAME = "source.aura"
        const val ACK_NAME = "physical.ack"
        const val META_NAME = "bundle.json"
        const val OGG_NAME = "source.opus"
        const val WAV_NAME = "playback.wav"
        val LIMITS = ArchiveLimits(maxFileBytes = MAX_SOURCE_BYTES,
            maxPayloadBytes = MAX_SOURCE_BYTES, maxRecords = 1_000_000)
        val COLUMNS = arrayOf("key", "title", "context_text", "source_samples", "started_at_ms",
            "imported_at_ms", "status", "physical_status", "file_sha256", "receipt_digest",
            "playback_ready", "decoder_name", "decode_rate", "bundle_name")
    }
}
